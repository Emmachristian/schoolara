# students/modal_views.py

"""
Modal Views for Student Management

These views return HTML fragments for modals loaded via HTMX.
Each modal view is paired with an action view in views.py that handles the POST request.

Pattern:
1. GET request → modal_views.py (loads modal HTML)
2. POST request → views.py (processes action, returns response with headers)
"""

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q

from .models import (
    Student,
    Guardian,
    StudentGuardian,
    SiblingRelationship,
    EnrollmentStatusHistory,
)


# =============================================================================
# STUDENT MODALS
# =============================================================================

@login_required
def student_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    student = get_object_or_404(Student, pk=pk)
    
    # Check if student can be deleted
    can_delete = True
    warnings = []
    
    # Check enrollment status
    if student.enrollment_status == 'ACTIVE':
        can_delete = False
        warnings.append("Cannot delete active students. Please change status first.")
    
    # Check for guardians
    guardian_count = student.guardians.count()
    if guardian_count > 0:
        warnings.append(f"Student has {guardian_count} guardian(s) that will be unlinked")
    
    # Check for siblings
    sibling_count = student.sibling_relationships.count() + student.reverse_sibling_relationships.count()
    if sibling_count > 0:
        warnings.append(f"Student has {sibling_count} sibling relationship(s) that will be removed")
    
    # Check for class enrollments
    if hasattr(student, 'class_enrollments'):
        enrollment_count = student.class_enrollments.count()
        if enrollment_count > 0:
            can_delete = False
            warnings.append(f"Student has {enrollment_count} class enrollment(s). Cannot delete.")
    
    # Check for invoices/payments
    if hasattr(student, 'invoices'):
        invoice_count = student.invoices.count()
        if invoice_count > 0:
            can_delete = False
            warnings.append(f"Student has {invoice_count} financial record(s). Cannot delete.")
    
    return render(request, 'students/modals/_delete_student.html', {
        'student': student,
        'can_delete': can_delete,
        'warnings': warnings,
    })


@login_required
def student_activate_modal(request, pk):
    """Return activation confirmation modal content via HTMX"""
    student = get_object_or_404(Student, pk=pk)
    
    return render(request, 'students/modals/_activate_student.html', {
        'student': student
    })


@login_required
def student_suspend_modal(request, pk):
    """Return suspension modal with reason input via HTMX"""
    student = get_object_or_404(Student, pk=pk)
    
    return render(request, 'students/modals/_suspend_student.html', {
        'student': student
    })


@login_required
def student_status_change_modal(request, pk):
    """Modal for changing student enrollment status"""
    student = get_object_or_404(Student, pk=pk)
    
    return render(request, 'students/modals/_status_change.html', {
        'student': student,
        'status_choices': Student.ENROLLMENT_STATUS_CHOICES,
    })


# =============================================================================
# GUARDIAN MODALS
# =============================================================================

@login_required
def guardian_delete_modal(request, pk):
    """Return delete confirmation modal content via HTMX"""
    guardian = get_object_or_404(Guardian, pk=pk)
    
    # Check if guardian can be deleted
    can_delete = True
    warnings = []
    
    # Check for students
    student_count = guardian.students.count()
    if student_count > 0:
        can_delete = False
        warnings.append(f"Guardian has {student_count} student(s). Remove relationships first.")
    
    # Check if primary guardian
    primary_count = guardian.student_relationships.filter(is_primary=True).count()
    if primary_count > 0:
        can_delete = False
        warnings.append(f"Guardian is primary guardian for {primary_count} student(s)")
    
    return render(request, 'students/modals/_delete_guardian.html', {
        'guardian': guardian,
        'can_delete': can_delete,
        'warnings': warnings,
    })


# =============================================================================
# STUDENT-GUARDIAN RELATIONSHIP MODALS
# =============================================================================

@login_required
def student_guardian_form_modal(request, student_pk, relationship_pk=None):
    """
    Unified modal for creating or editing student-guardian relationship
    - student_pk: Required for creation
    - relationship_pk: Optional, if provided it's edit mode
    """
    student = get_object_or_404(Student, pk=student_pk)
    relationship = get_object_or_404(StudentGuardian, pk=relationship_pk) if relationship_pk else None
    
    # Get available guardians (not already linked to this student)
    if not relationship:
        existing_guardian_ids = student.guardians.values_list('id', flat=True)
        available_guardians = Guardian.objects.filter(
            is_active=True
        ).exclude(id__in=existing_guardian_ids).order_by('last_name', 'first_name')
    else:
        available_guardians = Guardian.objects.filter(is_active=True).order_by('last_name', 'first_name')
    
    return render(request, 'students/modals/_student_guardian_form.html', {
        'student': student,
        'relationship': relationship,
        'relationship_choices': StudentGuardian.RELATIONSHIP_CHOICES,
        'available_guardians': available_guardians,
    })


@login_required
def student_guardian_delete_modal(request, pk):
    """Return student-guardian relationship delete confirmation modal via HTMX"""
    relationship = get_object_or_404(
        StudentGuardian.objects.select_related('student', 'guardian'),
        pk=pk
    )
    
    # Check if relationship can be deleted
    can_delete = True
    warnings = []
    
    # Check if primary guardian
    if relationship.is_primary:
        warnings.append("This is the primary guardian relationship")
    
    # Check if last guardian
    guardian_count = relationship.student.guardians.count()
    if guardian_count == 1:
        warnings.append("This is the student's only guardian")
    
    # Check if emergency contact
    if relationship.emergency_contact_priority <= 5:
        warnings.append("This guardian is an emergency contact")
    
    return render(request, 'students/modals/_delete_student_guardian.html', {
        'relationship': relationship,
        'can_delete': can_delete,
        'warnings': warnings,
    })


@login_required
def student_guardian_set_primary_modal(request, pk):
    """Return set primary guardian confirmation modal via HTMX"""
    relationship = get_object_or_404(
        StudentGuardian.objects.select_related('student', 'guardian'),
        pk=pk
    )
    
    return render(request, 'students/modals/_set_primary_guardian.html', {
        'relationship': relationship,
    })


@login_required
def add_guardian_modal(request, student_pk):
    """Modal for adding guardian to student"""
    student = get_object_or_404(Student, pk=student_pk)
    
    # Get available guardians (not already linked to this student)
    existing_guardian_ids = student.guardians.values_list('id', flat=True)
    available_guardians = Guardian.objects.filter(
        is_active=True
    ).exclude(id__in=existing_guardian_ids).order_by('last_name', 'first_name')
    
    return render(request, 'students/modals/_add_guardian.html', {
        'student': student,
        'available_guardians': available_guardians,
        'relationship_choices': StudentGuardian.RELATIONSHIP_CHOICES,
    })


# =============================================================================
# SIBLING RELATIONSHIP MODALS
# =============================================================================

@login_required
def sibling_form_modal(request, student_pk, sibling_pk=None):
    """
    Unified modal for creating or editing sibling relationship
    - student_pk: Required for creation
    - sibling_pk: Optional, if provided it's edit mode
    """
    student = get_object_or_404(Student, pk=student_pk)
    sibling_rel = get_object_or_404(SiblingRelationship, pk=sibling_pk) if sibling_pk else None
    
    # Get available students (not already siblings and not self)
    if not sibling_rel:
        existing_sibling_ids = list(student.sibling_relationships.values_list('to_student_id', flat=True))
        existing_sibling_ids += list(student.reverse_sibling_relationships.values_list('from_student_id', flat=True))
        
        available_students = Student.objects.filter(
            enrollment_status='ACTIVE'
        ).exclude(
            Q(id=student.pk) | Q(id__in=existing_sibling_ids)
        ).order_by('admission_number')
    else:
        available_students = Student.objects.filter(enrollment_status='ACTIVE').order_by('admission_number')
    
    return render(request, 'students/modals/_sibling_form.html', {
        'student': student,
        'sibling_rel': sibling_rel,
        'relationship_types': SiblingRelationship.RELATIONSHIP_TYPES,
        'available_students': available_students,
    })


@login_required
def sibling_delete_modal(request, pk):
    """Return sibling relationship delete confirmation modal via HTMX"""
    relationship = get_object_or_404(
        SiblingRelationship.objects.select_related('from_student', 'to_student'),
        pk=pk
    )
    
    warnings = []
    
    # Check if reciprocal relationship exists
    reciprocal = SiblingRelationship.objects.filter(
        from_student=relationship.to_student,
        to_student=relationship.from_student
    ).first()
    
    if reciprocal:
        warnings.append("Reciprocal relationship will also be deleted")
    
    return render(request, 'students/modals/_delete_sibling.html', {
        'relationship': relationship,
        'warnings': warnings,
    })


@login_required
def add_sibling_modal(request, student_pk):
    """Modal for adding sibling relationship"""
    student = get_object_or_404(Student, pk=student_pk)
    
    # Get available students (not already siblings and not self)
    existing_sibling_ids = list(student.sibling_relationships.values_list('to_student_id', flat=True))
    existing_sibling_ids += list(student.reverse_sibling_relationships.values_list('from_student_id', flat=True))
    
    available_students = Student.objects.filter(
        enrollment_status='ACTIVE'
    ).exclude(
        Q(id=student.pk) | Q(id__in=existing_sibling_ids)
    ).order_by('admission_number')
    
    return render(request, 'students/modals/_add_sibling.html', {
        'student': student,
        'available_students': available_students,
        'relationship_types': SiblingRelationship.RELATIONSHIP_TYPES,
    })


# =============================================================================
# ENROLLMENT STATUS HISTORY MODALS
# =============================================================================

@login_required
def enrollment_status_history_detail_modal(request, pk):
    """Modal for viewing enrollment status history details"""
    history = get_object_or_404(
        EnrollmentStatusHistory.objects.select_related(
            'student__current_academic_level',
            'academic_session'
        ),
        pk=pk
    )
    
    return render(request, 'students/modals/_enrollment_history_detail.html', {
        'history': history,
    })


# =============================================================================
# BULK ACTION MODALS
# =============================================================================

@login_required
def bulk_status_change_modal(request):
    """Modal for bulk student status changes"""
    student_ids = request.GET.getlist('student_ids')
    students = Student.objects.filter(pk__in=student_ids)
    
    return render(request, 'students/modals/_bulk_status_change.html', {
        'students': students,
        'student_count': students.count(),
        'status_choices': Student.ENROLLMENT_STATUS_CHOICES,
    })


@login_required
def bulk_assign_guardian_modal(request):
    """Modal for bulk guardian assignment"""
    student_ids = request.GET.getlist('student_ids')
    students = Student.objects.filter(pk__in=student_ids)
    
    # Get all active guardians
    guardians = Guardian.objects.filter(is_active=True).order_by('last_name', 'first_name')
    
    return render(request, 'students/modals/_bulk_assign_guardian.html', {
        'students': students,
        'student_count': students.count(),
        'guardians': guardians,
        'relationship_choices': StudentGuardian.RELATIONSHIP_CHOICES,
    })


# =============================================================================
# PRINT OPTIONS MODALS
# =============================================================================

@login_required
def student_print_options_modal(request):
    """Modal for selecting student print options"""
    
    field_options = [
        {'value': 'admission_number', 'label': 'Admission Number'},
        {'value': 'full_name', 'label': 'Full Name'},
        {'value': 'first_name', 'label': 'First Name'},
        {'value': 'last_name', 'label': 'Last Name'},
        {'value': 'national_student_number', 'label': 'National Student Number'},
        {'value': 'date_of_birth', 'label': 'Date of Birth'},
        {'value': 'age', 'label': 'Age'},
        {'value': 'gender', 'label': 'Gender'},
        {'value': 'nationality', 'label': 'Nationality'},
        {'value': 'phone_number', 'label': 'Phone'},
        {'value': 'personal_email', 'label': 'Email'},
        {'value': 'home_address', 'label': 'Home Address'},
        {'value': 'current_academic_level', 'label': 'Current Grade/Class'},
        {'value': 'admission_academic_level', 'label': 'Admission Grade/Class'},
        {'value': 'enrollment_status', 'label': 'Status'},
        {'value': 'admission_date', 'label': 'Admission Date'},
        {'value': 'health_condition', 'label': 'Health'},
        {'value': 'has_special_needs', 'label': 'Special Needs'},
        {'value': 'transportation_required', 'label': 'Transport'},
        {'value': 'religious_affiliation', 'label': 'Religion'},
    ]
    
    return render(request, 'students/modals/_print_options.html', {
        'field_options': field_options,
    })


@login_required
def guardian_print_options_modal(request):
    """Modal for selecting guardian print options"""
    
    field_options = [
        {'value': 'full_name', 'label': 'Full Name'},
        {'value': 'guardian_type', 'label': 'Guardian Type'},
        {'value': 'primary_phone', 'label': 'Primary Phone'},
        {'value': 'secondary_phone', 'label': 'Secondary Phone'},
        {'value': 'email', 'label': 'Email'},
        {'value': 'occupation', 'label': 'Occupation'},
        {'value': 'employer', 'label': 'Employer'},
        {'value': 'home_address', 'label': 'Home Address'},
        {'value': 'is_active', 'label': 'Active Status'},
        {'value': 'student_count', 'label': 'Number of Students'},
    ]
    
    return render(request, 'students/modals/_guardian_print_options.html', {
        'field_options': field_options,
    })


# =============================================================================
# EXPORT OPTIONS MODALS
# =============================================================================

@login_required
def export_options_modal(request):
    """Modal for selecting export format and options"""
    
    export_type = request.GET.get('export_type', 'students')  # students or guardians
    
    return render(request, 'students/modals/_export_options.html', {
        'export_type': export_type,
    })