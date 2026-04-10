# boarding/stats.py

"""
Boarding statistics functions.

WHAT BELONGS HERE
-----------------
Aggregate statistics — counts, percentages, averages, trend lists — that
feed dashboards and reports.  Every function returns a number, a dict of
numbers, or a list of dicts.

WHAT DOES NOT BELONG HERE
--------------------------
- Raw queryset helpers → boarding/utils.py
  (get_available_dormitories, get_expiring_boarding_enrollments, etc.)
- Individual record operations → boarding/models.py or boarding/services.py

REMOVED FROM ORIGINAL
---------------------
- get_boarding_enrollment_by_date_range  — returns a queryset, not a stat
- get_recent_boarding_enrollments        — queryset helper; inline where needed
- get_expiring_boarding_enrollments      — moved to boarding/utils.py (fixed)

RENAMED
-------
- get_students_without_boarding → get_students_without_boarding_count
  to make explicit that the return value is an int, not a queryset
  (boarding/utils.py has get_students_without_boarding(session) → queryset)

FIXED
-----
- avg_enrollment_duration:  replaced Python loop with a single DB aggregation
- get_boarding_occupancy_trends: replaced timedelta(days=i*30) approximation
  with proper calendar-month arithmetic
- get_overdue_boarding_enrollments: expected_end_date → effective_end_date
- All timezone.now().date() calls → get_school_today()
"""

from django.db.models import (
    Count, Avg, Q, Sum, F,
    ExpressionWrapper, DurationField, FloatField,
)
from django.db.models.functions import TruncMonth
from datetime import timedelta, date

from core.utils import (
    get_school_today,
    get_school_current_time,
    get_active_academic_session,
)


# =============================================================================
# GENERAL BOARDING STATISTICS
# =============================================================================

def get_boarding_statistics():
    """
    Comprehensive statistics for the entire boarding system (all sessions).

    Returns:
        dict with keys:
            total_boarders, boarding_type_counts, enrollment_status_counts,
            gender_distribution, male_percentage, female_percentage,
            avg_enrollment_duration, dormitory_occupancy, pending_approvals.

    FIX: avg_enrollment_duration is now a single DB aggregation rather than a
    Python loop over completed enrollment records.
    """
    from .models import BoardingEnrollment, Dormitory

    enrollments        = BoardingEnrollment.objects.all()
    active_enrollments = enrollments.filter(status='ACTIVE')
    total_boarders     = active_enrollments.count()

    # Boarding type breakdown
    boarding_type_counts = {
        code: active_enrollments.filter(boarding_type=code).count()
        for code, _ in BoardingEnrollment.BOARDING_TYPE_CHOICES
    }

    # Enrollment status breakdown
    enrollment_status_counts = {
        code: enrollments.filter(status=code).count()
        for code, _ in BoardingEnrollment.ENROLLMENT_STATUS_CHOICES
    }

    # Gender distribution
    male_count   = active_enrollments.filter(student__gender='M').count()
    female_count = active_enrollments.filter(student__gender='F').count()

    gender_distribution = {'male': male_count, 'female': female_count}

    male_pct   = round(male_count   / total_boarders * 100, 1) if total_boarders else 0
    female_pct = round(female_count / total_boarders * 100, 1) if total_boarders else 0

    # Average enrollment duration — single DB aggregation
    # FIX: replaced Python loop that loaded every completed record into memory.
    avg_raw = enrollments.filter(
        status='COMPLETED',
        effective_end_date__isnull=False,
    ).aggregate(
        avg=Avg(
            ExpressionWrapper(
                F('effective_end_date') - F('effective_start_date'),
                output_field=DurationField(),
            )
        )
    )['avg']

    avg_enrollment_duration = round(avg_raw.days, 1) if avg_raw else 0

    # Dormitory occupancy summary
    dormitories    = Dormitory.objects.filter(is_active=True)
    cap_agg        = dormitories.aggregate(
        total_capacity=Sum('total_capacity'),
        total_occupied=Sum('current_occupancy'),
    )
    total_capacity = cap_agg['total_capacity'] or 0
    total_occupied = cap_agg['total_occupied'] or 0
    occupancy_rate = round(total_occupied / total_capacity * 100, 1) if total_capacity else 0

    dormitory_occupancy = {
        'total_capacity':   total_capacity,
        'total_occupied':   total_occupied,
        'total_available':  total_capacity - total_occupied,
        'occupancy_rate':   occupancy_rate,
        'dormitory_count':  dormitories.count(),
    }

    return {
        'total_boarders':            total_boarders,
        'boarding_type_counts':      boarding_type_counts,
        'enrollment_status_counts':  enrollment_status_counts,
        'gender_distribution':       gender_distribution,
        'male_percentage':           male_pct,
        'female_percentage':         female_pct,
        'avg_enrollment_duration':   avg_enrollment_duration,
        'dormitory_occupancy':       dormitory_occupancy,
        'pending_approvals':         enrollments.filter(status='PENDING').count(),
    }


# =============================================================================
# DORMITORY STATISTICS
# =============================================================================

def get_dormitory_statistics():
    """
    Detailed statistics for all dormitories.

    Returns:
        dict with keys:
            total_dormitories, active_dormitories, type_breakdown,
            maintenance_status_counts, occupancy_levels,
            avg_occupancy_rate, dormitory_breakdown.
    """
    from .models import Dormitory

    dormitories        = Dormitory.objects.all()
    active_dormitories = dormitories.filter(is_active=True)

    type_breakdown = {
        code: dormitories.filter(dormitory_type=code).count()
        for code, _ in Dormitory.DORMITORY_TYPE_CHOICES
    }

    maintenance_status_counts = {
        code: dormitories.filter(maintenance_status=code).count()
        for code, _ in Dormitory.MAINTENANCE_STATUS_CHOICES
    }

    occupancy_levels = {'empty': 0, 'low': 0, 'medium': 0, 'high': 0}
    total_occupancy_rate         = 0.0
    dormitories_with_capacity    = 0
    dormitory_breakdown          = []

    for dorm in active_dormitories:
        pct   = dorm.get_occupancy_percentage()
        level = dorm.get_occupancy_level()

        occupancy_levels[level] += 1

        if dorm.total_capacity > 0:
            total_occupancy_rate      += pct
            dormitories_with_capacity += 1

        dormitory_breakdown.append({
            'id':                  dorm.id,
            'name':                dorm.name,
            'type':                dorm.get_dormitory_type_display(),
            'capacity':            dorm.total_capacity,
            'occupancy':           dorm.current_occupancy,
            'available':           dorm.get_available_capacity(),
            'occupancy_percentage': pct,
            'occupancy_level':     level,
            'is_full':             dorm.is_full,
            'maintenance_status':  dorm.get_maintenance_status_display(),
        })

    avg_occupancy_rate = (
        round(total_occupancy_rate / dormitories_with_capacity, 1)
        if dormitories_with_capacity
        else 0
    )

    return {
        'total_dormitories':       dormitories.count(),
        'active_dormitories':      active_dormitories.count(),
        'type_breakdown':          type_breakdown,
        'maintenance_status_counts': maintenance_status_counts,
        'occupancy_levels':        occupancy_levels,
        'avg_occupancy_rate':      avg_occupancy_rate,
        'dormitory_breakdown':     dormitory_breakdown,
    }


# =============================================================================
# SIMPLE COUNT FUNCTIONS
# =============================================================================

def get_active_boarders_count():
    """Return the number of students with an ACTIVE boarding enrollment."""
    from .models import BoardingEnrollment
    return BoardingEnrollment.objects.filter(status='ACTIVE').count()


def get_boarding_type_count(boarding_type):
    """
    Return the number of ACTIVE boarders of the given type.

    Args:
        boarding_type (str): One of FULL_BOARDER, WEEKLY_BOARDER, FLEXI_BOARDER.
    """
    from .models import BoardingEnrollment
    return BoardingEnrollment.objects.filter(
        status='ACTIVE',
        boarding_type=boarding_type,
    ).count()


def get_pending_approvals_count():
    """Return the number of boarding enrollments awaiting approval."""
    from .models import BoardingEnrollment
    return BoardingEnrollment.objects.filter(status='PENDING').count()


def get_students_without_boarding_count():
    """
    Return the count of active students with no ACTIVE boarding enrollment
    (across all sessions).

    For a session-scoped queryset of unenrolled students use
    boarding.utils.get_students_without_boarding(session).
    """
    from students.models import Student
    from .models import BoardingEnrollment

    students_with_boarding = BoardingEnrollment.objects.filter(
        status='ACTIVE',
    ).values_list('student_id', flat=True)

    return Student.objects.filter(
        enrollment_status='ACTIVE',
    ).exclude(
        id__in=students_with_boarding,
    ).count()


# =============================================================================
# DORMITORY-SPECIFIC STATISTICS
# =============================================================================

def get_dormitory_occupancy_rate(dormitory_id):
    """
    Return the occupancy percentage for a single dormitory.

    Args:
        dormitory_id: PK of the Dormitory.

    Returns:
        float: Occupancy percentage, or 0.0 if not found.
    """
    from .models import Dormitory
    try:
        return Dormitory.objects.get(id=dormitory_id).get_occupancy_percentage()
    except Dormitory.DoesNotExist:
        return 0.0


def get_dormitory_gender_distribution(dormitory_id):
    """
    Return male / female counts for ACTIVE residents of a dormitory.

    Args:
        dormitory_id: PK of the Dormitory.

    Returns:
        dict: {'male': int, 'female': int}
    """
    from .models import BoardingEnrollment

    qs = BoardingEnrollment.objects.filter(
        dormitory_id=dormitory_id,
        status='ACTIVE',
    )
    return {
        'male':   qs.filter(student__gender='M').count(),
        'female': qs.filter(student__gender='F').count(),
    }


# =============================================================================
# SESSION-SCOPED STATISTICS
# =============================================================================

def get_boarding_statistics_by_session(academic_session=None):
    """
    Boarding statistics scoped to a single academic session.

    Args:
        academic_session: AcademicSession instance or PK.  Defaults to the
                          current active session.

    Returns:
        dict with keys:
            total_enrollments, active_enrollments, boarding_type_counts,
            status_counts, pending_approvals.
        Returns an error dict if no session can be resolved.
    """
    from .models import BoardingEnrollment

    if academic_session is None:
        academic_session = get_active_academic_session()
        if academic_session is None:
            return {
                'error': 'No academic session provided and no active session found',
                'total_enrollments': 0,
            }

    filter_kwargs = (
        {'academic_session': academic_session}
        if hasattr(academic_session, 'id')
        else {'academic_session_id': academic_session}
    )

    enrollments        = BoardingEnrollment.objects.filter(**filter_kwargs)
    active_enrollments = enrollments.filter(status='ACTIVE')

    boarding_type_counts = {
        code: active_enrollments.filter(boarding_type=code).count()
        for code, _ in BoardingEnrollment.BOARDING_TYPE_CHOICES
    }

    status_counts = {
        code: enrollments.filter(status=code).count()
        for code, _ in BoardingEnrollment.ENROLLMENT_STATUS_CHOICES
    }

    return {
        'total_enrollments':     enrollments.count(),
        'active_enrollments':    active_enrollments.count(),
        'boarding_type_counts':  boarding_type_counts,
        'status_counts':         status_counts,
        'pending_approvals':     enrollments.filter(status='PENDING').count(),
    }


# =============================================================================
# MAINTENANCE AND CONDITION
# =============================================================================

def get_dormitories_needing_maintenance():
    """
    Return active dormitories where maintenance is overdue or the condition
    is at or below 'Fair'.

    Uses get_school_today() so the date comparison respects the school's
    configured operational timezone.

    Returns:
        QuerySet[Dormitory]
    """
    from .models import Dormitory

    today = get_school_today()

    return Dormitory.objects.filter(
        Q(next_maintenance_due__lte=today) |
        Q(maintenance_status__in=('NEEDS_REPAIR', 'FAIR')),
        is_active=True,
    ).order_by('next_maintenance_due')


# =============================================================================
# CAPACITY REPORT
# =============================================================================

def get_dormitory_capacity_report():
    """
    Aggregate capacity metrics broken down by dormitory type.

    Returns:
        dict with an 'overall' key and one key per DORMITORY_TYPE_CHOICES code.
        Each value is a dict with:
            total_capacity, current_occupancy, available_capacity, occupancy_rate.
        Type-level entries also include dormitory_count and type_name.
    """
    from .models import Dormitory

    dormitories = Dormitory.objects.filter(is_active=True)

    def _build_section(qs):
        agg     = qs.aggregate(
            total_cap=Sum('total_capacity'),
            total_occ=Sum('current_occupancy'),
        )
        cap     = agg['total_cap'] or 0
        occ     = agg['total_occ'] or 0
        return {
            'total_capacity':     cap,
            'current_occupancy':  occ,
            'available_capacity': cap - occ,
            'occupancy_rate':     round(occ / cap * 100, 1) if cap else 0,
        }

    report = {'overall': _build_section(dormitories)}

    for code, name in Dormitory.DORMITORY_TYPE_CHOICES:
        type_qs = dormitories.filter(dormitory_type=code)
        section = _build_section(type_qs)
        section['type_name']       = name
        section['dormitory_count'] = type_qs.count()
        report[code]               = section

    return report


# =============================================================================
# CONSENT STATISTICS
# =============================================================================

def get_boarding_consent_status():
    """
    Guardian consent statistics for all ACTIVE boarders.

    Returns:
        dict: with_consent, without_consent, total_active, consent_rate.
    """
    from .models import BoardingEnrollment

    active       = BoardingEnrollment.objects.filter(status='ACTIVE')
    with_consent = active.filter(guardian_consent=True).count()
    total        = active.count()

    return {
        'with_consent':    with_consent,
        'without_consent': total - with_consent,
        'total_active':    total,
        'consent_rate':    round(with_consent / total * 100, 1) if total else 0,
    }


# =============================================================================
# OVERDUE ENROLLMENTS
# =============================================================================

def get_overdue_boarding_enrollments():
    """
    Return ACTIVE enrollments whose effective_end_date has already passed.

    These are enrollments that should have ended but have not been marked
    as COMPLETED or TERMINATED.

    FIX: field was expected_end_date — corrected to effective_end_date.
    FIX: uses get_school_today() instead of timezone.now().date().

    Returns:
        QuerySet[BoardingEnrollment]: Ordered by effective_end_date ascending
        (most overdue first).
    """
    from .models import BoardingEnrollment

    today = get_school_today()

    return BoardingEnrollment.objects.filter(
        status='ACTIVE',
        effective_end_date__isnull=False,
        effective_end_date__lt=today,
    ).select_related('student', 'dormitory').order_by('effective_end_date')


# =============================================================================
# TREND FUNCTIONS
# =============================================================================

def get_boarding_enrollment_trends(months=6):
    """
    Count of new boarding enrollments grouped by calendar month for the last
    ``months`` months.

    Uses TruncMonth on enrollment_date so grouping is exact.

    Args:
        months (int): Number of months to include (default 6).

    Returns:
        list[dict]: Each dict has 'month' (date) and 'count' (int).
    """
    from .models import BoardingEnrollment

    today      = get_school_today()
    start_date = _first_of_month(today, months_back=months - 1)

    return list(
        BoardingEnrollment.objects
        .filter(enrollment_date__gte=start_date)
        .annotate(month=TruncMonth('enrollment_date'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    )


def get_boarding_occupancy_trends(months=6):
    """
    Count of boarding enrollments that started each calendar month for the
    last ``months`` months, as a proxy for occupancy growth over time.

    FIX: replaced the timedelta(days=i * 30) approximation — which drifted
    by several days over longer periods — with exact calendar-month
    boundaries using TruncMonth on effective_start_date.

    Args:
        months (int): Number of months to include (default 6).

    Returns:
        list[dict]: Each dict has 'month' (date) and 'active_boarders' (int).
    """
    from .models import BoardingEnrollment

    today      = get_school_today()
    start_date = _first_of_month(today, months_back=months - 1)

    return list(
        BoardingEnrollment.objects
        .filter(effective_start_date__gte=start_date)
        .annotate(month=TruncMonth('effective_start_date'))
        .values('month')
        .annotate(active_boarders=Count('id'))
        .order_by('month')
    )


# =============================================================================
# COMPREHENSIVE SUMMARY
# =============================================================================

def get_boarding_statistics_summary():
    """
    Single entry-point for all key boarding metrics.  Intended for dashboard
    widgets that need a broad overview without issuing many separate queries.

    Imports get_expiring_boarding_enrollments from boarding.utils (the
    queryset helper) rather than duplicating it here.

    Returns:
        dict: Aggregated stats from all other functions in this module plus
        a few cross-cutting counts.
    """
    from boarding.utils import get_expiring_boarding_enrollments

    today = get_school_today()

    return {
        'general_stats':                get_boarding_statistics(),
        'dormitory_stats':              get_dormitory_statistics(),
        'active_boarders':              get_active_boarders_count(),
        'pending_approvals':            get_pending_approvals_count(),
        'students_without_boarding':    get_students_without_boarding_count(),
        'consent_status':               get_boarding_consent_status(),
        'dormitories_needing_maintenance': get_dormitories_needing_maintenance().count(),
        'expiring_enrollments_30days':  get_expiring_boarding_enrollments(days=30).count(),
        'overdue_enrollments':          get_overdue_boarding_enrollments().count(),
        'current_date':                 today,
    }


# =============================================================================
# PRIVATE HELPERS
# =============================================================================

def _first_of_month(reference_date, months_back=0):
    """
    Return the first day of the calendar month that is ``months_back`` months
    before ``reference_date``.

    Uses pure arithmetic rather than dateutil so there is no extra dependency.

    Args:
        reference_date (date): Starting point (usually today).
        months_back (int):     How many months to go back (0 = current month).

    Returns:
        date: First day of the target month.
    """
    month = reference_date.month - months_back
    year  = reference_date.year

    # Normalise month underflow
    while month <= 0:
        month += 12
        year  -= 1

    return date(year, month, 1)