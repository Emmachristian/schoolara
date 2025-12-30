# students/views.py

"""
Student Management Views

Comprehensive view functions for:
- Student Registration and Profile Management (using Wizard)
- Guardian Management
- Student-Guardian Relationships
- Sibling Relationships
- Enrollment Status Tracking
- Reports and Analytics

All views delegate business logic to services.py where appropriate
Uses stats.py for comprehensive statistics and analytics
Uses SweetAlert2 for all notifications via Django messages
Preserves SessionWizardView for student registration
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count, Sum, Avg, Prefetch
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.core.files.storage import FileSystemStorage
from formtools.wizard.views import SessionWizardView
from datetime import timedelta, date, datetime
from decimal import Decimal
import os
import logging

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from io import BytesIO

from .models import (
    Student,
    Guardian,
    StudentGuardian,
    SiblingRelationship,
    EnrollmentStatusHistory,
)

from .forms import (
    STUDENT_WIZARD_FORMS,
    STUDENT_WIZARD_STEP_NAMES,
    StudentForm,
    GuardianForm,
    StudentGuardianForm,
    StudentFilterForm,
    GuardianFilterForm,
)

# Import stats functions
from . import stats as student_stats

from core.utils import format_money, get_school_today

logger = logging.getLogger(__name__)


# =============================================================================
# DASHBOARD
# =============================================================================

@login_required
def students_dashboard(request):
    """Main students dashboard with overview statistics - USES stats.py"""
    
    try:
        # Get comprehensive statistics
        student_statistics = student_stats.get_student_statistics()
        guardian_statistics = student_stats.get_guardian_statistics()
        sibling_statistics = student_stats.get_sibling_statistics()
        family_statistics = student_stats.get_family_statistics()
        
    except Exception as e:
        logger.error(f"Error getting dashboard statistics: {e}")
        student_statistics = {}
        guardian_statistics = {}
        sibling_statistics = {}
        family_statistics = {}
    
    # Get recent activities (limited queries for display)
    recent_students = Student.objects.select_related(
        'current_academic_level'
    ).order_by('-created_at')[:10]
    
    pending_approval = Student.objects.filter(
        enrollment_status='PENDING_APPROVAL'
    ).order_by('admission_date')[:10]
    
    # Get students needing attention
    students_without_guardians = Student.objects.filter(
        enrollment_status='ACTIVE'
    ).annotate(
        guardian_count=Count('guardians')
    ).filter(guardian_count=0).order_by('admission_date')[:10]
    
    medical_alerts = Student.objects.filter(
        enrollment_status='ACTIVE'
    ).filter(
        Q(medical_conditions__isnull=False) & ~Q(medical_conditions='') |
        Q(allergies__isnull=False) & ~Q(allergies='') |
        Q(has_special_needs=True)
    ).order_by('-updated_at')[:10]
    
    # Get birthdays this week
    today = get_school_today()
    week_from_now = today + timedelta(days=7)
    
    upcoming_birthdays = Student.objects.filter(
        enrollment_status='ACTIVE',
        date_of_birth__month=today.month,
        date_of_birth__day__gte=today.day,
        date_of_birth__day__lte=week_from_now.day
    ).order_by('date_of_birth__day')[:10]
    
    # Recent status changes
    recent_status_changes = EnrollmentStatusHistory.objects.select_related(
        'student', 'academic_session'
    ).order_by('-effective_date')[:10]
    
    context = {
        'student_statistics': student_statistics,
        'guardian_statistics': guardian_statistics,
        'sibling_statistics': sibling_statistics,
        'family_statistics': family_statistics,
        'recent_students': recent_students,
        'pending_approval': pending_approval,
        'students_without_guardians': students_without_guardians,
        'medical_alerts': medical_alerts,
        'upcoming_birthdays': upcoming_birthdays,
        'recent_status_changes': recent_status_changes,
    }
    
    return render(request, 'students/dashboard.html', context)


# =============================================================================
# STUDENT VIEWS
# =============================================================================

@login_required
def student_list(request):
    """List all students - HTMX loads data on page load"""
    
    # Initialize filter form
    filter_form = StudentFilterForm()
    
    # Get initial stats from stats.py
    try:
        initial_stats = student_stats.get_student_statistics()
    except Exception as e:
        logger.error(f"Error getting student statistics: {e}")
        initial_stats = {}
    
    context = {
        'filter_form': filter_form,
        'stats': initial_stats,
        'Student': Student,
    }
    
    return render(request, 'students/list.html', context)


@login_required
def student_print_view(request):
    """Generate printable student list with selected fields"""
    
    # Get selected fields from the modal
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        # Default fields if none selected
        selected_fields = [
            'admission_number', 'full_name', 'date_of_birth', 'gender',
            'current_academic_level', 'enrollment_status', 'phone_number'
        ]
    
    # Get additional options
    include_stats = request.GET.get('include_stats') == 'true'
    landscape_mode = request.GET.get('landscape') == 'true'
    
    # Get filter parameters from URL
    query = request.GET.get('q', '')
    enrollment_status = request.GET.get('enrollment_status', '')
    gender = request.GET.get('gender', '')
    current_academic_level = request.GET.get('current_academic_level', '')
    has_special_needs = request.GET.get('has_special_needs', '')
    
    # Build queryset
    students = Student.objects.select_related(
        'current_academic_level',
        'admission_academic_level'
    ).order_by('admission_number')
    
    # Apply filters (same as student_search in htmx_views.py)
    if query:
        students = students.filter(
            Q(admission_number__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(phone_number__icontains=query) |
            Q(personal_email__icontains=query)
        )
    
    if enrollment_status:
        students = students.filter(enrollment_status=enrollment_status)
    
    if gender:
        students = students.filter(gender=gender)
    
    if current_academic_level:
        students = students.filter(current_academic_level_id=current_academic_level)
    
    if has_special_needs:
        students = students.filter(has_special_needs=(has_special_needs.lower() == 'true'))
    
    # Calculate stats only if requested
    stats = None
    if include_stats:
        total = students.count()
        active_count = students.filter(enrollment_status='ACTIVE').count()
        
        stats = {
            'total': total,
            'active': active_count,
            'active_percentage': round((active_count / total * 100), 1) if total > 0 else 0,
            'male': students.filter(gender='M').count(),
            'female': students.filter(gender='F').count(),
            'special_needs': students.filter(has_special_needs=True).count(),
        }
    
    # Field display names mapping
    field_names = {
        'admission_number': 'Admission Number',
        'full_name': 'Full Name',
        'first_name': 'First Name',
        'last_name': 'Last Name',
        'national_student_number': 'National Student Number',
        'date_of_birth': 'Date of Birth',
        'age': 'Age',
        'gender': 'Gender',
        'nationality': 'Nationality',
        'phone_number': 'Phone',
        'personal_email': 'Email',
        'home_address': 'Home Address',
        'current_academic_level': 'Current Grade/Class',
        'admission_academic_level': 'Admission Grade/Class',
        'enrollment_status': 'Status',
        'admission_date': 'Admission Date',
        'health_condition': 'Health',
        'has_special_needs': 'Special Needs',
        'transportation_required': 'Transport',
        'religious_affiliation': 'Religion',
    }
    
    # Create ordered list of field display names for template
    selected_field_names = [
        field_names.get(field, field.replace('_', ' ').title()) 
        for field in selected_fields
    ]
    
    context = {
        'students': students,
        'stats': stats,
        'now': timezone.now(),
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'field_names': field_names,
        'landscape': landscape_mode,
    }
    
    return render(request, 'students/print.html', context)


# =============================================================================
# STUDENT WIZARD FOR CREATION
# =============================================================================

class StudentWizardFileStorage(FileSystemStorage):
    """Custom storage for handling file uploads in wizard"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.location = os.path.join(self.location, 'wizard_temp')


class StudentCreateWizard(SessionWizardView):
    """
    Multi-step wizard for creating a student.
    
    Steps:
    1. Basic Information - personal details and identification
    2. Contact Information - address and contact details
    3. Academic Information - academic level and previous education
    4. Health Information - medical and health details
    5. Guardian Information - primary guardian (optional)
    6. Confirmation - review and confirm
    
    Note: Admission number is automatically generated by pre_save signal in signals.py
    """

    form_list = STUDENT_WIZARD_FORMS
    template_name = 'students/wizard.html'
    file_storage = StudentWizardFileStorage()

    def get_template_names(self):
        """Return the template for all steps"""
        return [self.template_name]

    def get_context_data(self, form, **kwargs):
        """Add step names and progress tracking"""
        context = super().get_context_data(form=form, **kwargs)

        total_steps = len(self.form_list)
        current_step_index = list(self.form_list).index(self.steps.current)

        context.update({
            'step_names': STUDENT_WIZARD_STEP_NAMES,
            'current_step_name': STUDENT_WIZARD_STEP_NAMES.get(
                self.steps.current, 'Step'
            ),
            'progress_percentage': ((current_step_index) / (total_steps - 1)) * 100 if total_steps > 1 else 100,
        })

        # Add review data for confirmation step
        if self.steps.current == 'confirmation':
            context['basic_data'] = self.get_cleaned_data_for_step('basic_info')
            context['contact_data'] = self.get_cleaned_data_for_step('contact_info')
            context['academic_data'] = self.get_cleaned_data_for_step('academic_info')
            context['health_data'] = self.get_cleaned_data_for_step('health_info')
            context['guardian_data'] = self.get_cleaned_data_for_step('guardian_info')

        return context

    def get_form_kwargs(self, step=None):
        """Pass additional kwargs to forms if needed"""
        kwargs = super().get_form_kwargs(step)
        # Don't pass user/request to avoid compatibility issues with BaseModelForm
        # Forms can access these via self.request if needed in done() method
        return kwargs

    @transaction.atomic
    def done(self, form_list, **kwargs):
        """
        Persist all wizard data and create student.
        Admission number generation is handled automatically by the pre_save signal
        in signals.py (generate_admission_number function).
        """
        
        logger.info("=" * 80)
        logger.info("WIZARD DONE - Creating Student")
        logger.info("=" * 80)

        try:
            # Merge cleaned data from all steps
            form_data = {}
            
            for step, form in zip(self.form_list.keys(), form_list):
                form_data.update(form.cleaned_data)

            # ------------------------------------------------------------------
            # Create Student
            # ------------------------------------------------------------------
            student = Student(
                # Basic info
                first_name=form_data.get('first_name'),
                middle_name=form_data.get('middle_name', ''),
                last_name=form_data.get('last_name'),
                date_of_birth=form_data.get('date_of_birth'),
                gender=form_data.get('gender'),
                admission_date=form_data.get('admission_date'),
                national_student_number=form_data.get('national_student_number', ''),
                birth_certificate_number=form_data.get('birth_certificate_number', ''),
                nationality=form_data.get('nationality', ''),
                ethnicity=form_data.get('ethnicity', ''),
                birth_place=form_data.get('birth_place', ''),
                birth_country=form_data.get('birth_country', ''),
                religious_affiliation=form_data.get('religious_affiliation', ''),
                
                # Contact info
                personal_email=form_data.get('personal_email', ''),
                phone_number=form_data.get('phone_number', ''),
                home_address=form_data.get('home_address'),
                mailing_address=form_data.get('mailing_address', ''),
                district=form_data.get('district', ''),
                region=form_data.get('region', ''),
                country_of_residence=form_data.get('country_of_residence', ''),
                transportation_required=form_data.get('transportation_required', False),
                transport_route=form_data.get('transport_route', ''),
                pickup_point=form_data.get('pickup_point', ''),
                pickup_time=form_data.get('pickup_time'),
                
                # Academic info
                current_academic_level=form_data.get('current_academic_level'),
                admission_academic_level=form_data.get('admission_academic_level'),
                enrollment_status=form_data.get('enrollment_status', 'ACTIVE'),
                previous_school=form_data.get('previous_school', ''),
                previous_school_address=form_data.get('previous_school_address', ''),
                previous_academic_level=form_data.get('previous_academic_level'),
                transfer_reason=form_data.get('transfer_reason', ''),
                transfer_certificate_number=form_data.get('transfer_certificate_number', ''),
                previous_school_completion_date=form_data.get('previous_school_completion_date'),
                
                # Health info
                health_condition=form_data.get('health_condition', 'GOOD'),
                blood_type=form_data.get('blood_type', 'UNKNOWN'),
                medical_conditions=form_data.get('medical_conditions', ''),
                allergies=form_data.get('allergies', ''),
                medications=form_data.get('medications', ''),
                special_medical_needs=form_data.get('special_medical_needs', ''),
                emergency_medical_contact=form_data.get('emergency_medical_contact', ''),
                preferred_hospital=form_data.get('preferred_hospital', ''),
                medical_insurance=form_data.get('medical_insurance', ''),
                insurance_policy_number=form_data.get('insurance_policy_number', ''),
                has_special_needs=form_data.get('has_special_needs', False),
                special_needs_description=form_data.get('special_needs_description', ''),
                learning_disabilities=form_data.get('learning_disabilities', ''),
                learning_accommodations=form_data.get('learning_accommodations', ''),
                requires_special_diet=form_data.get('requires_special_diet', False),
                special_diet_details=form_data.get('special_diet_details', ''),
            )
            
            # Note: admission_number is NOT set here - it will be auto-generated
            # by the pre_save signal in signals.py
            
            student.save()

            # ------------------------------------------------------------------
            # Handle Guardian
            # ------------------------------------------------------------------
            guardian_option = form_data.get('guardian_option', 'skip')
            
            if guardian_option == 'new':
                # Create new guardian
                guardian = Guardian.objects.create(
                    first_name=form_data.get('guardian_first_name'),
                    last_name=form_data.get('guardian_last_name'),
                    primary_phone=form_data.get('guardian_phone'),
                    email=form_data.get('guardian_email', ''),
                    home_address=form_data.get('guardian_address', ''),
                    occupation=form_data.get('guardian_occupation', ''),
                    guardian_type='PRIMARY',
                )
                
                # Create relationship
                StudentGuardian.objects.create(
                    student=student,
                    guardian=guardian,
                    relationship=form_data.get('relationship'),
                    is_primary=True,
                    is_financial_responsible=True,
                    emergency_contact_priority=1,
                )
                
                logger.info(f"Created new guardian: {guardian.get_full_name()}")
            
            elif guardian_option == 'existing':
                guardian = form_data.get('existing_guardian')
                if guardian:
                    StudentGuardian.objects.create(
                        student=student,
                        guardian=guardian,
                        relationship=form_data.get('relationship'),
                        is_primary=True,
                        is_financial_responsible=True,
                        emergency_contact_priority=1,
                    )
                    logger.info(f"Linked existing guardian: {guardian.get_full_name()}")

            # ------------------------------------------------------------------
            # Success - Admission number was auto-generated by signal
            # ------------------------------------------------------------------
            messages.success(
                self.request,
                f"Student {student.get_full_name()} "
                f"(#{student.admission_number}) was created successfully!",
                extra_tags='sweetalert'
            )

            return redirect('students:student_profile', pk=student.pk)

        except Exception as exc:
            logger.exception("Error in wizard done method:")
            logger.exception(exc)
            
            messages.error(
                self.request,
                f"Error creating student: {exc}",
                extra_tags='sweetalert-error'
            )
            return redirect('students:student_list')


# View entry point
student_create = StudentCreateWizard.as_view()


@login_required
def student_edit(request, pk):
    """Edit existing student"""
    student = get_object_or_404(Student, pk=pk)

    if request.method == "POST":
        form = StudentForm(request.POST, request.FILES, instance=student)
        if form.is_valid():
            student = form.save()
            
            messages.success(
                request,
                f"Student {student.get_full_name()} was updated successfully",
                extra_tags='sweetalert'
            )
            return redirect("students:student_profile", pk=student.pk)
        else:
            messages.error(
                request,
                "Please correct the errors in the form",
                extra_tags='sweetalert-error'
            )
    else:
        form = StudentForm(instance=student)

    context = {
        'form': form,
        'student': student,
        'title': 'Update Student',
    }

    return render(request, 'students/form.html', context)


@login_required
def student_profile(request, pk):
    """View student profile with all related information - USES stats.py"""
    student = get_object_or_404(
        Student.objects.prefetch_related(
            Prefetch(
                'guardian_relationships',
                queryset=StudentGuardian.objects.filter(is_active=True).select_related('guardian')
            ),
            'sibling_relationships',
            'reverse_sibling_relationships',
        ),
        pk=pk
    )

    # Get student summary
    try:
        summary = {
            'admission_number': student.admission_number,
            'full_name': student.get_full_name(),
            'status': student.get_enrollment_status_display(),
            'age': student.age,
            'years_in_school': student_stats.get_years_in_school(student),
            'days_until_birthday': student_stats.get_days_until_birthday(student),
            'is_birthday_today': student_stats.is_birthday_today(student),
            
            # Related counts
            'guardian_count': student.guardians.count(),
            'sibling_count': student_stats.get_sibling_count_for_student(student),
            'has_medical_alerts': student.has_medical_alert(),
        }
    except Exception as e:
        logger.error(f"Error getting student summary: {e}")
        summary = {}

    # Get related data
    guardians = student.guardian_relationships.filter(is_active=True)
    primary_guardian = guardians.filter(is_primary=True).first()
    emergency_contacts = guardians.filter(emergency_contact_priority__lte=5).order_by('emergency_contact_priority')
    
    # Sibling relationships
    siblings_forward = student.sibling_relationships.select_related('to_student__current_academic_level')
    siblings_reverse = student.reverse_sibling_relationships.select_related('from_student__current_academic_level')
    
    # Recent status changes
    status_history = student.status_history.select_related('academic_session').order_by('-effective_date')[:5]

    context = {
        'student': student,
        'summary': summary,
        'guardians': guardians,
        'primary_guardian': primary_guardian,
        'emergency_contacts': emergency_contacts,
        'siblings_forward': siblings_forward,
        'siblings_reverse': siblings_reverse,
        'status_history': status_history,
    }
    
    return render(request, "students/profile.html", context)


@login_required
def student_activate(request, pk):
    """Activate a student"""
    student = get_object_or_404(Student, pk=pk)
    
    if request.method == 'POST':
        student.enrollment_status = 'ACTIVE'
        student.save()
        
        messages.success(
            request,
            f"Student {student.get_full_name()} has been activated successfully",
            extra_tags='sweetalert'
        )
        
        return redirect('students:student_profile', pk=student.pk)
    
    return redirect('students:student_profile', pk=student.pk)


@login_required
def student_suspend(request, pk):
    """Suspend a student"""
    student = get_object_or_404(Student, pk=pk)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', 'No reason provided')
        
        student.enrollment_status = 'SUSPENDED'
        student.save()
        
        messages.warning(
            request,
            f"Student {student.get_full_name()} has been suspended",
            extra_tags='sweetalert'
        )
        
        return redirect('students:student_profile', pk=student.pk)
    
    return redirect('students:student_profile', pk=student.pk)


# =============================================================================
# GUARDIAN VIEWS
# =============================================================================

@login_required
def guardian_list(request):
    """List all guardians - HTMX loads data on page load"""
    
    filter_form = GuardianFilterForm()
    
    try:
        initial_stats = student_stats.get_guardian_statistics()
    except Exception as e:
        logger.error(f"Error getting guardian statistics: {e}")
        initial_stats = {}
    
    context = {
        'filter_form': filter_form,
        'stats': initial_stats,
        'Guardian': Guardian,
    }
    
    return render(request, 'students/guardians/list.html', context)


@login_required
def guardian_create(request):
    """Create new guardian"""
    if request.method == 'POST':
        form = GuardianForm(request.POST, request.FILES)
        if form.is_valid():
            guardian = form.save()
            
            messages.success(
                request,
                f"Guardian {guardian.get_full_name()} was created successfully",
                extra_tags='sweetalert'
            )
            return redirect('students:guardian_profile', pk=guardian.pk)
        else:
            messages.error(
                request,
                "Please correct the errors in the form",
                extra_tags='sweetalert-error'
            )
    else:
        form = GuardianForm()
    
    context = {
        'form': form,
        'title': 'Create Guardian',
    }
    
    return render(request, 'students/guardians/form.html', context)


@login_required
def guardian_edit(request, pk):
    """Edit existing guardian"""
    guardian = get_object_or_404(Guardian, pk=pk)
    
    if request.method == 'POST':
        form = GuardianForm(request.POST, request.FILES, instance=guardian)
        if form.is_valid():
            guardian = form.save()
            
            messages.success(
                request,
                f"Guardian {guardian.get_full_name()} was updated successfully",
                extra_tags='sweetalert'
            )
            return redirect('students:guardian_profile', pk=guardian.pk)
        else:
            messages.error(
                request,
                "Please correct the errors in the form",
                extra_tags='sweetalert-error'
            )
    else:
        form = GuardianForm(instance=guardian)
    
    context = {
        'form': form,
        'guardian': guardian,
        'title': 'Update Guardian',
    }
    
    return render(request, 'students/guardians/form.html', context)


@login_required
def guardian_profile(request, pk):
    """View guardian profile"""
    guardian = get_object_or_404(
        Guardian.objects.prefetch_related(
            Prefetch(
                'student_relationships',
                queryset=StudentGuardian.objects.filter(is_active=True).select_related(
                    'student__current_academic_level'
                )
            )
        ),
        pk=pk
    )
    
    # Get related students
    students = guardian.student_relationships.filter(is_active=True)
    primary_students = students.filter(is_primary=True)
    financial_students = students.filter(is_financial_responsible=True)
    
    context = {
        'guardian': guardian,
        'students': students,
        'primary_students': primary_students,
        'financial_students': financial_students,
    }
    
    return render(request, 'students/guardians/profile.html', context)


@login_required
def guardian_print_view(request):
    """Generate printable guardian list"""
    
    selected_fields = request.GET.getlist('fields')
    if not selected_fields:
        selected_fields = [
            'full_name', 'guardian_type', 'primary_phone', 
            'email', 'occupation', 'is_active'
        ]
    
    include_stats = request.GET.get('include_stats') == 'true'
    landscape_mode = request.GET.get('landscape') == 'true'
    
    # Get filter parameters
    query = request.GET.get('q', '')
    guardian_type = request.GET.get('guardian_type', '')
    is_active = request.GET.get('is_active', '')
    
    # Build queryset
    guardians = Guardian.objects.annotate(
        student_count=Count('students', distinct=True)
    ).order_by('last_name', 'first_name')
    
    # Apply filters
    if query:
        guardians = guardians.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(primary_phone__icontains=query) |
            Q(email__icontains=query)
        )
    
    if guardian_type:
        guardians = guardians.filter(guardian_type=guardian_type)
    
    if is_active:
        guardians = guardians.filter(is_active=(is_active.lower() == 'true'))
    
    # Calculate stats
    stats = None
    if include_stats:
        total = guardians.count()
        active = guardians.filter(is_active=True).count()
        
        stats = {
            'total': total,
            'active': active,
            'primary': guardians.filter(guardian_type='PRIMARY').count(),
            'with_email': guardians.exclude(Q(email='') | Q(email__isnull=True)).count(),
        }
    
    field_names = {
        'full_name': 'Full Name',
        'guardian_type': 'Guardian Type',
        'primary_phone': 'Primary Phone',
        'secondary_phone': 'Secondary Phone',
        'email': 'Email',
        'occupation': 'Occupation',
        'employer': 'Employer',
        'home_address': 'Home Address',
        'is_active': 'Active Status',
        'student_count': 'Number of Students',
    }
    
    selected_field_names = [
        field_names.get(field, field.replace('_', ' ').title()) 
        for field in selected_fields
    ]
    
    context = {
        'guardians': guardians,
        'stats': stats,
        'now': timezone.now(),
        'selected_fields': selected_fields,
        'selected_field_names': selected_field_names,
        'field_names': field_names,
        'landscape': landscape_mode,
    }
    
    return render(request, 'students/guardians/print.html', context)


# =============================================================================
# STUDENT-GUARDIAN RELATIONSHIP VIEWS
# =============================================================================

@login_required
def student_guardian_list(request):
    """List all student-guardian relationships"""
    
    context = {
        'title': 'Student-Guardian Relationships',
    }
    
    return render(request, 'students/relationships/list.html', context)


@login_required
def student_guardian_create(request):
    """Create new student-guardian relationship"""
    
    if request.method == 'POST':
        form = StudentGuardianForm(request.POST)
        if form.is_valid():
            relationship = form.save()
            
            messages.success(
                request,
                f"Relationship created: {relationship.guardian.get_full_name()} - {relationship.student.get_full_name()}",
                extra_tags='sweetalert'
            )
            return redirect('students:student_profile', pk=relationship.student.pk)
        else:
            messages.error(
                request,
                "Please correct the errors in the form",
                extra_tags='sweetalert-error'
            )
    else:
        form = StudentGuardianForm()
    
    context = {
        'form': form,
        'title': 'Create Relationship',
    }
    
    return render(request, 'students/relationships/form.html', context)


@login_required
def student_guardian_detail(request, pk):
    """View student-guardian relationship details"""
    
    relationship = get_object_or_404(
        StudentGuardian.objects.select_related('student', 'guardian'),
        pk=pk
    )
    
    context = {
        'relationship': relationship,
    }
    
    return render(request, 'students/relationships/detail.html', context)


@login_required
def student_guardian_edit(request, pk):
    """Edit student-guardian relationship"""
    
    relationship = get_object_or_404(StudentGuardian, pk=pk)
    
    if request.method == 'POST':
        form = StudentGuardianForm(request.POST, instance=relationship)
        if form.is_valid():
            relationship = form.save()
            
            messages.success(
                request,
                "Relationship updated successfully",
                extra_tags='sweetalert'
            )
            return redirect('students:relationship_detail', pk=relationship.pk)
        else:
            messages.error(
                request,
                "Please correct the errors in the form",
                extra_tags='sweetalert-error'
            )
    else:
        form = StudentGuardianForm(instance=relationship)
    
    context = {
        'form': form,
        'relationship': relationship,
        'title': 'Update Relationship',
    }
    
    return render(request, 'students/relationships/form.html', context)


# =============================================================================
# SIBLING RELATIONSHIP VIEWS
# =============================================================================

@login_required
def sibling_list(request):
    """List all sibling relationships"""
    
    context = {
        'title': 'Sibling Relationships',
    }
    
    return render(request, 'students/siblings/list.html', context)


@login_required
def sibling_create(request):
    """Create new sibling relationship"""
    
    if request.method == 'POST':
        from_student_id = request.POST.get('from_student')
        to_student_id = request.POST.get('to_student')
        relationship_type = request.POST.get('relationship_type', 'FULL')
        
        try:
            from_student = Student.objects.get(pk=from_student_id)
            to_student = Student.objects.get(pk=to_student_id)
            
            # Check if already exists
            if SiblingRelationship.objects.filter(
                Q(from_student=from_student, to_student=to_student) |
                Q(from_student=to_student, to_student=from_student)
            ).exists():
                messages.error(
                    request,
                    "This sibling relationship already exists",
                    extra_tags='sweetalert-error'
                )
            else:
                # Create relationship (signal will create reciprocal)
                relationship = SiblingRelationship.objects.create(
                    from_student=from_student,
                    to_student=to_student,
                    relationship_type=relationship_type,
                )
                
                messages.success(
                    request,
                    f"Sibling relationship created: {from_student.get_full_name()} - {to_student.get_full_name()}",
                    extra_tags='sweetalert'
                )
                return redirect('students:student_profile', pk=from_student.pk)
                
        except Student.DoesNotExist:
            messages.error(
                request,
                "Student not found",
                extra_tags='sweetalert-error'
            )
    
    # Get all active students for the form
    students = Student.objects.filter(
        enrollment_status='ACTIVE'
    ).order_by('admission_number')
    
    context = {
        'students': students,
        'relationship_types': SiblingRelationship.RELATIONSHIP_TYPES,
        'title': 'Create Sibling Relationship',
    }
    
    return render(request, 'students/siblings/form.html', context)


@login_required
def sibling_detail(request, pk):
    """View sibling relationship details"""
    
    relationship = get_object_or_404(
        SiblingRelationship.objects.select_related(
            'from_student__current_academic_level',
            'to_student__current_academic_level'
        ),
        pk=pk
    )
    
    context = {
        'relationship': relationship,
    }
    
    return render(request, 'students/siblings/detail.html', context)


@login_required
def sibling_edit(request, pk):
    """Edit sibling relationship"""
    
    relationship = get_object_or_404(SiblingRelationship, pk=pk)
    
    if request.method == 'POST':
        relationship_type = request.POST.get('relationship_type')
        is_verified = request.POST.get('is_verified') == 'on'
        notes = request.POST.get('notes', '')
        
        relationship.relationship_type = relationship_type
        relationship.is_verified = is_verified
        relationship.notes = notes
        
        if is_verified and not relationship.verification_date:
            relationship.verification_date = timezone.now()
        
        relationship.save()
        
        messages.success(
            request,
            "Sibling relationship updated successfully",
            extra_tags='sweetalert'
        )
        return redirect('students:sibling_detail', pk=relationship.pk)
    
    context = {
        'relationship': relationship,
        'relationship_types': SiblingRelationship.RELATIONSHIP_TYPES,
        'title': 'Update Sibling Relationship',
    }
    
    return render(request, 'students/siblings/form.html', context)


# =============================================================================
# ENROLLMENT STATUS HISTORY VIEWS
# =============================================================================

@login_required
def enrollment_history_list(request):
    """List enrollment status history"""
    
    context = {
        'title': 'Enrollment Status History',
    }
    
    return render(request, 'students/enrollment_history/list.html', context)


@login_required
def enrollment_history_detail(request, pk):
    """View enrollment status history entry details"""
    
    history = get_object_or_404(
        EnrollmentStatusHistory.objects.select_related(
            'student__current_academic_level',
            'academic_session'
        ),
        pk=pk
    )
    
    context = {
        'history': history,
    }
    
    return render(request, 'students/enrollment_history/detail.html', context)


# =============================================================================
# REPORTS & ANALYTICS
# =============================================================================

@login_required
def student_reports_dashboard(request):
    """Dashboard for student reports and analytics"""
    
    try:
        stats = student_stats.get_comprehensive_statistics()
    except Exception as e:
        logger.error(f"Error getting comprehensive statistics: {e}")
        stats = {}
    
    context = {
        'stats': stats,
        'title': 'Student Reports & Analytics',
    }
    
    return render(request, 'students/reports/dashboard.html', context)


@login_required
def demographics_report(request):
    """Demographics report"""
    
    try:
        student_stats_data = student_stats.get_student_statistics()
        family_stats_data = student_stats.get_family_statistics()
    except Exception as e:
        logger.error(f"Error getting demographics: {e}")
        student_stats_data = {}
        family_stats_data = {}
    
    context = {
        'student_stats': student_stats_data,
        'family_stats': family_stats_data,
        'title': 'Demographics Report',
    }
    
    return render(request, 'students/reports/demographics.html', context)


@login_required
def health_report(request):
    """Health and medical report"""
    
    # Get students with medical alerts
    medical_alerts = Student.objects.filter(
        enrollment_status='ACTIVE'
    ).filter(
        Q(medical_conditions__isnull=False) & ~Q(medical_conditions='') |
        Q(allergies__isnull=False) & ~Q(allergies='') |
        Q(medications__isnull=False) & ~Q(medications='') |
        Q(has_special_needs=True)
    ).select_related('current_academic_level').order_by('admission_number')
    
    # Statistics
    total_active = Student.objects.filter(enrollment_status='ACTIVE').count()
    stats = {
        'total_with_alerts': medical_alerts.count(),
        'with_conditions': medical_alerts.exclude(Q(medical_conditions='') | Q(medical_conditions__isnull=True)).count(),
        'with_allergies': medical_alerts.exclude(Q(allergies='') | Q(allergies__isnull=True)).count(),
        'on_medications': medical_alerts.exclude(Q(medications='') | Q(medications__isnull=True)).count(),
        'special_needs': medical_alerts.filter(has_special_needs=True).count(),
        'special_diet': Student.objects.filter(enrollment_status='ACTIVE', requires_special_diet=True).count(),
        'percentage': round((medical_alerts.count() / total_active * 100), 1) if total_active > 0 else 0,
    }
    
    context = {
        'medical_alerts': medical_alerts,
        'stats': stats,
        'title': 'Health & Medical Report',
    }
    
    return render(request, 'students/reports/health.html', context)


@login_required
def guardian_report(request):
    """Guardian report"""
    
    try:
        guardian_stats_data = student_stats.get_guardian_statistics()
        occupation_stats = student_stats.get_guardian_occupation_stats()
    except Exception as e:
        logger.error(f"Error getting guardian stats: {e}")
        guardian_stats_data = {}
        occupation_stats = {}
    
    # Students without guardians
    students_without_guardians = Student.objects.filter(
        enrollment_status='ACTIVE'
    ).annotate(
        guardian_count=Count('guardians')
    ).filter(guardian_count=0).select_related('current_academic_level')
    
    context = {
        'guardian_stats': guardian_stats_data,
        'occupation_stats': occupation_stats,
        'students_without_guardians': students_without_guardians,
        'title': 'Guardian Report',
    }
    
    return render(request, 'students/reports/guardians.html', context)


@login_required
def sibling_report(request):
    """Sibling relationships report"""
    
    try:
        sibling_stats_data = student_stats.get_sibling_statistics()
        largest_groups = student_stats.get_largest_sibling_groups()
    except Exception as e:
        logger.error(f"Error getting sibling stats: {e}")
        sibling_stats_data = {}
        largest_groups = []
    
    context = {
        'sibling_stats': sibling_stats_data,
        'largest_groups': largest_groups,
        'title': 'Sibling Relationships Report',
    }
    
    return render(request, 'students/reports/siblings.html', context)


@login_required
def birthday_report(request):
    """Birthday report (upcoming birthdays)"""
    
    today = get_school_today()
    
    # Get birthdays for next 30 days
    upcoming_birthdays = []
    for i in range(30):
        check_date = today + timedelta(days=i)
        students = Student.objects.filter(
            enrollment_status='ACTIVE',
            date_of_birth__month=check_date.month,
            date_of_birth__day=check_date.day
        ).select_related('current_academic_level').order_by('date_of_birth')
        
        if students:
            upcoming_birthdays.append({
                'date': check_date,
                'students': students,
                'days_away': i,
            })
    
    context = {
        'upcoming_birthdays': upcoming_birthdays,
        'title': 'Birthday Report',
    }
    
    return render(request, 'students/reports/birthdays.html', context)


# =============================================================================
# EXPORT FUNCTIONS
# =============================================================================

@login_required
def export_students_excel(request):
    """Export students to Excel"""
    
    # Get filtered students
    students = Student.objects.select_related(
        'current_academic_level'
    ).order_by('admission_number')
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Students"
    
    # Headers
    headers = [
        'Admission Number', 'Full Name', 'Gender', 'Date of Birth', 'Age',
        'Current Grade', 'Status', 'Phone', 'Email', 'Admission Date'
    ]
    ws.append(headers)
    
    # Style headers
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
        cell.font = Font(bold=True, color='FFFFFF')
    
    # Data rows
    for student in students:
        ws.append([
            student.admission_number,
            student.get_full_name(),
            student.get_gender_display(),
            student.date_of_birth.strftime('%Y-%m-%d') if student.date_of_birth else '',
            student.age,
            str(student.current_academic_level) if student.current_academic_level else '',
            student.get_enrollment_status_display(),
            student.phone_number or '',
            student.personal_email or '',
            student.admission_date.strftime('%Y-%m-%d') if student.admission_date else '',
        ])
    
    # Prepare response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="students_{timezone.now().strftime("%Y%m%d")}.xlsx"'
    
    wb.save(response)
    return response


@login_required
def export_students_pdf(request):
    """Export students to PDF"""
    
    students = Student.objects.select_related(
        'current_academic_level'
    ).order_by('admission_number')
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    # Title
    elements.append(Paragraph('Student List', title_style))
    elements.append(Spacer(1, 20))
    
    # Table data
    data = [['Admission #', 'Name', 'Gender', 'Age', 'Grade', 'Status']]
    
    for student in students:
        data.append([
            student.admission_number,
            student.get_full_name()[:30],
            student.get_gender_display(),
            str(student.age),
            str(student.current_academic_level)[:20] if student.current_academic_level else '',
            student.get_enrollment_status_display()
        ])
    
    # Create table
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(table)
    doc.build(elements)
    
    # Prepare response
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="students_{timezone.now().strftime("%Y%m%d")}.pdf"'
    
    return response


@login_required
def export_guardians_excel(request):
    """Export guardians to Excel"""
    
    guardians = Guardian.objects.annotate(
        student_count=Count('students', distinct=True)
    ).order_by('last_name', 'first_name')
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Guardians"
    
    # Headers
    headers = [
        'Full Name', 'Type', 'Primary Phone', 'Email', 'Occupation',
        'Employer', 'Home Address', '# Students', 'Status'
    ]
    ws.append(headers)
    
    # Style headers
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
        cell.font = Font(bold=True, color='FFFFFF')
    
    # Data rows
    for guardian in guardians:
        ws.append([
            guardian.get_full_name(),
            guardian.get_guardian_type_display(),
            guardian.primary_phone,
            guardian.email or '',
            guardian.occupation or '',
            guardian.employer or '',
            guardian.home_address or '',
            guardian.student_count,
            'Active' if guardian.is_active else 'Inactive',
        ])
    
    # Prepare response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="guardians_{timezone.now().strftime("%Y%m%d")}.xlsx"'
    
    wb.save(response)
    return response


@login_required
def export_guardians_pdf(request):
    """Export guardians to PDF"""
    
    guardians = Guardian.objects.annotate(
        student_count=Count('students', distinct=True)
    ).order_by('last_name', 'first_name')
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    # Title
    elements.append(Paragraph('Guardian List', title_style))
    elements.append(Spacer(1, 20))
    
    # Table data
    data = [['Name', 'Type', 'Phone', 'Email', 'Occupation', '# Students']]
    
    for guardian in guardians:
        data.append([
            guardian.get_full_name()[:30],
            guardian.get_guardian_type_display(),
            guardian.primary_phone,
            guardian.email[:25] if guardian.email else '',
            guardian.occupation[:20] if guardian.occupation else '',
            str(guardian.student_count),
        ])
    
    # Create table
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(table)
    doc.build(elements)
    
    # Prepare response
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="guardians_{timezone.now().strftime("%Y%m%d")}.pdf"'
    
    return response