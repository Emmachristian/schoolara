"""
hr/modal_views.py

GET-only modal trigger functions.
──────────────────────────────────
CONTRACT: every function in this file MUST:
  • accept only GET requests (no POST handling, no form.save())
  • load a form (blank or pre-filled from an existing instance)
    OR load an object for confirmation / quick-view templates
  • return render(request, '<template>', context)

All create / update / delete / action logic lives in views.py.
Modal templates point their hx-post attributes at the views.py URLs.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404

from .models import (
    Department, Designation, Contract,
    Staff, StaffDesignation, Teacher,
    Attendance, Payroll, PayrollPayment, 
)
from .forms import StaffDesignationForm


# =============================================================================
# DEPARTMENTS
# =============================================================================

@login_required
def department_delete_modal(request, pk):
    department = get_object_or_404(Department, pk=pk)
    staff_count   = department.primary_staff.count()
    sub_dept_count = department.sub_departments.count()
    return render(request, 'hr/departments/modals/delete.html', {
        'department':    department,
        'can_delete':    staff_count == 0 and sub_dept_count == 0,
        'staff_count':   staff_count,
        'sub_dept_count': sub_dept_count,
        'designation_count': department.designations.count(),
    })


@login_required
def department_quick_view_modal(request, pk):
    department = get_object_or_404(Department, pk=pk)
    return render(request, 'hr/departments/modals/quick_view.html', {
        'department': department,
    })


# =============================================================================
# DESIGNATIONS
# =============================================================================

@login_required
def designation_delete_modal(request, pk):
    designation  = get_object_or_404(Designation, pk=pk)
    staff_count  = designation.staff_members.count()
    subordinates = designation.subordinate_designations.count()
    return render(request, 'hr/designations/modals/delete.html', {
        'designation':   designation,
        'can_delete':    staff_count == 0,
        'staff_count':   staff_count,
        'subordinate_count': subordinates,
    })


@login_required
def designation_quick_view_modal(request, pk):
    designation = get_object_or_404(Designation, pk=pk)
    return render(request, 'hr/designations/modals/quick_view.html', {
        'designation': designation,
    })


# =============================================================================
# STAFF
# =============================================================================

@login_required
def staff_delete_modal(request, pk):
    staff = get_object_or_404(Staff, pk=pk)

    can_delete = True
    warnings   = []

    if staff.is_active:
        can_delete = False
        warnings.append('Cannot delete active staff — deactivate first.')

    active_contract_count = staff.contracts.filter(status='ACTIVE').count()
    if active_contract_count:
        can_delete = False
        warnings.append(f'Staff has {active_contract_count} active contract(s).')

    if hasattr(staff, 'payrolls') and staff.payrolls.exists():
        can_delete = False
        warnings.append(f'Staff has {staff.payrolls.count()} payroll record(s).')

    designation_count = staff.staffdesignation_set.filter(is_active=True).count()
    if designation_count:
        warnings.append(f'{designation_count} active designation(s) will be removed.')

    return render(request, 'hr/staff/modals/delete.html', {
        'staff':      staff,
        'can_delete': can_delete,
        'warnings':   warnings,
    })


@login_required
def staff_activate_modal(request, pk):
    staff = get_object_or_404(Staff, pk=pk)
    return render(request, 'hr/staff/modals/activate.html', {'staff': staff})


@login_required
def staff_deactivate_modal(request, pk):
    staff = get_object_or_404(Staff, pk=pk)
    return render(request, 'hr/staff/modals/deactivate.html', {
        'staff':            staff,
        'active_contracts': staff.contracts.filter(status='ACTIVE').count(),
        'teaching_profile': hasattr(staff, 'teacher') and staff.teacher.is_active,
    })


@login_required
def staff_quick_view_modal(request, pk):
    staff = get_object_or_404(
        Staff.objects.select_related('primary_department').prefetch_related(
            'staffdesignation_set__designation',
        ),
        pk=pk,
    )
    return render(request, 'hr/staff/modals/quick_view.html', {'staff': staff})


# --- Staff designation modals -----------------------------------------------

@login_required
def staff_assign_designation_modal(request, staff_pk):
    from .forms import StaffDesignationForm
    staff = get_object_or_404(Staff, pk=staff_pk)
    form  = StaffDesignationForm(initial={'staff': staff})
    return render(request, 'hr/staff/modals/assign_designation.html', {
        'staff': staff,
        'form':  form,
    })

@login_required
def staff_designation_delete_modal(request, pk):
    sd = get_object_or_404(
        StaffDesignation.objects.select_related('staff', 'designation'), pk=pk
    )
    warnings = []
    if sd.is_primary:
        warnings.append('This is the primary designation for this staff member.')
    if sd.staff.designations.count() == 1:
        warnings.append("This is the staff member's only designation.")
    return render(request, 'hr/staff/modals/delete_designation.html', {
        'assignment': sd,
        'can_delete': True,
        'warnings':   warnings,
    })

@login_required
def staff_designation_edit_modal(request, pk):
    from .forms import StaffDesignationForm
    sd = get_object_or_404(
        StaffDesignation.objects.select_related('staff', 'designation'), pk=pk
    )
    form = StaffDesignationForm(instance=sd)
    return render(request, 'hr/staff/modals/edit_designation.html', {
        'sd':   sd,
        'form': form,
    })

@login_required
def staff_designation_activate_modal(request, pk):
    sd = get_object_or_404(StaffDesignation, pk=pk)
    return render(request, 'hr/staff/modals/activate_designation.html', {
        'staff_designation': sd,
    })


@login_required
def staff_designation_deactivate_modal(request, pk):
    sd = get_object_or_404(StaffDesignation, pk=pk)

    can_deactivate = True
    message        = None

    if sd.is_primary:
        other_active = StaffDesignation.objects.filter(
            staff=sd.staff, is_active=True
        ).exclude(pk=sd.pk).exists()
        if not other_active:
            can_deactivate = False
            message = 'Cannot deactivate the only active designation — assign another first.'

    return render(request, 'hr/staff/modals/deactivate_designation.html', {
        'staff_designation': sd,
        'can_deactivate':    can_deactivate,
        'message':           message,
    })


@login_required
def staff_designation_set_primary_modal(request, pk):
    sd = get_object_or_404(StaffDesignation, pk=pk)
    can_set_primary = sd.is_active
    return render(request, 'hr/staff/modals/set_primary_designation.html', {
        'staff_designation': sd,
        'can_set_primary':   can_set_primary,
        'message': None if can_set_primary else 'Cannot set inactive designation as primary — activate it first.',
    })


# =============================================================================
# CONTRACTS
# =============================================================================

@login_required
def contract_delete_modal(request, pk):
    contract = get_object_or_404(Contract, pk=pk)
    warnings = []

    if contract.salary_changes.exists():
        warnings.append(f'{contract.salary_changes.count()} salary change(s) will be removed.')
    if contract.benefits.exists():
        warnings.append(f'{contract.benefits.count()} benefit(s) will be removed.')

    return render(request, 'hr/contracts/modals/delete.html', {
        'contract':   contract,
        'can_delete': contract.status != 'ACTIVE',
        'warnings':   warnings,
    })


@login_required
def contract_activate_modal(request, pk):
    contract = get_object_or_404(Contract, pk=pk)
    return render(request, 'hr/contracts/modals/activate.html', {
        'contract':     contract,
        'can_activate': contract.status in ['DRAFT', 'SUSPENDED'],
    })


@login_required
def contract_terminate_modal(request, pk):
    contract = get_object_or_404(Contract, pk=pk)
    return render(request, 'hr/contracts/modals/terminate.html', {
        'contract':          contract,
        'can_terminate':     contract.status == 'ACTIVE',
        'termination_reasons': Contract.TERMINATION_REASON_CHOICES,
    })


@login_required
def contract_renew_modal(request, pk):
    from datetime import timedelta
    contract = get_object_or_404(Contract, pk=pk)
    suggested_end_date = None
    if contract.end_date:
        suggested_end_date = contract.end_date + timedelta(
            days=contract.renewal_period_months * 30
        )
    return render(request, 'hr/contracts/modals/renew.html', {
        'contract':           contract,
        'suggested_end_date': suggested_end_date,
    })


@login_required
def contract_quick_view_modal(request, pk):
    contract = get_object_or_404(
        Contract.objects.select_related('staff'), pk=pk
    )
    return render(request, 'hr/contracts/modals/quick_view.html', {
        'contract': contract,
    })


# =============================================================================
# TEACHERS
# =============================================================================

@login_required
def teacher_edit_modal(request, pk):
    from .forms import TeacherForm
    teacher = get_object_or_404(
        Teacher.objects.select_related(
            'staff__primary_department'
        ).prefetch_related('qualified_subjects', 'assigned_classes', 'preferred_academic_levels'),
        pk=pk
    )
    form = TeacherForm(instance=teacher)
    return render(request, 'hr/teachers/modals/edit.html', {
        'teacher': teacher,
        'form':    form,
    })

@login_required
def teacher_delete_modal(request, pk):
    teacher     = get_object_or_404(Teacher, pk=pk)
    class_count = teacher.assigned_classes.count()
    warnings    = []
    if teacher.current_teaching_load > 0:
        warnings.append(f'Teacher has current teaching load of {teacher.current_teaching_load} hours.')
    return render(request, 'hr/teachers/modals/delete.html', {
        'teacher':     teacher,
        'can_delete':  class_count == 0,
        'class_count': class_count,
        'warnings':    warnings,
    })


@login_required
def teacher_reactivate_modal(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    return render(request, 'hr/teachers/modals/reactivate.html', {'teacher': teacher})


@login_required
def teacher_deactivate_modal(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)

    has_teaching_designation = StaffDesignation.objects.filter(
        staff=teacher.staff, designation__is_teaching=True, is_active=True
    ).exists()

    return render(request, 'hr/teachers/modals/deactivate.html', {
        'teacher':                   teacher,
        'can_deactivate':            not has_teaching_designation,
        'has_teaching_designation':  has_teaching_designation,
    })


@login_required
def teacher_quick_view_modal(request, pk):
    teacher = get_object_or_404(
        Teacher.objects.select_related('staff__primary_department').prefetch_related(
            'qualified_subjects', 'assigned_classes',
        ),
        pk=pk,
    )
    return render(request, 'hr/teachers/modals/quick_view.html', {'teacher': teacher})


# =============================================================================
# ATTENDANCE
# =============================================================================

@login_required
def attendance_delete_modal(request, pk):
    attendance = get_object_or_404(Attendance, pk=pk)
    return render(request, 'hr/attendance/modals/delete.html', {'attendance': attendance})


@login_required
def attendance_detail_modal(request, pk):
    attendance = get_object_or_404(
        Attendance.objects.select_related('staff__primary_department'), pk=pk
    )
    return render(request, 'hr/attendance/modals/detail.html', {'attendance': attendance})


@login_required
def bulk_attendance_modal(request):
    from core.utils import get_school_today
    today        = get_school_today()
    existing     = Attendance.objects.filter(date=today).count()
    active_staff = Staff.objects.filter(is_active=True).count()
    return render(request, 'hr/attendance/modals/bulk_attendance.html', {
        'today':             today,
        'active_staff_count': active_staff,
        'existing_count':    existing,
    })


# =============================================================================
# PAYROLL
# =============================================================================

@login_required
def payroll_delete_modal(request, pk):
    payroll = get_object_or_404(Payroll, pk=pk)
    can_delete = payroll.status in ['DRAFT', 'CANCELLED'] and not payroll.reversed
    message    = None
    if payroll.reversed:
        message = 'Cannot delete reversed payrolls — they must be kept for audit trail.'
    elif payroll.status not in ['DRAFT', 'CANCELLED']:
        message = (
            f'Cannot delete payroll with status: {payroll.get_status_display()}. '
            'Only DRAFT or CANCELLED payrolls can be deleted.'
        )
    return render(request, 'hr/payroll/modals/delete.html', {
        'payroll':    payroll,
        'can_delete': can_delete,
        'message':    message,
    })


@login_required
def payroll_approve_modal(request, pk):
    payroll    = get_object_or_404(Payroll, pk=pk)
    can_approve = payroll.status == 'DRAFT' and not payroll.reversed
    message    = None
    if payroll.reversed:
        message = 'Cannot approve a reversed payroll.'
    elif payroll.status != 'DRAFT':
        message = f'Payroll is already {payroll.get_status_display()}.'
    return render(request, 'hr/payroll/modals/approve.html', {
        'payroll':     payroll,
        'can_approve': can_approve,
        'message':     message,
    })


@login_required
def payroll_process_payment_modal(request, pk):
    payroll     = get_object_or_404(Payroll, pk=pk)
    can_process = payroll.status == 'APPROVED' and not payroll.reversed
    message     = None
    if payroll.reversed:
        message = 'Cannot process payment for a reversed payroll.'
    elif payroll.status != 'APPROVED':
        message = (
            f'Payroll must be approved before payment. '
            f'Current status: {payroll.get_status_display()}.'
        )
    return render(request, 'hr/payroll/modals/process_payment.html', {
        'payroll':     payroll,
        'can_process': can_process,
        'message':     message,
    })


@login_required
def payroll_reverse_modal(request, pk):
    payroll = get_object_or_404(Payroll, pk=pk)
    can_reverse, reason = payroll.can_be_reversed()
    return render(request, 'hr/payroll/modals/reverse.html', {
        'payroll':            payroll,
        'can_reverse':        can_reverse,
        'reversal_reason':    reason,
        'requires_statutory': payroll.requires_statutory_adjustments(),
    })


@login_required
def payroll_detail_modal(request, pk):
    payroll = get_object_or_404(
        Payroll.objects.select_related(
            'staff__primary_department', 'fiscal_period', 'payment_method',
        ).prefetch_related('allowances', 'deductions', 'bonuses'),
        pk=pk,
    )
    return render(request, 'hr/payroll/modals/detail.html', {
        'payroll':             payroll,
        'effective_net_pay':   payroll.effective_net_pay,
        'effective_gross_pay': payroll.effective_gross_pay,
    })


@login_required
def bulk_payroll_generation_modal(request):
    from core.utils import get_school_today
    from calendar import monthrange
    from core.models import FiscalPeriod

    today             = get_school_today()
    staff_with_contracts = Staff.objects.filter(
        is_active=True, contracts__status='ACTIVE'
    ).distinct().count()
    last_day = monthrange(today.year, today.month)[1]

    return render(request, 'hr/payroll/modals/bulk_generation.html', {
        'staff_with_contracts': staff_with_contracts,
        'suggested_pay_start':  today.replace(day=1),
        'suggested_pay_end':    today.replace(day=last_day),
        'available_periods':    FiscalPeriod.objects.filter(
                                    is_closed=False,
                                    start_date__lte=today,
                                    end_date__gte=today,
                                ).order_by('-start_date'),
    })

@login_required
def payroll_record_payment_modal(request, pk):
    from .forms import PayrollPaymentForm
    payroll = get_object_or_404(
        Payroll.objects.select_related(
            'staff', 'payment_method',
        ).prefetch_related('salary_payments__payment_method'),
        pk=pk,
    )
    form = PayrollPaymentForm(payroll=payroll)
    return render(request, 'hr/payroll/modals/record_payment.html', {
        'payroll': payroll,
        'form':    form,
    })

# =============================================================================
# BULK STAFF
# =============================================================================

@login_required
def bulk_staff_action_modal(request):
    selected_ids  = [i for i in request.GET.get('ids', '').split(',') if i]
    return render(request, 'hr/staff/modals/bulk_action.html', {
        'selected_count': len(selected_ids),
        'selected_ids':   ','.join(selected_ids),
    })