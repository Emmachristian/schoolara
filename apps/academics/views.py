# academics/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db.models import Q
from datetime import datetime
from io import BytesIO
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone

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
    AcademicSession, Holiday, AcademicLevel, Subject, 
    ClassRoom, Class, ClassSubject
)
from .forms import (
    AcademicSessionForm, HolidayForm, AcademicLevelForm,
    SubjectForm, ClassRoomForm, ClassForm, ClassSubjectForm
)

from .utils import (
    paginate_queryset, analyze_break_gaps, sync_breaks_with_preview,
    get_break_recommendations
) 
from .stats import (
    get_academic_level_statistics, get_session_timeline_data, get_holiday_statistics,
    get_subject_statistics, get_class_statistics, get_classroom_statistics,
    get_academic_session_statistics, get_class_subject_statistics, get_academic_dashboard_statistics
)

# =============================================================================
# ACADEMIC SESSION VIEWS
# =============================================================================

@login_required
def academic_session_list(request):
    """List all academic sessions with pagination and statistics"""
    
    # Fetch all sessions, ordered by start date and term number
    sessions_queryset = AcademicSession.objects.all().order_by('-start_date', 'term_number')
    
    # Use paginate_queryset utility
    sessions_page, paginator = paginate_queryset(request, sessions_queryset, per_page=15)
    
    # Get statistics directly from statistics module
    stats = get_academic_session_statistics()
    
    context = {
        'sessions': sessions_page,
        'stats': stats,
    }
    
    return render(request, 'sessions/list.html', context)

@login_required
def academic_session_create(request):
    """Create a new academic session"""
    
    if request.method == 'POST':
        form = AcademicSessionForm(request.POST)
        if form.is_valid():
            session = form.save()
            messages.success(request, f'Academic session "{session.name}" created successfully.')
            return redirect('academics:academic_session_detail', pk=session.pk)
    else:
        form = AcademicSessionForm()
    
    context = {
        'form': form,
        'form_action': 'Create',
        'title': 'Create Academic Session'
    }
    
    return render(request, 'sessions/form.html', context)

@login_required
def academic_session_update(request, pk):
    """Update an existing academic session"""
    
    session = get_object_or_404(AcademicSession, pk=pk)
    
    if request.method == 'POST':
        form = AcademicSessionForm(request.POST, instance=session)
        if form.is_valid():
            session = form.save()
            messages.success(request, f'Academic session "{session.name}" updated successfully.')
            return redirect('academics:academic_session_detail', pk=session.pk)
    else:
        form = AcademicSessionForm(instance=session)
    
    context = {
        'form': form,
        'session': session,
        'form_action': 'Update',
        'title': f'Update {session.name}'
    }
    
    return render(request, 'sessions/form.html', context)

@login_required
def academic_session_detail(request, pk):
    """View details of an academic session with statistics"""
    
    session = get_object_or_404(AcademicSession, pk=pk)
    
    # Get related data
    classes = Class.objects.filter(academic_session=session)
    holidays = Holiday.objects.filter(academic_session=session)
    
    # Get session-specific statistics
    session_stats = get_class_statistics(filters={'academic_session': str(session.id)})
    
    context = {
        'session': session,
        'classes': classes[:10],  # Show first 10
        'holidays': holidays[:5],  # Show first 5
        'stats': session_stats,
    }
    
    return render(request, 'sessions/detail.html', context)

@login_required
def academic_session_delete(request, pk):
    """Delete an academic session"""

    session = get_object_or_404(AcademicSession, pk=pk)

    if request.method == "POST":
        session_name = str(session)  # or session.name
        session.delete()
        messages.success(request, f'Academic session "{session_name}" deleted successfully.')
        return redirect("academics:academic_session_list")

    # If the request is not POST, just redirect back to the list
    return redirect("academics:academic_session_list")

# =============================================================================
# HOLIDAY VIEWS
# =============================================================================

@login_required
def holiday_list(request):
    """List all holidays with pagination and statistics"""
    
    # Fetch all holidays ordered by start date
    holidays_queryset = Holiday.objects.all().order_by('start_date')
    
    # Use the utility for pagination
    holidays_page, paginator = paginate_queryset(request, holidays_queryset, per_page=20)
    
    # Get statistics from statistics module
    stats = get_holiday_statistics()
    
    # Available years for filters
    current_year = timezone.now().year
    available_years = range(current_year - 2, current_year + 3)
    
    context = {
        'holidays': holidays_page,
        'available_years': available_years,
        'stats': stats,
    }
    
    return render(request, 'holidays/list.html', context)

@login_required
def holiday_create(request):
    """Create a new holiday"""
    
    if request.method == 'POST':
        form = HolidayForm(request.POST)
        if form.is_valid():
            holiday = form.save()
            messages.success(request, f'Holiday "{holiday.name}" created successfully.')
            return redirect('academics:holiday_list')
    else:
        form = HolidayForm()
    
    context = {
        'form': form,
        'form_action': 'Create',
        'title': 'Create Holiday'
    }
    
    return render(request, 'holidays/form.html', context)

@login_required
def holiday_update(request, pk):
    """Update an existing holiday"""
    
    holiday = get_object_or_404(Holiday, pk=pk)
    
    if request.method == 'POST':
        form = HolidayForm(request.POST, instance=holiday)
        if form.is_valid():
            holiday = form.save()
            messages.success(request, f'Holiday "{holiday.name}" updated successfully.')
            return redirect('academics:holiday_list')
    else:
        form = HolidayForm(instance=holiday)
    
    context = {
        'form': form,
        'holiday': holiday,
        'form_action': 'Update',
        'title': f'Update {holiday.name}'
    }
    
    return render(request, 'holidays/form.html', context)

@login_required
def holiday_delete(request, pk):
    """Delete a holiday"""

    holiday = get_object_or_404(Holiday, pk=pk)

    if request.method == "POST":
        holiday_name = str(holiday)  # or holiday.name
        holiday.delete()
        messages.success(request, f'Holiday "{holiday_name}" deleted successfully.')
        return redirect("academics:holiday_list")

    # If not POST, just redirect back to the list
    return redirect("academics:holiday_list")

@login_required
def break_analysis(request):
    """Analyze breaks between academic sessions"""
    
    year_filter = request.GET.get('year', '')
    
    # Get break gap analysis
    analysis = analyze_break_gaps(year_filter=year_filter if year_filter else None)
    
    # Get recommendations
    recommendations = get_break_recommendations()
    
    # Get available years
    available_years = AcademicSession.objects.values_list('year_name', flat=True).distinct()
    
    context = {
        'analysis': analysis,
        'recommendations': recommendations,
        'available_years': available_years,
        'year_filter': year_filter,
    }
    
    return render(request, 'holidays/break_analysis.html', context)

@login_required
def sync_breaks(request):
    """Synchronize breaks with academic sessions"""
    
    if request.method == 'POST':
        scope = request.POST.get('scope', 'missing_only')
        year_filter = request.POST.get('year_filter', None)
        force_recreation = request.POST.get('force_recreation') == 'true'
        dry_run = request.POST.get('dry_run') != 'false'
        
        result = sync_breaks_with_preview(
            scope=scope,
            year_filter=year_filter,
            force_recreation=force_recreation,
            dry_run=dry_run
        )
        
        if not dry_run and result['success']:
            messages.success(request, f"Successfully synchronized {result['statistics']['creates']} breaks.")
        elif not result['success']:
            messages.error(request, "Error synchronizing breaks. Check logs for details.")
        
        return JsonResponse(result)
    
    # GET request - show preview
    scope = request.GET.get('scope', 'missing_only')
    year_filter = request.GET.get('year_filter', None)
    
    preview = sync_breaks_with_preview(
        scope=scope,
        year_filter=year_filter,
        dry_run=True
    )
    
    context = {
        'preview': preview,
        'scope': scope,
        'year_filter': year_filter,
    }
    
    return render(request, 'holidays/sync_breaks.html', context)

# =============================================================================
# ACADEMIC LEVEL VIEWS
# =============================================================================

@login_required
def academic_level_list(request):
    """List all academic levels with statistics"""
    
    levels_queryset = AcademicLevel.objects.all().order_by('order')
    
    # Use utility for pagination
    levels_page, paginator = paginate_queryset(request, levels_queryset, per_page=10)
    
    # Get statistics from statistics module
    stats = get_academic_level_statistics()
    
    context = {
        'levels': levels_page,
        'stats': stats,
    }
    
    return render(request, 'levels/list.html', context)

def academic_level_create(request):
    """Create a new academic level"""
    if request.method == 'POST':
        form = AcademicLevelForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('academics:academic_level_list')  
    else:
        form = AcademicLevelForm()
    
    context = {'form': form}
    return render(request, 'levels/form.html', context)

@login_required
def academic_level_update(request, pk):
    """Update academic level"""
    level = get_object_or_404(AcademicLevel, pk=pk)
    
    if request.method == 'POST':
        form = AcademicLevelForm(request.POST, instance=level)
        if form.is_valid():
            level = form.save(commit=False)
            level.save()           
    else:
        form = AcademicLevelForm(instance=level)
    
    context = {
        'form': form,
        'level': level,
        'form_action': 'Update'
    }
    
    return render(request, 'levels/form.html', context)

@login_required
def academic_level_delete(request, pk):
    """Delete an academic level safely"""

    level = get_object_or_404(AcademicLevel, pk=pk)

    if request.method == "POST":
        # Check if any other level points to this as next_level
        dependent_levels = AcademicLevel.objects.filter(next_level=level)
        if dependent_levels.exists():
            # Optional: prevent deletion or handle them
            messages.error(
                request, 
                f'Cannot delete "{level.name}" because {dependent_levels.count()} level(s) depend on it as their next level.'
            )
            return redirect("academics:academic_level_list")

        level_name = str(level)
        level.delete()
        messages.success(request, f'Academic level "{level_name}" deleted successfully.')
        return redirect("academics:academic_level_list")

    # For GET, just redirect to the list
    return redirect("academics:academic_level_list")

# =============================================================================
# SUBJECT VIEWS
# =============================================================================

@login_required
def subject_list(request):
    """List all subjects with pagination and statistics"""
    
    subjects_queryset = Subject.objects.all().order_by('subject_type', 'abbreviation')
    
    # Pagination
    subjects_page, paginator = paginate_queryset(request, subjects_queryset, per_page=20)
    
    # Get statistics from statistics module
    stats = get_subject_statistics()
    
    context = {
        'subjects': subjects_page,
        'stats': stats,
    }
    
    return render(request, 'subjects/list.html', context)

@login_required
def subject_create(request):
    """Create a new subject"""
    
    if request.method == 'POST':
        form = SubjectForm(request.POST)
        if form.is_valid():
            subject = form.save()
            messages.success(request, f'Subject "{subject.name}" created successfully.')
            return redirect('academics:subject_detail', pk=subject.pk)
    else:
        form = SubjectForm()
    
    context = {
        'form': form,
        'form_action': 'Create',
        'title': 'Create Subject'
    }
    
    return render(request, 'subjects/form.html', context)

@login_required
def subject_update(request, pk):
    """Update an existing subject"""
    
    subject = get_object_or_404(Subject, pk=pk)
    
    if request.method == 'POST':
        form = SubjectForm(request.POST, instance=subject)
        if form.is_valid():
            subject = form.save()
            messages.success(request, f'Subject "{subject.name}" updated successfully.')
            return redirect('academics:subject_detail', pk=subject.pk)
    else:
        form = SubjectForm(instance=subject)
    
    context = {
        'form': form,
        'subject': subject,
        'form_action': 'Update',
        'title': f'Update {subject.name}'
    }
    
    return render(request, 'subjects/form.html', context)

@login_required
def subject_detail(request, pk):
    """View details of a subject with statistics"""
    
    subject = get_object_or_404(Subject, pk=pk)
    
    # Get related data
    class_subjects = ClassSubject.objects.filter(subject=subject).select_related('class_instance', 'teacher')
    prerequisites = subject.prerequisites.all()
    prerequisite_for = subject.prerequisite_for.all()
    
    # Get subject-specific statistics
    subject_stats = get_class_subject_statistics(filters={'subject': str(subject.id)})
    
    context = {
        'subject': subject,
        'class_subjects': class_subjects[:10],
        'prerequisites': prerequisites,
        'prerequisite_for': prerequisite_for,
        'stats': subject_stats,
    }
    
    return render(request, 'subjects/detail.html', context)

@login_required
def subject_delete(request, pk):
    """Delete a subject safely"""

    subject = get_object_or_404(Subject, pk=pk)

    # Check if subject is assigned to any classes
    if ClassSubject.objects.filter(subject=subject).exists():
        messages.error(request, 'Cannot delete subject that is assigned to classes.')
        return redirect('academics:subject_list')

    if request.method == "POST":
        subject_name = subject.name
        subject.delete()
        messages.success(request, f'Subject "{subject_name}" deleted successfully.')
        return redirect('academics:subject_list')

    # For GET requests, just redirect to list (modal will handle confirmation)
    return redirect('academics:subject_list')


# =============================================================================
# CLASSROOM VIEWS
# =============================================================================

@login_required
def classroom_list(request):
    """List all classrooms with pagination and statistics"""
    
    classrooms_queryset = ClassRoom.objects.all().order_by('building', 'floor', 'room_number')
    
    # Get distinct buildings for frontend display
    available_buildings = ClassRoom.objects.values_list('building', flat=True).distinct()
    
    # Pagination
    classrooms_page, paginator = paginate_queryset(request, classrooms_queryset, per_page=20)
    
    # Get statistics from statistics module
    stats = get_classroom_statistics()
    
    context = {
        'classrooms': classrooms_page,
        'available_buildings': available_buildings,
        'stats': stats,
    }
    
    return render(request, 'classrooms/list.html', context)

@login_required
def classroom_create(request):
    """Create a new classroom"""
    
    if request.method == 'POST':
        form = ClassRoomForm(request.POST)
        if form.is_valid():
            classroom = form.save()
            messages.success(request, f'Classroom "{classroom.name}" created successfully.')
            return redirect('academics:classroom_detail', pk=classroom.pk)
    else:
        form = ClassRoomForm()
    
    context = {
        'form': form,
        'form_action': 'Create',
        'title': 'Create Classroom'
    }
    
    return render(request, 'classrooms/form.html', context)

@login_required
def classroom_update(request, pk):
    """Update an existing classroom"""
    
    classroom = get_object_or_404(ClassRoom, pk=pk)
    
    if request.method == 'POST':
        form = ClassRoomForm(request.POST, instance=classroom)
        if form.is_valid():
            classroom = form.save()
            messages.success(request, f'Classroom "{classroom.name}" updated successfully.')
            return redirect('academics:classroom_detail', pk=classroom.pk)
    else:
        form = ClassRoomForm(instance=classroom)
    
    context = {
        'form': form,
        'classroom': classroom,
        'form_action': 'Update',
        'title': f'Update {classroom.name}'
    }
    
    return render(request, 'classrooms/form.html', context)

@login_required
def classroom_detail(request, pk):
    """View details of a classroom with statistics"""
    
    classroom = get_object_or_404(ClassRoom, pk=pk)
    
    # Get assigned classes
    assigned_classes = Class.objects.filter(classroom=classroom)
    
    # Get classroom-specific statistics (filter by this classroom)
    classroom_stats = {
        'total_classes': assigned_classes.count(),
        'active_classes': assigned_classes.filter(is_active=True).count(),
        'total_capacity': classroom.capacity,
    }
    
    context = {
        'classroom': classroom,
        'assigned_classes': assigned_classes,
        'stats': classroom_stats,
    }
    
    return render(request, 'classrooms/detail.html', context)

@login_required
def classroom_delete(request, pk):
    """Delete a classroom safely"""

    classroom = get_object_or_404(ClassRoom, pk=pk)

    # Check if classroom is assigned to any classes
    if Class.objects.filter(classroom=classroom).exists():
        messages.error(request, 'Cannot delete classroom that is assigned to classes.')
        return redirect('academics:classroom_list')

    if request.method == "POST":
        classroom_name = classroom.name
        classroom.delete()
        messages.success(request, f'Classroom "{classroom_name}" deleted successfully.')
        return redirect('academics:classroom_list')

    # For GET requests, just redirect to list (modal will handle confirmation)
    return redirect('academics:classroom_list')

# =============================================================================
# CLASS VIEWS
# =============================================================================

@login_required
def class_list(request):
    """List all classes with pagination and statistics"""
    
    classes_queryset = Class.objects.all().select_related(
        'academic_level', 'academic_session', 'class_teacher', 'classroom'
    ).order_by('academic_level__order', 'section')
    
    # Filter options for frontend dropdowns
    available_levels = AcademicLevel.objects.filter(is_active=True).order_by('order')
    available_sessions = AcademicSession.objects.all().order_by('-start_date')
    
    # Pagination
    classes_page, paginator = paginate_queryset(request, classes_queryset, per_page=20)
    
    # Get statistics from statistics module
    stats = get_class_statistics()
    
    context = {
        'classes': classes_page,
        'available_levels': available_levels,
        'available_sessions': available_sessions,
        'stats': stats,
    }
    
    return render(request, 'classes/list.html', context)

@login_required
def class_create(request):
    """Create a new class"""
    
    if request.method == 'POST':
        form = ClassForm(request.POST)
        if form.is_valid():
            class_obj = form.save()
            messages.success(request, f'Class "{class_obj.name}" created successfully.')
            return redirect('academics:class_detail', pk=class_obj.pk)
    else:
        form = ClassForm()
    
    context = {
        'form': form,
        'form_action': 'Create',
        'title': 'Create Class'
    }
    
    return render(request, 'classes/form.html', context)

@login_required
def class_update(request, pk):
    """Update an existing class"""
    
    class_obj = get_object_or_404(Class, pk=pk)
    
    if request.method == 'POST':
        form = ClassForm(request.POST, instance=class_obj)
        if form.is_valid():
            class_obj = form.save()
            messages.success(request, f'Class "{class_obj.name}" updated successfully.')
            return redirect('academics:class_detail', pk=class_obj.pk)
    else:
        form = ClassForm(instance=class_obj)
    
    context = {
        'form': form,
        'class': class_obj,
        'form_action': 'Update',
        'title': f'Update {class_obj.name}'
    }
    
    return render(request, 'classes/form.html', context)

@login_required
def class_detail(request, pk):
    """View details of a class with statistics"""
    
    class_obj = get_object_or_404(Class, pk=pk)
    
    # Get related data
    class_subjects = ClassSubject.objects.filter(
        class_instance=class_obj
    ).select_related('subject', 'teacher')
    
    # Get class-specific statistics
    class_stats = get_class_subject_statistics(filters={'class_instance': str(class_obj.id)})
    
    # Add enrollment info
    enrollment_count = class_obj.get_current_enrollment_count()
    available_capacity = class_obj.get_available_capacity()
    occupancy_percentage = class_obj.get_occupancy_percentage()
    
    class_stats['enrollment_info'] = {
        'current_enrollment': enrollment_count,
        'available_capacity': available_capacity,
        'occupancy_percentage': occupancy_percentage,
        'max_students': class_obj.max_students,
    }
    
    context = {
        'class': class_obj,
        'class_subjects': class_subjects,
        'stats': class_stats,
    }
    
    return render(request, 'classes/detail.html', context)

@login_required
def class_delete(request, pk):
    """Delete a class safely"""

    class_obj = get_object_or_404(Class, pk=pk)

    # Prevent deletion if there are enrolled students
    enrollment_count = class_obj.get_current_enrollment_count()
    if enrollment_count > 0:
        messages.error(request, f'Cannot delete class with {enrollment_count} enrolled students.')
        return redirect('academics:class_list')

    if request.method == "POST":
        class_name = class_obj.name
        class_obj.delete()
        messages.success(request, f'Class "{class_name}" deleted successfully.')
        return redirect('academics:class_list')

    # For GET requests, just redirect to list (modal handles confirmation)
    return redirect('academics:class_list')

# =============================================================================
# CLASS SUBJECT VIEWS
# =============================================================================

@login_required
def class_subject_list(request):
    """List all class subject assignments with statistics"""
    
    class_subjects_queryset = ClassSubject.objects.all().select_related(
        'class_instance__academic_level', 'subject', 'teacher'
    ).order_by('class_instance__academic_level__order', 'subject__name')
    
    # Filter options for dropdowns
    available_classes = Class.objects.filter(is_active=True).select_related('academic_level')
    available_subjects = Subject.objects.filter(is_active=True).order_by('name')

    from hr.models import Teacher
    available_teachers = Teacher.objects.filter(
        staff__is_active=True,
        staff__employment_status='ACTIVE'  # if this field exists
    ).select_related('staff')
    
    # Pagination
    class_subjects_page, paginator = paginate_queryset(request, class_subjects_queryset, per_page=30)
    
    # Get statistics from statistics module
    stats = get_class_subject_statistics()
    
    context = {
        'class_subjects': class_subjects_page,
        'available_classes': available_classes,
        'available_subjects': available_subjects,
        'available_teachers': available_teachers,
        'stats': stats,
    }
    
    return render(request, 'class_subjects/list.html', context)

@login_required
def class_subject_create(request):
    """Assign a subject to a class"""
    
    if request.method == 'POST':
        form = ClassSubjectForm(request.POST)
        if form.is_valid():
            class_subject = form.save()
            messages.success(
                request, 
                f'Subject "{class_subject.subject.name}" assigned to {class_subject.class_instance.name} successfully.'
            )
            return redirect('academics:class_detail', pk=class_subject.class_instance.pk)
    else:
        # Pre-fill class if provided in URL
        class_id = request.GET.get('class_id')
        initial = {}
        if class_id:
            initial['class_instance'] = class_id
        form = ClassSubjectForm(initial=initial)
    
    context = {
        'form': form,
        'form_action': 'Create',
        'title': 'Assign Subject to Class'
    }
    
    return render(request, 'class_subjects/form.html', context)

@login_required
def class_subject_update(request, pk):
    """Update a class subject assignment"""
    
    class_subject = get_object_or_404(ClassSubject, pk=pk)
    
    if request.method == 'POST':
        form = ClassSubjectForm(request.POST, instance=class_subject)
        if form.is_valid():
            class_subject = form.save()
            messages.success(request, 'Class subject assignment updated successfully.')
            return redirect('academics:class_detail', pk=class_subject.class_instance.pk)
    else:
        form = ClassSubjectForm(instance=class_subject)
    
    context = {
        'form': form,
        'class_subject': class_subject,
        'form_action': 'Update',
        'title': f'Update {class_subject.subject.name} for {class_subject.class_instance.name}'
    }
    
    return render(request, 'class_subjects/form.html', context)

@login_required
def class_subject_delete(request, pk):
    """Remove a subject from a class safely"""

    class_subject = get_object_or_404(ClassSubject, pk=pk)
    class_instance = class_subject.class_instance

    if request.method == "POST":
        subject_name = class_subject.subject.name
        class_subject.delete()
        messages.success(request, f'Subject "{subject_name}" removed from class successfully.')
        return redirect('academics:class_detail', pk=class_instance.pk)

    # For GET requests, just redirect to the class detail (modal handles confirmation)
    return redirect('academics:class_detail', pk=class_instance.pk)


# =============================================================================
# EXPORT VIEWS
# =============================================================================

@login_required
def export_levels_excel(request):
    """Export academic levels to Excel with filters applied"""
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    is_active = request.GET.get('is_active', '')
    has_sections = request.GET.get('has_sections', '')
    is_graduation_level = request.GET.get('is_graduation_level', '')
    
    # Apply filters
    levels = AcademicLevel.objects.all().order_by('order').select_related('next_level')
    
    if query:
        terms = query.split()
        q_objects = Q()
        for term in terms:
            q_objects &= Q(name__icontains=term) | Q(code__icontains=term)
        levels = levels.filter(q_objects)
    
    if is_active != '':
        levels = levels.filter(is_active=(is_active.lower() == 'true'))
    
    if has_sections != '':
        levels = levels.filter(has_sections=(has_sections.lower() == 'true'))
    
    if is_graduation_level != '':
        levels = levels.filter(is_graduation_level=(is_graduation_level.lower() == 'true'))
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Academic Levels"
    
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
    ws.merge_cells('A1:H1')
    title_cell = ws['A1']
    title_cell.value = "Academic Levels Report"
    title_cell.font = Font(bold=True, size=16, color="4472C4")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # Subtitle with date and filters
    ws.merge_cells('A2:H2')
    subtitle_cell = ws['A2']
    filter_text = f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    if query:
        filter_text += f" | Search: {query}"
    if is_active != '':
        filter_text += f" | Active: {'Yes' if is_active.lower() == 'true' else 'No'}"
    if has_sections != '':
        filter_text += f" | Has Sections: {'Yes' if has_sections.lower() == 'true' else 'No'}"
    if is_graduation_level != '':
        filter_text += f" | Graduation Level: {'Yes' if is_graduation_level.lower() == 'true' else 'No'}"
    
    subtitle_cell.value = filter_text
    subtitle_cell.font = Font(size=10, italic=True)
    subtitle_cell.alignment = Alignment(horizontal="center")
    
    ws.append([])  # Empty row
    
    # Headers
    headers = [
        'Order', 'Level Name', 'Code', 'Description', 'Next Level', 
        'Has Sections', 'Is Active', 'Graduation Level'
    ]
    
    ws.append(headers)
    header_row = ws[4]
    
    for cell in header_row:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = border_style
    
    # Data rows
    for level in levels:
        row_data = [
            level.order,
            level.name,
            level.code,
            level.description if level.description else '',
            level.next_level.name if level.next_level else 'Terminal Level',
            'Yes' if level.has_sections else 'No',
            'Yes' if level.is_active else 'No',
            'Yes' if level.is_graduation_level else 'No',
        ]
        
        ws.append(row_data)
        
        # Style data rows
        current_row = ws.max_row
        for cell in ws[current_row]:
            cell.border = border_style
            cell.alignment = Alignment(vertical="center", wrap_text=True)
    
    # Adjust column widths
    column_widths = {
        'A': 8,   # Order
        'B': 25,  # Level Name
        'C': 12,  # Code
        'D': 40,  # Description
        'E': 20,  # Next Level
        'F': 12,  # Has Sections
        'G': 10,  # Is Active
        'H': 15,  # Graduation Level
    }
    
    for col, width in column_widths.items():
        ws.column_dimensions[col].width = width
    
    # Summary at bottom
    summary_row = ws.max_row + 2
    ws[f'A{summary_row}'] = 'Total Levels:'
    ws[f'B{summary_row}'] = levels.count()
    ws[f'A{summary_row}'].font = Font(bold=True)
    ws[f'B{summary_row}'].font = Font(bold=True)
    
    # Additional statistics
    active_count = levels.filter(is_active=True).count()
    graduation_count = levels.filter(is_graduation_level=True).count()
    sections_count = levels.filter(has_sections=True).count()
    
    ws[f'A{summary_row + 1}'] = 'Active Levels:'
    ws[f'B{summary_row + 1}'] = active_count
    ws[f'A{summary_row + 1}'].font = Font(bold=True)
    
    ws[f'A{summary_row + 2}'] = 'Graduation Levels:'
    ws[f'B{summary_row + 2}'] = graduation_count
    ws[f'A{summary_row + 2}'].font = Font(bold=True)
    
    ws[f'A{summary_row + 3}'] = 'Levels with Sections:'
    ws[f'B{summary_row + 3}'] = sections_count
    ws[f'A{summary_row + 3}'].font = Font(bold=True)
    
    # Freeze panes (header row)
    ws.freeze_panes = 'A5'
    
    # Create response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"academic_levels_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response

@login_required
def export_levels_pdf(request):
    """Export academic levels to PDF with filters applied"""
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    is_active = request.GET.get('is_active', '')
    has_sections = request.GET.get('has_sections', '')
    is_graduation_level = request.GET.get('is_graduation_level', '')
    
    # Apply filters
    levels = AcademicLevel.objects.all().order_by('order').select_related('next_level')
    
    if query:
        terms = query.split()
        q_objects = Q()
        for term in terms:
            q_objects &= Q(name__icontains=term) | Q(code__icontains=term)
        levels = levels.filter(q_objects)
    
    if is_active != '':
        levels = levels.filter(is_active=(is_active.lower() == 'true'))
    
    if has_sections != '':
        levels = levels.filter(has_sections=(has_sections.lower() == 'true'))
    
    if is_graduation_level != '':
        levels = levels.filter(is_graduation_level=(is_graduation_level.lower() == 'true'))
    
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
    title = Paragraph("Academic Levels Report", title_style)
    elements.append(title)
    
    # Subtitle with filters
    filter_text = f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    if query:
        filter_text += f" | Search: {query}"
    if is_active != '':
        filter_text += f" | Active: {'Yes' if is_active.lower() == 'true' else 'No'}"
    if has_sections != '':
        filter_text += f" | Has Sections: {'Yes' if has_sections.lower() == 'true' else 'No'}"
    if is_graduation_level != '':
        filter_text += f" | Graduation: {'Yes' if is_graduation_level.lower() == 'true' else 'No'}"
    
    subtitle = Paragraph(filter_text, subtitle_style)
    elements.append(subtitle)
    elements.append(Spacer(1, 0.2*inch))
    
    # Table data
    data = [['Order', 'Level Name', 'Code', 'Next Level', 'Sections', 'Active', 'Graduation']]
    
    for level in levels:
        row = [
            str(level.order),
            level.name[:30],  # Truncate long names
            level.code,
            level.next_level.code[:15] if level.next_level else 'Terminal',
            'Yes' if level.has_sections else 'No',
            'Yes' if level.is_active else 'No',
            'Yes' if level.is_graduation_level else 'No',
        ]
        data.append(row)
    
    # Create table
    table = Table(data, colWidths=[
        0.6*inch,  # Order
        2.2*inch,  # Level Name
        0.9*inch,  # Code
        1.5*inch,  # Next Level
        0.8*inch,  # Sections
        0.7*inch,  # Active
        1*inch,    # Graduation
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
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # Order column
        ('ALIGN', (4, 1), (-1, -1), 'CENTER'),  # Sections, Active, Graduation columns
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        
        # Alternating row colors
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
        
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    
    elements.append(table)
    
    # Summary statistics
    elements.append(Spacer(1, 0.3*inch))
    
    active_count = levels.filter(is_active=True).count()
    graduation_count = levels.filter(is_graduation_level=True).count()
    sections_count = levels.filter(has_sections=True).count()
    
    summary_text = f"""
    <b>Summary Statistics:</b><br/>
    Total Levels: {levels.count()}<br/>
    Active Levels: {active_count}<br/>
    Graduation Levels: {graduation_count}<br/>
    Levels with Sections: {sections_count}
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
    filename = f"academic_levels_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write(pdf)
    
    return response