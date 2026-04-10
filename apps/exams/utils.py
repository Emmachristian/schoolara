"""
exams/utils.py
==============
Utility functions for the Examinations app.

Covers:
  - Exam code generation
  - Student eligibility checks (payment & registration gating)
  - Score / grade calculation helpers
  - Result display & formatting
  - Bulk grade locking helpers
  - Grading-system resolution helpers
  - Rank calculation utilities

All date/time calls delegate to ``core.utils`` so the school's
configured timezone is respected everywhere.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import TYPE_CHECKING, Optional

from django.db.models import Avg, Count, Max, Min, Q, QuerySet
from django.utils import timezone

from core.utils import get_school_current_time, get_school_today

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from students.models import Student
    from .models import (
        ClassGradingSystem,
        Examination,
        GradingSystem,
        StudentExamResult,
    )

logger = logging.getLogger(__name__)


# =============================================================================
# CODE GENERATION
# =============================================================================

def generate_exam_code(exam_category_abbr: str, subject_code: str, session_code: str) -> str:
    """
    Generate a unique, human-readable examination code.

    Format: ``<CATEGORY>-<SUBJECT>-<SESSION>-<SEQUENCE>``
    Example: ``MID-MTH-2025T1-00003``

    Args:
        exam_category_abbr: Abbreviation from ``ExamCategory.abbreviation``
        subject_code:        Short code identifying the subject
        session_code:        Short code identifying the academic session

    Returns:
        str: Next available examination code (guaranteed unique)
    """
    from .models import Examination

    prefix = f"{exam_category_abbr.upper()}-{subject_code.upper()}-{session_code.upper()}"

    last = (
        Examination.objects.filter(code__startswith=prefix)
        .order_by("-code")
        .values_list("code", flat=True)
        .first()
    )

    sequence = 1
    if last:
        try:
            sequence = int(last.rsplit("-", 1)[-1]) + 1
        except (ValueError, IndexError):
            sequence = 1

    return f"{prefix}-{sequence:05d}"


def generate_result_reference(student_id: int, exam_id: int, attempt: int = 1) -> str:
    """
    Generate a stable reference string for a ``StudentExamResult``.

    Format: ``RES-<STUDENT_ID>-<EXAM_ID>-ATT<ATTEMPT>``

    Args:
        student_id: Primary key of the student
        exam_id:    Primary key of the examination
        attempt:    Attempt number (default 1)

    Returns:
        str: Result reference string
    """
    return f"RES-{student_id:06d}-{exam_id:06d}-ATT{attempt}"


# =============================================================================
# STUDENT ELIGIBILITY
# =============================================================================

def check_student_exam_eligibility(
    student: "Student",
    examination: "Examination",
) -> dict:
    """
    Determine whether a student may sit a given examination.

    Checks (in order):
    1. Fee-payment requirement defined on ``ExamCategory``
    2. Existing ``StudentExamResult`` attempts vs. ``ExamCategory.max_retakes``
    3. Examination status (must be PLANNED / SCHEDULED / ONGOING)

    Args:
        student:     ``Student`` instance
        examination: ``Examination`` instance

    Returns:
        dict with keys:
            ``eligible``        (bool)
            ``reasons``         (list[str]) – human-readable failure reasons
            ``payment_info``    (dict)      – raw output from ``get_payment_requirement_for_student``
            ``attempts_used``   (int)
            ``max_attempts``    (int)
    """
    from .models import StudentExamResult

    reasons: list[str] = []
    exam_category = examination.exam_category

    # ── 1. Payment gate ──────────────────────────────────────────────────────
    payment_info = exam_category.get_payment_requirement_for_student(student)
    if not payment_info.get("meets_requirement", True):
        pct_paid = payment_info.get("payment_percentage", 0)
        required = payment_info.get("required_percentage", 0)
        reasons.append(
            f"Fee payment insufficient – {pct_paid:.1f}% paid, "
            f"{required}% required."
        )

    # ── 2. Attempt / retake gate ─────────────────────────────────────────────
    attempts_used = StudentExamResult.objects.filter(
        student=student,
        examination=examination,
    ).count()

    max_attempts = 1 + (exam_category.max_retakes if exam_category.allows_retakes else 0)

    if attempts_used >= max_attempts:
        reasons.append(
            f"Maximum attempts reached ({attempts_used}/{max_attempts})."
        )

    # ── 3. Exam status gate ───────────────────────────────────────────────────
    allowed_statuses = {"PLANNED", "SCHEDULED", "ONGOING"}
    if examination.status not in allowed_statuses:
        reasons.append(
            f"Examination is not open for sitting (status: {examination.status})."
        )

    return {
        "eligible": len(reasons) == 0,
        "reasons": reasons,
        "payment_info": payment_info,
        "attempts_used": attempts_used,
        "max_attempts": max_attempts,
    }


def get_eligible_students_for_exam(examination: "Examination") -> QuerySet:
    """
    Return a queryset of students eligible to sit ``examination``.

    Delegates per-student eligibility to :func:`check_student_exam_eligibility`.
    Students who are already registered are included only if they still have
    remaining attempts.

    Args:
        examination: ``Examination`` instance

    Returns:
        QuerySet[Student]: Filtered student queryset
    """
    from students.models import Student

    # All students in the target classes
    candidates = Student.objects.filter(
        current_class__in=examination.target_classes.all(),
        is_active=True,
    ).distinct()

    eligible_pks = [
        s.pk
        for s in candidates
        if check_student_exam_eligibility(s, examination)["eligible"]
    ]

    return candidates.filter(pk__in=eligible_pks)


# =============================================================================
# SCORE & GRADE CALCULATION
# =============================================================================

def calculate_percentage_score(
    raw_score: Decimal | float | int,
    total_marks: Decimal | float | int,
    decimal_places: int = 2,
) -> Decimal:
    """
    Compute ``(raw_score / total_marks) * 100``, safely.

    Args:
        raw_score:     Student's raw score
        total_marks:   Maximum possible marks
        decimal_places: Rounding precision

    Returns:
        Decimal: Percentage (0.00 if ``total_marks`` is zero)
    """
    try:
        score = Decimal(str(raw_score))
        total = Decimal(str(total_marks))
        if total == 0:
            return Decimal("0.00")
        return (score / total * 100).quantize(
            Decimal("0." + "0" * decimal_places), rounding=ROUND_HALF_UP
        )
    except (InvalidOperation, TypeError, ZeroDivisionError):
        logger.warning(
            "calculate_percentage_score failed – score=%s total=%s",
            raw_score,
            total_marks,
        )
        return Decimal("0.00")


def resolve_grading_system(examination: "Examination") -> Optional["GradingSystem"]:
    """
    Resolve the effective grading system for an examination.

    Priority order:
    1. Explicitly assigned ``Examination.grading_system``
    2. Active ``ClassGradingSystem`` for the target class + session + subject
    3. Active ``ClassGradingSystem`` for the target class + session (no subject)
    4. System-wide default ``GradingSystem``

    Args:
        examination: ``Examination`` instance

    Returns:
        GradingSystem or None
    """
    from .models import ClassGradingSystem, GradingSystem

    if examination.grading_system_id:
        return examination.grading_system

    for cls in examination.target_classes.all():
        gs = ClassGradingSystem.get_active_grading_system(
            cls, examination.academic_session, examination.subject
        )
        if gs:
            return gs

    return GradingSystem.objects.filter(is_default=True, is_active=True).first()


def get_grade_info_for_score(
    score: Decimal | float | int,
    examination: "Examination",
) -> dict:
    """
    Return full grade metadata for a raw score against an examination.

    Args:
        score:       Raw score value
        examination: ``Examination`` instance (used to resolve grading system)

    Returns:
        dict with keys: ``grade``, ``aggregate``, ``comments``,
        ``color_code``, ``gpa_points``, ``is_passing``, ``percentage``,
        ``grading_system_name``.
        Returns sensible defaults when no grading system is found.
    """
    grading_system = resolve_grading_system(examination)
    percentage = calculate_percentage_score(score, examination.total_marks)

    if grading_system:
        info = grading_system.get_grade_for_score(float(score)) or {}
    else:
        info = {}

    return {
        "grade": info.get("grade", "N/A"),
        "aggregate": info.get("aggregate", ""),
        "comments": info.get("comments", ""),
        "color_code": info.get("color_code", "#CCCCCC"),
        "gpa_points": info.get("gpa_points"),
        "is_passing": float(score) >= float(examination.pass_marks),
        "percentage": percentage,
        "grading_system_name": grading_system.name if grading_system else "None",
    }


def normalize_score(
    score: Decimal | float | int,
    source_total: Decimal | float | int,
    target_total: Decimal | float | int,
) -> Decimal:
    """
    Scale ``score`` from ``source_total`` to ``target_total``.

    Useful when combining scores across papers with different maximum marks.

    Example::

        normalize_score(45, 60, 100)  # → Decimal('75.00')

    Args:
        score:        Raw score to scale
        source_total: Maximum marks of the original paper
        target_total: Desired maximum marks

    Returns:
        Decimal: Scaled score, rounded to 2 decimal places
    """
    try:
        s = Decimal(str(score))
        src = Decimal(str(source_total))
        tgt = Decimal(str(target_total))
        if src == 0:
            return Decimal("0.00")
        return (s / src * tgt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ZeroDivisionError):
        return Decimal("0.00")


# =============================================================================
# RANK CALCULATION
# =============================================================================

def calculate_ranks_for_examination(examination: "Examination") -> int:
    """
    Compute and persist ``rank_in_class`` for all completed results of
    ``examination``.

    Students are ranked by descending score.  Ties share the same rank;
    the next rank skips accordingly (standard competition ranking).

    Args:
        examination: ``Examination`` instance

    Returns:
        int: Number of result records updated
    """
    from .models import StudentExamResult

    results = list(
        StudentExamResult.objects.filter(
            examination=examination,
            status__in=["COMPLETED", "SUBMITTED"],
            score__isnull=False,
        ).order_by("-score", "student__last_name")
    )

    if not results:
        return 0

    updated = 0
    rank = 1
    for i, result in enumerate(results):
        if i > 0 and results[i].score != results[i - 1].score:
            rank = i + 1
        result.rank_in_class = rank

    StudentExamResult.objects.bulk_update(results, ["rank_in_class"])
    updated = len(results)

    logger.info(
        "Ranks calculated for examination '%s' (%d results updated).",
        examination.name,
        updated,
    )
    return updated


def calculate_subject_ranks(subject_id: int, academic_session_id: int) -> int:
    """
    Compute ``rank_in_subject`` across all examinations for a subject/session.

    Ranks are based on the average percentage score per student across all
    non-cancelled results in the session.

    Args:
        subject_id:          PK of ``Subject``
        academic_session_id: PK of ``AcademicSession``

    Returns:
        int: Number of result records updated
    """
    from .models import StudentExamResult

    results = (
        StudentExamResult.objects.filter(
            examination__subject_id=subject_id,
            examination__academic_session_id=academic_session_id,
            status__in=["COMPLETED", "SUBMITTED"],
            percentage__isnull=False,
        )
        .select_related("student")
    )

    # Group average percentages by student
    from collections import defaultdict

    student_scores: dict[int, list[Decimal]] = defaultdict(list)
    result_map: dict[int, list["StudentExamResult"]] = defaultdict(list)

    for r in results:
        student_scores[r.student_id].append(r.percentage or Decimal("0"))
        result_map[r.student_id].append(r)

    averages = sorted(
        [
            (sid, sum(scores) / len(scores))
            for sid, scores in student_scores.items()
        ],
        key=lambda x: x[1],
        reverse=True,
    )

    # Assign ranks
    ranked_map: dict[int, int] = {}
    rank = 1
    for i, (sid, avg) in enumerate(averages):
        if i > 0 and avg != averages[i - 1][1]:
            rank = i + 1
        ranked_map[sid] = rank

    to_update: list["StudentExamResult"] = []
    for sid, rs in result_map.items():
        for r in rs:
            r.rank_in_subject = ranked_map.get(sid)
            to_update.append(r)

    StudentExamResult.objects.bulk_update(to_update, ["rank_in_subject"])
    return len(to_update)


# =============================================================================
# BULK GRADE LOCKING
# =============================================================================

def bulk_lock_grades(
    queryset: QuerySet,
    locked_by: Optional["User"] = None,
    reason: str = "Bulk lock",
) -> dict:
    """
    Lock all unlocked, graded results in ``queryset``.

    Only results that have a score **and** a grade are eligible.
    Already-locked results are skipped silently.

    Args:
        queryset:  QuerySet of ``StudentExamResult`` instances
        locked_by: ``User`` performing the lock (may be None for system locks)
        reason:    Human-readable reason stored on each result

    Returns:
        dict with keys ``locked`` (int), ``skipped`` (int), ``errors`` (int)
    """
    locked = skipped = errors = 0

    for result in queryset.filter(is_grade_locked=False, score__isnull=False).exclude(grade=""):
        try:
            success = result.lock_grade(locked_by=locked_by, reason=reason)
            if success:
                locked += 1
            else:
                skipped += 1
        except Exception as exc:
            logger.error("bulk_lock_grades – error locking result pk=%s: %s", result.pk, exc)
            errors += 1

    logger.info(
        "bulk_lock_grades – locked=%d skipped=%d errors=%d reason='%s'",
        locked,
        skipped,
        errors,
        reason,
    )
    return {"locked": locked, "skipped": skipped, "errors": errors}


def bulk_unlock_grades(
    queryset: QuerySet,
    unlocked_by: Optional["User"] = None,
    reason: str = "Bulk unlock",
) -> dict:
    """
    Unlock all locked results in ``queryset``.

    Args:
        queryset:    QuerySet of ``StudentExamResult`` instances
        unlocked_by: ``User`` authorising the unlock
        reason:      Human-readable reason stored on each result

    Returns:
        dict with keys ``unlocked`` (int), ``skipped`` (int), ``errors`` (int)
    """
    unlocked = skipped = errors = 0

    for result in queryset.filter(is_grade_locked=True):
        try:
            success = result.unlock_grade(unlocked_by=unlocked_by, reason=reason)
            if success:
                unlocked += 1
            else:
                skipped += 1
        except Exception as exc:
            logger.error(
                "bulk_unlock_grades – error unlocking result pk=%s: %s", result.pk, exc
            )
            errors += 1

    logger.info(
        "bulk_unlock_grades – unlocked=%d skipped=%d errors=%d reason='%s'",
        unlocked,
        skipped,
        errors,
        reason,
    )
    return {"unlocked": unlocked, "skipped": skipped, "errors": errors}


# =============================================================================
# RESULT DISPLAY & FORMATTING
# =============================================================================

def format_score_display(
    score: Optional[Decimal],
    total_marks: Decimal,
    show_percentage: bool = True,
    locked: bool = False,
) -> str:
    """
    Build a human-readable score string.

    Examples::

        format_score_display(75, 100)              → "75/100 (75.00%)"
        format_score_display(75, 100, locked=True) → "75/100 (75.00%) 🔒"
        format_score_display(None, 100)            → "Not Scored"

    Args:
        score:           Raw score or None
        total_marks:     Maximum possible marks
        show_percentage: Append percentage (default True)
        locked:          Append lock icon (default False)

    Returns:
        str: Formatted display string
    """
    if score is None:
        return "Not Scored"

    text = f"{score}/{total_marks}"

    if show_percentage:
        pct = calculate_percentage_score(score, total_marks)
        text += f" ({pct}%)"

    if locked:
        text += " 🔒"

    return text


def format_grade_badge(grade: str, color_code: str = "") -> str:
    """
    Return an HTML badge snippet for use in templates.

    Args:
        grade:      Grade letter / label
        color_code: Optional hex color (e.g. ``"#28a745"``)

    Returns:
        str: HTML ``<span>`` badge string (safe for ``mark_safe``)
    """
    style = f' style="background-color:{color_code};"' if color_code else ""
    return f'<span class="grade-badge"{style}>{grade}</span>'


def get_result_status_label(status_code: str) -> str:
    """
    Return the human-readable label for a ``StudentExamResult.status`` code.

    Args:
        status_code: One of the ``RESULT_STATUS_CHOICES`` keys

    Returns:
        str: Display label, or the raw code if not recognised
    """
    _MAP = {
        "NOT_STARTED": "Not Started",
        "IN_PROGRESS": "In Progress",
        "SUBMITTED": "Submitted",
        "COMPLETED": "Completed",
        "CANCELLED": "Cancelled",
        "DISQUALIFIED": "Disqualified",
        "ABSENT": "Absent",
    }
    return _MAP.get(status_code, status_code)


def summarise_result_for_report_card(result: "StudentExamResult") -> dict:
    """
    Build a flat dictionary suitable for report-card template rendering.

    Args:
        result: ``StudentExamResult`` instance

    Returns:
        dict with keys:
            ``subject``, ``exam_name``, ``score``, ``total_marks``,
            ``percentage``, ``grade``, ``grade_points``, ``is_pass``,
            ``rank_in_class``, ``is_grade_locked``, ``comments``,
            ``score_display``
    """
    examination = result.examination
    subject = examination.subject

    return {
        "subject": str(subject),
        "exam_name": examination.name,
        "score": result.score,
        "total_marks": examination.total_marks,
        "percentage": result.percentage,
        "grade": result.grade,
        "grade_points": result.grade_points,
        "is_pass": result.is_pass,
        "rank_in_class": result.rank_in_class,
        "is_grade_locked": result.is_grade_locked,
        "comments": result.teacher_comments,
        "score_display": format_score_display(
            result.score,
            examination.total_marks,
            locked=result.is_grade_locked,
        ),
    }


# =============================================================================
# GRADING SYSTEM RESOLUTION HELPERS
# =============================================================================

def get_applicable_grading_system(
    academic_level=None,
    subject=None,
    curriculum_type: str = "ALL",
) -> Optional["GradingSystem"]:
    """
    Find the most appropriate active grading system based on context filters.

    Priority: level-specific > subject-specific > curriculum-specific > default

    Args:
        academic_level:  ``AcademicLevel`` instance or None
        subject:         ``Subject`` instance or None
        curriculum_type: Curriculum code string (default ``"ALL"``)

    Returns:
        GradingSystem or None
    """
    from .models import GradingSystem

    qs = GradingSystem.objects.filter(is_active=True)

    if curriculum_type and curriculum_type != "ALL":
        qs = qs.filter(curriculum_compatibility__in=["ALL", curriculum_type])

    if academic_level:
        level_specific = qs.filter(applicable_levels=academic_level)
        if level_specific.exists():
            return level_specific.order_by("-is_default").first()

    if subject:
        subject_specific = qs.filter(applicable_subjects=subject)
        if subject_specific.exists():
            return subject_specific.order_by("-is_default").first()

    default = qs.filter(is_default=True).first()
    if default:
        return default

    return qs.first()


def list_grading_systems_for_class(class_instance, academic_session) -> list[dict]:
    """
    Return all active grading system assignments for a class/session combo.

    Args:
        class_instance:  ``Class`` instance
        academic_session: ``AcademicSession`` instance

    Returns:
        list[dict]: Each item has keys ``subject``, ``grading_system``,
                    ``priority``, ``pass_mark``, ``max_score``
    """
    from .models import ClassGradingSystem

    assignments = ClassGradingSystem.objects.filter(
        class_instance=class_instance,
        academic_session=academic_session,
        is_active=True,
    ).select_related("subject", "grading_system").order_by("priority")

    return [
        {
            "subject": str(a.subject) if a.subject else "All Subjects",
            "grading_system": str(a.grading_system),
            "priority": a.priority,
            "pass_mark": a.get_effective_pass_mark(),
            "max_score": a.get_effective_maximum_score(),
        }
        for a in assignments
    ]


# =============================================================================
# MISCELLANEOUS HELPERS
# =============================================================================

def exam_is_upcoming(examination: "Examination", days_ahead: int = 7) -> bool:
    """
    Return True if the exam falls within the next ``days_ahead`` days.

    Args:
        examination: ``Examination`` instance
        days_ahead:  Look-ahead window in days (default 7)

    Returns:
        bool
    """
    from datetime import timedelta

    today = get_school_today()
    window_end = today + timedelta(days=days_ahead)
    return today <= examination.exam_date <= window_end


def get_duration_label(minutes: int) -> str:
    """
    Convert a duration in minutes to a readable label.

    Examples::

        get_duration_label(90)  → "1 hr 30 min"
        get_duration_label(60)  → "1 hr"
        get_duration_label(45)  → "45 min"

    Args:
        minutes: Duration in minutes

    Returns:
        str: Human-readable duration
    """
    if minutes <= 0:
        return "0 min"
    hours, mins = divmod(int(minutes), 60)
    parts = []
    if hours:
        parts.append(f"{hours} hr")
    if mins:
        parts.append(f"{mins} min")
    return " ".join(parts)


def validate_score_within_bounds(
    score: Decimal | float | int,
    examination: "Examination",
) -> tuple[bool, str]:
    """
    Validate that a score falls within the examination's allowed bounds.

    Args:
        score:       Score to validate
        examination: ``Examination`` instance

    Returns:
        tuple[bool, str]: (is_valid, error_message)
            ``error_message`` is empty when ``is_valid`` is True.
    """
    try:
        s = Decimal(str(score))
    except InvalidOperation:
        return False, f"'{score}' is not a valid numeric score."

    if s < 0:
        return False, "Score cannot be negative."

    if s > examination.total_marks:
        return (
            False,
            f"Score {s} exceeds total marks {examination.total_marks}.",
        )

    return True, ""