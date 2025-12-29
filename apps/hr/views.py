# hr/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db.models import Q, Count
from django.db import transaction
from formtools.wizard.views import SessionWizardView
from django.core.files.storage import FileSystemStorage
from datetime import datetime
from io import BytesIO
import os
import logging

# Excel imports
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# PDF imports
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER

from .models import (
    Department, Designation, ContractType, Contract,
    Staff, StaffDesignation, Teacher
)
from .forms import (
    DepartmentForm, DesignationForm, ContractTypeForm, ContractForm,
    StaffForm, StaffDesignationForm, TeacherForm,
    STAFF_WIZARD_FORMS, STAFF_WIZARD_STEP_NAMES,
)
from .utils import paginate_queryset
from .stats import (
    get_staff_statistics, get_department_statistics,
    get_designation_statistics, get_contract_statistics,
    get_teacher_statistics, get_hr_dashboard_statistics,
    get_contract_type_statistics
)

logger = logging.getLogger(__name__)


# =============================================================================
# DASHBOARD VIEW
# =============================================================================

@login_required
def hr_dashboard(request):
    """HR Dashboard with comprehensive statistics"""
    
    # Get comprehensive dashboard statistics
    dashboard_stats = get_hr_dashboard_statistics()
    
    context = {
        'stats': dashboard_stats,
    }
    
    return render(request, 'hr/dashboard.html', context)


# =============================================================================
# STAFF VIEWS
# =============================================================================

@login_required
def staff_list(request):
    """List all staff with pagination and statistics"""
    
    # Fetch all staff with related data
    staff_queryset = Staff.objects.all().select_related(
        'primary_department'
    ).order_by('-created_at')
    
    # Filter options for frontend dropdowns
    departments = Department.objects.filter(is_active=True).order_by('name')
    
    # Pagination
    staff_page, paginator = paginate_queryset(request, staff_queryset, per_page=10)
    
    # Get statistics from statistics module
    stats = get_staff_statistics()
    
    context = {
        'staff': staff_page,
        'departments': departments,
        'stats': stats,
    }
    
    return render(request, 'staff/list.html', context)

class StaffWizardFileStorage(FileSystemStorage):
    """Custom storage for handling file uploads in wizard"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.location = os.path.join(self.location, 'wizard_temp')


class StaffCreateWizard(SessionWizardView):
    """Multi-step wizard for creating a staff member"""
    
    form_list = STAFF_WIZARD_FORMS
    template_name = 'staff/wizard.html'
    file_storage = StaffWizardFileStorage()
    
    def get_context_data(self, form, **kwargs):
        """Add step names and progress tracking"""
        context = super().get_context_data(form=form, **kwargs)
        
        total_steps = len(self.form_list)
        current_step_index = list(self.form_list).index(self.steps.current)
        
        context.update({
            'step_names': STAFF_WIZARD_STEP_NAMES,
            'current_step_name': STAFF_WIZARD_STEP_NAMES.get(
                self.steps.current, 'Step'
            ),
            'progress_percentage': ((current_step_index) / (total_steps - 1)) * 100 if total_steps > 1 else 100,
        })
        
        # Add review data for confirmation step
        if self.steps.current == 'confirmation':
            context['basic_data'] = self.get_cleaned_data_for_step('basic_info')
            context['contact_data'] = self.get_cleaned_data_for_step('contact_info')
            context['employment_data'] = self.get_cleaned_data_for_step('employment_info')
            context['qualifications_data'] = self.get_cleaned_data_for_step('qualifications')
            context['banking_data'] = self.get_cleaned_data_for_step('banking_info')
            context['designation_contract_data'] = self.get_cleaned_data_for_step('designation_contract')
            
            logger.info("=" * 50)
            logger.info("CONFIRMATION STEP - Review Data:")
            logger.info(f"Basic: {context['basic_data']}")
            logger.info(f"Contact: {context['contact_data']}")
            logger.info(f"Employment: {context['employment_data']}")
            logger.info(f"Qualifications: {context['qualifications_data']}")
            logger.info(f"Banking: {context['banking_data']}")
            logger.info(f"Designation/Contract: {context['designation_contract_data']}")
            logger.info("=" * 50)
        
        return context
    
    def post(self, *args, **kwargs):
        """Override post to add debugging"""
        logger.info("=" * 50)
        logger.info(f"POST REQUEST - Current step: {self.steps.current}")
        logger.info(f"All steps: {list(self.form_list.keys())}")
        logger.info(f"Is last step: {self.steps.current == self.steps.last}")
        logger.info(f"POST keys: {list(self.request.POST.keys())}")
        logger.info("=" * 50)
        return super().post(*args, **kwargs)
    
    def process_step(self, form):
        """Process each step and store data"""
        logger.info(f"Processing step: {self.steps.current}")
        logger.info(f"Form is valid: {form.is_valid()}")
        if not form.is_valid():
            logger.error(f"Form errors: {form.errors}")
        else:
            logger.info(f"Form data: {form.cleaned_data}")
        return super().process_step(form)
    
    @transaction.atomic
    def done(self, form_list, **kwargs):
        """Persist all wizard data and create staff member"""
        
        logger.info("=" * 80)
        logger.info("WIZARD DONE METHOD CALLED!!!")
        logger.info(f"Number of forms: {len(list(form_list))}")
        logger.info("=" * 80)
        
        try:
            # Merge cleaned data from all steps
            form_data = {}
            form_dict = {}
            
            for step, form in zip(self.form_list.keys(), form_list):
                logger.info(f"Processing form: {form.__class__.__name__}")
                logger.info(f"Cleaned data: {form.cleaned_data}")
                form_data.update(form.cleaned_data)
                form_dict[step] = form
            
            logger.info("=" * 50)
            logger.info("MERGED FORM DATA:")
            logger.info(form_data)
            logger.info("=" * 50)
            
            # ------------------------------------------------------------------
            # Step 1: Create staff instance from BasicInfoForm
            # ------------------------------------------------------------------
            basic_form = form_dict.get('basic_info')
            
            if not basic_form:
                raise ValueError("Basic info form not found in form list!")
            
            # Create staff instance but don't save yet
            staff = basic_form.save(commit=False)
            
            logger.info(f"Staff instance created: {staff}")
            
            # ------------------------------------------------------------------
            # Step 2: Contact information
            # ------------------------------------------------------------------
            staff.phone_number = form_data.get('phone_number', '')
            staff.alternative_phone = form_data.get('alternative_phone', '')
            staff.personal_email = form_data.get('personal_email', '')
            
            staff.emergency_contact_name = form_data.get('emergency_contact_name', '')
            staff.emergency_contact_relationship = form_data.get('emergency_contact_relationship', '')
            staff.emergency_contact_phone = form_data.get('emergency_contact_phone', '')
            staff.emergency_contact_address = form_data.get('emergency_contact_address', '')
            
            # ------------------------------------------------------------------
            # Step 3: Employment information
            # ------------------------------------------------------------------
            staff.staff_id = form_data.get('staff_id', '')
            staff.date_of_joining = form_data.get('date_of_joining')
            staff.employment_status = form_data.get('employment_status', 'FT')
            staff.primary_department = form_data.get('primary_department')
            staff.date_of_leaving = form_data.get('date_of_leaving')
            
            # ------------------------------------------------------------------
            # Step 4: Qualifications
            # ------------------------------------------------------------------
            staff.qualification = form_data.get('qualification', '')
            staff.experience = form_data.get('experience', '')
            staff.skills = form_data.get('skills', '')
            staff.languages_spoken = form_data.get('languages_spoken', '')
            staff.professional_memberships = form_data.get('professional_memberships', '')
            staff.certifications = form_data.get('certifications', '')
            
            # ------------------------------------------------------------------
            # Step 5: Banking & statutory information
            # ------------------------------------------------------------------
            staff.bank_account_name = form_data.get('bank_account_name', '')
            staff.bank_account_number = form_data.get('bank_account_number', '')
            staff.bank_name = form_data.get('bank_name', '')
            staff.bank_branch = form_data.get('bank_branch', '')
            staff.tax_identification_number = form_data.get('tax_identification_number', '')
            staff.social_security_number = form_data.get('social_security_number', '')
            
            # ------------------------------------------------------------------
            # Save staff (staff ID is already auto-generated in form)
            # ------------------------------------------------------------------
            logger.info("About to save staff...")
            staff.save()
            logger.info(f"Staff saved successfully! ID: {staff.pk}, Staff ID: {staff.staff_id}")
            
            # ------------------------------------------------------------------
            # Step 6: Designation assignment (optional)
            # ------------------------------------------------------------------
            create_designation = form_data.get('create_designation', False)
            
            if create_designation:
                designation = form_data.get('designation')
                if designation:
                    staff_designation = StaffDesignation.objects.create(
                        staff=staff,
                        designation=designation,
                        is_primary=form_data.get('is_primary_designation', True),
                        role_allowance=form_data.get('role_allowance', 0),
                        assignment_type='PERMANENT',
                        is_active=True,
                    )
                    logger.info(f"Designation assigned: {staff_designation}")
            
            # ------------------------------------------------------------------
            # Step 7: Contract creation (optional)
            # ------------------------------------------------------------------
            create_contract = form_data.get('create_contract', False)
            
            if create_contract:
                contract_type = form_data.get('contract_type')
                if contract_type:
                    from .utils import generate_contract_number
                    from datetime import timedelta
                    
                    start_date = form_data.get('contract_start_date')
                    duration_months = form_data.get('contract_duration_months', 12)
                    end_date = start_date + timedelta(days=duration_months * 30)
                    
                    contract = Contract.objects.create(
                        staff=staff,
                        contract_type=contract_type,
                        contract_number=generate_contract_number(contract_type),
                        status='DRAFT',
                        start_date=start_date,
                        end_date=end_date,
                        basic_salary=form_data.get('basic_salary', 0),
                        salary_frequency='MONTHLY',
                        job_title=form_data.get('job_title', ''),
                        working_hours_per_week=40,
                        annual_leave_days=21,
                    )
                    logger.info(f"Contract created: {contract.contract_number}")
            
            # ------------------------------------------------------------------
            # Success
            # ------------------------------------------------------------------
            logger.info("=" * 80)
            logger.info("STAFF CREATED SUCCESSFULLY!")
            logger.info(f"Staff: {staff.full_name()}")
            logger.info(f"ID: {staff.pk}")
            logger.info(f"Staff ID: {staff.staff_id}")
            logger.info("=" * 80)
            
            messages.success(
                self.request,
                f"Staff member {staff.full_name()} "
                f"(Staff ID: {staff.staff_id}) was created successfully!"
            )
            
            return redirect('hr:staff_profile', pk=staff.pk)
        
        except Exception as exc:
            logger.exception("=" * 80)
            logger.exception("ERROR IN WIZARD DONE METHOD:")
            logger.exception(exc)
            logger.exception("=" * 80)
            
            messages.error(
                self.request,
                f"Error creating staff member: {exc}"
            )
            return redirect('hr:staff_list')


# View entry point
staff_create_wizard = StaffCreateWizard.as_view()


@login_required
def staff_update(request, pk):
    """Update existing staff member"""
    
    staff = get_object_or_404(Staff, pk=pk)
    
    if request.method == 'POST':
        form = StaffForm(request.POST, request.FILES, instance=staff)
        if form.is_valid():
            staff = form.save()
            messages.success(request, f'Staff member "{staff.full_name()}" updated successfully.')
            return redirect('hr:staff_profile', pk=staff.pk)
    else:
        form = StaffForm(instance=staff)
    
    context = {
        'form': form,
        'staff': staff,
        'form_action': 'Update',
        'title': f'Update {staff.full_name()}'
    }
    
    return render(request, 'staff/form.html', context)


@login_required
def staff_profile(request, pk):
    """View staff member profile with comprehensive information"""
    
    staff = get_object_or_404(
        Staff.objects.select_related('primary_department').prefetch_related(
            'designations', 'contracts', 'teacher'
        ),
        pk=pk
    )
    
    # Get related data
    designations = StaffDesignation.objects.filter(
        staff=staff, is_active=True
    ).select_related('designation', 'designation__department')
    
    contracts = Contract.objects.filter(staff=staff).order_by('-start_date')
    current_contract = contracts.filter(status='ACTIVE').first()
    
    # Check if teacher
    is_teacher = hasattr(staff, 'teacher')
    teacher_info = staff.teacher if is_teacher else None
    
    # Get staff-specific statistics
    from .utils import (
        get_staff_age, get_years_of_service,
        get_days_until_birthday, is_staff_due_for_retirement
    )
    
    staff_stats = {
        'age': get_staff_age(staff),
        'years_of_service': get_years_of_service(staff),
        'days_until_birthday': get_days_until_birthday(staff),
        'retirement_info': is_staff_due_for_retirement(staff),
    }
    
    context = {
        'staff': staff,
        'designations': designations,
        'contracts': contracts,
        'current_contract': current_contract,
        'is_teacher': is_teacher,
        'teacher_info': teacher_info,
        'stats': staff_stats,
    }
    
    return render(request, 'hr/staff/profile.html', context)


@login_required
def staff_delete(request, pk):
    """Delete a staff member safely"""
    
    staff = get_object_or_404(Staff, pk=pk)
    
    # Check if staff has active contracts
    active_contracts = Contract.objects.filter(staff=staff, status='ACTIVE').count()
    if active_contracts > 0:
        messages.error(request, f'Cannot delete staff member with {active_contracts} active contract(s).')
        return redirect('hr:staff_list')
    
    if request.method == "POST":
        staff_name = staff.full_name()
        staff.delete()
        messages.success(request, f'Staff member "{staff_name}" deleted successfully.')
        return redirect('hr:staff_list')
    
    # For GET requests, just redirect to list (modal handles confirmation)
    return redirect('hr:staff_list')


# =============================================================================
# DEPARTMENT VIEWS
# =============================================================================

@login_required
def department_list(request):
    """List all departments with statistics"""
    
    departments_queryset = Department.objects.annotate(
        staff_count=Count('primary_staff', filter=Q(primary_staff__is_active=True))
    ).order_by('department_type', 'name')
    
    # Pagination
    departments_page, paginator = paginate_queryset(request, departments_queryset, per_page=15)
    
    # Get statistics from statistics module
    stats = get_department_statistics()
    
    context = {
        'departments': departments_page,
        'stats': stats,
    }
    
    return render(request, 'departments/list.html', context)


@login_required
def department_create(request):
    """Create a new department"""
    
    if request.method == 'POST':
        form = DepartmentForm(request.POST)
        if form.is_valid():
            department = form.save()
            messages.success(request, f'Department "{department.name}" created successfully.')
            return redirect('hr:department_detail', pk=department.pk)
    else:
        form = DepartmentForm()
    
    context = {
        'form': form,
        'form_action': 'Create',
        'title': 'Create Department'
    }
    
    return render(request, 'departments/form.html', context)


@login_required
def department_update(request, pk):
    """Update an existing department"""
    
    department = get_object_or_404(Department, pk=pk)
    
    if request.method == 'POST':
        form = DepartmentForm(request.POST, instance=department)
        if form.is_valid():
            department = form.save()
            messages.success(request, f'Department "{department.name}" updated successfully.')
            return redirect('hr:department_detail', pk=department.pk)
    else:
        form = DepartmentForm(instance=department)
    
    context = {
        'form': form,
        'department': department,
        'form_action': 'Update',
        'title': f'Update {department.name}'
    }
    
    return render(request, 'departments/form.html', context)


@login_required
def department_detail(request, pk):
    """View department details with staff list"""
    
    department = get_object_or_404(
        Department.objects.select_related('head', 'parent_department'),
        pk=pk
    )
    
    # Get staff in this department
    staff_members = Staff.objects.filter(
        primary_department=department,
        is_active=True
    ).order_by('last_name', 'first_name')
    
    # Get sub-departments
    sub_departments = Department.objects.filter(parent_department=department)
    
    # Get department-specific statistics
    dept_stats = {
        'total_staff': staff_members.count(),
        'sub_departments_count': sub_departments.count(),
    }
    
    context = {
        'department': department,
        'staff_members': staff_members,
        'sub_departments': sub_departments,
        'stats': dept_stats,
    }
    
    return render(request, 'departments/detail.html', context)


@login_required
def department_delete(request, pk):
    """Delete a department safely"""
    
    department = get_object_or_404(Department, pk=pk)
    
    # Check if department has staff
    staff_count = Staff.objects.filter(primary_department=department).count()
    if staff_count > 0:
        messages.error(request, f'Cannot delete department with {staff_count} staff member(s).')
        return redirect('hr:department_list')
    
    # Check if department has sub-departments
    sub_dept_count = Department.objects.filter(parent_department=department).count()
    if sub_dept_count > 0:
        messages.error(request, f'Cannot delete department with {sub_dept_count} sub-department(s).')
        return redirect('hr:department_list')
    
    if request.method == "POST":
        dept_name = department.name
        department.delete()
        messages.success(request, f'Department "{dept_name}" deleted successfully.')
        return redirect('hr:department_list')
    
    return redirect('hr:department_list')


# =============================================================================
# DESIGNATION VIEWS
# =============================================================================

@login_required
def designation_list(request):
    """List all designations with statistics"""
    
    designations_queryset = Designation.objects.select_related('department').annotate(
        staff_count=Count('staff_members', filter=Q(staffdesignation__is_active=True), distinct=True)
    ).order_by('rank_order', 'name')
    
    # Filter options
    departments = Department.objects.filter(is_active=True).order_by('name')
    
    # Pagination
    designations_page, paginator = paginate_queryset(request, designations_queryset, per_page=20)
    
    # Get statistics from statistics module
    stats = get_designation_statistics()
    
    context = {
        'designations': designations_page,
        'departments': departments,
        'stats': stats,
    }
    
    return render(request, 'designations/list.html', context)


@login_required
def designation_create(request):
    """Create a new designation"""
    
    if request.method == 'POST':
        form = DesignationForm(request.POST)
        if form.is_valid():
            designation = form.save()
            messages.success(request, f'Designation "{designation.name}" created successfully.')
            return redirect('hr:designation_detail', pk=designation.pk)
    else:
        form = DesignationForm()
    
    context = {
        'form': form,
        'form_action': 'Create',
        'title': 'Create Designation'
    }
    
    return render(request, 'hr/designations/form.html', context)


@login_required
def designation_update(request, pk):
    """Update an existing designation"""
    
    designation = get_object_or_404(Designation, pk=pk)
    
    if request.method == 'POST':
        form = DesignationForm(request.POST, instance=designation)
        if form.is_valid():
            designation = form.save()
            messages.success(request, f'Designation "{designation.name}" updated successfully.')
            return redirect('hr:designation_detail', pk=designation.pk)
    else:
        form = DesignationForm(instance=designation)
    
    context = {
        'form': form,
        'designation': designation,
        'form_action': 'Update',
        'title': f'Update {designation.name}'
    }
    
    return render(request, 'hr/designations/form.html', context)


@login_required
def designation_detail(request, pk):
    """View designation details with staff list"""
    
    designation = get_object_or_404(
        Designation.objects.select_related('department', 'reports_to'),
        pk=pk
    )
    
    # Get staff with this designation
    staff_assignments = StaffDesignation.objects.filter(
        designation=designation,
        is_active=True
    ).select_related('staff').order_by('-is_primary', 'staff__last_name')
    
    # Get salary reference range
    salary_range = designation.get_salary_reference_range()
    
    context = {
        'designation': designation,
        'staff_assignments': staff_assignments,
        'salary_range': salary_range,
    }
    
    return render(request, 'hr/designations/detail.html', context)


@login_required
def designation_delete(request, pk):
    """Delete a designation safely"""
    
    designation = get_object_or_404(Designation, pk=pk)
    
    # Check if designation is assigned to staff
    staff_count = StaffDesignation.objects.filter(
        designation=designation,
        is_active=True
    ).count()
    
    if staff_count > 0:
        messages.error(request, f'Cannot delete designation assigned to {staff_count} staff member(s).')
        return redirect('hr:designation_list')
    
    if request.method == "POST":
        designation_name = designation.name
        designation.delete()
        messages.success(request, f'Designation "{designation_name}" deleted successfully.')
        return redirect('hr:designation_list')
    
    return redirect('hr:designation_list')


# =============================================================================
# CONTRACT VIEWS
# =============================================================================

@login_required
def contract_list(request):
    """List all contracts with statistics"""
    
    contracts_queryset = Contract.objects.select_related(
        'staff', 'contract_type'
    ).order_by('-start_date')
    
    # Filter options
    contract_types = ContractType.objects.filter(is_active=True).order_by('name')
    
    # Pagination
    contracts_page, paginator = paginate_queryset(request, contracts_queryset, per_page=15)
    
    # Get statistics from statistics module
    stats = get_contract_statistics()
    
    context = {
        'contracts': contracts_page,
        'contract_types': contract_types,
        'stats': stats,
    }
    
    return render(request, 'contracts/list.html', context)


@login_required
def contract_create(request):
    """Create a new contract"""
    
    if request.method == 'POST':
        form = ContractForm(request.POST, request.FILES)
        if form.is_valid():
            contract = form.save()
            messages.success(request, f'Contract "{contract.contract_number}" created successfully.')
            return redirect('hr:contract_detail', pk=contract.pk)
    else:
        form = ContractForm()
    
    context = {
        'form': form,
        'form_action': 'Create',
        'title': 'Create Contract'
    }
    
    return render(request, 'contracts/form.html', context)


@login_required
def contract_update(request, pk):
    """Update an existing contract"""
    
    contract = get_object_or_404(Contract, pk=pk)
    
    if request.method == 'POST':
        form = ContractForm(request.POST, request.FILES, instance=contract)
        if form.is_valid():
            contract = form.save()
            messages.success(request, f'Contract "{contract.contract_number}" updated successfully.')
            return redirect('hr:contract_detail', pk=contract.pk)
    else:
        form = ContractForm(instance=contract)
    
    context = {
        'form': form,
        'contract': contract,
        'form_action': 'Update',
        'title': f'Update Contract {contract.contract_number}'
    }
    
    return render(request, 'contracts/form.html', context)


@login_required
def contract_detail(request, pk):
    """View contract details"""
    
    contract = get_object_or_404(
        Contract.objects.select_related('staff', 'contract_type', 'reporting_to'),
        pk=pk
    )
    
    # Calculate salary information
    from .utils import calculate_monthly_salary, calculate_annual_salary
    
    salary_info = {
        'monthly_salary': calculate_monthly_salary(contract),
        'annual_salary': calculate_annual_salary(contract),
    }
    
    context = {
        'contract': contract,
        'salary_info': salary_info,
    }
    
    return render(request, 'contracts/detail.html', context)


@login_required
def contract_delete(request, pk):
    """Delete a contract safely"""
    
    contract = get_object_or_404(Contract, pk=pk)
    
    # Only allow deletion of draft contracts
    if contract.status not in ['DRAFT', 'CANCELLED']:
        messages.error(
            request,
            f'Cannot delete contract in {contract.get_status_display()} status. '
            'Only DRAFT or CANCELLED contracts can be deleted.'
        )
        return redirect('hr:contract_list')
    
    if request.method == "POST":
        contract_number = contract.contract_number
        contract.delete()
        messages.success(request, f'Contract "{contract_number}" deleted successfully.')
        return redirect('hr:contract_list')
    
    return redirect('hr:contract_list')

# =============================================================================
# CONTRACT TYPE VIEWS
# =============================================================================

@login_required
def contract_type_list(request):
    """List all contract types"""
    
    contract_types_queryset = ContractType.objects.annotate(
        contract_count=Count('contracts')
    ).order_by('name')
    
    # Pagination
    contract_types_page, paginator = paginate_queryset(request, contract_types_queryset, per_page=15)
    
    # Get statistics from statistics module
    stats = get_contract_type_statistics()
    
    context = {
        'contract_types': contract_types_page,
        'stats': stats,
    }
    
    return render(request, 'contract/types_list.html', context)


@login_required
def contract_type_create(request):
    """Create a new contract type"""
    
    if request.method == 'POST':
        form = ContractTypeForm(request.POST)
        if form.is_valid():
            contract_type = form.save()
            messages.success(request, f'Contract type "{contract_type.name}" created successfully.')
            return redirect('hr:contract_type_detail', pk=contract_type.pk)
    else:
        form = ContractTypeForm()
    
    context = {
        'form': form,
        'form_action': 'Create',
        'title': 'Create Contract Type'
    }
    
    return render(request, 'contract/types_form.html', context)


@login_required
def contract_type_update(request, pk):
    """Update an existing contract type"""
    
    contract_type = get_object_or_404(ContractType, pk=pk)
    
    if request.method == 'POST':
        form = ContractTypeForm(request.POST, instance=contract_type)
        if form.is_valid():
            contract_type = form.save()
            messages.success(request, f'Contract type "{contract_type.name}" updated successfully.')
            return redirect('hr:contract_type_detail', pk=contract_type.pk)
    else:
        form = ContractTypeForm(instance=contract_type)
    
    context = {
        'form': form,
        'contract_type': contract_type,
        'form_action': 'Update',
        'title': f'Update {contract_type.name}'
    }
    
    return render(request, 'contract/types_form.html', context)


@login_required
def contract_type_detail(request, pk):
    """View contract type details with contracts using it"""
    
    contract_type = get_object_or_404(ContractType, pk=pk)
    
    # Get contracts using this type
    contracts = Contract.objects.filter(
        contract_type=contract_type
    ).select_related('staff').order_by('-start_date')[:20]
    
    # Get contract type statistics
    contract_type_stats = {
        'total_contracts': Contract.objects.filter(contract_type=contract_type).count(),
        'active_contracts': Contract.objects.filter(
            contract_type=contract_type,
            status='ACTIVE'
        ).count(),
        'draft_contracts': Contract.objects.filter(
            contract_type=contract_type,
            status='DRAFT'
        ).count(),
        'expired_contracts': Contract.objects.filter(
            contract_type=contract_type,
            status='EXPIRED'
        ).count(),
    }
    
    context = {
        'contract_type': contract_type,
        'contracts': contracts,
        'stats': contract_type_stats,
    }
    
    return render(request, 'contract/types_detail.html', context)


@login_required
def contract_type_delete(request, pk):
    """Delete a contract type safely"""
    
    contract_type = get_object_or_404(ContractType, pk=pk)
    
    # Check if contract type is used by any contracts
    contract_count = Contract.objects.filter(contract_type=contract_type).count()
    
    if contract_count > 0:
        messages.error(
            request, 
            f'Cannot delete contract type used by {contract_count} contract(s). '
            'Please reassign or delete those contracts first.'
        )
        return redirect('hr:contract_type_list')
    
    if request.method == "POST":
        type_name = contract_type.name
        contract_type.delete()
        messages.success(request, f'Contract type "{type_name}" deleted successfully.')
        return redirect('hr:contract_type_list')
    
    return redirect('hr:contract_type_list')


# =============================================================================
# TEACHER VIEWS
# =============================================================================

@login_required
def teacher_list(request):
    """List all teachers with statistics"""
    
    teachers_queryset = Teacher.objects.select_related(
        'staff', 'staff__primary_department'
    ).filter(staff__is_active=True).order_by('staff__last_name')
    
    # Pagination
    teachers_page, paginator = paginate_queryset(request, teachers_queryset, per_page=15)
    
    # Get statistics from statistics module
    stats = get_teacher_statistics()
    
    context = {
        'teachers': teachers_page,
        'stats': stats,
    }
    
    return render(request, 'hr/teachers/list.html', context)


@login_required
def teacher_create(request):
    """Create a new teacher profile"""
    
    if request.method == 'POST':
        form = TeacherForm(request.POST)
        if form.is_valid():
            teacher = form.save()
            messages.success(request, f'Teacher profile for "{teacher.staff.full_name()}" created successfully.')
            return redirect('hr:staff_profile', pk=teacher.staff.pk)
    else:
        form = TeacherForm()
    
    context = {
        'form': form,
        'form_action': 'Create',
        'title': 'Create Teacher Profile'
    }
    
    return render(request, 'hr/teachers/form.html', context)


@login_required
def teacher_update(request, pk):
    """Update an existing teacher profile"""
    
    teacher = get_object_or_404(Teacher, pk=pk)
    
    if request.method == 'POST':
        form = TeacherForm(request.POST, instance=teacher)
        if form.is_valid():
            teacher = form.save()
            messages.success(request, f'Teacher profile for "{teacher.staff.full_name()}" updated successfully.')
            return redirect('hr:staff_profile', pk=teacher.staff.pk)
    else:
        form = TeacherForm(instance=teacher)
    
    context = {
        'form': form,
        'teacher': teacher,
        'form_action': 'Update',
        'title': f'Update Teacher Profile for {teacher.staff.full_name()}'
    }
    
    return render(request, 'hr/teachers/form.html', context)


@login_required
def teacher_delete(request, pk):
    """Delete a teacher profile"""
    
    teacher = get_object_or_404(Teacher, pk=pk)
    staff = teacher.staff
    
    if request.method == "POST":
        teacher_name = staff.full_name()
        teacher.delete()
        messages.success(request, f'Teacher profile for "{teacher_name}" deleted successfully.')
        return redirect('hr:staff_profile', pk=staff.pk)
    
    return redirect('hr:staff_profile', pk=staff.pk)


# =============================================================================
# EXPORT VIEWS - STAFF
# =============================================================================

@login_required
def export_staff_excel(request):
    """Export staff to Excel with filters applied"""
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    gender = request.GET.get('gender', '')
    department = request.GET.get('department', '')
    employment_status = request.GET.get('employment_status', '')
    is_teaching = request.GET.get('is_teaching', '')
    
    # Apply filters
    staff = Staff.objects.all().select_related('primary_department').order_by('staff_id')
    
    if query:
        terms = query.split()
        q_objects = Q()
        for term in terms:
            q_objects &= (
                Q(first_name__icontains=term) |
                Q(middle_name__icontains=term) |
                Q(last_name__icontains=term) |
                Q(staff_id__icontains=term) |
                Q(personal_email__icontains=term)
            )
        staff = staff.filter(q_objects)
    
    if gender:
        staff = staff.filter(gender=gender)
    if department:
        staff = staff.filter(primary_department_id=department)
    if employment_status:
        staff = staff.filter(employment_status=employment_status)
    if is_teaching:
        if is_teaching.lower() == 'true':
            teacher_staff_ids = Teacher.objects.values_list('staff_id', flat=True)
            staff = staff.filter(id__in=teacher_staff_ids)
        elif is_teaching.lower() == 'false':
            teacher_staff_ids = Teacher.objects.values_list('staff_id', flat=True)
            staff = staff.exclude(id__in=teacher_staff_ids)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Staff Directory"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    
    border_style = Border(
        left=Side(style='thin', color='000000'),
        right=Side(style='thin', color='000000'),
        top=Side(style='thin', color='000000'),
        bottom=Side(style='thin', color='000000')
    )
    
    # Title row
    ws.merge_cells('A1:K1')
    title_cell = ws['A1']
    title_cell.value = "Staff Directory Report"
    title_cell.font = Font(bold=True, size=16, color="4472C4")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # Subtitle with date and filters
    ws.merge_cells('A2:K2')
    subtitle_cell = ws['A2']
    filter_text = f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    if query:
        filter_text += f" | Search: {query}"
    if gender:
        filter_text += f" | Gender: {dict(Staff.GENDER_CHOICES).get(gender)}"
    if employment_status:
        filter_text += f" | Status: {dict(Staff.EMPLOYMENT_STATUS_CHOICES).get(employment_status)}"
    
    subtitle_cell.value = filter_text
    subtitle_cell.font = Font(size=10, italic=True)
    subtitle_cell.alignment = Alignment(horizontal="center")
    
    ws.append([])  # Empty row
    
    # Headers
    headers = [
        '#', 'Staff ID', 'Full Name', 'Gender', 'Date of Birth', 'Age',
        'Department', 'Employment Status', 'Date of Joining', 'Phone', 'Email'
    ]
    
    ws.append(headers)
    header_row = ws[4]
    
    for cell in header_row:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = border_style
    
    # Data rows
    from .utils import get_staff_age
    
    for idx, s in enumerate(staff, start=1):
        is_teacher = Teacher.objects.filter(staff=s).exists()
        
        row_data = [
            idx,
            s.staff_id,
            s.full_name(),
            s.get_gender_display(),
            s.date_of_birth.strftime('%Y-%m-%d') if s.date_of_birth else '',
            get_staff_age(s) or '',
            s.primary_department.name if s.primary_department else 'Not Assigned',
            s.get_employment_status_display(),
            s.date_of_joining.strftime('%Y-%m-%d') if s.date_of_joining else '',
            s.phone_number or '',
            s.personal_email or '',
        ]
        
        ws.append(row_data)
        
        # Style data rows
        current_row = ws.max_row
        for cell in ws[current_row]:
            cell.border = border_style
            cell.alignment = Alignment(vertical="center", wrap_text=True)
    
    # Adjust column widths
    column_widths = {
        'A': 5, 'B': 15, 'C': 25, 'D': 10, 'E': 12, 'F': 8,
        'G': 20, 'H': 18, 'I': 15, 'J': 15, 'K': 25
    }
    
    for col, width in column_widths.items():
        ws.column_dimensions[col].width = width
    
    # Summary at bottom
    summary_row = ws.max_row + 2
    ws[f'A{summary_row}'] = 'Total Staff:'
    ws[f'B{summary_row}'] = staff.count()
    ws[f'A{summary_row}'].font = Font(bold=True)
    ws[f'B{summary_row}'].font = Font(bold=True)
    
    # Additional statistics
    active_count = staff.filter(is_active=True).count()
    male_count = staff.filter(gender='M').count()
    female_count = staff.filter(gender='F').count()
    
    ws[f'A{summary_row + 1}'] = 'Active Staff:'
    ws[f'B{summary_row + 1}'] = active_count
    ws[f'A{summary_row + 1}'].font = Font(bold=True)
    
    ws[f'A{summary_row + 2}'] = 'Male:'
    ws[f'B{summary_row + 2}'] = male_count
    ws[f'A{summary_row + 2}'].font = Font(bold=True)
    
    ws[f'A{summary_row + 3}'] = 'Female:'
    ws[f'B{summary_row + 3}'] = female_count
    ws[f'A{summary_row + 3}'].font = Font(bold=True)
    
    # Freeze panes (header row)
    ws.freeze_panes = 'A5'
    
    # Create response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"staff_directory_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
def export_staff_pdf(request):
    """Export staff to PDF with filters applied"""
    
    # Get filter parameters (same as Excel export)
    query = request.GET.get('q', '').strip()
    gender = request.GET.get('gender', '')
    department = request.GET.get('department', '')
    employment_status = request.GET.get('employment_status', '')
    is_teaching = request.GET.get('is_teaching', '')
    
    # Apply filters
    staff = Staff.objects.all().select_related('primary_department').order_by('staff_id')
    
    if query:
        terms = query.split()
        q_objects = Q()
        for term in terms:
            q_objects &= (
                Q(first_name__icontains=term) |
                Q(middle_name__icontains=term) |
                Q(last_name__icontains=term) |
                Q(staff_id__icontains=term)
            )
        staff = staff.filter(q_objects)
    
    if gender:
        staff = staff.filter(gender=gender)
    if department:
        staff = staff.filter(primary_department_id=department)
    if employment_status:
        staff = staff.filter(employment_status=employment_status)
    if is_teaching:
        if is_teaching.lower() == 'true':
            teacher_staff_ids = Teacher.objects.values_list('staff_id', flat=True)
            staff = staff.filter(id__in=teacher_staff_ids)
        elif is_teaching.lower() == 'false':
            teacher_staff_ids = Teacher.objects.values_list('staff_id', flat=True)
            staff = staff.exclude(id__in=teacher_staff_ids)
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=18,
    )
    
    # Container for PDF elements
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#4472C4'),
        spaceAfter=12,
        alignment=TA_CENTER,
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.grey,
        spaceAfter=20,
        alignment=TA_CENTER,
    )
    
    # Title
    title = Paragraph("Staff Directory Report", title_style)
    elements.append(title)
    
    # Subtitle with filters
    filter_text = f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    if query:
        filter_text += f" | Search: {query}"
    if gender:
        filter_text += f" | Gender: {dict(Staff.GENDER_CHOICES).get(gender)}"
    if employment_status:
        filter_text += f" | Status: {dict(Staff.EMPLOYMENT_STATUS_CHOICES).get(employment_status)}"
    
    subtitle = Paragraph(filter_text, subtitle_style)
    elements.append(subtitle)
    elements.append(Spacer(1, 0.2*inch))
    
    # Table data
    from .utils import get_staff_age
    
    data = [['#', 'Staff ID', 'Full Name', 'Gender', 'Age', 'Department', 'Status', 'Phone']]
    
    for idx, s in enumerate(staff, start=1):
        row = [
            str(idx),
            s.staff_id,
            s.full_name()[:30],  # Truncate long names
            s.get_gender_display(),
            str(get_staff_age(s) or ''),
            str(s.primary_department)[:20] if s.primary_department else 'N/A',
            s.get_employment_status_display()[:12],
            s.phone_number[:15] if s.phone_number else ''
        ]
        data.append(row)
    
    # Create table
    table = Table(data, colWidths=[
        0.4*inch,  # #
        1*inch,    # Staff ID
        2*inch,    # Full Name
        0.8*inch,  # Gender
        0.6*inch,  # Age
        1.5*inch,  # Department
        1.2*inch,  # Status
        1*inch,    # Phone
    ])
    
    # Table style
    table.setStyle(TableStyle([
        # Header
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        
        # Data rows
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # # column
        ('ALIGN', (4, 1), (4, -1), 'CENTER'),  # Age column
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        
        # Alternating row colors
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
        
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    
    elements.append(table)
    
    # Summary
    elements.append(Spacer(1, 0.3*inch))
    
    active_count = staff.filter(is_active=True).count()
    male_count = staff.filter(gender='M').count()
    female_count = staff.filter(gender='F').count()
    
    summary_text = f"""
    <b>Summary Statistics:</b><br/>
    Total Staff: {staff.count()}<br/>
    Active Staff: {active_count}<br/>
    Male: {male_count}<br/>
    Female: {female_count}
    """
    
    summary = Paragraph(summary_text, styles['Normal'])
    elements.append(summary)
    
    # Build PDF
    doc.build(elements)
    
    # Get PDF value
    pdf = buffer.getvalue()
    buffer.close()
    
    # Create response
    response = HttpResponse(content_type='application/pdf')
    filename = f"staff_directory_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write(pdf)
    
    return response