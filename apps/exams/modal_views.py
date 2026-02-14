# exams/modal_views.py

"""
Modal Views for Examination Management

This module contains modal views for the exams app.
These are lightweight views that return HTML partials for modals.

IMPORTANT: This module does NOT contain form modals for create/edit operations.
Create and Edit operations use full template pages in views.py instead.

Modal types included:
- Delete confirmation modals
- Toggle action modals (activate/deactivate)
- Quick view modals (preview)
- Action confirmation modals (lock, unlock, publish, etc.)
- Bulk operation modals
- Status update modals
- Analytics modals
- Report generation modals
- Import/export option modals
- Settings modals
- History modals
"""

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, Avg, Max, Min, Sum
from django.core.exceptions import PermissionDenied
from decimal import Decimal

from .models import (
    ExamCategory,
    GradingSystem,
    GradingRange,
    ClassGradingSystem,
    Examination,
    ExamRegistration,
    StudentExamResult,
    ExamAnalytics,
)
from students.models import Student
from academics.models import Class, Subject, AcademicSession

from core.utils import get_school_today, get_school_current_time, get_active_academic_session

import logging

logger = logging.getLogger(__name__)


# =============================================================================
# EXAM CATEGORY MODALS
# =============================================================================

@login_required
def exam_category_delete_modal(request, pk):
    """Return delete confirmation modal for exam category"""
    category = get_object_or_404(ExamCategory, pk=pk)
    
    # Check if can be deleted
    can_delete = True
    warnings = []
    
    # Check for examinations
    exam_count = category.examinations.count()
    if exam_count > 0:
        can_delete = False
        warnings.append(f"Has {exam_count} examination(s)")
    
    context = {
        'category': category,
        'can_delete': can_delete,
        'warnings': warnings,
    }
    
    return render(request, 'exams/categories/modals/delete_category.html', context)


@login_required
def exam_category_toggle_active_modal(request, pk):
    """Toggle active modal for exam category"""
    category = get_object_or_404(ExamCategory, pk=pk)
    
    action = 'deactivate' if category.is_active else 'activate'
    
    context = {
        'category': category,
        'action': action,
    }
    
    return render(request, 'exams/categories/modals/toggle_active.html', context)


@login_required
def exam_category_quick_view_modal(request, pk):
    """Quick view modal for exam category"""
    category = get_object_or_404(ExamCategory, pk=pk)
    
    # Get statistics
    total_exams = category.examinations.count()
    active_exams = category.examinations.filter(status='ONGOING').count()
    completed_exams = category.examinations.filter(status='COMPLETED').count()
    upcoming_exams = category.examinations.filter(
        exam_date__gte=get_school_today(),
        status__in=['PLANNED', 'SCHEDULED']
    ).count()
    
    context = {
        'category': category,
        'total_exams': total_exams,
        'active_exams': active_exams,
        'completed_exams': completed_exams,
        'upcoming_exams': upcoming_exams,
    }
    
    return render(request, 'exams/categories/modals/quick_view.html', context)


# =============================================================================
# GRADING SYSTEM MODALS
# =============================================================================

@login_required
def grading_system_delete_modal(request, pk):
    """Return delete confirmation modal for grading system"""
    system = get_object_or_404(GradingSystem, pk=pk)
    
    # Check if can be deleted
    can_delete = True
    warnings = []
    
    if system.is_default:
        can_delete = False
        warnings.append("This is the default grading system")
    
    # Check for class assignments
    assignment_count = system.class_assignments.count()
    if assignment_count > 0:
        can_delete = False
        warnings.append(f"Has {assignment_count} class assignment(s)")
    
    # Check for examinations
    exam_count = system.examinations.count()
    if exam_count > 0:
        can_delete = False
        warnings.append(f"Used in {exam_count} examination(s)")
    
    context = {
        'system': system,
        'can_delete': can_delete,
        'warnings': warnings,
    }
    
    return render(request, 'exams/grading_systems/modals/delete_system.html', context)


@login_required
def grading_system_toggle_active_modal(request, pk):
    """Toggle active modal for grading system"""
    system = get_object_or_404(GradingSystem, pk=pk)
    
    action = 'deactivate' if system.is_active else 'activate'
    
    context = {
        'system': system,
        'action': action,
    }
    
    return render(request, 'exams/grading_systems/modals/toggle_active.html', context)


@login_required
def grading_system_set_default_modal(request, pk):
    """Set grading system as default modal"""
    system = get_object_or_404(GradingSystem, pk=pk)
    
    current_default = GradingSystem.objects.filter(is_default=True).first()
    
    context = {
        'system': system,
        'current_default': current_default,
    }
    
    return render(request, 'exams/grading_systems/modals/set_default.html', context)


@login_required
def grading_system_quick_view_modal(request, pk):
    """Quick view modal for grading system"""
    system = get_object_or_404(GradingSystem, pk=pk)
    
    ranges = system.ranges.all().order_by('-min_score')
    assignments = system.class_assignments.filter(is_active=True).count()
    examinations = system.examinations.count()
    
    context = {
        'system': system,
        'ranges': ranges,
        'assignments': assignments,
        'examinations': examinations,
    }
    
    return render(request, 'exams/grading_systems/modals/quick_view.html', context)


# =============================================================================
# GRADING RANGE MODALS (LEGACY - Consider removing if using formsets)
# =============================================================================

@login_required
def grading_range_delete_modal(request, pk):
    """Return delete confirmation modal for grading range"""
    range_obj = get_object_or_404(GradingRange, pk=pk)
    
    # ✅ ADDED: Check if this is the last range
    can_delete = True
    warnings = []
    
    if range_obj.grading_system.ranges.count() <= 1:
        can_delete = False
        warnings.append("Cannot delete the last grading range")
    
    context = {
        'range': range_obj,
        'can_delete': can_delete,  # ✅ ADDED
        'warnings': warnings,  # ✅ ADDED
    }
    
    return render(request, 'exams/grading_ranges/modals/delete_range.html', context)


@login_required
def grading_range_quick_view_modal(request, pk):
    """Quick view modal for grading range"""
    range_obj = get_object_or_404(GradingRange, pk=pk)
    
    context = {
        'range': range_obj,
    }
    
    return render(request, 'exams/grading_ranges/modals/quick_view.html', context)


# =============================================================================
# CLASS GRADING SYSTEM MODALS
# =============================================================================

@login_required
def class_grading_system_delete_modal(request, pk):
    """Return delete confirmation modal for class grading system assignment"""
    assignment = get_object_or_404(ClassGradingSystem, pk=pk)
    
    context = {
        'assignment': assignment,
    }
    
    return render(request, 'exams/class_grading_systems/modals/delete_assignment.html', context)


@login_required
def class_grading_system_toggle_active_modal(request, pk):
    """Toggle active modal for class grading system assignment"""
    assignment = get_object_or_404(ClassGradingSystem, pk=pk)
    
    action = 'deactivate' if assignment.is_active else 'activate'
    
    context = {
        'assignment': assignment,
        'action': action,
    }
    
    return render(request, 'exams/class_grading_systems/modals/toggle_active.html', context)


@login_required
def class_grading_system_quick_view_modal(request, pk):
    """Quick view modal for class grading system assignment"""
    assignment = get_object_or_404(
        ClassGradingSystem.objects.select_related(
            'class_instance', 'grading_system', 'academic_session', 'subject'
        ),
        pk=pk
    )
    
    ranges = assignment.grading_system.ranges.all().order_by('-min_score')
    
    context = {
        'assignment': assignment,
        'ranges': ranges,
    }
    
    return render(request, 'exams/class_grading_systems/modals/quick_view.html', context)


@login_required
def bulk_class_grading_system_assign_modal(request):
    """Return modal for bulk class grading system assignment"""
    grading_systems = GradingSystem.objects.filter(is_active=True).order_by('name')
    sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')
    classes = Class.objects.filter(is_active=True).select_related('academic_level').order_by('academic_level__order', 'section')  # ✅ FIXED: 'name' -> 'section'
    subjects = Subject.objects.filter(is_active=True).order_by('name')
    
    context = {
        'grading_systems': grading_systems,
        'sessions': sessions,
        'classes': classes,
        'subjects': subjects,
    }
    
    return render(request, 'exams/class_grading_systems/modals/bulk_assign.html', context)


# =============================================================================
# EXAMINATION MODALS
# =============================================================================

@login_required
def examination_delete_modal(request, pk):
    """Return delete confirmation modal for examination"""
    examination = get_object_or_404(Examination, pk=pk)
    
    # Check if can be deleted
    can_delete = True
    warnings = []
    
    if examination.status in ['ONGOING', 'COMPLETED']:
        can_delete = False
        warnings.append(f"Examination is {examination.get_status_display()}")
    
    # Check for results
    result_count = examination.student_results.count()
    if result_count > 0:
        can_delete = False
        warnings.append(f"Has {result_count} result(s)")
    
    # Check for registrations
    registration_count = examination.registrations.count()
    if registration_count > 0:
        warnings.append(f"Has {registration_count} registration(s) - these will also be deleted")
    
    context = {
        'examination': examination,
        'can_delete': can_delete,
        'warnings': warnings,
    }
    
    return render(request, 'exams/examinations/modals/delete_examination.html', context)


@login_required
def examination_toggle_active_modal(request, pk):
    """Toggle active modal for examination (actually toggles between PLANNED and CANCELLED)"""
    examination = get_object_or_404(Examination, pk=pk)
    
    if examination.status == 'CANCELLED':
        action = 'reactivate'
        new_status = 'PLANNED'
    else:
        action = 'cancel'
        new_status = 'CANCELLED'
    
    context = {
        'examination': examination,
        'action': action,
        'new_status': new_status,
    }
    
    return render(request, 'exams/examinations/modals/toggle_active.html', context)


@login_required
def examination_update_status_modal(request, pk):
    """Return modal for updating examination status"""
    examination = get_object_or_404(Examination, pk=pk)
    
    # Get available status transitions
    available_statuses = []
    current_status = examination.status
    
    if current_status == 'PLANNED':
        available_statuses = ['SCHEDULED', 'CANCELLED']
    elif current_status == 'SCHEDULED':
        available_statuses = ['ONGOING', 'POSTPONED', 'CANCELLED']
    elif current_status == 'ONGOING':
        available_statuses = ['COMPLETED', 'SUSPENDED']
    elif current_status == 'COMPLETED':
        available_statuses = ['ONGOING']  # Allow reopening if needed
    elif current_status in ['CANCELLED', 'POSTPONED', 'SUSPENDED']:
        available_statuses = ['PLANNED', 'SCHEDULED']
    
    context = {
        'examination': examination,
        'available_statuses': available_statuses,
        'status_choices': Examination.EXAM_STATUS_CHOICES,
    }
    
    return render(request, 'exams/examinations/modals/update_status.html', context)


@login_required
def examination_publish_results_modal(request, pk):
    """Return modal for publishing examination results"""
    examination = get_object_or_404(Examination, pk=pk)
    
    # Get statistics
    total_results = examination.student_results.count()
    completed_results = examination.student_results.filter(status__in=['COMPLETED', 'SUBMITTED']).count()
    published_results = examination.student_results.filter(is_published=True).count()
    locked_results = examination.student_results.filter(is_grade_locked=True).count()
    unlocked_results = total_results - locked_results
    
    warnings = []
    can_publish = True
    
    if examination.results_published:
        warnings.append("Results are already published")
    
    if total_results == 0:
        can_publish = False
        warnings.append("No results to publish")
    
    if completed_results < total_results:
        warnings.append(f"Only {completed_results} of {total_results} results are completed")
    
    context = {
        'examination': examination,
        'total_results': total_results,
        'completed_results': completed_results,
        'published_results': published_results,
        'locked_results': locked_results,
        'unlocked_results': unlocked_results,
        'warnings': warnings,
        'can_publish': can_publish,
    }
    
    return render(request, 'exams/examinations/modals/publish_results.html', context)


@login_required
def examination_unpublish_results_modal(request, pk):
    """Return modal for unpublishing examination results"""
    examination = get_object_or_404(Examination, pk=pk)
    
    total_results = examination.student_results.count()
    published_results = examination.student_results.filter(is_published=True).count()
    locked_results = examination.student_results.filter(is_grade_locked=True).count()
    
    warnings = []
    if locked_results > 0:
        warnings.append(f"{locked_results} grade(s) are locked - these will remain locked")
    
    context = {
        'examination': examination,
        'total_results': total_results,
        'published_results': published_results,
        'locked_results': locked_results,
        'warnings': warnings,
    }
    
    return render(request, 'exams/examinations/modals/unpublish_results.html', context)


@login_required
def examination_quick_view_modal(request, pk):
    """Quick view modal for examination"""
    examination = get_object_or_404(
        Examination.objects.select_related(
            'subject', 'exam_category', 'academic_session', 'grading_system'
        ),
        pk=pk
    )
    
    # Get statistics
    registration_count = examination.registrations.count()
    result_count = examination.student_results.count()
    published_count = examination.student_results.filter(is_published=True).count()
    
    result_stats = examination.student_results.filter(status='COMPLETED').aggregate(
        highest=Max('score'),
        lowest=Min('score'),
        average=Avg('score'),
    )
    
    context = {
        'examination': examination,
        'registration_count': registration_count,
        'result_count': result_count,
        'published_count': published_count,
        'highest_score': result_stats['highest'],
        'lowest_score': result_stats['lowest'],
        'average_score': result_stats['average'],
    }
    
    return render(request, 'exams/examinations/modals/quick_view.html', context)


# =============================================================================
# EXAM REGISTRATION MODALS
# =============================================================================

@login_required
def exam_registration_delete_modal(request, pk):
    """Return delete confirmation modal for exam registration"""
    registration = get_object_or_404(ExamRegistration, pk=pk)
    
    warnings = []
    can_delete = True
    
    if registration.status == 'CONFIRMED':
        warnings.append("Registration is confirmed")
    
    if registration.payment_verified:
        warnings.append("Payment has been verified")
    
    context = {
        'registration': registration,
        'can_delete': can_delete,
        'warnings': warnings,
    }
    
    return render(request, 'exams/registrations/modals/delete_registration.html', context)


@login_required
def exam_registration_update_status_modal(request, pk):
    """Return modal for updating registration status"""
    registration = get_object_or_404(ExamRegistration, pk=pk)
    
    context = {
        'registration': registration,
        'status_choices': ExamRegistration.REGISTRATION_STATUS_CHOICES,
    }
    
    return render(request, 'exams/registrations/modals/update_status.html', context)


@login_required
def exam_registration_verify_payment_modal(request, pk):
    """Return modal for verifying payment"""
    registration = get_object_or_404(ExamRegistration, pk=pk)
    
    warnings = []
    if registration.payment_verified:
        warnings.append("Payment is already verified")
    
    context = {
        'registration': registration,
        'warnings': warnings,
    }
    
    return render(request, 'exams/registrations/modals/verify_payment.html', context)


@login_required
def exam_registration_quick_view_modal(request, pk):
    """Quick view modal for exam registration"""
    registration = get_object_or_404(
        ExamRegistration.objects.select_related(
            'student', 'examination__subject', 'examination__academic_session'
        ),
        pk=pk
    )
    
    context = {
        'registration': registration,
    }
    
    return render(request, 'exams/registrations/modals/quick_view.html', context)


@login_required
def bulk_exam_registration_modal(request):
    """Return modal for bulk exam registration"""
    # Get examinations that are accepting registrations
    examinations = Examination.objects.filter(
        status__in=['PLANNED', 'SCHEDULED']
    ).select_related('subject', 'academic_session', 'exam_category').order_by('-exam_date')
    
    # Get active students
    students = Student.objects.filter(enrollment_status='ACTIVE').order_by('first_name', 'last_name')  # ✅ ADDED ordering
    
    # Get classes for filtering
    classes = Class.objects.filter(is_active=True).select_related('academic_level').order_by('academic_level__order', 'section')  # ✅ FIXED: 'name' -> 'section'
    
    context = {
        'examinations': examinations,
        'students': students,
        'classes': classes,
    }
    
    return render(request, 'exams/registrations/modals/bulk_create.html', context)


# =============================================================================
# STUDENT RESULT MODALS
# =============================================================================

@login_required
def student_result_delete_modal(request, pk):
    """Return delete confirmation modal for student result"""
    result = get_object_or_404(StudentExamResult, pk=pk)
    
    # Check if can be deleted
    can_delete = True
    warnings = []
    
    if result.is_grade_locked:
        can_delete = False
        warnings.append("Grade is locked")
    
    if result.is_published:
        can_delete = False
        warnings.append("Result is published")
    
    if result.is_verified:
        warnings.append("Result has been verified")
    
    context = {
        'result': result,
        'can_delete': can_delete,
        'warnings': warnings,
    }
    
    return render(request, 'exams/results/modals/delete_result.html', context)


@login_required
def student_result_verify_modal(request, pk):
    """Return modal for verifying result"""
    result = get_object_or_404(StudentExamResult, pk=pk)
    
    warnings = []
    if result.is_verified:
        warnings.append("Result is already verified")
    
    if not result.score:
        warnings.append("No score entered yet")
    
    context = {
        'result': result,
        'warnings': warnings,
    }
    
    return render(request, 'exams/results/modals/verify_result.html', context)


@login_required
def student_result_moderate_modal(request, pk):
    """Return modal for moderating result"""
    result = get_object_or_404(StudentExamResult, pk=pk)
    
    warnings = []
    if result.is_moderated:
        warnings.append(f"Result already moderated (Score: {result.moderated_score})")
    
    context = {
        'result': result,
        'warnings': warnings,
    }
    
    return render(request, 'exams/results/modals/moderate_result.html', context)


@login_required
def lock_grade_modal(request, pk):
    """Return modal for locking grade"""
    result = get_object_or_404(StudentExamResult, pk=pk)
    
    # ✅ FIXED: Check permission properly
    can_lock = request.user.has_perm('exams.can_lock_grades')  # Note: should match permission in model Meta
    
    warnings = []
    if result.is_grade_locked:
        warnings.append("Grade is already locked")
        can_lock = False
    
    if not result.grade:
        warnings.append("No grade assigned yet")
        can_lock = False
    
    if not result.score:
        warnings.append("No score entered yet")
        can_lock = False
    
    context = {
        'result': result,
        'warnings': warnings,
        'can_lock': can_lock,
    }
    
    return render(request, 'exams/results/modals/lock_grade.html', context)


@login_required
def unlock_grade_modal(request, pk):
    """Return modal for unlocking grade"""
    result = get_object_or_404(StudentExamResult, pk=pk)
    
    # ✅ FIXED: Use model method if it exists
    try:
        can_unlock = result.can_unlock_grade(request.user)
    except AttributeError:
        # Fallback if method doesn't exist
        can_unlock = request.user.has_perm('exams.can_unlock_grades')
    
    warnings = []
    if not result.is_grade_locked:
        warnings.append("Grade is not locked")
        can_unlock = False
    
    if not can_unlock:
        warnings.append("You don't have permission to unlock this grade")
    
    # Get lock information
    lock_info = None
    if result.is_grade_locked:
        lock_info = {
            'locked_by': result.grade_locked_by.get_full_name() if result.grade_locked_by else 'Unknown',
            'locked_at': result.grade_locked_at,
            'reason': result.lock_reason,
        }
    
    context = {
        'result': result,
        'warnings': warnings,
        'can_unlock': can_unlock,
        'lock_info': lock_info,
    }
    
    return render(request, 'exams/results/modals/unlock_grade.html', context)


@login_required
def student_result_quick_view_modal(request, pk):
    """Quick view modal for student result"""
    result = get_object_or_404(
        StudentExamResult.objects.select_related(
            'student', 'examination__subject', 'examination__academic_session'
        ),
        pk=pk
    )
    
    # ✅ FIXED: Use model method if exists
    try:
        performance = result.get_performance_summary()
    except AttributeError:
        performance = None
    
    context = {
        'result': result,
        'performance': performance,
    }
    
    return render(request, 'exams/results/modals/quick_view.html', context)


@login_required
def grade_history_modal(request, pk):
    """Show grade history for a result"""
    result = get_object_or_404(StudentExamResult, pk=pk)
    
    # ✅ FIXED: Use model method if exists
    try:
        grade_history = result.get_grade_history() if result.is_grade_locked else None
    except AttributeError:
        grade_history = None
    
    context = {
        'result': result,
        'grade_history': grade_history,
    }
    
    return render(request, 'exams/results/modals/grade_history.html', context)


# =============================================================================
# BULK RESULT OPERATION MODALS
# =============================================================================

@login_required
def bulk_result_entry_modal(request):
    """Return modal for bulk result entry configuration"""
    examinations = Examination.objects.filter(
        status__in=['ONGOING', 'COMPLETED']
    ).select_related('subject', 'academic_session').order_by('-exam_date')
    
    classes = Class.objects.filter(is_active=True).select_related('academic_level').order_by('academic_level__order', 'section')  # ✅ FIXED: 'name' -> 'section'
    
    context = {
        'examinations': examinations,
        'classes': classes,
    }
    
    return render(request, 'exams/results/modals/bulk_entry.html', context)


@login_required
def bulk_lock_grades_modal(request):
    """Return modal for bulk grade locking"""
    # ✅ FIXED: Check permission properly
    if not request.user.has_perm('exams.can_lock_grades'):
        raise PermissionDenied("You don't have permission to lock grades")
    
    examinations = Examination.objects.filter(
        status='COMPLETED',
        results_published=True
    ).select_related('subject', 'academic_session').order_by('-exam_date')
    
    # Get lockable results for each examination
    exam_data = []
    for exam in examinations:
        lockable = exam.student_results.filter(
            is_grade_locked=False,
            is_published=True,
            score__isnull=False,
            grade__isnull=False
        ).count()
        
        if lockable > 0:
            exam_data.append({
                'examination': exam,
                'lockable_count': lockable,
            })
    
    context = {
        'exam_data': exam_data,
    }
    
    return render(request, 'exams/results/modals/bulk_lock_grades.html', context)


@login_required
def bulk_unlock_grades_modal(request):
    """Return modal for bulk grade unlocking"""
    # ✅ FIXED: Check permission properly
    if not request.user.has_perm('exams.can_unlock_grades'):
        raise PermissionDenied("You don't have permission to unlock grades")
    
    examinations = Examination.objects.filter(
        status='COMPLETED'
    ).select_related('subject', 'academic_session').order_by('-exam_date')
    
    # Get locked results for each examination
    exam_data = []
    for exam in examinations:
        locked = exam.student_results.filter(is_grade_locked=True).count()
        
        if locked > 0:
            exam_data.append({
                'examination': exam,
                'locked_count': locked,
            })
    
    context = {
        'exam_data': exam_data,
    }
    
    return render(request, 'exams/results/modals/bulk_unlock_grades.html', context)


@login_required
def bulk_publish_results_modal(request):
    """Return modal for bulk result publication"""
    examinations = Examination.objects.filter(
        status='COMPLETED',
        results_published=False
    ).select_related('subject', 'academic_session').order_by('-exam_date')
    
    # Get publishable results for each examination
    exam_data = []
    for exam in examinations:
        total = exam.student_results.count()
        completed = exam.student_results.filter(status__in=['COMPLETED', 'SUBMITTED']).count()
        
        if completed > 0:
            exam_data.append({
                'examination': exam,
                'total_results': total,
                'completed_results': completed,
            })
    
    context = {
        'exam_data': exam_data,
    }
    
    return render(request, 'exams/results/modals/bulk_publish_results.html', context)


# =============================================================================
# ANALYTICS MODALS
# =============================================================================

@login_required
def examination_analytics_modal(request, examination_pk):
    """Return modal for examination analytics"""
    examination = get_object_or_404(Examination, pk=examination_pk)
    
    try:
        analytics = examination.analytics
    except ExamAnalytics.DoesNotExist:
        analytics = None
    
    context = {
        'examination': examination,
        'analytics': analytics,
    }
    
    return render(request, 'exams/analytics/modals/examination_analytics.html', context)


@login_required
def grade_distribution_modal(request):
    """Return modal for grade distribution analysis"""
    examination_id = request.GET.get('examination')
    
    if examination_id:
        examination = get_object_or_404(Examination, pk=examination_id)
        results = examination.student_results.filter(status='COMPLETED')
        
        # Calculate grade distribution
        grade_distribution = {}
        for result in results:
            if result.grade:
                grade_distribution[result.grade] = grade_distribution.get(result.grade, 0) + 1
        
        context = {
            'examination': examination,
            'grade_distribution': grade_distribution,
        }
    else:
        context = {}
    
    return render(request, 'exams/analytics/modals/grade_distribution.html', context)


@login_required
def performance_trends_modal(request):
    """Return modal for performance trends analysis"""
    student_id = request.GET.get('student')
    
    if student_id:
        student = get_object_or_404(Student, pk=student_id)
        results = StudentExamResult.objects.filter(
            student=student,
            status='COMPLETED'
        ).select_related('examination__subject').order_by('examination__exam_date')
        
        context = {
            'student': student,
            'results': results,
        }
    else:
        context = {}
    
    return render(request, 'exams/analytics/modals/performance_trends.html', context)


@login_required
def examination_statistics_modal(request, examination_pk):
    """Return modal for detailed examination statistics"""
    examination = get_object_or_404(Examination, pk=examination_pk)
    
    results = examination.student_results.filter(status='COMPLETED')
    
    # Calculate statistics
    stats = results.aggregate(
        total=Count('id'),
        highest=Max('score'),
        lowest=Min('score'),
        average=Avg('score'),
        pass_count=Count('id', filter=Q(is_pass=True)),
    )
    
    # Grade distribution
    grade_distribution = {}
    for result in results:
        if result.grade:
            grade_distribution[result.grade] = grade_distribution.get(result.grade, 0) + 1
    
    context = {
        'examination': examination,
        'stats': stats,
        'grade_distribution': grade_distribution,
    }
    
    return render(request, 'exams/examinations/modals/statistics.html', context)


# =============================================================================
# REPORT GENERATION MODALS
# =============================================================================

@login_required
def exam_summary_report_modal(request):
    """Return modal for exam summary report generation"""
    sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')
    categories = ExamCategory.objects.filter(is_active=True).order_by('name')
    subjects = Subject.objects.filter(is_active=True).order_by('name')
    
    context = {
        'sessions': sessions,
        'categories': categories,
        'subjects': subjects,
    }
    
    return render(request, 'exams/reports/modals/exam_summary.html', context)


@login_required
def result_summary_report_modal(request):
    """Return modal for result summary report generation"""
    sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')
    classes = Class.objects.filter(is_active=True).select_related('academic_level').order_by('academic_level__order', 'section')  # ✅ FIXED: 'name' -> 'section'
    subjects = Subject.objects.filter(is_active=True).order_by('name')
    
    context = {
        'sessions': sessions,
        'classes': classes,
        'subjects': subjects,
    }
    
    return render(request, 'exams/reports/modals/result_summary.html', context)


@login_required
def grade_sheet_report_modal(request):
    """Return modal for grade sheet report generation"""
    examinations = Examination.objects.filter(
        status='COMPLETED'
    ).select_related('subject', 'academic_session').order_by('-exam_date')
    
    context = {
        'examinations': examinations,
    }
    
    return render(request, 'exams/reports/modals/grade_sheet.html', context)


@login_required
def mark_sheet_report_modal(request):
    """Return modal for mark sheet report generation"""
    examinations = Examination.objects.filter(
        status='COMPLETED'
    ).select_related('subject', 'academic_session').order_by('-exam_date')
    
    classes = Class.objects.filter(is_active=True).select_related('academic_level').order_by('academic_level__order', 'section')  # ✅ FIXED: 'name' -> 'section'
    
    context = {
        'examinations': examinations,
        'classes': classes,
    }
    
    return render(request, 'exams/reports/modals/mark_sheet.html', context)


@login_required
def pass_fail_report_modal(request):
    """Return modal for pass/fail report generation"""
    examinations = Examination.objects.filter(
        status='COMPLETED'
    ).select_related('subject', 'academic_session').order_by('-exam_date')
    
    context = {
        'examinations': examinations,
    }
    
    return render(request, 'exams/reports/modals/pass_fail.html', context)


@login_required
def rank_list_report_modal(request):
    """Return modal for rank list report generation"""
    examinations = Examination.objects.filter(
        status='COMPLETED'
    ).select_related('subject', 'academic_session').order_by('-exam_date')
    
    classes = Class.objects.filter(is_active=True).select_related('academic_level').order_by('academic_level__order', 'section')  # ✅ FIXED: 'name' -> 'section'
    
    context = {
        'examinations': examinations,
        'classes': classes,
    }
    
    return render(request, 'exams/reports/modals/rank_list.html', context)


@login_required
def merit_list_report_modal(request):
    """Return modal for merit list report generation"""
    examinations = Examination.objects.filter(
        status='COMPLETED'
    ).select_related('subject', 'academic_session').order_by('-exam_date')
    
    context = {
        'examinations': examinations,
    }
    
    return render(request, 'exams/reports/modals/merit_list.html', context)


# =============================================================================
# TIMETABLE MODALS
# =============================================================================

@login_required
def generate_timetable_modal(request):
    """Return modal for generating exam timetable"""
    sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')
    categories = ExamCategory.objects.filter(is_active=True).order_by('name')
    
    context = {
        'sessions': sessions,
        'categories': categories,
    }
    
    return render(request, 'exams/timetable/modals/generate.html', context)


@login_required
def exam_timetable_modal(request, session_pk):
    """Return modal for viewing exam timetable"""
    session = get_object_or_404(AcademicSession, pk=session_pk)
    
    examinations = Examination.objects.filter(
        academic_session=session
    ).select_related('subject', 'exam_category').order_by('exam_date', 'start_time')
    
    context = {
        'session': session,
        'examinations': examinations,
    }
    
    return render(request, 'exams/timetable/modals/view.html', context)


# =============================================================================
# IMPORT/EXPORT MODALS
# =============================================================================

@login_required
def import_results_modal(request):
    """Return modal for importing results"""
    examinations = Examination.objects.filter(
        status__in=['ONGOING', 'COMPLETED']
    ).select_related('subject', 'academic_session').order_by('-exam_date')
    
    context = {
        'examinations': examinations,
    }
    
    return render(request, 'exams/import/modals/import_results.html', context)


@login_required
def import_examinations_modal(request):
    """Return modal for importing examinations"""
    sessions = AcademicSession.objects.filter(is_active=True).order_by('-start_date')
    categories = ExamCategory.objects.filter(is_active=True).order_by('name')
    
    context = {
        'sessions': sessions,
        'categories': categories,
    }
    
    return render(request, 'exams/import/modals/import_examinations.html', context)


@login_required
def import_grading_systems_modal(request):
    """Return modal for importing grading systems"""
    context = {}
    
    return render(request, 'exams/import/modals/import_grading_systems.html', context)


@login_required
def export_options_modal(request, resource_type):
    """Return modal for export options"""
    valid_types = ['categories', 'grading_systems', 'examinations', 'registrations', 'results']
    
    if resource_type not in valid_types:
        resource_type = 'results'
    
    context = {
        'resource_type': resource_type,
    }
    
    return render(request, 'exams/export/modals/export_options.html', context)


# =============================================================================
# SETTINGS MODALS
# =============================================================================

@login_required
def exam_settings_modal(request):
    """Return modal for exam settings"""
    context = {}
    
    return render(request, 'exams/settings/modals/exam_settings.html', context)


@login_required
def grading_scale_settings_modal(request):
    """Return modal for grading scale settings"""
    grading_systems = GradingSystem.objects.filter(is_active=True).order_by('name')
    
    context = {
        'grading_systems': grading_systems,
    }
    
    return render(request, 'exams/settings/modals/grading_scale.html', context)


@login_required
def grade_locking_settings_modal(request):
    """Return modal for grade locking settings"""
    context = {}
    
    return render(request, 'exams/settings/modals/grade_locking.html', context)


# =============================================================================
# UTILITY MODALS
# =============================================================================

@login_required
def history_modal(request, content_type, object_id):
    """Return modal for viewing object history"""
    # This would integrate with django-simple-history or similar
    context = {
        'content_type': content_type,
        'object_id': object_id,
    }
    
    return render(request, 'exams/modals/history.html', context)


@login_required
def confirm_action_modal(request):
    """Return generic confirmation modal"""
    action = request.GET.get('action', 'perform this action')
    message = request.GET.get('message', 'Are you sure you want to proceed?')
    
    context = {
        'action': action,
        'message': message,
    }
    
    return render(request, 'exams/modals/confirm_action.html', context)


@login_required
def student_exam_history_modal(request, student_pk):
    """Return modal for student exam history"""
    student = get_object_or_404(Student, pk=student_pk)
    
    results = StudentExamResult.objects.filter(
        student=student
    ).select_related('examination__subject', 'examination__academic_session').order_by('-examination__exam_date')
    
    context = {
        'student': student,
        'results': results,
    }
    
    return render(request, 'exams/students/modals/exam_history.html', context)


@login_required
def student_results_summary_modal(request, student_pk):
    """Return modal for student results summary"""
    student = get_object_or_404(Student, pk=student_pk)
    
    # Get current session results
    current_session = get_active_academic_session()
    
    if current_session:
        results = StudentExamResult.objects.filter(
            student=student,
            examination__academic_session=current_session,
            status='COMPLETED'
        ).select_related('examination__subject')
        
        # Calculate statistics
        stats = results.aggregate(
            total=Count('id'),
            average=Avg('score'),
            pass_count=Count('id', filter=Q(is_pass=True)),
        )
    else:
        results = StudentExamResult.objects.none()
        stats = {'total': 0, 'average': 0, 'pass_count': 0}
    
    context = {
        'student': student,
        'current_session': current_session,
        'results': results,
        'stats': stats,
    }
    
    return render(request, 'exams/students/modals/results_summary.html', context)