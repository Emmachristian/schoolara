"""
exams/services.py
=================
Business-logic service layer for the Examinations app.

Services coordinate multi-step workflows that span several models and/or
apps.  They are the *only* place where cross-model side-effects (e.g.
notifications, audit entries, bulk DB updates) should be initiated from
the exam domain.

Each public function:
  - Accepts plain Python scalars / model instances as arguments
  - Returns a structured result dict (``{success, message, …}``)
  - Logs all significant events
  - Never raises uncaught exceptions to the caller (returns
    ``{success: False, error: "…"}`` instead)

Timezone-aware timestamps use ``core.utils.get_school_current_time()``.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import QuerySet

from core.utils import get_school_current_time, get_school_today

from .utils import (
    bulk_lock_grades,
    bulk_unlock_grades,
    calculate_ranks_for_examination,
    calculate_subject_ranks,
    check_student_exam_eligibility,
    generate_exam_code,
    get_grade_info_for_score,
    validate_score_within_bounds,
)

logger = logging.getLogger(__name__)


# =============================================================================
# RESULT ENTRY SERVICE
# =============================================================================

class ResultEntryService:
    """
    Handles recording and updating student exam scores.

    All score mutations go through this service to guarantee:
      - Eligibility / bounds validation
      - Automatic grade resolution via the grading system
      - Locked-grade protection
      - Consistent audit trail
    """

    @staticmethod
    def record_score(
        student,
        examination,
        score: Decimal | float | int,
        recorded_by: Optional[User] = None,
        teacher_comments: str = "",
        status: str = "COMPLETED",
    ) -> dict:
        """
        Create or update a ``StudentExamResult`` for a student/exam pair.

        If a result already exists for attempt 1 it is updated; otherwise a
        new record is created.  Locked grades are never overwritten.

        Args:
            student:          ``Student`` instance
            examination:      ``Examination`` instance
            score:            Raw score value
            recorded_by:      ``User`` performing the entry
            teacher_comments: Optional teacher feedback
            status:           Result status string (default ``"COMPLETED"``)

        Returns:
            dict: ``{success, result_id, message, grade, percentage}``
        """
        from .models import StudentExamResult

        # ── Validate score bounds ────────────────────────────────────────────
        valid, error_msg = validate_score_within_bounds(score, examination)
        if not valid:
            return {"success": False, "message": error_msg}

        # ── Eligibility check ────────────────────────────────────────────────
        eligibility = check_student_exam_eligibility(student, examination)
        if not eligibility["eligible"] and not _result_already_exists(student, examination):
            return {
                "success": False,
                "message": "Student is not eligible: " + "; ".join(eligibility["reasons"]),
            }

        try:
            with transaction.atomic():
                result, created = StudentExamResult.objects.get_or_create(
                    student=student,
                    examination=examination,
                    attempt_number=1,
                    defaults={"status": status, "score": Decimal(str(score))},
                )

                if not created:
                    if result.is_grade_locked:
                        return {
                            "success": False,
                            "message": (
                                f"Grade is locked for {student} – {examination.name}. "
                                "Unlock before editing."
                            ),
                        }
                    result.score = Decimal(str(score))
                    result.status = status

                result.teacher_comments = teacher_comments
                result.save()

                grade_info = get_grade_info_for_score(score, examination)
                logger.info(
                    "Score recorded – student=%s exam=%s score=%s grade=%s by=%s",
                    student,
                    examination.name,
                    score,
                    grade_info.get("grade"),
                    recorded_by,
                )

                return {
                    "success": True,
                    "result_id": result.pk,
                    "created": created,
                    "message": "Score recorded successfully.",
                    "grade": grade_info.get("grade"),
                    "percentage": grade_info.get("percentage"),
                    "is_pass": grade_info.get("is_passing"),
                }

        except Exception as exc:
            logger.error(
                "ResultEntryService.record_score failed – student=%s exam=%s: %s",
                student,
                examination,
                exc,
            )
            return {"success": False, "message": str(exc)}

    @staticmethod
    def bulk_record_scores(
        examination,
        score_map: dict,
        recorded_by: Optional[User] = None,
    ) -> dict:
        """
        Record scores for multiple students in a single transaction.

        Args:
            examination: ``Examination`` instance
            score_map:   ``{student_instance: score_value}``
            recorded_by: ``User`` performing the bulk entry

        Returns:
            dict: ``{success, total, recorded, skipped, errors, error_details}``
        """
        recorded = skipped = errors = 0
        error_details: list[str] = []

        for student, score in score_map.items():
            result = ResultEntryService.record_score(
                student=student,
                examination=examination,
                score=score,
                recorded_by=recorded_by,
            )
            if result["success"]:
                recorded += 1
            elif "locked" in result.get("message", "").lower():
                skipped += 1
            else:
                errors += 1
                error_details.append(f"{student}: {result.get('message')}")

        return {
            "success": errors == 0,
            "total": len(score_map),
            "recorded": recorded,
            "skipped": skipped,
            "errors": errors,
            "error_details": error_details,
        }


# =============================================================================
# RESULT PUBLICATION SERVICE
# =============================================================================

class ResultPublicationService:
    """
    Manages the lifecycle of publishing examination results.

    Publication:
      1. Validates that all expected results are recorded
      2. Calculates class/subject ranks
      3. Marks results as published
      4. Auto-locks grades (delegated to ``StudentExamResult.save()``)
      5. Updates examination status to COMPLETED
    """

    @staticmethod
    def publish_examination_results(
        examination,
        published_by: Optional[User] = None,
        force: bool = False,
    ) -> dict:
        """
        Publish all completed results for an examination.

        Args:
            examination:  ``Examination`` instance
            published_by: ``User`` triggering publication
            force:        Skip "all students scored" check (default False)

        Returns:
            dict: ``{success, published_count, locked_count, message}``
        """
        from .models import StudentExamResult

        if examination.results_published and not force:
            return {
                "success": False,
                "message": f"Results for '{examination.name}' are already published.",
            }

        # ── Completeness check ───────────────────────────────────────────────
        incomplete = StudentExamResult.objects.filter(
            examination=examination,
            status__in=["NOT_STARTED", "IN_PROGRESS"],
        ).count()

        if incomplete and not force:
            return {
                "success": False,
                "message": (
                    f"{incomplete} result(s) are still in progress. "
                    "Use force=True to publish anyway."
                ),
                "incomplete_count": incomplete,
            }

        try:
            with transaction.atomic():
                # Rank calculation
                calculate_ranks_for_examination(examination)
                calculate_subject_ranks(
                    examination.subject_id,
                    examination.academic_session_id,
                )

                now = get_school_current_time()

                # Publish all completed/submitted results
                updated = StudentExamResult.objects.filter(
                    examination=examination,
                    status__in=["COMPLETED", "SUBMITTED"],
                    is_published=False,
                    score__isnull=False,
                ).count()

                results_qs = StudentExamResult.objects.filter(
                    examination=examination,
                    status__in=["COMPLETED", "SUBMITTED"],
                    is_published=False,
                    score__isnull=False,
                )

                # Save individually to trigger auto-lock in model's save()
                published_count = 0
                locked_count = 0
                for result in results_qs:
                    was_locked = result.is_grade_locked
                    result.is_published = True
                    result.publication_date = now
                    result.save()
                    published_count += 1
                    if result.is_grade_locked and not was_locked:
                        locked_count += 1

                # Mark examination as completed
                examination.status = "COMPLETED"
                examination.results_published = True
                examination.results_publication_date = now
                examination.save(update_fields=[
                    "status", "results_published", "results_publication_date"
                ])

                logger.info(
                    "Results published – exam='%s' published=%d auto_locked=%d by=%s",
                    examination.name,
                    published_count,
                    locked_count,
                    published_by,
                )

                return {
                    "success": True,
                    "published_count": published_count,
                    "locked_count": locked_count,
                    "message": (
                        f"Successfully published {published_count} result(s). "
                        f"{locked_count} grade(s) auto-locked."
                    ),
                }

        except Exception as exc:
            logger.error(
                "ResultPublicationService.publish_examination_results failed – exam=%s: %s",
                examination,
                exc,
            )
            return {"success": False, "message": str(exc)}

    @staticmethod
    def unpublish_examination_results(
        examination,
        reason: str = "",
        unpublished_by: Optional[User] = None,
    ) -> dict:
        """
        Retract publication of an examination's results.

        Grades are NOT unlocked automatically; call
        :func:`GradeLockService.bulk_unlock` separately if re-entry is needed.

        Args:
            examination:    ``Examination`` instance
            reason:         Reason for retraction (stored in logs)
            unpublished_by: ``User`` authorising the action

        Returns:
            dict: ``{success, unpublished_count, message}``
        """
        from .models import StudentExamResult

        if not examination.results_published:
            return {
                "success": False,
                "message": "Results are not currently published.",
            }

        try:
            with transaction.atomic():
                count = StudentExamResult.objects.filter(
                    examination=examination, is_published=True
                ).update(is_published=False, publication_date=None)

                examination.results_published = False
                examination.results_publication_date = None
                examination.status = "COMPLETED"
                examination.save(update_fields=[
                    "results_published", "results_publication_date", "status"
                ])

                logger.info(
                    "Results unpublished – exam='%s' count=%d reason='%s' by=%s",
                    examination.name,
                    count,
                    reason,
                    unpublished_by,
                )

                return {
                    "success": True,
                    "unpublished_count": count,
                    "message": f"Retracted publication for {count} result(s).",
                }

        except Exception as exc:
            logger.error(
                "ResultPublicationService.unpublish failed – exam=%s: %s",
                examination,
                exc,
            )
            return {"success": False, "message": str(exc)}


# =============================================================================
# GRADE LOCK SERVICE
# =============================================================================

class GradeLockService:
    """
    Central service for grade-locking / unlocking operations.

    All lock/unlock calls should go through this service so permission
    checks, audit logging, and business rules are applied consistently.
    """

    @staticmethod
    def lock_result(
        result,
        locked_by: Optional[User] = None,
        reason: str = "Manual lock",
    ) -> dict:
        """
        Lock the grade for a single ``StudentExamResult``.

        Args:
            result:    ``StudentExamResult`` instance
            locked_by: ``User`` performing the lock
            reason:    Human-readable reason

        Returns:
            dict: ``{success, message}``
        """
        if result.is_grade_locked:
            return {"success": False, "message": "Grade is already locked."}

        if not result.grade:
            return {"success": False, "message": "Cannot lock: no grade assigned yet."}

        success = result.lock_grade(locked_by=locked_by, reason=reason)
        if success:
            return {"success": True, "message": f"Grade locked ({reason})."}
        return {"success": False, "message": "Lock operation failed – see server logs."}

    @staticmethod
    def unlock_result(
        result,
        unlocked_by: Optional[User] = None,
        reason: str = "Manual unlock",
    ) -> dict:
        """
        Unlock a grade with permission validation.

        Args:
            result:      ``StudentExamResult`` instance
            unlocked_by: ``User`` authorising the unlock
            reason:      Human-readable reason

        Returns:
            dict: ``{success, message}``
        """
        if not result.is_grade_locked:
            return {"success": False, "message": "Grade is not locked."}

        if unlocked_by and not result.can_unlock_grade(unlocked_by):
            return {
                "success": False,
                "message": (
                    "Permission denied or unlock window has expired. "
                    "Contact an administrator."
                ),
            }

        success = result.unlock_grade(unlocked_by=unlocked_by, reason=reason)
        if success:
            return {"success": True, "message": f"Grade unlocked ({reason})."}
        return {"success": False, "message": "Unlock operation failed – see server logs."}

    @staticmethod
    def bulk_lock(
        queryset: QuerySet,
        locked_by: Optional[User] = None,
        reason: str = "Bulk lock",
    ) -> dict:
        """
        Lock all eligible results in ``queryset``.

        Args:
            queryset:  QuerySet of ``StudentExamResult``
            locked_by: ``User`` performing the action
            reason:    Human-readable reason

        Returns:
            dict: ``{success, locked, skipped, errors}``
        """
        result = bulk_lock_grades(queryset, locked_by=locked_by, reason=reason)
        result["success"] = result["errors"] == 0
        return result

    @staticmethod
    def bulk_unlock(
        queryset: QuerySet,
        unlocked_by: Optional[User] = None,
        reason: str = "Bulk unlock",
    ) -> dict:
        """
        Unlock all locked results in ``queryset``.

        Args:
            queryset:    QuerySet of ``StudentExamResult``
            unlocked_by: ``User`` authorising the action
            reason:      Human-readable reason

        Returns:
            dict: ``{success, unlocked, skipped, errors}``
        """
        result = bulk_unlock_grades(queryset, unlocked_by=unlocked_by, reason=reason)
        result["success"] = result["errors"] == 0
        return result

    @staticmethod
    def lock_all_for_examination(
        examination,
        locked_by: Optional[User] = None,
        reason: str = "Exam finalisation",
    ) -> dict:
        """
        Lock every unlocked, graded result for an examination.

        Args:
            examination: ``Examination`` instance
            locked_by:   ``User`` performing the action
            reason:      Human-readable reason

        Returns:
            dict: ``{success, locked, skipped, errors}``
        """
        from .models import StudentExamResult

        qs = StudentExamResult.objects.filter(
            examination=examination,
            is_grade_locked=False,
            score__isnull=False,
        ).exclude(grade="")

        return GradeLockService.bulk_lock(qs, locked_by=locked_by, reason=reason)


# =============================================================================
# EXAMINATION CREATION SERVICE
# =============================================================================

class ExaminationService:
    """
    Handles creating and scheduling examinations.
    """

    @staticmethod
    def create_examination(
        name: str,
        exam_category,
        academic_session,
        subject,
        target_classes: list,
        exam_date,
        start_time,
        end_time,
        total_marks: Decimal = Decimal("100.00"),
        pass_marks: Decimal = Decimal("50.00"),
        exam_mode: str = "WRITTEN",
        grading_system=None,
        curriculum_type: str = "",
        created_by: Optional[User] = None,
        **extra_fields,
    ) -> dict:
        """
        Create a new ``Examination`` with auto-generated code.

        Args:
            name:            Examination name
            exam_category:   ``ExamCategory`` instance
            academic_session: ``AcademicSession`` instance
            subject:         ``Subject`` instance
            target_classes:  list of ``Class`` instances
            exam_date:       ``date`` object
            start_time:      ``time`` object
            end_time:        ``time`` object
            total_marks:     Maximum marks (default 100)
            pass_marks:      Pass threshold (default 50)
            exam_mode:       Mode string (default ``"WRITTEN"``)
            grading_system:  Optional ``GradingSystem`` instance
            curriculum_type: Optional curriculum code
            created_by:      ``User`` creating the record
            **extra_fields:  Any other ``Examination`` field values

        Returns:
            dict: ``{success, examination_id, code, message}``
        """
        from .models import Examination

        # Prevent scheduling in the past
        today = get_school_today()
        if exam_date < today:
            return {
                "success": False,
                "message": "Examination date cannot be in the past.",
            }

        try:
            with transaction.atomic():
                session_code = getattr(academic_session, "code", str(academic_session.pk))
                subject_code = getattr(subject, "code", str(subject.pk))
                code = generate_exam_code(
                    exam_category.abbreviation, subject_code, session_code
                )

                exam = Examination(
                    name=name,
                    code=code,
                    exam_category=exam_category,
                    academic_session=academic_session,
                    subject=subject,
                    exam_date=exam_date,
                    start_time=start_time,
                    end_time=end_time,
                    total_marks=total_marks,
                    pass_marks=pass_marks,
                    exam_mode=exam_mode,
                    grading_system=grading_system,
                    curriculum_type=curriculum_type,
                    status="PLANNED",
                    **extra_fields,
                )
                exam.full_clean()
                exam.save()
                exam.target_classes.set(target_classes)

                logger.info(
                    "Examination created – code=%s name='%s' by=%s",
                    code,
                    name,
                    created_by,
                )

                return {
                    "success": True,
                    "examination_id": exam.pk,
                    "code": code,
                    "message": f"Examination '{name}' created successfully.",
                }

        except Exception as exc:
            logger.error("ExaminationService.create_examination failed: %s", exc)
            return {"success": False, "message": str(exc)}

    @staticmethod
    def cancel_examination(
        examination,
        reason: str = "",
        cancelled_by: Optional[User] = None,
    ) -> dict:
        """
        Cancel a planned or scheduled examination.

        Completed examinations cannot be cancelled.

        Args:
            examination:  ``Examination`` instance
            reason:       Cancellation reason
            cancelled_by: ``User`` authorising the action

        Returns:
            dict: ``{success, message}``
        """
        if examination.status in {"COMPLETED", "CANCELLED"}:
            return {
                "success": False,
                "message": (
                    f"Cannot cancel an examination with status '{examination.status}'."
                ),
            }

        try:
            examination.status = "CANCELLED"
            examination.notes = (
                f"Cancelled by {cancelled_by} on {get_school_today()}: {reason}\n"
                + examination.notes
            )
            examination.save(update_fields=["status", "notes"])
            logger.info(
                "Examination cancelled – exam='%s' reason='%s' by=%s",
                examination.name,
                reason,
                cancelled_by,
            )
            return {"success": True, "message": f"Examination '{examination.name}' cancelled."}
        except Exception as exc:
            logger.error("ExaminationService.cancel_examination failed: %s", exc)
            return {"success": False, "message": str(exc)}

    @staticmethod
    def reschedule_examination(
        examination,
        new_date,
        new_start_time=None,
        new_end_time=None,
        reason: str = "",
        rescheduled_by: Optional[User] = None,
    ) -> dict:
        """
        Move an examination to a new date/time.

        Args:
            examination:     ``Examination`` instance
            new_date:        New ``date`` object
            new_start_time:  New ``time`` (optional, keeps existing if None)
            new_end_time:    New ``time`` (optional, keeps existing if None)
            reason:          Reason for rescheduling
            rescheduled_by:  ``User`` authorising the change

        Returns:
            dict: ``{success, message}``
        """
        if examination.status == "COMPLETED":
            return {
                "success": False,
                "message": "Cannot reschedule a completed examination.",
            }

        if new_date < get_school_today():
            return {
                "success": False,
                "message": "New examination date cannot be in the past.",
            }

        try:
            old_date = examination.exam_date
            examination.exam_date = new_date
            if new_start_time:
                examination.start_time = new_start_time
            if new_end_time:
                examination.end_time = new_end_time
            examination.status = "SCHEDULED"
            examination.notes = (
                f"Rescheduled from {old_date} to {new_date} by {rescheduled_by}: {reason}\n"
                + examination.notes
            )
            examination.full_clean()
            examination.save(update_fields=[
                "exam_date", "start_time", "end_time", "status", "notes"
            ])
            logger.info(
                "Examination rescheduled – exam='%s' from=%s to=%s by=%s",
                examination.name,
                old_date,
                new_date,
                rescheduled_by,
            )
            return {
                "success": True,
                "message": (
                    f"'{examination.name}' rescheduled from {old_date} to {new_date}."
                ),
            }
        except Exception as exc:
            logger.error("ExaminationService.reschedule_examination failed: %s", exc)
            return {"success": False, "message": str(exc)}


# =============================================================================
# GRADING SYSTEM ASSIGNMENT SERVICE
# =============================================================================

class GradingSystemAssignmentService:
    """
    Manages assigning / switching grading systems for classes and sessions.
    """

    @staticmethod
    def assign_grading_system(
        class_instance,
        grading_system,
        academic_session,
        subject=None,
        priority: int = 100,
        custom_pass_mark: Optional[Decimal] = None,
        assigned_by: Optional[User] = None,
        reason: str = "",
    ) -> dict:
        """
        Assign a grading system to a class for a session.

        Deactivates any existing active assignment at the same priority
        before creating the new one.

        Args:
            class_instance:   ``Class`` instance
            grading_system:   ``GradingSystem`` instance
            academic_session: ``AcademicSession`` instance
            subject:          Optional ``Subject`` (for subject-specific assignment)
            priority:         Assignment priority (lower = higher priority)
            custom_pass_mark: Override pass mark (optional)
            assigned_by:      ``User`` making the assignment
            reason:           Reason / notes

        Returns:
            dict: ``{success, assignment_id, message}``
        """
        from .models import ClassGradingSystem

        try:
            with transaction.atomic():
                # Deactivate conflicting active assignments
                ClassGradingSystem.objects.filter(
                    class_instance=class_instance,
                    academic_session=academic_session,
                    subject=subject,
                    priority=priority,
                    is_active=True,
                ).update(is_active=False)

                assignment = ClassGradingSystem.objects.create(
                    class_instance=class_instance,
                    grading_system=grading_system,
                    academic_session=academic_session,
                    subject=subject,
                    priority=priority,
                    custom_pass_mark=custom_pass_mark,
                    assigned_by=assigned_by,
                    assignment_reason=reason,
                    is_active=True,
                    effective_date=get_school_today(),
                )

                logger.info(
                    "Grading system assigned – class=%s system=%s session=%s by=%s",
                    class_instance,
                    grading_system,
                    academic_session,
                    assigned_by,
                )

                return {
                    "success": True,
                    "assignment_id": assignment.pk,
                    "message": (
                        f"'{grading_system.name}' assigned to "
                        f"'{class_instance}' for '{academic_session}'."
                    ),
                }

        except Exception as exc:
            logger.error(
                "GradingSystemAssignmentService.assign_grading_system failed: %s", exc
            )
            return {"success": False, "message": str(exc)}


# =============================================================================
# SCORE MODERATION SERVICE
# =============================================================================

class ModerationService:
    """
    Handles moderator adjustments to student scores.

    A moderated score replaces the raw score for grade calculation while
    preserving the original score for auditing.
    """

    @staticmethod
    def apply_moderation(
        result,
        moderated_score: Decimal | float | int,
        moderator,
        notes: str = "",
    ) -> dict:
        """
        Apply a moderated score to a ``StudentExamResult``.

        Moderation is only allowed on unlocked results that have already been
        scored.

        Args:
            result:           ``StudentExamResult`` instance
            moderated_score:  The adjusted score
            moderator:        ``Staff`` or ``User`` performing moderation
            notes:            Moderation rationale

        Returns:
            dict: ``{success, message, new_grade, new_percentage}``
        """
        if result.is_grade_locked:
            return {
                "success": False,
                "message": "Cannot moderate a locked grade. Unlock first.",
            }

        if result.score is None:
            return {
                "success": False,
                "message": "Cannot moderate: no original score recorded.",
            }

        valid, err = validate_score_within_bounds(moderated_score, result.examination)
        if not valid:
            return {"success": False, "message": err}

        try:
            with transaction.atomic():
                result.moderated_score = Decimal(str(moderated_score))
                result.score = result.moderated_score  # grade is re-derived from score
                result.is_moderated = True
                result.moderator = moderator
                result.moderation_notes = notes
                result.save()

                return {
                    "success": True,
                    "message": "Moderation applied successfully.",
                    "new_grade": result.grade,
                    "new_percentage": result.percentage,
                }

        except Exception as exc:
            logger.error("ModerationService.apply_moderation failed: %s", exc)
            return {"success": False, "message": str(exc)}


# =============================================================================
# RANK RECALCULATION SERVICE
# =============================================================================

class RankService:
    """
    Triggers rank recalculation for exams and subjects.
    """

    @staticmethod
    def recalculate_exam_ranks(examination) -> dict:
        """
        Recalculate class ranks for a single examination.

        Args:
            examination: ``Examination`` instance

        Returns:
            dict: ``{success, updated, message}``
        """
        try:
            updated = calculate_ranks_for_examination(examination)
            return {
                "success": True,
                "updated": updated,
                "message": f"Ranks updated for {updated} result(s).",
            }
        except Exception as exc:
            logger.error("RankService.recalculate_exam_ranks failed: %s", exc)
            return {"success": False, "message": str(exc)}

    @staticmethod
    def recalculate_subject_ranks(subject_id: int, academic_session_id: int) -> dict:
        """
        Recalculate subject-wide ranks across all exams in a session.

        Args:
            subject_id:          PK of ``Subject``
            academic_session_id: PK of ``AcademicSession``

        Returns:
            dict: ``{success, updated, message}``
        """
        try:
            updated = calculate_subject_ranks(subject_id, academic_session_id)
            return {
                "success": True,
                "updated": updated,
                "message": f"Subject ranks updated for {updated} result(s).",
            }
        except Exception as exc:
            logger.error("RankService.recalculate_subject_ranks failed: %s", exc)
            return {"success": False, "message": str(exc)}


# =============================================================================
# INTERNAL HELPERS
# =============================================================================

def _result_already_exists(student, examination) -> bool:
    """Return True if any result record exists for this student/exam pair."""
    from .models import StudentExamResult
    return StudentExamResult.objects.filter(
        student=student, examination=examination
    ).exists()