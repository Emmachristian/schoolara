# boarding/modal_views.py

"""
Modal Views for Boarding Management

These views return HTML fragments for modals loaded via HTMX.
Each modal view is paired with an action view in views.py that handles the POST request.

Pattern:
1. GET request → modal_views.py (loads modal HTML)
2. POST request → views.py (processes action, returns response with headers)

Following the same pattern as savings/modal_views.py with unified modals for create/edit
"""

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from core.utils import format_money
from django.db.models import Q, Count

from .models import Dormitory, BoardingEnrollment
from .forms import (
    DormitoryForm,
    BoardingEnrollmentForm,
    BoardingApprovalForm,
    BoardingTerminationForm,
)


# =============================================================================
# DORMITORY MODALS
# =============================================================================

@login_required
def dormitory_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    dormitory = get_object_or_404(Dormitory, pk=pk)
    
    # Check if dormitory has enrollments
    has_enrollments = dormitory.boarding_enrollments.exists()
    enrollment_count = dormitory.boarding_enrollments.count()
    active_enrollments = dormitory.boarding_enrollments.filter(status='ACTIVE').count()
    
    return render(request, 'boarding/dormitories/modals/delete_dormitory.html', {
        'dormitory': dormitory,
        'has_enrollments': has_enrollments,
        'enrollment_count': enrollment_count,
        'active_enrollments': active_enrollments,
    })


@login_required
def dormitory_activate_modal(request, pk):
    """Return activation confirmation modal content via HTMX"""
    dormitory = get_object_or_404(Dormitory, pk=pk)
    
    return render(request, 'boarding/dormitories/modals/activate_dormitory.html', {
        'dormitory': dormitory
    })


@login_required
def dormitory_deactivate_modal(request, pk):
    """Return deactivation confirmation modal content via HTMX"""
    dormitory = get_object_or_404(Dormitory, pk=pk)
    
    # Get active enrollment count
    active_enrollments = dormitory.boarding_enrollments.filter(status='ACTIVE').count()
    
    return render(request, 'boarding/dormitories/modals/deactivate_dormitory.html', {
        'dormitory': dormitory,
        'active_enrollments': active_enrollments,
    })


@login_required
def dormitory_form_modal(request, pk=None):
    """
    Unified modal for creating or editing dormitory
    - pk: Optional, if provided it's edit mode
    
    Pattern matches savings module:
    - /dormitories/add/ → Create
    - /dormitories/<pk>/edit/ → Edit
    """
    dormitory = get_object_or_404(Dormitory, pk=pk) if pk else None
    
    if request.method == 'POST':
        form = DormitoryForm(request.POST, instance=dormitory)
    else:
        form = DormitoryForm(instance=dormitory)
    
    return render(request, 'boarding/dormitories/modals/dormitory_form.html', {
        'form': form,
        'dormitory': dormitory,
    })


# =============================================================================
# BOARDING ENROLLMENT MODALS
# =============================================================================

@login_required
def boarding_enrollment_delete_modal(request, pk):
    """
    Return delete confirmation modal for boarding enrollment.
    Properly handles DRAFT/POSTED/REVERSED/VOID journal entries.
    """
    enrollment = get_object_or_404(BoardingEnrollment, pk=pk)

    can_delete = True
    warnings = []
    deletion_impact = None

    invoice = enrollment.boarding_invoice

    if invoice:
        # PRIMARY CHECK: Journal Entry Status (highest priority)
        if invoice.journal_entry:
            je_status = invoice.journal_entry.status
            
            if je_status == 'POSTED':
                can_delete = False
                warnings.append(
                    f"Journal entry {invoice.journal_entry.entry_number} already posted"
                )
            elif je_status == 'REVERSED':
                can_delete = False
                warnings.append(
                    f"Journal entry {invoice.journal_entry.entry_number} has been reversed"
                )
            # DRAFT journal entries are fine - don't block deletion

        # SECONDARY CHECK: Invoice Status
        # Allow deletion for DRAFT and VOID invoices
        if invoice.status not in ['DRAFT', 'VOID'] and can_delete:
            can_delete = False
            warnings.append(f"Invoice status is {invoice.get_status_display()}")

        # TERTIARY CHECK: Payments
        if invoice.paid_amount > 0 and can_delete:
            can_delete = False
            warnings.append(f"Invoice has payments of {format_money(invoice.paid_amount)}")

        # CALCULATE DELETION IMPACT (only for deletable invoices)
        if can_delete:
            boarding_items = invoice.items.filter(
                fee_category__category_type__in=['BOARDING', 'LAUNDRY']
            )
            
            if boarding_items.exists():
                boarding_total = sum(item.final_amount for item in boarding_items)
                deletion_impact = {
                    'will_remove_items': True,
                    'items_count': boarding_items.count(),
                    'boarding_amount': boarding_total,
                    'invoice_number': invoice.invoice_number,
                    'new_total': invoice.total_amount - boarding_total,
                    'is_void': invoice.status == 'VOID',  # Flag for template
                }

    # ENROLLMENT-SPECIFIC WARNING (informational, doesn't block)
    if enrollment.status == 'ACTIVE' and can_delete:
        # This is just a suggestion, not a blocker
        pass  # You can add an info message to deletion_impact if needed

    return render(request, 'boarding/enrollments/modals/delete_enrollment.html', {
        'enrollment': enrollment,
        'can_delete': can_delete,
        'warnings': warnings,
        'deletion_impact': deletion_impact,
    })

@login_required
def boarding_enrollment_approve_modal(request, pk):
    """Return enrollment approval modal via HTMX"""
    enrollment = get_object_or_404(BoardingEnrollment, pk=pk)
    
    # Check if enrollment can be approved
    dormitory = enrollment.dormitory
    can_approve = (
        enrollment.status == 'PENDING' and
        dormitory.is_active and
        dormitory.available_capacity > 0  # ✅ FIXED: Use property, not method
    )
    
    # Check gender compatibility
    can_accommodate, message = dormitory.can_accommodate(enrollment.student)
    
    return render(request, 'boarding/enrollments/modals/approve_enrollment.html', {
        'enrollment': enrollment,
        'can_approve': can_approve and can_accommodate,
        'message': None if can_accommodate else message,
    })


@login_required
def boarding_enrollment_terminate_modal(request, pk):
    """Return enrollment termination modal with form via HTMX"""
    enrollment = get_object_or_404(BoardingEnrollment, pk=pk)
    
    # Check if enrollment can be terminated
    can_terminate = enrollment.status in ['PENDING', 'ACTIVE']
    
    if request.method == 'POST':
        form = BoardingTerminationForm(request.POST)
    else:
        form = BoardingTerminationForm()
    
    return render(request, 'boarding/enrollments/modals/terminate_enrollment.html', {
        'enrollment': enrollment,
        'form': form,
        'can_terminate': can_terminate,
    })


@login_required
def boarding_enrollment_suspend_modal(request, pk):
    """Return enrollment suspension modal with reason input via HTMX"""
    enrollment = get_object_or_404(BoardingEnrollment, pk=pk)
    
    # Check if enrollment can be suspended
    can_suspend = enrollment.status == 'ACTIVE'
    
    return render(request, 'boarding/enrollments/modals/suspend_enrollment.html', {
        'enrollment': enrollment,
        'can_suspend': can_suspend,
    })

@login_required
def boarding_enrollment_detail_modal(request, pk):
    """Return enrollment details modal via HTMX"""
    enrollment = get_object_or_404(
        BoardingEnrollment.objects.select_related(
            'student',
            'academic_session',
            'dormitory',
            'consenting_guardian',
            'approved_by',
            'boarding_invoice'
        ),
        pk=pk
    )
    
    return render(request, 'boarding/enrollments/modals/enrollment_detail.html', {
        'enrollment': enrollment
    })


@login_required
def boarding_enrollment_assign_room_modal(request, pk):
    """Return room/bed assignment modal via HTMX"""
    enrollment = get_object_or_404(BoardingEnrollment, pk=pk)
    
    return render(request, 'boarding/enrollments/modals/assign_room.html', {
        'enrollment': enrollment
    })


@login_required
def boarding_enrollment_update_consent_modal(request, pk):
    """Return guardian consent update modal via HTMX"""
    enrollment = get_object_or_404(BoardingEnrollment, pk=pk)
    
    return render(request, 'boarding/enrollments/modals/update_consent.html', {
        'enrollment': enrollment
    })


@login_required
def boarding_enrollment_change_dormitory_modal(request, pk):
    """Return change dormitory modal via HTMX"""
    enrollment = get_object_or_404(BoardingEnrollment, pk=pk)
    
    # Get available dormitories that can accommodate the student
    from .models import Dormitory
    available_dormitories = []
    
    for dormitory in Dormitory.objects.filter(is_active=True, is_available_for_new_admissions=True):
        can_accommodate, message = dormitory.can_accommodate(enrollment.student)
        if can_accommodate and dormitory.id != enrollment.dormitory_id:
            available_dormitories.append(dormitory)
    
    return render(request, 'boarding/enrollments/modals/change_dormitory.html', {
        'enrollment': enrollment,
        'available_dormitories': available_dormitories,
    })


@login_required
def boarding_enrollment_update_boarding_type_modal(request, pk):
    """Return boarding type update modal via HTMX"""
    enrollment = get_object_or_404(BoardingEnrollment, pk=pk)
    
    return render(request, 'boarding/enrollments/modals/update_boarding_type.html', {
        'enrollment': enrollment
    })


@login_required
def boarding_enrollment_add_note_modal(request, pk):
    """Return add note modal via HTMX"""
    enrollment = get_object_or_404(BoardingEnrollment, pk=pk)
    
    return render(request, 'boarding/enrollments/modals/add_note.html', {
        'enrollment': enrollment
    })


# =============================================================================
# BULK ENROLLMENT MODALS
# =============================================================================

@login_required
def bulk_enrollment_preview_modal(request):
    """Return bulk enrollment preview modal via HTMX"""
    # Get student IDs from request
    student_ids = request.GET.get('student_ids', '')
    
    if not student_ids:
        return render(request, 'boarding/bulk_enrollment/modals/preview.html', {
            'error_message': 'No students selected',
        })
    
    # Parse student IDs
    from students.models import Student
    ids = [id.strip() for id in student_ids.split(',') if id.strip()]
    students = Student.objects.filter(id__in=ids).select_related('current_academic_level')
    
    return render(request, 'boarding/bulk_enrollment/modals/preview.html', {
        'students': students,
        'student_count': len(ids),
    })


@login_required
def bulk_enrollment_confirm_modal(request):
    """Return bulk enrollment confirmation modal via HTMX"""
    from .forms import BulkBoardingEnrollmentConfirmationForm
    
    # Get student IDs from request
    student_ids = request.GET.get('student_ids', '')
    student_count = len([id for id in student_ids.split(',') if id.strip()]) if student_ids else 0
    
    if request.method == 'POST':
        form = BulkBoardingEnrollmentConfirmationForm(request.POST, student_count=student_count)
    else:
        initial = {'selected_student_ids': student_ids}
        form = BulkBoardingEnrollmentConfirmationForm(initial=initial, student_count=student_count)
    
    return render(request, 'boarding/bulk_enrollment/modals/confirm.html', {
        'form': form,
        'student_count': student_count,
    })


# =============================================================================
# REPORT MODALS
# =============================================================================

@login_required
def dormitory_occupancy_report_modal(request):
    """Return dormitory occupancy report modal via HTMX"""
    from .models import Dormitory
    
    dormitories = Dormitory.objects.filter(is_active=True).annotate(
        active_enrollment_count=Count(
            'boarding_enrollments',
            filter=Q(boarding_enrollments__status='ACTIVE')
        )
    ).order_by('dormitory_type', 'name')
    
    return render(request, 'boarding/reports/modals/occupancy_report.html', {
        'dormitories': dormitories
    })


@login_required
def boarding_statistics_modal(request):
    """Return boarding statistics modal via HTMX"""
    from django.db.models import Count, Q
    from .models import Dormitory, BoardingEnrollment
    
    # Get comprehensive statistics
    stats = {
        'dormitories': Dormitory.objects.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(is_active=True)),
            boys=Count('id', filter=Q(dormitory_type='BOYS')),
            girls=Count('id', filter=Q(dormitory_type='GIRLS')),
        ),
        'enrollments': BoardingEnrollment.objects.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status='ACTIVE')),
            pending=Count('id', filter=Q(status='PENDING')),
            full_boarders=Count('id', filter=Q(boarding_type='FULL_BOARDER', status='ACTIVE')),
            weekly_boarders=Count('id', filter=Q(boarding_type='WEEKLY_BOARDER', status='ACTIVE')),
        ),
    }
    
    return render(request, 'boarding/reports/modals/statistics.html', {
        'stats': stats
    })


# =============================================================================
# CAPACITY PLANNING MODALS
# =============================================================================

@login_required
def dormitory_capacity_check_modal(request, pk):
    """Return dormitory capacity check modal via HTMX"""
    dormitory = get_object_or_404(Dormitory, pk=pk)
    
    # Calculate capacity metrics
    occupancy_percentage = dormitory.get_occupancy_percentage()
    available_capacity = dormitory.get_available_capacity()
    occupancy_level = dormitory.get_occupancy_level()
    
    return render(request, 'boarding/dormitories/modals/capacity_check.html', {
        'dormitory': dormitory,
        'occupancy_percentage': occupancy_percentage,
        'available_capacity': available_capacity,
        'occupancy_level': occupancy_level,
    })


@login_required
def student_boarding_eligibility_modal(request, student_id):
    """Return student boarding eligibility check modal via HTMX"""
    from students.models import Student
    from .models import Dormitory
    
    student = get_object_or_404(Student, pk=student_id)
    
    # Find compatible dormitories
    compatible_dormitories = []
    incompatible_dormitories = []
    
    for dormitory in Dormitory.objects.filter(is_active=True, is_available_for_new_admissions=True):
        can_accommodate, message = dormitory.can_accommodate(student)
        if can_accommodate:
            compatible_dormitories.append(dormitory)
        else:
            incompatible_dormitories.append({
                'dormitory': dormitory,
                'reason': message
            })
    
    return render(request, 'boarding/enrollments/modals/boarding_eligibility.html', {
        'student': student,
        'compatible_dormitories': compatible_dormitories,
        'incompatible_dormitories': incompatible_dormitories,
    })


# =============================================================================
# MAINTENANCE MODALS
# =============================================================================

@login_required
def dormitory_maintenance_schedule_modal(request, pk):
    """Return dormitory maintenance schedule modal via HTMX"""
    dormitory = get_object_or_404(Dormitory, pk=pk)
    
    return render(request, 'boarding/dormitories/modals/maintenance_schedule.html', {
        'dormitory': dormitory
    })


@login_required
def dormitory_update_maintenance_modal(request, pk):
    """Return update maintenance status modal via HTMX"""
    dormitory = get_object_or_404(Dormitory, pk=pk)
    
    return render(request, 'boarding/dormitories/modals/update_maintenance.html', {
        'dormitory': dormitory
    })