"""
exams/stats.py
==============
Statistical analysis layer for the Examinations app.

All public functions return plain Python dicts (or lists of dicts) so they
can be consumed by views, serializers, Celery tasks, and management commands
without any further ORM coupling.

Coverage:
  - Examination-level aggregates (class performance per exam)
  - Student performance across exams / sessions
  - Subject performance across classes
  - Grade-distribution breakdowns
  - Pass-rate and failure analytics
  - Grading-system effectiveness reports
  - Comparative (cross-session) performance tracking
  - Dashboard summary helpers

All date/time logic delegates to ``core.utils`` for timezone consistency.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Optional

from django.db.models import (
    Avg,
    Case,
    Count,
    DecimalField,
    F,
    IntegerField,
    Max,
    Min,
    Q,
    StdDev,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce

from core.utils import get_school_today

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Convenience aliases (avoids repeated imports inside each function)
# ---------------------------------------------------------------------------
def _results():
    from .models import StudentExamResult
    return StudentExamResult


def _exams():
    from .models import Examination
    return Examination


# =============================================================================
# EXAMINATION-LEVEL STATISTICS
# =============================================================================

def get_examination_stats(examination_id: int) -> dict:
    """
    Aggregate performance statistics for a single examination.

    Returns key metrics including average score, pass rate, highest/lowest
    scores, standard deviation, and a grade-distribution breakdown.

    Args:
        examination_id: PK of ``Examination``

    Returns:
        dict with keys:
            ``examination_id``, ``examination_name``, ``total_registered``,
            ``total_completed``, ``total_absent``, ``total_disqualified``,
            ``average_score``, ``average_percentage``, ``highest_score``,
            ``lowest_score``, ``std_deviation``, ``pass_count``,
            ``fail_count``, ``pass_rate``, ``grade_distribution``
    """
    Result = _results()

    base_qs = Result.objects.filter(examination_id=examination_id)

    agg = base_qs.filter(
        status__in=["COMPLETED", "SUBMITTED"],
        score__isnull=False,
    ).aggregate(
        average_score=Avg("score"),
        average_percentage=Avg("percentage"),
        highest_score=Max("score"),
        lowest_score=Min("score"),
        std_deviation=StdDev("score"),
        pass_count=Count("id", filter=Q(is_pass=True)),
        fail_count=Count("id", filter=Q(is_pass=False)),
        total_scored=Count("id"),
    )

    total_registered = base_qs.count()
    total_absent = base_qs.filter(status="ABSENT").count()
    total_disqualified = base_qs.filter(status="DISQUALIFIED").count()
    total_completed = agg.get("total_scored") or 0
    pass_count = agg.get("pass_count") or 0
    pass_rate = round(pass_count / total_completed * 100, 2) if total_completed else 0.0

    # Grade distribution
    grade_dist = (
        base_qs.filter(status__in=["COMPLETED", "SUBMITTED"])
        .exclude(grade="")
        .values("grade")
        .annotate(count=Count("id"))
        .order_by("grade")
    )
    grade_distribution = {row["grade"]: row["count"] for row in grade_dist}

    try:
        exam = _exams().objects.get(pk=examination_id)
        exam_name = exam.name
    except Exception:
        exam_name = f"Exam #{examination_id}"

    return {
        "examination_id": examination_id,
        "examination_name": exam_name,
        "total_registered": total_registered,
        "total_completed": total_completed,
        "total_absent": total_absent,
        "total_disqualified": total_disqualified,
        "average_score": _decimal_or_none(agg.get("average_score")),
        "average_percentage": _decimal_or_none(agg.get("average_percentage")),
        "highest_score": _decimal_or_none(agg.get("highest_score")),
        "lowest_score": _decimal_or_none(agg.get("lowest_score")),
        "std_deviation": _decimal_or_none(agg.get("std_deviation")),
        "pass_count": pass_count,
        "fail_count": agg.get("fail_count") or 0,
        "pass_rate": pass_rate,
        "grade_distribution": grade_distribution,
    }


def get_class_performance_for_exam(examination_id: int, class_id: int) -> dict:
    """
    Per-class breakdown of performance for a single examination.

    Args:
        examination_id: PK of ``Examination``
        class_id:       PK of ``Class``

    Returns:
        dict (same schema as :func:`get_examination_stats` plus ``class_id``)
    """
    from students.models import Student

    Result = _results()

    student_pks = Student.objects.filter(
        current_class_id=class_id, is_active=True
    ).values_list("pk", flat=True)

    qs = Result.objects.filter(
        examination_id=examination_id,
        student_id__in=student_pks,
    )

    agg = qs.filter(
        status__in=["COMPLETED", "SUBMITTED"],
        score__isnull=False,
    ).aggregate(
        average_score=Avg("score"),
        average_percentage=Avg("percentage"),
        highest_score=Max("score"),
        lowest_score=Min("score"),
        std_deviation=StdDev("score"),
        pass_count=Count("id", filter=Q(is_pass=True)),
        fail_count=Count("id", filter=Q(is_pass=False)),
        total_scored=Count("id"),
    )

    total_completed = agg.get("total_scored") or 0
    pass_count = agg.get("pass_count") or 0
    pass_rate = round(pass_count / total_completed * 100, 2) if total_completed else 0.0

    grade_dist = (
        qs.filter(status__in=["COMPLETED", "SUBMITTED"])
        .exclude(grade="")
        .values("grade")
        .annotate(count=Count("id"))
        .order_by("grade")
    )

    return {
        "examination_id": examination_id,
        "class_id": class_id,
        "total_students": qs.count(),
        "total_completed": total_completed,
        "total_absent": qs.filter(status="ABSENT").count(),
        "average_score": _decimal_or_none(agg.get("average_score")),
        "average_percentage": _decimal_or_none(agg.get("average_percentage")),
        "highest_score": _decimal_or_none(agg.get("highest_score")),
        "lowest_score": _decimal_or_none(agg.get("lowest_score")),
        "std_deviation": _decimal_or_none(agg.get("std_deviation")),
        "pass_count": pass_count,
        "fail_count": agg.get("fail_count") or 0,
        "pass_rate": pass_rate,
        "grade_distribution": {row["grade"]: row["count"] for row in grade_dist},
    }


# =============================================================================
# STUDENT PERFORMANCE STATISTICS
# =============================================================================

def get_student_performance(student_id: int, academic_session_id: int) -> dict:
    """
    Aggregate a student's performance across all exams in a session.

    Args:
        student_id:          PK of ``Student``
        academic_session_id: PK of ``AcademicSession``

    Returns:
        dict with keys:
            ``student_id``, ``academic_session_id``, ``exams_taken``,
            ``exams_passed``, ``exams_failed``, ``average_percentage``,
            ``highest_percentage``, ``lowest_percentage``, ``total_score``,
            ``total_possible``, ``overall_percentage``, ``pass_rate``,
            ``subject_breakdown``, ``grade_tally``
    """
    Result = _results()

    qs = Result.objects.filter(
        student_id=student_id,
        examination__academic_session_id=academic_session_id,
        status__in=["COMPLETED", "SUBMITTED"],
        score__isnull=False,
    ).select_related("examination__subject")

    agg = qs.aggregate(
        exams_taken=Count("id"),
        exams_passed=Count("id", filter=Q(is_pass=True)),
        exams_failed=Count("id", filter=Q(is_pass=False)),
        average_percentage=Avg("percentage"),
        highest_percentage=Max("percentage"),
        lowest_percentage=Min("percentage"),
        total_score=Sum("score"),
        total_possible=Sum("examination__total_marks"),
    )

    exams_taken = agg.get("exams_taken") or 0
    exams_passed = agg.get("exams_passed") or 0
    pass_rate = round(exams_passed / exams_taken * 100, 2) if exams_taken else 0.0

    total_score = agg.get("total_score") or Decimal("0")
    total_possible = agg.get("total_possible") or Decimal("0")
    overall_pct = (
        round(float(total_score) / float(total_possible) * 100, 2)
        if total_possible
        else 0.0
    )

    # Per-subject breakdown
    subject_breakdown = {}
    for result in qs:
        subj = result.examination.subject
        key = str(subj)
        entry = subject_breakdown.setdefault(
            key,
            {
                "subject_id": subj.pk,
                "exams": 0,
                "total_score": Decimal("0"),
                "total_possible": Decimal("0"),
                "average_percentage": Decimal("0"),
                "best_grade": None,
            },
        )
        entry["exams"] += 1
        entry["total_score"] += result.score or Decimal("0")
        entry["total_possible"] += result.examination.total_marks
        if result.percentage:
            entry["average_percentage"] = (
                entry["average_percentage"] * (entry["exams"] - 1) + result.percentage
            ) / entry["exams"]
        if result.grade and (entry["best_grade"] is None or result.grade < entry["best_grade"]):
            entry["best_grade"] = result.grade

    # Grade tally
    grade_tally = Counter(r.grade for r in qs if r.grade)

    return {
        "student_id": student_id,
        "academic_session_id": academic_session_id,
        "exams_taken": exams_taken,
        "exams_passed": exams_passed,
        "exams_failed": agg.get("exams_failed") or 0,
        "average_percentage": _decimal_or_none(agg.get("average_percentage")),
        "highest_percentage": _decimal_or_none(agg.get("highest_percentage")),
        "lowest_percentage": _decimal_or_none(agg.get("lowest_percentage")),
        "total_score": _decimal_or_none(total_score),
        "total_possible": _decimal_or_none(total_possible),
        "overall_percentage": overall_pct,
        "pass_rate": pass_rate,
        "subject_breakdown": subject_breakdown,
        "grade_tally": dict(grade_tally),
    }


def get_student_trend(student_id: int, subject_id: int, limit: int = 5) -> list[dict]:
    """
    Recent trend of a student's scores in a subject across the last N exams.

    Useful for drawing sparkline charts on dashboards.

    Args:
        student_id: PK of ``Student``
        subject_id: PK of ``Subject``
        limit:      Maximum number of results to return (default 5)

    Returns:
        list[dict]: Each item has ``exam_date``, ``exam_name``,
                    ``score``, ``percentage``, ``grade``, ``is_pass``
    """
    Result = _results()

    qs = (
        Result.objects.filter(
            student_id=student_id,
            examination__subject_id=subject_id,
            status__in=["COMPLETED", "SUBMITTED"],
            score__isnull=False,
        )
        .select_related("examination")
        .order_by("-examination__exam_date")[:limit]
    )

    return [
        {
            "exam_date": r.examination.exam_date,
            "exam_name": r.examination.name,
            "score": r.score,
            "percentage": r.percentage,
            "grade": r.grade,
            "is_pass": r.is_pass,
        }
        for r in reversed(list(qs))  # chronological order
    ]


# =============================================================================
# SUBJECT PERFORMANCE STATISTICS
# =============================================================================

def get_subject_performance(subject_id: int, academic_session_id: int) -> dict:
    """
    Aggregated performance metrics for a subject across an academic session.

    Args:
        subject_id:          PK of ``Subject``
        academic_session_id: PK of ``AcademicSession``

    Returns:
        dict with keys:
            ``subject_id``, ``academic_session_id``, ``total_results``,
            ``average_score``, ``average_percentage``, ``highest_score``,
            ``lowest_score``, ``pass_rate``, ``grade_distribution``,
            ``class_breakdown``
    """
    from students.models import Student

    Result = _results()

    qs = Result.objects.filter(
        examination__subject_id=subject_id,
        examination__academic_session_id=academic_session_id,
        status__in=["COMPLETED", "SUBMITTED"],
        score__isnull=False,
    ).select_related("examination", "student__current_class")

    agg = qs.aggregate(
        total_results=Count("id"),
        average_score=Avg("score"),
        average_percentage=Avg("percentage"),
        highest_score=Max("score"),
        lowest_score=Min("score"),
        pass_count=Count("id", filter=Q(is_pass=True)),
    )

    total = agg.get("total_results") or 0
    pass_rate = (
        round((agg.get("pass_count") or 0) / total * 100, 2) if total else 0.0
    )

    grade_dist = (
        qs.exclude(grade="")
        .values("grade")
        .annotate(count=Count("id"))
        .order_by("grade")
    )

    # Per-class breakdown
    class_breakdown: dict[str, dict] = {}
    for result in qs:
        cls = result.student.current_class
        if cls is None:
            continue
        key = str(cls)
        entry = class_breakdown.setdefault(
            key,
            {
                "class_id": cls.pk,
                "total": 0,
                "passed": 0,
                "avg_percentage": Decimal("0"),
            },
        )
        entry["total"] += 1
        if result.is_pass:
            entry["passed"] += 1
        if result.percentage:
            entry["avg_percentage"] = (
                entry["avg_percentage"] * (entry["total"] - 1) + result.percentage
            ) / entry["total"]

    return {
        "subject_id": subject_id,
        "academic_session_id": academic_session_id,
        "total_results": total,
        "average_score": _decimal_or_none(agg.get("average_score")),
        "average_percentage": _decimal_or_none(agg.get("average_percentage")),
        "highest_score": _decimal_or_none(agg.get("highest_score")),
        "lowest_score": _decimal_or_none(agg.get("lowest_score")),
        "pass_rate": pass_rate,
        "grade_distribution": {row["grade"]: row["count"] for row in grade_dist},
        "class_breakdown": class_breakdown,
    }


# =============================================================================
# PASS/FAIL ANALYTICS
# =============================================================================

def get_pass_fail_breakdown(
    academic_session_id: int,
    class_id: Optional[int] = None,
    subject_id: Optional[int] = None,
) -> dict:
    """
    Pass/fail summary, optionally filtered by class and/or subject.

    Args:
        academic_session_id: PK of ``AcademicSession``
        class_id:            Optional PK of ``Class``
        subject_id:          Optional PK of ``Subject``

    Returns:
        dict with keys:
            ``total``, ``passed``, ``failed``, ``absent``,
            ``disqualified``, ``pass_rate``, ``fail_rate``
    """
    Result = _results()

    qs = Result.objects.filter(
        examination__academic_session_id=academic_session_id
    )

    if class_id:
        from students.models import Student
        student_pks = Student.objects.filter(
            current_class_id=class_id, is_active=True
        ).values_list("pk", flat=True)
        qs = qs.filter(student_id__in=student_pks)

    if subject_id:
        qs = qs.filter(examination__subject_id=subject_id)

    agg = qs.aggregate(
        total=Count("id"),
        passed=Count("id", filter=Q(is_pass=True, status__in=["COMPLETED", "SUBMITTED"])),
        failed=Count("id", filter=Q(is_pass=False, status__in=["COMPLETED", "SUBMITTED"])),
        absent=Count("id", filter=Q(status="ABSENT")),
        disqualified=Count("id", filter=Q(status="DISQUALIFIED")),
        scored=Count("id", filter=Q(status__in=["COMPLETED", "SUBMITTED"], score__isnull=False)),
    )

    scored = agg.get("scored") or 0
    passed = agg.get("passed") or 0
    pass_rate = round(passed / scored * 100, 2) if scored else 0.0
    fail_rate = round(100 - pass_rate, 2) if scored else 0.0

    return {
        "total": agg.get("total") or 0,
        "passed": passed,
        "failed": agg.get("failed") or 0,
        "absent": agg.get("absent") or 0,
        "disqualified": agg.get("disqualified") or 0,
        "pass_rate": pass_rate,
        "fail_rate": fail_rate,
    }


def get_at_risk_students(
    academic_session_id: int,
    fail_threshold: int = 2,
    class_id: Optional[int] = None,
) -> list[dict]:
    """
    Identify students who have failed more than ``fail_threshold`` exams.

    Args:
        academic_session_id: PK of ``AcademicSession``
        fail_threshold:      Minimum failures to be considered "at risk" (default 2)
        class_id:            Optional PK of ``Class``

    Returns:
        list[dict]: Each item has ``student_id``, ``student_name``,
                    ``fail_count``, ``exam_count``, ``average_percentage``
    """
    Result = _results()

    qs = Result.objects.filter(
        examination__academic_session_id=academic_session_id,
        status__in=["COMPLETED", "SUBMITTED"],
        score__isnull=False,
    )

    if class_id:
        from students.models import Student
        student_pks = Student.objects.filter(
            current_class_id=class_id, is_active=True
        ).values_list("pk", flat=True)
        qs = qs.filter(student_id__in=student_pks)

    student_stats = (
        qs.values("student_id", "student__first_name", "student__last_name")
        .annotate(
            fail_count=Count("id", filter=Q(is_pass=False)),
            exam_count=Count("id"),
            average_percentage=Avg("percentage"),
        )
        .filter(fail_count__gte=fail_threshold)
        .order_by("-fail_count")
    )

    return [
        {
            "student_id": row["student_id"],
            "student_name": f"{row['student__first_name']} {row['student__last_name']}".strip(),
            "fail_count": row["fail_count"],
            "exam_count": row["exam_count"],
            "average_percentage": _decimal_or_none(row["average_percentage"]),
        }
        for row in student_stats
    ]


# =============================================================================
# GRADE DISTRIBUTION ANALYTICS
# =============================================================================

def get_grade_distribution(
    academic_session_id: int,
    class_id: Optional[int] = None,
    subject_id: Optional[int] = None,
) -> dict:
    """
    Count of results per grade letter, optionally filtered.

    Args:
        academic_session_id: PK of ``AcademicSession``
        class_id:            Optional PK of ``Class``
        subject_id:          Optional PK of ``Subject``

    Returns:
        dict: ``{grade_letter: count, ...}``  e.g. ``{"A": 12, "B": 25, ...}``
    """
    Result = _results()

    qs = Result.objects.filter(
        examination__academic_session_id=academic_session_id,
        status__in=["COMPLETED", "SUBMITTED"],
    ).exclude(grade="")

    if class_id:
        from students.models import Student
        pks = Student.objects.filter(current_class_id=class_id).values_list("pk", flat=True)
        qs = qs.filter(student_id__in=pks)

    if subject_id:
        qs = qs.filter(examination__subject_id=subject_id)

    rows = qs.values("grade").annotate(count=Count("id")).order_by("grade")
    return {row["grade"]: row["count"] for row in rows}


def get_score_distribution_buckets(
    examination_id: int,
    bucket_size: int = 10,
) -> list[dict]:
    """
    Split scores into equal-width buckets for histogram visualisation.

    Args:
        examination_id: PK of ``Examination``
        bucket_size:    Width of each bucket in marks (default 10)

    Returns:
        list[dict]: Each item has ``bucket_label``, ``min``, ``max``, ``count``
        Ordered by ascending ``min``.
    """
    Result = _results()

    scores = list(
        Result.objects.filter(
            examination_id=examination_id,
            status__in=["COMPLETED", "SUBMITTED"],
            score__isnull=False,
        ).values_list("score", flat=True)
    )

    if not scores:
        return []

    try:
        exam = _exams().objects.get(pk=examination_id)
        max_possible = int(exam.total_marks)
    except Exception:
        max_possible = int(max(scores))

    buckets: dict[int, int] = defaultdict(int)
    for score in scores:
        bucket_floor = (int(score) // bucket_size) * bucket_size
        buckets[bucket_floor] += 1

    result_list = []
    for floor in range(0, max_possible + 1, bucket_size):
        ceiling = min(floor + bucket_size - 1, max_possible)
        result_list.append(
            {
                "bucket_label": f"{floor}–{ceiling}",
                "min": floor,
                "max": ceiling,
                "count": buckets.get(floor, 0),
            }
        )

    return result_list


# =============================================================================
# CROSS-SESSION COMPARATIVE STATS
# =============================================================================

def get_session_comparison(
    subject_id: int,
    session_ids: list[int],
    class_id: Optional[int] = None,
) -> list[dict]:
    """
    Compare subject performance across multiple academic sessions.

    Args:
        subject_id:  PK of ``Subject``
        session_ids: Ordered list of ``AcademicSession`` PKs to compare
        class_id:    Optional PK of ``Class``

    Returns:
        list[dict]: One item per session with ``session_id``,
                    ``average_percentage``, ``pass_rate``, ``total_results``
    """
    from academics.models import AcademicSession

    Result = _results()
    output = []

    for sid in session_ids:
        qs = Result.objects.filter(
            examination__subject_id=subject_id,
            examination__academic_session_id=sid,
            status__in=["COMPLETED", "SUBMITTED"],
            score__isnull=False,
        )
        if class_id:
            from students.models import Student
            pks = Student.objects.filter(current_class_id=class_id).values_list("pk", flat=True)
            qs = qs.filter(student_id__in=pks)

        agg = qs.aggregate(
            average_percentage=Avg("percentage"),
            pass_count=Count("id", filter=Q(is_pass=True)),
            total=Count("id"),
        )
        total = agg.get("total") or 0
        pass_rate = (
            round((agg.get("pass_count") or 0) / total * 100, 2) if total else 0.0
        )

        try:
            session_name = AcademicSession.objects.get(pk=sid).name
        except Exception:
            session_name = f"Session #{sid}"

        output.append(
            {
                "session_id": sid,
                "session_name": session_name,
                "average_percentage": _decimal_or_none(agg.get("average_percentage")),
                "pass_rate": pass_rate,
                "total_results": total,
            }
        )

    return output


# =============================================================================
# GRADING SYSTEM EFFECTIVENESS
# =============================================================================

def get_grading_system_effectiveness(grading_system_id: int) -> dict:
    """
    Analyse how scores are distributed across grade bands for a given
    grading system, revealing whether the bands are well-calibrated.

    Args:
        grading_system_id: PK of ``GradingSystem``

    Returns:
        dict with keys:
            ``grading_system_id``, ``grading_system_name``,
            ``total_results``, ``grade_band_analysis``
                → list of ``{grade, min_score, max_score, result_count, percentage}``
    """
    from .models import GradingSystem

    Result = _results()

    try:
        gs = GradingSystem.objects.prefetch_related("ranges").get(pk=grading_system_id)
    except GradingSystem.DoesNotExist:
        return {"error": f"GradingSystem #{grading_system_id} not found"}

    total_results = Result.objects.filter(
        examination__grading_system_id=grading_system_id,
        status__in=["COMPLETED", "SUBMITTED"],
        score__isnull=False,
    ).count()

    band_analysis = []
    for gr in gs.ranges.all().order_by("-min_score"):
        count = Result.objects.filter(
            examination__grading_system_id=grading_system_id,
            status__in=["COMPLETED", "SUBMITTED"],
            grade=gr.grade,
        ).count()
        band_analysis.append(
            {
                "grade": gr.grade,
                "grade_name": gr.grade_name,
                "min_score": gr.min_score,
                "max_score": gr.max_score,
                "result_count": count,
                "percentage": round(count / total_results * 100, 2) if total_results else 0.0,
                "is_passing_grade": gr.is_passing_grade,
            }
        )

    return {
        "grading_system_id": grading_system_id,
        "grading_system_name": gs.name,
        "total_results": total_results,
        "grade_band_analysis": band_analysis,
    }


# =============================================================================
# GRADE LOCK STATISTICS
# =============================================================================

def get_grade_lock_stats(academic_session_id: int) -> dict:
    """
    Summarise grade-locking activity for an academic session.

    Args:
        academic_session_id: PK of ``AcademicSession``

    Returns:
        dict with keys:
            ``total_results``, ``locked_count``, ``unlocked_count``,
            ``lock_rate``, ``auto_locked``, ``manually_locked``,
            ``published_and_locked``, ``published_and_unlocked``
    """
    Result = _results()

    qs = Result.objects.filter(
        examination__academic_session_id=academic_session_id
    )

    agg = qs.aggregate(
        total=Count("id"),
        locked=Count("id", filter=Q(is_grade_locked=True)),
        auto_locked=Count(
            "id",
            filter=Q(is_grade_locked=True, lock_reason__icontains="auto"),
        ),
        published_locked=Count(
            "id", filter=Q(is_grade_locked=True, is_published=True)
        ),
        published_unlocked=Count(
            "id", filter=Q(is_grade_locked=False, is_published=True)
        ),
    )

    total = agg.get("total") or 0
    locked = agg.get("locked") or 0
    lock_rate = round(locked / total * 100, 2) if total else 0.0
    auto_locked = agg.get("auto_locked") or 0
    manually_locked = locked - auto_locked

    return {
        "total_results": total,
        "locked_count": locked,
        "unlocked_count": total - locked,
        "lock_rate": lock_rate,
        "auto_locked": auto_locked,
        "manually_locked": manually_locked,
        "published_and_locked": agg.get("published_locked") or 0,
        "published_and_unlocked": agg.get("published_unlocked") or 0,
    }


# =============================================================================
# DASHBOARD SUMMARY
# =============================================================================

def get_exam_dashboard_summary(academic_session_id: int) -> dict:
    """
    High-level summary for the examinations management dashboard.

    Args:
        academic_session_id: PK of ``AcademicSession``

    Returns:
        dict with keys:
            ``total_exams``, ``exams_by_status``, ``upcoming_exams``,
            ``total_results``, ``overall_pass_rate``, ``published_results``,
            ``unpublished_results``, ``grade_lock_summary``
    """
    Exam = _exams()
    Result = _results()

    today = get_school_today()

    exam_qs = Exam.objects.filter(academic_session_id=academic_session_id)
    result_qs = Result.objects.filter(
        examination__academic_session_id=academic_session_id
    )

    # Exams by status
    exams_by_status = dict(
        exam_qs.values("status")
        .annotate(count=Count("id"))
        .values_list("status", "count")
    )

    upcoming = exam_qs.filter(
        exam_date__gte=today, status__in=["PLANNED", "SCHEDULED"]
    ).order_by("exam_date")[:5]

    scored_qs = result_qs.filter(
        status__in=["COMPLETED", "SUBMITTED"], score__isnull=False
    )
    scored_total = scored_qs.count()
    pass_count = scored_qs.filter(is_pass=True).count()
    overall_pass_rate = (
        round(pass_count / scored_total * 100, 2) if scored_total else 0.0
    )

    return {
        "total_exams": exam_qs.count(),
        "exams_by_status": exams_by_status,
        "upcoming_exams": [
            {
                "id": e.pk,
                "name": e.name,
                "subject": str(e.subject),
                "exam_date": e.exam_date,
                "status": e.status,
            }
            for e in upcoming
        ],
        "total_results": result_qs.count(),
        "total_scored": scored_total,
        "overall_pass_rate": overall_pass_rate,
        "published_results": result_qs.filter(is_published=True).count(),
        "unpublished_results": result_qs.filter(is_published=False).count(),
        "grade_lock_summary": get_grade_lock_stats(academic_session_id),
    }


def get_top_performers(
    academic_session_id: int,
    class_id: Optional[int] = None,
    subject_id: Optional[int] = None,
    limit: int = 10,
) -> list[dict]:
    """
    Return the top-performing students by average percentage.

    Args:
        academic_session_id: PK of ``AcademicSession``
        class_id:            Optional filter by class
        subject_id:          Optional filter by subject
        limit:               Maximum results to return (default 10)

    Returns:
        list[dict]: Each item has ``student_id``, ``student_name``,
                    ``average_percentage``, ``exams_taken``, ``pass_rate``
    """
    Result = _results()

    qs = Result.objects.filter(
        examination__academic_session_id=academic_session_id,
        status__in=["COMPLETED", "SUBMITTED"],
        score__isnull=False,
    )

    if class_id:
        from students.models import Student
        pks = Student.objects.filter(current_class_id=class_id).values_list("pk", flat=True)
        qs = qs.filter(student_id__in=pks)

    if subject_id:
        qs = qs.filter(examination__subject_id=subject_id)

    rows = (
        qs.values("student_id", "student__first_name", "student__last_name")
        .annotate(
            average_percentage=Avg("percentage"),
            exams_taken=Count("id"),
            pass_count=Count("id", filter=Q(is_pass=True)),
        )
        .order_by("-average_percentage")[:limit]
    )

    return [
        {
            "student_id": row["student_id"],
            "student_name": f"{row['student__first_name']} {row['student__last_name']}".strip(),
            "average_percentage": _decimal_or_none(row["average_percentage"]),
            "exams_taken": row["exams_taken"],
            "pass_rate": round(
                row["pass_count"] / row["exams_taken"] * 100, 2
            ) if row["exams_taken"] else 0.0,
        }
        for row in rows
    ]


# =============================================================================
# INTERNAL HELPERS
# =============================================================================

def _decimal_or_none(value) -> Optional[Decimal]:
    """Coerce a value to Decimal, returning None if the value is None."""
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception:
        return None