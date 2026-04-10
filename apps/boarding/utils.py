# boarding/utils.py

"""
Utility functions for the boarding app.

WHAT BELONGS HERE
-----------------
- Roll number generation (requires select_for_update — not suitable for a model method)
- Queryset helpers that combine multiple models or add annotations
- Financial summary helpers that aggregate across invoices
- Pure validation helpers (boarding_days format, room assignment)

WHAT DOES NOT BELONG HERE
--------------------------
- Capacity / occupancy calculations → Dormitory model methods
  (get_available_capacity, get_occupancy_percentage, get_occupancy_level,
  get_occupancy_color, has_capacity, is_full, can_accommodate)
- Single-student pre-flight validation → BoardingEnrollmentValidationService
- Aggregate boarding statistics → boarding/stats.py
- Fee amount calculations → fees app / FeesStructure model

CHANGES FROM PREVIOUS VERSION
------------------------------
generate_boarding_roll_number:
  FIX: was using last.boarding_roll_number.isdigit() which returns False for
  the legacy format BRD-2026T1-115, causing every new enrolment in a session
  that already had records to be assigned 001.  Now uses re.search(r'(\d+)$')
  to extract the trailing number from any format, so both the old prefixed
  format and the new plain-digit format are handled correctly.
"""

import re
from django.db import transaction
from django.db.models import (
    Q, F, Count, Sum, ExpressionWrapper, FloatField, Case, When,
)
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import logging

from core.utils import get_school_today

logger = logging.getLogger(__name__)


# =============================================================================
# ROLL NUMBER GENERATION
# =============================================================================

def generate_boarding_roll_number(*, dormitory, academic_session):
    """
    Generate the next sequential boarding roll number for a dormitory / session
    pair.

    Uses select_for_update() inside an atomic block to prevent duplicate
    numbers when multiple enrolments are created concurrently.

    Format: zero-padded 3 digits — 001, 002, 003, …

    Handles legacy prefixed numbers such as BRD-2026T1-115 by extracting the
    trailing digit group with a regex rather than calling .isdigit() on the
    full string.  This means the function works correctly on both old and new
    data without a migration.

    Args:
        dormitory (Dormitory):              Target dormitory.
        academic_session (AcademicSession): Target session.

    Returns:
        str: Next available roll number, e.g. '007'.
    """
    from boarding.models import BoardingEnrollment

    with transaction.atomic():
        last = (
            BoardingEnrollment.objects
            .select_for_update()
            .filter(
                dormitory=dormitory,
                academic_session=academic_session,
            )
            .exclude(boarding_roll_number='')
            .exclude(boarding_roll_number__isnull=True)
            .order_by('-boarding_roll_number')
            .first()
        )

        if last and last.boarding_roll_number:
            # FIX: extract trailing digits rather than testing the whole string
            # with .isdigit() — handles both "042" and "BRD-2026T1-115".
            match = re.search(r'(\d+)$', last.boarding_roll_number)
            next_number = int(match.group(1)) + 1 if match else 1
        else:
            next_number = 1

        return f"{next_number:03d}"


def reset_dormitory_roll_numbers(dormitory, academic_session):
    """
    Regenerate sequential roll numbers for all enrolments in a dormitory /
    session, ordered alphabetically by student surname then name.

    Useful after the legacy BRD-prefixed migration or whenever gaps need
    closing.

    Args:
        dormitory (Dormitory):           Target dormitory.
        academic_session (AcademicSession): Target session.

    Returns:
        int: Number of records updated.

    Note:
        Uses save(update_fields=['boarding_roll_number']) so the pre_save
        signal that auto-generates roll numbers does NOT fire — it only fires
        for new records (_state.adding == True).  This is intentional.
    """
    from boarding.models import BoardingEnrollment

    with transaction.atomic():
        enrollments = (
            BoardingEnrollment.objects
            .select_for_update()
            .filter(
                dormitory=dormitory,
                academic_session=academic_session,
            )
            .order_by('student__last_name', 'student__first_name')
        )

        count = 0
        for index, enrollment in enumerate(enrollments, start=1):
            enrollment.boarding_roll_number = f"{index:03d}"
            enrollment.save(update_fields=['boarding_roll_number'])
            count += 1

    logger.info(
        "Reset %d boarding roll numbers for %s — %s",
        count, dormitory.name, academic_session.name,
    )
    return count


# =============================================================================
# DORMITORY QUERY HELPERS
# =============================================================================

def get_available_dormitories(gender, session, boarding_type=None):
    """
    Return dormitories that can accommodate a student of the given gender and
    still have free beds for the given session.

    Args:
        gender (str):                    'M' or 'F'.
        session (AcademicSession):       The academic session.
        boarding_type (str | None):      Optional — not used to filter at the
                                         dormitory level (all boarding types can
                                         use any dormitory), but passed through
                                         for callers that may use it.

    Returns:
        QuerySet[Dormitory]: Active, available, non-condemned dormitories with
        spare capacity that are gender-compatible.
    """
    from boarding.models import Dormitory

    # current_occupancy is now a @property — use a subquery to filter at DB level.
    from django.db.models import OuterRef, Subquery, IntegerField
    from django.db.models.functions import Coalesce
    from boarding.models import BoardingEnrollment as _BE

    live_count = (
        _BE.objects
        .filter(dormitory=OuterRef('pk'), status='ACTIVE')
        .values('dormitory')
        .annotate(c=Count('pk'))
        .values('c')
    )

    qs = Dormitory.objects.filter(
        is_active=True,
        is_available_for_new_admissions=True,
    ).exclude(
        maintenance_status__in=('CONDEMNED', 'UNDER_MAINTENANCE'),
    ).annotate(
        live_occupancy=Coalesce(
            Subquery(live_count, output_field=IntegerField()), 0
        ),
    ).filter(
        live_occupancy__lt=F('total_capacity'),
    )

    if gender == 'M':
        qs = qs.filter(Q(dormitory_type='BOYS') | Q(dormitory_type='MIXED'))
    elif gender == 'F':
        qs = qs.filter(Q(dormitory_type='GIRLS') | Q(dormitory_type='MIXED'))

    return qs.order_by('dormitory_type', 'name')


def get_dormitories_by_gender(gender):
    """
    Return all active dormitories compatible with the given gender, regardless
    of capacity.

    Args:
        gender (str): 'M' or 'F'.

    Returns:
        QuerySet[Dormitory]
    """
    from boarding.models import Dormitory

    if gender == 'M':
        return Dormitory.objects.filter(
            Q(dormitory_type='BOYS') | Q(dormitory_type='MIXED'),
            is_active=True,
        )
    if gender == 'F':
        return Dormitory.objects.filter(
            Q(dormitory_type='GIRLS') | Q(dormitory_type='MIXED'),
            is_active=True,
        )
    return Dormitory.objects.none()


def _live_occupancy_subquery():
    """
    Subquery counting ACTIVE BoardingEnrollments per dormitory.
    Used in place of the old current_occupancy DB field (now a @property).
    """
    from django.db.models import OuterRef, Subquery, IntegerField
    from django.db.models.functions import Coalesce
    from boarding.models import BoardingEnrollment

    live = (
        BoardingEnrollment.objects
        .filter(dormitory=OuterRef('pk'), status='ACTIVE')
        .values('dormitory')
        .annotate(c=Count('pk'))
        .values('c')
    )
    return Coalesce(Subquery(live, output_field=IntegerField()), 0)


def get_dormitories_at_capacity():
    """
    Return active dormitories where live ACTIVE boarder count >= total_capacity.

    Uses a subquery annotation — current_occupancy is now a @property on
    Dormitory, not a DB column, so it cannot be used in ORM filters.

    Returns:
        QuerySet[Dormitory]
    """
    from boarding.models import Dormitory

    return (
        Dormitory.objects
        .filter(is_active=True)
        .annotate(live_occupancy=_live_occupancy_subquery())
        .filter(live_occupancy__gte=F('total_capacity'))
        .order_by('dormitory_type', 'name')
    )


def get_dormitories_with_low_occupancy(threshold_pct=50):
    """
    Return active dormitories whose occupancy percentage is below
    ``threshold_pct``.

    Uses a subquery annotation — current_occupancy is now a @property on
    Dormitory, not a DB column.

    Args:
        threshold_pct (int|float): Maximum occupancy percentage to include
                                   (default 50 %).

    Returns:
        QuerySet[Dormitory]: Annotated with ``occupancy_pct`` float field.
    """
    from boarding.models import Dormitory

    return (
        Dormitory.objects
        .filter(is_active=True, total_capacity__gt=0)
        .annotate(live_occupancy=_live_occupancy_subquery())
        .annotate(
            occupancy_pct=ExpressionWrapper(
                F('live_occupancy') * 100.0 / F('total_capacity'),
                output_field=FloatField(),
            )
        )
        .filter(occupancy_pct__lt=threshold_pct)
        .order_by('occupancy_pct')
    )


# =============================================================================
# BOARDING ENROLLMENT QUERY HELPERS
# =============================================================================

def get_active_boarders(session, dormitory=None):
    """
    Return ACTIVE boarding enrollments for a session, optionally filtered to a
    single dormitory.

    Args:
        session (AcademicSession): The academic session.
        dormitory (Dormitory | None): Optional dormitory filter.

    Returns:
        QuerySet[BoardingEnrollment]
    """
    from boarding.models import BoardingEnrollment

    qs = BoardingEnrollment.objects.filter(
        academic_session=session,
        status='ACTIVE',
    ).select_related('student', 'dormitory')

    if dormitory:
        qs = qs.filter(dormitory=dormitory)

    return qs


def get_boarding_enrollments_by_type(session, boarding_type):
    """
    Return ACTIVE boarding enrollments of a specific type for a session.

    Args:
        session (AcademicSession): The academic session.
        boarding_type (str):       One of BoardingEnrollment.BOARDING_TYPE_CHOICES.

    Returns:
        QuerySet[BoardingEnrollment]
    """
    from boarding.models import BoardingEnrollment

    return BoardingEnrollment.objects.filter(
        academic_session=session,
        boarding_type=boarding_type,
        status='ACTIVE',
    ).select_related('student', 'dormitory')


def get_pending_boarding_approvals(session=None):
    """
    Return PENDING boarding enrollments ordered by creation date (oldest first,
    so approvers tackle the queue in submission order).

    Args:
        session (AcademicSession | None): Optional session filter.

    Returns:
        QuerySet[BoardingEnrollment]
    """
    from boarding.models import BoardingEnrollment

    qs = BoardingEnrollment.objects.filter(
        status='PENDING',
    ).select_related('student', 'dormitory', 'academic_session')

    if session:
        qs = qs.filter(academic_session=session)

    return qs.order_by('created_at')


def get_expiring_boarding_enrollments(days=30, session=None):
    """
    Return ACTIVE enrollments whose effective_end_date falls within the next
    ``days`` days.

    Args:
        days (int):                     Look-ahead window in days (default 30).
        session (AcademicSession | None): Optional session filter.

    Returns:
        QuerySet[BoardingEnrollment]: Ordered by effective_end_date ascending.

    FIX: Uses get_school_today() instead of timezone.now().date().
    FIX: Field is effective_end_date, not expected_end_date.
    """
    from boarding.models import BoardingEnrollment

    today       = get_school_today()
    cutoff_date = today + timedelta(days=days)

    qs = BoardingEnrollment.objects.filter(
        status='ACTIVE',
        effective_end_date__isnull=False,
        effective_end_date__gte=today,
        effective_end_date__lte=cutoff_date,
    ).select_related('student', 'dormitory')

    if session:
        qs = qs.filter(academic_session=session)

    return qs.order_by('effective_end_date')


def get_students_without_boarding(session):
    """
    Return active students who have no PENDING or ACTIVE boarding enrollment
    for the given session.

    Args:
        session (AcademicSession): The academic session.

    Returns:
        QuerySet[Student]
    """
    from students.models import Student
    from boarding.models import BoardingEnrollment

    enrolled_ids = BoardingEnrollment.objects.filter(
        academic_session=session,
        status__in=('PENDING', 'ACTIVE'),
    ).values_list('student_id', flat=True)

    return Student.objects.filter(
        enrollment_status='ACTIVE',
    ).exclude(
        id__in=enrolled_ids,
    )


# =============================================================================
# DORMITORY RESIDENT HELPERS
# =============================================================================

def get_dormitory_resident_list(dormitory, session):
    """
    Return ACTIVE enrollments for a dormitory / session, ordered by roll number
    then student surname — the natural order for printed registers.

    Automatically filters by student gender when the dormitory type is BOYS or
    GIRLS so that only gender-compatible students appear.

    Args:
        dormitory (Dormitory):           The dormitory.
        session (AcademicSession):       The academic session.

    Returns:
        QuerySet[BoardingEnrollment]
    """
    from boarding.models import BoardingEnrollment

    qs = BoardingEnrollment.objects.filter(
        dormitory=dormitory,
        academic_session=session,
        status='ACTIVE',
    ).select_related(
        'student',
        'student__current_academic_level',
        'boarding_invoice',
    ).order_by('boarding_roll_number', 'student__last_name')

    # Enforce gender consistency for single-gender dormitories.
    if dormitory.dormitory_type == 'BOYS':
        qs = qs.filter(student__gender='M')
    elif dormitory.dormitory_type == 'GIRLS':
        qs = qs.filter(student__gender='F')

    return qs


def get_dormitory_residents_by_class(dormitory, session):
    """
    Return a dict mapping academic-level name → list of enrollment records for
    a dormitory / session.

    Args:
        dormitory (Dormitory):     The dormitory.
        session (AcademicSession): The academic session.

    Returns:
        dict[str, list[BoardingEnrollment]]
    """
    residents = get_dormitory_resident_list(dormitory, session)

    grouped = {}
    for enrollment in residents:
        level = enrollment.student.current_academic_level
        key   = str(level) if level else 'Unassigned'
        grouped.setdefault(key, []).append(enrollment)

    return grouped


# =============================================================================
# FINANCIAL SUMMARY HELPERS
# =============================================================================

def get_boarding_fee_summary(enrollment):
    """
    Return a summary of the financial state for a single boarding enrollment.

    Does not calculate fees — reads from the linked FeeInvoice if one exists.

    Args:
        enrollment (BoardingEnrollment): The enrollment.

    Returns:
        dict: Keys: has_invoice, invoice_number, total_amount, paid_amount,
              balance, status, is_paid, is_overdue.
    """
    invoice = enrollment.boarding_invoice

    if not invoice:
        return {
            'has_invoice':  False,
            'total_amount': Decimal('0.00'),
            'paid_amount':  Decimal('0.00'),
            'balance':      Decimal('0.00'),
        }

    return {
        'has_invoice':      True,
        'invoice_number':   invoice.invoice_number,
        'total_amount':     invoice.total_amount,
        'paid_amount':      invoice.paid_amount,
        'balance':          invoice.balance,
        'status':           invoice.status,
        'is_paid':          invoice.status == 'PAID',
        'is_overdue':       invoice.is_overdue,
    }


def get_dormitory_financial_summary(dormitory, session):
    """
    Return aggregate invoice totals for all ACTIVE enrollments in a dormitory
    / session.

    Args:
        dormitory (Dormitory):           The dormitory.
        session (AcademicSession):       The academic session.

    Returns:
        dict: Keys: total_enrollments, total_invoiced, total_paid,
              total_balance, paid_count, pending_count, collection_rate.
    """
    from boarding.models import BoardingEnrollment

    enrollments = BoardingEnrollment.objects.filter(
        dormitory=dormitory,
        academic_session=session,
        status='ACTIVE',
    )

    invoice_agg = enrollments.filter(
        boarding_invoice__isnull=False,
    ).aggregate(
        total_invoiced=Sum('boarding_invoice__total_amount'),
        total_paid=Sum('boarding_invoice__paid_amount'),
        total_balance=Sum('boarding_invoice__balance'),
    )

    total_invoiced = invoice_agg['total_invoiced'] or Decimal('0.00')
    total_paid     = invoice_agg['total_paid']     or Decimal('0.00')
    total_balance  = invoice_agg['total_balance']  or Decimal('0.00')

    paid_count = enrollments.filter(
        boarding_invoice__status='PAID',
    ).count()

    pending_count = enrollments.filter(
        Q(boarding_invoice__status='PENDING') |
        Q(boarding_invoice__status='PARTIALLY_PAID'),
    ).count()

    collection_rate = (
        round(float(total_paid) / float(total_invoiced) * 100, 1)
        if total_invoiced
        else 0.0
    )

    return {
        'total_enrollments': enrollments.count(),
        'total_invoiced':    total_invoiced,
        'total_paid':        total_paid,
        'total_balance':     total_balance,
        'paid_count':        paid_count,
        'pending_count':     pending_count,
        'collection_rate':   collection_rate,
    }


# =============================================================================
# PURE VALIDATION HELPERS
# =============================================================================

VALID_BOARDING_DAYS = (
    'Monday', 'Tuesday', 'Wednesday', 'Thursday',
    'Friday', 'Saturday', 'Sunday',
)


def validate_boarding_days(boarding_days):
    """
    Validate the boarding_days value for a FLEXI_BOARDER enrollment.

    Args:
        boarding_days: Value to validate (expected: non-empty list of day names).

    Returns:
        tuple(bool, str | None): (is_valid, error_message).  error_message is
        None when valid.
    """
    if not isinstance(boarding_days, list):
        return False, "Boarding days must be a list"

    if len(boarding_days) == 0:
        return False, "At least one boarding day must be specified"

    invalid = [d for d in boarding_days if d not in VALID_BOARDING_DAYS]
    if invalid:
        return (
            False,
            f"Invalid day(s): {', '.join(invalid)}. "
            f"Must be one of: {', '.join(VALID_BOARDING_DAYS)}",
        )

    return True, None


def validate_room_assignment(dormitory, room_number, bed_number):
    """
    Basic validation of a room / bed assignment string.

    Extend this function when a dedicated Room model is introduced.

    Args:
        dormitory (Dormitory): The dormitory.
        room_number (str):     Room identifier.
        bed_number (str):      Bed identifier.

    Returns:
        tuple(bool, str | None): (is_valid, error_message).
    """
    if not room_number or not room_number.strip():
        return False, "Room number is required"

    if len(room_number) > 20:
        return False, "Room number cannot exceed 20 characters"

    if bed_number and len(bed_number) > 20:
        return False, "Bed number cannot exceed 20 characters"

    return True, None