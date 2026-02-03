# hr/modal_views.py

"""
Modal Views for HR Management

These views return HTML fragments for modals loaded via HTMX.
Each modal view is paired with an action view in views.py that handles the POST request.

Pattern:
1. GET request → modal_views.py (loads modal HTML)
2. POST request → views.py (processes action, returns response with headers)

NOTE: Form modals are NOT included here - they are handled in dedicated form templates.
This file ONLY contains confirmation/action modals (delete, activate, deactivate, etc.)
"""

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from .models import (
    Department,
    Designation,
    Contract,
    Staff,
    StaffDesignation,
    Teacher,
    Attendance,
    Payroll,
    SalaryHistory,
    ContractBenefit,
)


# =============================================================================
# STAFF MODALS (Action/Confirmation only)
# =============================================================================

@login_required
def staff_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    staff = get_object_or_404(Staff, pk=pk)
    
    # Check if staff can be deleted
    can_delete = True
    warnings = []
    
    # Check if active
    if staff.is_active:
        can_delete = False
        warnings.append("Cannot delete active staff. Please deactivate first.")
    
    # Check for active contracts
    active_contract_count = staff.contracts.filter(status='ACTIVE').count()
    if active_contract_count > 0:
        can_delete = False
        warnings.append(f"Staff has {active_contract_count} active contract(s). Cannot delete.")
    
    # Check for designation assignments
    designation_count = staff.staffdesignation_set.filter(is_active=True).count()
    if designation_count > 0:
        warnings.append(f"Staff has {designation_count} active designation(s) that will be removed")
    
    # Check for payroll records
    if hasattr(staff, 'payrolls'):
        payroll_count = staff.payrolls.count()
        if payroll_count > 0:
            can_delete = False
            warnings.append(f"Staff has {payroll_count} payroll record(s). Cannot delete.")
    
    # Check for attendance records
    if hasattr(staff, 'attendance_records'):
        attendance_count = staff.attendance_records.count()
        if attendance_count > 0:
            warnings.append(f"Staff has {attendance_count} attendance record(s) that will be removed")
    
    return render(request, 'hr/staff/modals/delete_staff.html', {
        'staff': staff,
        'can_delete': can_delete,
        'warnings': warnings,
    })


@login_required
def staff_activate_modal(request, pk):
    """Return activation confirmation modal content via HTMX"""
    staff = get_object_or_404(Staff, pk=pk)
    
    return render(request, 'hr/staff/modals/activate_staff.html', {
        'staff': staff
    })


@login_required
def staff_deactivate_modal(request, pk):
    """Return deactivation confirmation modal content via HTMX"""
    staff = get_object_or_404(Staff, pk=pk)
    
    # Check for warnings
    active_contracts = staff.contracts.filter(status='ACTIVE').count()
    teaching_profile = hasattr(staff, 'teacher') and staff.teacher.is_active
    
    return render(request, 'hr/staff/modals/deactivate_staff.html', {
        'staff': staff,
        'active_contracts': active_contracts,
        'teaching_profile': teaching_profile,
    })


# =============================================================================
# DEPARTMENT MODALS (Action/Confirmation only)
# =============================================================================

@login_required
def department_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    department = get_object_or_404(Department, pk=pk)
    
    # Check if department can be deleted
    can_delete = True
    warnings = []
    
    # Check for staff
    staff_count = department.primary_staff.count()
    if staff_count > 0:
        can_delete = False
        warnings.append(f"Department has {staff_count} staff member(s). Reassign staff first.")
    
    # Check for sub-departments
    sub_dept_count = department.sub_departments.count()
    if sub_dept_count > 0:
        can_delete = False
        warnings.append(f"Department has {sub_dept_count} sub-department(s).")
    
    # Check for designations
    designation_count = department.designations.count()
    if designation_count > 0:
        warnings.append(f"Department has {designation_count} designation(s) that will be removed")
    
    return render(request, 'hr/departments/modals/delete_department.html', {
        'department': department,
        'can_delete': can_delete,
        'warnings': warnings,
    })


# =============================================================================
# DESIGNATION MODALS (Action/Confirmation only)
# =============================================================================

@login_required
def designation_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    designation = get_object_or_404(Designation, pk=pk)
    
    # Check if designation can be deleted
    can_delete = True
    warnings = []
    
    # Check for staff assignments
    staff_count = designation.staff_members.count()
    if staff_count > 0:
        can_delete = False
        warnings.append(f"Designation is assigned to {staff_count} staff member(s). Remove assignments first.")
    
    # Check for subordinate designations
    subordinate_count = designation.subordinate_designations.count()
    if subordinate_count > 0:
        warnings.append(f"Designation has {subordinate_count} subordinate designation(s) that will be unlinked")
    
    return render(request, 'hr/designations/modals/delete_designation.html', {
        'designation': designation,
        'can_delete': can_delete,
        'warnings': warnings,
    })


# =============================================================================
# CONTRACT MODALS (Action/Confirmation only)
# =============================================================================

@login_required
def contract_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    contract = get_object_or_404(Contract, pk=pk)
    
    # Check if contract can be deleted
    can_delete = True
    warnings = []
    
    # Check if active
    if contract.status == 'ACTIVE':
        can_delete = False
        warnings.append("Cannot delete active contracts. Please terminate or change status first.")
    
    # Check for salary history
    salary_history_count = contract.salary_changes.count()
    if salary_history_count > 0:
        warnings.append(f"Contract has {salary_history_count} salary change(s) that will be removed")
    
    # Check for benefits
    benefit_count = contract.benefits.count()
    if benefit_count > 0:
        warnings.append(f"Contract has {benefit_count} benefit(s) that will be removed")
    
    return render(request, 'hr/contracts/modals/delete_contract.html', {
        'contract': contract,
        'can_delete': can_delete,
        'warnings': warnings,
    })


@login_required
def contract_activate_modal(request, pk):
    """Return contract activation confirmation modal via HTMX"""
    contract = get_object_or_404(Contract, pk=pk)
    
    # Check if can be activated
    can_activate = contract.status in ['DRAFT', 'SUSPENDED']
    
    return render(request, 'hr/contracts/modals/activate_contract.html', {
        'contract': contract,
        'can_activate': can_activate,
    })


@login_required
def contract_terminate_modal(request, pk):
    """Return contract termination modal with reason input via HTMX"""
    contract = get_object_or_404(Contract, pk=pk)
    
    # Check if can be terminated
    can_terminate = contract.status == 'ACTIVE'
    
    return render(request, 'hr/contracts/modals/terminate_contract.html', {
        'contract': contract,
        'can_terminate': can_terminate,
        'termination_reasons': Contract.TERMINATION_REASON_CHOICES,
    })


@login_required
def contract_renew_modal(request, pk):
    """Return contract renewal modal with form via HTMX"""
    contract = get_object_or_404(Contract, pk=pk)
    
    # Calculate suggested new end date
    if contract.end_date:
        from datetime import timedelta
        suggested_end_date = contract.end_date + timedelta(days=contract.renewal_period_months * 30)
    else:
        suggested_end_date = None
    
    return render(request, 'hr/contracts/modals/renew_contract.html', {
        'contract': contract,
        'suggested_end_date': suggested_end_date,
    })


# =============================================================================
# STAFF DESIGNATION MODALS (Action/Confirmation only)
# =============================================================================

@login_required
def staff_designation_delete_modal(request, pk):
    """Return staff designation delete confirmation modal via HTMX"""
    assignment = get_object_or_404(
        StaffDesignation.objects.select_related('staff', 'designation'),
        pk=pk
    )
    
    # Check if assignment can be deleted
    can_delete = True
    warnings = []
    
    # Check if primary designation
    if assignment.is_primary:
        warnings.append("This is the primary designation for this staff member")
    
    # Check if only designation
    designation_count = assignment.staff.designations.count()
    if designation_count == 1:
        warnings.append("This is the staff member's only designation")
    
    return render(request, 'hr/staff/modals/delete_designation.html', {
        'assignment': assignment,
        'can_delete': can_delete,
        'warnings': warnings,
    })


@login_required
def staff_designation_deactivate_modal(request, pk):
    """Return staff designation deactivation modal via HTMX"""
    staff_designation = get_object_or_404(StaffDesignation, pk=pk)
    
    # Check if can be deactivated
    can_deactivate = True
    message = None
    
    if staff_designation.is_primary:
        other_active = StaffDesignation.objects.filter(
            staff=staff_designation.staff,
            is_active=True
        ).exclude(pk=staff_designation.pk).exists()
        
        if not other_active:
            can_deactivate = False
            message = "Cannot deactivate the only active designation. Assign another designation first."
    
    return render(request, 'hr/staff/modals/deactivate_designation.html', {
        'staff_designation': staff_designation,
        'can_deactivate': can_deactivate,
        'message': message,
    })


@login_required
def staff_designation_activate_modal(request, pk):
    """Return staff designation activation confirmation modal via HTMX"""
    staff_designation = get_object_or_404(StaffDesignation, pk=pk)
    
    return render(request, 'hr/staff/modals/activate_designation.html', {
        'staff_designation': staff_designation
    })


@login_required
def staff_designation_set_primary_modal(request, pk):
    """Return set as primary confirmation modal via HTMX"""
    staff_designation = get_object_or_404(StaffDesignation, pk=pk)
    
    # Check if can be set as primary
    can_set_primary = staff_designation.is_active
    message = None if can_set_primary else "Cannot set inactive designation as primary. Activate it first."
    
    return render(request, 'hr/staff/modals/set_primary_designation.html', {
        'staff_designation': staff_designation,
        'can_set_primary': can_set_primary,
        'message': message,
    })


# =============================================================================
# TEACHER MODALS (Action/Confirmation only)
# =============================================================================

@login_required
def teacher_delete_modal(request, pk):
    """Return teacher delete confirmation modal via HTMX"""
    teacher = get_object_or_404(Teacher, pk=pk)
    
    # Check if teacher can be deleted
    can_delete = True
    warnings = []
    
    # Check for assigned classes
    class_count = teacher.assigned_classes.count()
    if class_count > 0:
        can_delete = False
        warnings.append(f"Teacher has {class_count} assigned class(es). Remove assignments first.")
    
    # Check for current teaching load
    if teacher.current_teaching_load > 0:
        warnings.append(f"Teacher has current teaching load of {teacher.current_teaching_load} hours")
    
    return render(request, 'hr/teachers/modals/delete_teacher.html', {
        'teacher': teacher,
        'can_delete': can_delete,
        'warnings': warnings,
    })


@login_required
def teacher_reactivate_modal(request, pk):
    """Return teacher reactivation confirmation modal via HTMX"""
    teacher = get_object_or_404(Teacher, pk=pk)
    
    return render(request, 'hr/teachers/modals/reactivate_teacher.html', {
        'teacher': teacher
    })


@login_required
def teacher_deactivate_modal(request, pk):
    """Return teacher deactivation modal via HTMX"""
    teacher = get_object_or_404(Teacher, pk=pk)
    
    # Check if they have active teaching designations
    has_teaching_designation = StaffDesignation.objects.filter(
        staff=teacher.staff,
        designation__is_teaching=True,
        is_active=True
    ).exists()
    
    can_deactivate = not has_teaching_designation
    message = None
    if has_teaching_designation:
        message = "Teacher has active teaching designations. Remove teaching designations first."
    
    return render(request, 'hr/teachers/modals/deactivate_teacher.html', {
        'teacher': teacher,
        'can_deactivate': can_deactivate,
        'message': message,
    })


# =============================================================================
# ATTENDANCE MODALS (Action/Confirmation only)
# =============================================================================

@login_required
def attendance_delete_modal(request, pk):
    """Return attendance delete confirmation modal via HTMX"""
    attendance = get_object_or_404(Attendance, pk=pk)
    
    return render(request, 'hr/attendance/modals/delete_attendance.html', {
        'attendance': attendance
    })


@login_required
def attendance_detail_modal(request, pk):
    """Return attendance record details modal via HTMX"""
    attendance = get_object_or_404(
        Attendance.objects.select_related('staff__primary_department'),
        pk=pk
    )
    
    return render(request, 'hr/attendance/modals/attendance_detail.html', {
        'attendance': attendance
    })


# =============================================================================
# PAYROLL MODALS (Action/Confirmation only) - UPDATED
# =============================================================================

@login_required
def payroll_delete_modal(request, pk):
    """Return payroll delete confirmation modal via HTMX - UPDATED"""
    payroll = get_object_or_404(Payroll, pk=pk)
    
    # Can only delete draft or cancelled payrolls, not reversed ones
    can_delete = payroll.status in ['DRAFT', 'CANCELLED'] and not payroll.reversed  # ⭐ UPDATED
    
    message = None
    if payroll.reversed:  # ⭐ NEW
        message = "Cannot delete reversed payrolls. They must be kept for audit trail."
    elif payroll.status not in ['DRAFT', 'CANCELLED']:
        message = f"Cannot delete payroll with status: {payroll.get_status_display()}. Only DRAFT or CANCELLED payrolls can be deleted."
    
    return render(request, 'hr/payroll/modals/delete_payroll.html', {
        'payroll': payroll,
        'can_delete': can_delete,
        'message': message,
    })


@login_required
def payroll_approve_modal(request, pk):
    """Return payroll approval confirmation modal via HTMX - UPDATED"""
    payroll = get_object_or_404(Payroll, pk=pk)
    
    # Check if can be approved
    can_approve = payroll.status == 'DRAFT' and not payroll.reversed  # ⭐ UPDATED
    
    message = None
    if payroll.reversed:  # ⭐ NEW
        message = "Cannot approve a reversed payroll"
    elif payroll.status != 'DRAFT':
        message = f"Payroll is already {payroll.get_status_display()}"
    
    return render(request, 'hr/payroll/modals/approve_payroll.html', {
        'payroll': payroll,
        'can_approve': can_approve,
        'message': message,  # ⭐ NEW
    })


@login_required
def payroll_process_payment_modal(request, pk):
    """Return process payment confirmation modal via HTMX - UPDATED"""
    payroll = get_object_or_404(Payroll, pk=pk)
    
    # Check if can be processed
    can_process = payroll.status == 'APPROVED' and not payroll.reversed  # ⭐ UPDATED
    
    message = None
    if payroll.reversed:  # ⭐ NEW
        message = "Cannot process payment for a reversed payroll"
    elif payroll.status != 'APPROVED':
        message = f"Payroll must be approved before payment. Current status: {payroll.get_status_display()}"
    
    return render(request, 'hr/payroll/modals/process_payment.html', {
        'payroll': payroll,
        'can_process': can_process,
        'message': message,
    })


@login_required
def payroll_detail_modal(request, pk):
    """Return payroll details modal via HTMX - UPDATED"""
    payroll = get_object_or_404(
        Payroll.objects.select_related(
            'staff__primary_department',
            'fiscal_period',  # ⭐ RENAMED from 'period'
            'fiscal_year',
            'payment_method',
            'journal_entry',  # ⭐ NEW
            'payment_journal_entry',  # ⭐ NEW
            'reversal_journal_entry',  # ⭐ NEW
        ).prefetch_related('allowances', 'deductions', 'bonuses'),
        pk=pk
    )
    
    # Calculate totals
    total_allowances = sum(a.amount for a in payroll.allowances.all())
    total_deductions = sum(d.amount for d in payroll.deductions.all())
    total_bonuses = sum(b.amount for b in payroll.bonuses.all())
    
    # ⭐ NEW: Get effective amounts
    effective_net_pay = payroll.effective_net_pay
    effective_gross_pay = payroll.effective_gross_pay
    
    return render(request, 'hr/payroll/modals/payroll_detail.html', {
        'payroll': payroll,
        'total_allowances': total_allowances,
        'total_deductions': total_deductions,
        'total_bonuses': total_bonuses,
        'effective_net_pay': effective_net_pay,  # ⭐ NEW
        'effective_gross_pay': effective_gross_pay,  # ⭐ NEW
    })


# ⭐ NEW: Payroll reversal modal
@login_required
def payroll_reverse_modal(request, pk):
    """Return payroll reversal modal via HTMX"""
    payroll = get_object_or_404(Payroll, pk=pk)
    
    # Check if can be reversed
    can_reverse, reason = payroll.can_be_reversed()
    
    # Check if requires statutory adjustments
    requires_statutory = payroll.requires_statutory_adjustments()
    
    return render(request, 'hr/payroll/modals/reverse_payroll.html', {
        'payroll': payroll,
        'can_reverse': can_reverse,
        'reversal_reason': reason,
        'requires_statutory': requires_statutory,
        'termination_reasons': Contract.TERMINATION_REASON_CHOICES,  # For dropdown if needed
    })


# =============================================================================
# BULK OPERATION MODALS - UPDATED
# =============================================================================

@login_required
def bulk_payroll_generation_modal(request):
    """Return bulk payroll generation modal via HTMX - UPDATED"""
    from core.utils import get_school_today
    from datetime import timedelta
    from calendar import monthrange
    
    # Get count of staff with active contracts
    staff_with_contracts = Staff.objects.filter(
        is_active=True,
        contracts__status='ACTIVE'
    ).distinct().count()
    
    # ⭐ NEW: Suggest default pay period (current month)
    today = get_school_today()
    first_day = today.replace(day=1)
    last_day_num = monthrange(today.year, today.month)[1]
    last_day = today.replace(day=last_day_num)
    
    # ⭐ NEW: Get available fiscal periods
    from core.models import FiscalPeriod
    available_periods = FiscalPeriod.objects.filter(
        is_closed=False,
        start_date__lte=today,
        end_date__gte=today
    ).order_by('-start_date')
    
    return render(request, 'hr/payroll/modals/bulk_generation.html', {
        'staff_with_contracts': staff_with_contracts,
        'suggested_pay_start': first_day,  # ⭐ NEW
        'suggested_pay_end': last_day,  # ⭐ NEW
        'available_periods': available_periods,  # ⭐ NEW
    })


# =============================================================================
# BULK OPERATION MODALS
# =============================================================================

@login_required
def bulk_staff_action_modal(request):
    """Return bulk action modal for staff via HTMX"""
    
    selected_ids = request.GET.get('ids', '').split(',')
    selected_count = len([id for id in selected_ids if id])
    
    return render(request, 'hr/staff/modals/bulk_action.html', {
        'selected_count': selected_count,
        'selected_ids': ','.join(selected_ids),
    })


@login_required
def bulk_attendance_modal(request):
    """Return bulk attendance recording modal via HTMX"""
    
    # Get count of active staff
    from core.utils import get_school_today
    
    active_staff_count = Staff.objects.filter(is_active=True).count()
    today = get_school_today()
    
    # Check if attendance already recorded today
    existing_count = Attendance.objects.filter(date=today).count()
    
    return render(request, 'hr/attendance/modals/bulk_attendance.html', {
        'active_staff_count': active_staff_count,
        'existing_count': existing_count,
        'today': today,
    })


@login_required
def bulk_payroll_generation_modal(request):
    """Return bulk payroll generation modal via HTMX"""
    
    # Get count of staff with active contracts
    staff_with_contracts = Staff.objects.filter(
        is_active=True,
        contracts__status='ACTIVE'
    ).distinct().count()
    
    return render(request, 'hr/payroll/modals/bulk_generation.html', {
        'staff_with_contracts': staff_with_contracts,
    })