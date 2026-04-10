# boarding/modal_views.py

"""
GET-only modal trigger functions for the boarding app.

CONTRACT: every function in this file MUST:
  • accept only GET requests  (no POST handling, no form.save())
  • load a form (blank or pre-filled from an existing instance)
    OR load an object for confirmation / quick-view templates
  • return render(request, '<template>', context)

All create / update / delete logic lives in views.py.
Modal templates point their hx-post attributes at views.py URLs.

CHANGES FROM ORIGINAL
---------------------
CONTRACT VIOLATIONS FIXED:
  - dormitory_form_modal: removed POST handling — form submit goes to
    dormitory_create / dormitory_edit in views.py
  - boarding_enrollment_terminate_modal: removed POST handling — form submit
    goes to boarding_enrollment_terminate in views.py
  - bulk_enrollment_confirm_modal: removed POST handling — confirm submit
    goes to bulk_enrollment_step2 in views.py

IMPORT:
  - Removed BoardingApprovalForm (deleted from forms.py; approval is a
    plain confirmation modal with no form fields)
  - Added explicit format_money import (used in delete modal)

boarding_enrollment_approve_modal:
  - Simplified: can_accommodate() already checks is_active and capacity,
    so the separate is_active / available_capacity checks were redundant.
    Now: check enrollment.status first, then call can_accommodate() once.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.db.models import Count, Q

from core.utils import format_money

from .models import Dormitory, BoardingEnrollment
from .forms import (
    DormitoryForm,
    BoardingEnrollmentForm,
    BoardingTerminationForm,
    BulkBoardingEnrollmentConfirmationForm,
)


# =============================================================================
# DORMITORY MODALS
# =============================================================================

@login_required
def dormitory_form_modal(request, pk=None):
    """
    Unified create / edit modal for a dormitory.

    GET /dormitories/add/modal/        → blank form (create)
    GET /dormitories/<pk>/edit/modal/  → pre-filled form (edit)

    The template posts to dormitory_create or dormitory_edit in views.py.

    FIX: removed if request.method == 'POST' block — modal views are GET-only.
    """
    dormitory = get_object_or_404(Dormitory, pk=pk) if pk else None
    form      = DormitoryForm(instance=dormitory)

    return render(request, 'boarding/dormitories/modals/dormitory_form.html', {
        'form':      form,
        'dormitory': dormitory,
    })


@login_required
def dormitory_delete_modal(request, pk):
    """Confirmation modal before deleting a dormitory."""
    dormitory = get_object_or_404(Dormitory, pk=pk)

    enrollment_count  = dormitory.boarding_enrollments.count()
    active_enrollments = dormitory.boarding_enrollments.filter(status='ACTIVE').count()

    return render(request, 'boarding/dormitories/modals/delete_dormitory.html', {
        'dormitory':         dormitory,
        'has_enrollments':   enrollment_count > 0,
        'enrollment_count':  enrollment_count,
        'active_enrollments': active_enrollments,
    })


@login_required
def dormitory_activate_modal(request, pk):
    """Confirmation modal before activating a dormitory."""
    dormitory = get_object_or_404(Dormitory, pk=pk)
    return render(request, 'boarding/dormitories/modals/activate_dormitory.html', {
        'dormitory': dormitory,
    })


@login_required
def dormitory_deactivate_modal(request, pk):
    """Confirmation modal before deactivating a dormitory."""
    dormitory          = get_object_or_404(Dormitory, pk=pk)
    active_enrollments = dormitory.boarding_enrollments.filter(status='ACTIVE').count()

    return render(request, 'boarding/dormitories/modals/deactivate_dormitory.html', {
        'dormitory':          dormitory,
        'active_enrollments': active_enrollments,
    })


@login_required
def dormitory_capacity_check_modal(request, pk):
    """
    Capacity overview modal for a single dormitory.
    Uses model methods — no duplicated calculation logic here.
    """
    dormitory = get_object_or_404(Dormitory, pk=pk)

    return render(request, 'boarding/dormitories/modals/capacity_check.html', {
        'dormitory':            dormitory,
        'occupancy_percentage': dormitory.get_occupancy_percentage(),
        'available_capacity':   dormitory.get_available_capacity(),
        'occupancy_level':      dormitory.get_occupancy_level(),
        'occupancy_color':      dormitory.get_occupancy_color(),
    })


@login_required
def dormitory_maintenance_schedule_modal(request, pk):
    """Maintenance schedule overview modal for a dormitory."""
    dormitory = get_object_or_404(Dormitory, pk=pk)
    return render(
        request,
        'boarding/dormitories/modals/maintenance_schedule.html',
        {'dormitory': dormitory},
    )


@login_required
def dormitory_update_maintenance_modal(request, pk):
    """Modal to update dormitory maintenance status and dates."""
    dormitory = get_object_or_404(Dormitory, pk=pk)
    return render(
        request,
        'boarding/dormitories/modals/update_maintenance.html',
        {'dormitory': dormitory},
    )


# =============================================================================
# BOARDING ENROLLMENT MODALS
# =============================================================================

# ── Add this to boarding/modal_views.py ──────────────────────────────────────

@login_required
def boarding_enrollment_create_modal(request, dormitory_pk):
    """
    Create enrollment modal pre-filled with the dormitory (and optionally
    the session) from the dormitory detail page.

    GET /dormitories/<dormitory_pk>/modal/enroll/?session_id=<uuid>
    """
    from academics.models import AcademicSession

    dormitory = get_object_or_404(Dormitory, pk=dormitory_pk)

    session_id = request.GET.get('session_id')
    session    = None
    if session_id:
        from academics.models import AcademicSession
        try:
            session = AcademicSession.objects.get(pk=session_id)
        except AcademicSession.DoesNotExist:
            pass

    # Pre-fill dormitory and session; student is chosen in the modal.
    initial = {
        'dormitory':       dormitory,
        'auto_create_invoice': True,
    }
    if session:
        initial['academic_session'] = session

    form = BoardingEnrollmentForm(initial=initial)

    return render(
        request,
        'boarding/enrollments/modals/enrollment_create.html',
        {
            'form':      form,
            'dormitory': dormitory,
            'session':   session,
        },
    )


@login_required
def boarding_enrollment_delete_modal(request, pk):
    """
    Deletion confirmation modal for a boarding enrollment.

    Mirrors the logic in the pre_delete signal so the user sees exactly what
    will happen before they confirm.  If the invoice cannot be safely removed,
    can_delete is False and the template shows the blocking reason.

    If deletion is safe, deletion_impact shows what will be cleaned up
    (boarding items removed from a DRAFT/VOID invoice, etc.) so there are
    no surprises.
    """
    enrollment = get_object_or_404(
        BoardingEnrollment.objects.select_related(
            'student', 'class_instance', 'academic_invoice',
            'boarding_invoice',
        ),
        pk=pk,
    )

    can_delete     = True
    warnings       = []
    deletion_impact = None
    invoice        = enrollment.boarding_invoice

    if invoice:
        # 1. Journal entry status (highest priority)
        if invoice.journal_entry:
            je_status = invoice.journal_entry.status
            if je_status == 'POSTED':
                can_delete = False
                warnings.append(
                    f"Journal entry {invoice.journal_entry.entry_number} "
                    f"is already posted"
                )
            elif je_status == 'REVERSED':
                can_delete = False
                warnings.append(
                    f"Journal entry {invoice.journal_entry.entry_number} "
                    f"has been reversed"
                )
            # DRAFT journal entries do not block deletion.

        # 2. Invoice status
        if can_delete and invoice.status not in ('DRAFT', 'VOID'):
            can_delete = False
            warnings.append(
                f"Invoice status is {invoice.get_status_display()} — "
                f"only DRAFT or VOID invoices can be removed with the enrollment"
            )

        # 3. Payments received
        if can_delete and invoice.paid_amount > 0:
            can_delete = False
            warnings.append(
                f"Invoice has received payments of "
                f"{format_money(invoice.paid_amount)}"
            )

        # 4. Compute what will be cleaned up for safe deletions
        if can_delete:
            boarding_items = invoice.items.filter(
                fee_category__category_type__in=('BOARDING', 'LAUNDRY')
            )
            if boarding_items.exists():
                boarding_total = sum(i.final_amount for i in boarding_items)
                deletion_impact = {
                    'will_remove_items': True,
                    'items_count':       boarding_items.count(),
                    'boarding_amount':   boarding_total,
                    'invoice_number':    invoice.invoice_number,
                    'new_total':         invoice.total_amount - boarding_total,
                    'is_void':           invoice.status == 'VOID',
                }

    return render(
        request,
        'boarding/enrollments/modals/delete_enrollment.html',
        {
            'enrollment':    enrollment,
            'can_delete':    can_delete,
            'warnings':      warnings,
            'deletion_impact': deletion_impact,
        },
    )


@login_required
def boarding_enrollment_approve_modal(request, pk):
    """
    Approval confirmation modal for a PENDING boarding enrollment.

    FIX: simplified the can_approve check.  Previously it checked
    enrollment.status, dormitory.is_active, and dormitory.available_capacity
    separately — then called can_accommodate() which repeats those same checks.
    Now: status is checked independently (it's the only non-dormitory gate),
    then can_accommodate() is called once for all dormitory-level checks.
    """
    enrollment = get_object_or_404(
        BoardingEnrollment.objects.select_related('student', 'dormitory'),
        pk=pk,
    )
    dormitory = enrollment.dormitory

    if enrollment.status != 'PENDING':
        can_approve = False
        reason      = (
            f"Enrollment status is '{enrollment.get_status_display()}' — "
            f"only Pending enrollments can be approved"
        )
    else:
        can_approve, reason = dormitory.can_accommodate(enrollment.student)

    return render(
        request,
        'boarding/enrollments/modals/approve_enrollment.html',
        {
            'enrollment':   enrollment,
            'can_approve':  can_approve,
            'reason':       None if can_approve else reason,
        },
    )


@login_required
def boarding_enrollment_terminate_modal(request, pk):
    """
    Termination form modal for a boarding enrollment.

    FIX: removed POST handling — the template posts to
    boarding_enrollment_terminate in views.py.
    """
    enrollment = get_object_or_404(BoardingEnrollment, pk=pk)
    can_terminate = enrollment.status in ('PENDING', 'ACTIVE')
    form          = BoardingTerminationForm()

    return render(
        request,
        'boarding/enrollments/modals/terminate_enrollment.html',
        {
            'enrollment':   enrollment,
            'form':         form,
            'can_terminate': can_terminate,
        },
    )


@login_required
def boarding_enrollment_suspend_modal(request, pk):
    """Suspension confirmation modal with reason input."""
    enrollment  = get_object_or_404(BoardingEnrollment, pk=pk)
    can_suspend = enrollment.status == 'ACTIVE'

    return render(
        request,
        'boarding/enrollments/modals/suspend_enrollment.html',
        {
            'enrollment': enrollment,
            'can_suspend': can_suspend,
        },
    )


@login_required
def boarding_enrollment_detail_modal(request, pk):
    enrollment = get_object_or_404(BoardingEnrollment, pk=pk)

    # approved_by is a FK to UserProfile on the default DB.
    # Django cannot follow cross-database FKs automatically, so we
    # resolve the display name manually here.
    approver_name = None
    if enrollment.approved_by_id:
        try:
            from accounts.models import UserProfile
            profile = UserProfile.objects.using('default').get(pk=enrollment.approved_by_id)
            approver_name = profile.user.get_full_name() or profile.user.username
        except Exception:
            approver_name = str(enrollment.approved_by_id)

    return render(
        request,
        'boarding/enrollments/modals/enrollment_detail.html',
        {
            'enrollment':    enrollment,
            'approver_name': approver_name,
        },
    )


@login_required
def boarding_enrollment_edit_modal(request, pk):
    """Edit form modal for an existing boarding enrollment."""
    enrollment = get_object_or_404(
        BoardingEnrollment.objects.select_related(
            'student',
            'academic_session',
            'dormitory',
            'boarding_invoice',
        ),
        pk=pk,
    )
    form = BoardingEnrollmentForm(instance=enrollment)

    return render(
        request,
        'boarding/enrollments/modals/enrollment_edit.html',
        {
            'form':       form,
            'enrollment': enrollment,
        },
    )


@login_required
def boarding_enrollment_assign_room_modal(request, pk):
    """Room and bed assignment modal."""
    enrollment = get_object_or_404(BoardingEnrollment, pk=pk)
    return render(
        request,
        'boarding/enrollments/modals/assign_room.html',
        {'enrollment': enrollment},
    )


@login_required
def boarding_enrollment_update_consent_modal(request, pk):
    """Guardian consent update modal."""
    enrollment = get_object_or_404(BoardingEnrollment, pk=pk)
    return render(
        request,
        'boarding/enrollments/modals/update_consent.html',
        {'enrollment': enrollment},
    )


@login_required
def boarding_enrollment_change_dormitory_modal(request, pk):
    """
    Dormitory transfer modal.

    Only shows dormitories that can actually accommodate the student
    (capacity, gender, active, available).  Uses can_accommodate() on each
    dormitory so all checks are in one place.
    """
    enrollment = get_object_or_404(
        BoardingEnrollment.objects.select_related('student', 'dormitory'),
        pk=pk,
    )

    available_dormitories = []
    for dormitory in Dormitory.objects.filter(
        is_active=True,
        is_available_for_new_admissions=True,
    ).exclude(pk=enrollment.dormitory_id):
        can, _ = dormitory.can_accommodate(enrollment.student)
        if can:
            available_dormitories.append(dormitory)

    return render(
        request,
        'boarding/enrollments/modals/change_dormitory.html',
        {
            'enrollment':           enrollment,
            'available_dormitories': available_dormitories,
        },
    )


@login_required
def boarding_enrollment_update_boarding_type_modal(request, pk):
    """Boarding type change modal."""
    enrollment = get_object_or_404(BoardingEnrollment, pk=pk)
    return render(
        request,
        'boarding/enrollments/modals/update_boarding_type.html',
        {'enrollment': enrollment},
    )


@login_required
def boarding_enrollment_add_note_modal(request, pk):
    """Add administrative note modal."""
    enrollment = get_object_or_404(BoardingEnrollment, pk=pk)
    return render(
        request,
        'boarding/enrollments/modals/add_note.html',
        {'enrollment': enrollment},
    )


# =============================================================================
# CAPACITY PLANNING MODALS
# =============================================================================

@login_required
def student_boarding_eligibility_modal(request, student_id):
    """
    Shows which dormitories can accommodate a specific student.

    Uses can_accommodate() on each dormitory so all checks (gender, capacity,
    active state, maintenance) are evaluated in one place.
    """
    from students.models import Student

    student              = get_object_or_404(Student, pk=student_id)
    compatible_dormitories   = []
    incompatible_dormitories = []

    for dormitory in Dormitory.objects.filter(
        is_active=True,
        is_available_for_new_admissions=True,
    ).order_by('dormitory_type', 'name'):
        can, reason = dormitory.can_accommodate(student)
        if can:
            compatible_dormitories.append(dormitory)
        else:
            incompatible_dormitories.append({
                'dormitory': dormitory,
                'reason':    reason,
            })

    return render(
        request,
        'boarding/enrollments/modals/boarding_eligibility.html',
        {
            'student':                  student,
            'compatible_dormitories':   compatible_dormitories,
            'incompatible_dormitories': incompatible_dormitories,
        },
    )


# =============================================================================
# BULK ENROLLMENT MODALS
# =============================================================================

@login_required
def bulk_enrollment_preview_modal(request):
    """
    Preview modal showing selected students before proceeding to step 2.
    """
    from students.models import Student

    student_ids = request.GET.get('student_ids', '')
    if not student_ids:
        return render(
            request,
            'boarding/bulk_enrollment/modals/preview.html',
            {'error_message': 'No students selected'},
        )

    ids      = [i.strip() for i in student_ids.split(',') if i.strip()]
    students = Student.objects.filter(
        id__in=ids,
    ).select_related('current_academic_level')

    return render(
        request,
        'boarding/bulk_enrollment/modals/preview.html',
        {
            'students':      students,
            'student_count': len(ids),
        },
    )


@login_required
def bulk_enrollment_confirm_modal(request):
    """
    Bulk enrollment configuration modal (step 2 preview).

    Loads a blank BulkBoardingEnrollmentConfirmationForm pre-populated with
    the student IDs from step 1.  The template posts to bulk_enrollment_step2
    in views.py.

    FIX: removed POST handling — modal views are GET-only.
    """
    student_ids   = request.GET.get('student_ids', '')
    ids           = [i.strip() for i in student_ids.split(',') if i.strip()]
    student_count = len(ids)

    form = BulkBoardingEnrollmentConfirmationForm(
        initial={'selected_student_ids': student_ids},
        student_count=student_count,
    )

    return render(
        request,
        'boarding/bulk_enrollment/modals/confirm.html',
        {
            'form':          form,
            'student_count': student_count,
        },
    )


# =============================================================================
# REPORT MODALS
# =============================================================================

@login_required
def dormitory_occupancy_report_modal(request):
    """Occupancy report modal showing all dormitories with their fill rates."""
    dormitories = Dormitory.objects.filter(is_active=True).annotate(
        active_enrollment_count=Count(
            'boarding_enrollments',
            filter=Q(boarding_enrollments__status='ACTIVE'),
        )
    ).order_by('dormitory_type', 'name')

    return render(
        request,
        'boarding/reports/modals/occupancy_report.html',
        {'dormitories': dormitories},
    )


@login_required
def boarding_statistics_modal(request):
    """High-level boarding statistics modal for the dashboard."""
    from .stats import get_boarding_statistics, get_dormitory_statistics

    return render(
        request,
        'boarding/reports/modals/statistics.html',
        {
            'general_stats':   get_boarding_statistics(),
            'dormitory_stats': get_dormitory_statistics(),
        },
    )