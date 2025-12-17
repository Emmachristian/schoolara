# academics/ajax_views.py

from django.http import JsonResponse
from django.db.models import Q
import logging

from .models import (
    AcademicSession, Holiday, Subject, AcademicLevel, 
    ClassRoom, Class, ClassSubject
)

from .utils import parse_filters, paginate_queryset

from .stats import (
    get_academic_session_statistics,
    get_holiday_statistics,
    get_subject_statistics,
    get_academic_level_statistics,
    get_classroom_statistics,
    get_class_statistics,
    
    get_class_subject_statistics,
)

logger = logging.getLogger(__name__)


# =============================================================================
# ACADEMIC SESSION SEARCH
# =============================================================================

def academic_session_search(request):
    """
    AJAX view to return filtered academic sessions as JSON with statistics
    """
    # Extract filters using parse_filters
    filters = parse_filters(request, [
        'q', 'year_name', 'period_type', 
        'is_current', 'is_active', 'is_closed', 'allows_promotion', 'page'
    ])
    
    query = filters['q']
    year_name = filters['year_name']
    period_type = filters['period_type']
    is_current = filters['is_current']
    is_active = filters['is_active']
    is_closed = filters['is_closed']
    allows_promotion = filters['allows_promotion']
    page = filters['page'] or 1

    # Start with all sessions
    sessions = AcademicSession.objects.all().order_by('-start_date', 'term_number')

    # Apply text search
    if query:
        sessions = sessions.filter(
            Q(year_name__icontains=query) |
            Q(term_name__icontains=query)
        )

    # Apply exact and boolean filters
    if year_name:
        sessions = sessions.filter(year_name=year_name)
    if period_type:
        sessions = sessions.filter(period_type=period_type)
    if is_current is not None:
        sessions = sessions.filter(is_current=(is_current.lower() == 'true'))
    if is_active is not None:
        sessions = sessions.filter(is_active=(is_active.lower() == 'true'))
    if is_closed is not None:
        sessions = sessions.filter(is_closed=(is_closed.lower() == 'true'))
    if allows_promotion is not None:
        sessions = sessions.filter(allows_promotion=(allows_promotion.lower() == 'true'))

    # Get comprehensive statistics using statistics module
    stats_filters = {}
    if year_name:
        stats_filters['year_name'] = year_name
    if period_type:
        stats_filters['period_type'] = period_type
    if is_active is not None:
        stats_filters['is_active'] = (is_active.lower() == 'true')
    if is_current is not None:
        stats_filters['is_current'] = (is_current.lower() == 'true')
    
    stats = get_academic_session_statistics(filters=stats_filters if stats_filters else None)

    # Handle pagination (or return all)
    if page == 'all':
        session_list = [{
            'id': str(s.id),
            'name': s.name,
            'display_name': s.display_name,
            'year_name': s.year_name,
            'term_name': s.term_name,
            'term_number': s.term_number,
            'period_type': s.get_period_type_display(),
            'start_date': s.start_date.isoformat(),
            'end_date': s.end_date.isoformat(),
            'is_current': s.is_current,
            'is_active': s.is_active,
            'is_closed': s.is_closed,
            'status': s.status_display,
            'days_remaining': s.days_remaining,
            'progress_percentage': s.progress_percentage,
            'allows_promotion': s.allows_promotion,
            'promotion_done': s.promotion_done,
            'enrollment_deadline': s.enrollment_deadline.isoformat() if s.enrollment_deadline else None,
            'is_enrollment_open': s.is_enrollment_open,
        } for s in sessions]
        return JsonResponse({
            'sessions': session_list,
            'total_count': sessions.count(),
            'stats': stats,
        })

    # Paginated response
    sessions_page, paginator = paginate_queryset(request, sessions, per_page=10)

    session_list = [{
        'id': str(s.id),
        'name': s.name,
        'display_name': s.display_name,
        'year_name': s.year_name,
        'term_name': s.term_name,
        'term_number': s.term_number,
        'period_type': s.get_period_type_display(),
        'start_date': s.start_date.isoformat(),
        'end_date': s.end_date.isoformat(),
        'is_current': s.is_current,
        'is_active': s.is_active,
        'is_closed': s.is_closed,
        'status': s.status_display,
        'days_remaining': s.days_remaining,
        'progress_percentage': s.progress_percentage,
        'allows_promotion': s.allows_promotion,
        'promotion_done': s.promotion_done,
        'enrollment_deadline': s.enrollment_deadline.isoformat() if s.enrollment_deadline else None,
        'is_enrollment_open': s.is_enrollment_open,
    } for s in sessions_page]

    return JsonResponse({
        'sessions': session_list,
        'current_page': sessions_page.number,
        'total_pages': paginator.num_pages,
        'total_count': paginator.count,
        'has_previous': sessions_page.has_previous(),
        'has_next': sessions_page.has_next(),
        'start_index': sessions_page.start_index(),
        'end_index': sessions_page.end_index(),
        'stats': stats,
    })


# =============================================================================
# HOLIDAY SEARCH
# =============================================================================

def holiday_search(request):
    """
    AJAX view to return filtered holidays as JSON with statistics
    """
    filter_keys = ['q', 'holiday_type', 'break_type', 'academic_session', 'year', 'month', 'page']
    filters = parse_filters(request, filter_keys)
    
    holidays = Holiday.objects.all().select_related(
        'academic_session', 'previous_session', 'next_session'
    ).order_by('start_date')
    
    # Apply filters
    if filters['q']:
        holidays = holidays.filter(
            Q(name__icontains=filters['q']) | 
            Q(description__icontains=filters['q'])
        )
    if filters['holiday_type']:
        holidays = holidays.filter(holiday_type=filters['holiday_type'])
    if filters['break_type']:
        holidays = holidays.filter(break_type=filters['break_type'])
    if filters['academic_session']:
        holidays = holidays.filter(academic_session_id=filters['academic_session'])
    if filters['year']:
        try:
            holidays = holidays.filter(start_date__year=int(filters['year']))
        except ValueError:
            pass
    if filters['month']:
        try:
            holidays = holidays.filter(start_date__month=int(filters['month']))
        except ValueError:
            pass

    # Get comprehensive statistics using statistics module
    stats_filters = {}
    if filters['holiday_type']:
        stats_filters['holiday_type'] = filters['holiday_type']
    if filters['break_type']:
        stats_filters['break_type'] = filters['break_type']
    if filters['year']:
        try:
            stats_filters['year'] = int(filters['year'])
        except ValueError:
            pass
    if filters['academic_session']:
        stats_filters['academic_session'] = filters['academic_session']
    
    stats = get_holiday_statistics(filters=stats_filters if stats_filters else None)

    # Pagination
    if filters['page'] == 'all':
        holiday_list = [{
            'id': str(h.id),
            'name': h.name,
            'holiday_type': h.get_holiday_type_display(),
            'break_type': h.get_break_type_display() if h.break_type else None,
            'start_date': h.start_date.isoformat(),
            'end_date': h.end_date.isoformat() if h.end_date else None,
            'duration': h.duration,
            'description': h.description,
            'academic_session': h.academic_session.name if h.academic_session else None,
            'previous_session': h.previous_session.name if h.previous_session else None,
            'next_session': h.next_session.name if h.next_session else None,
        } for h in holidays]
        return JsonResponse({
            'holidays': holiday_list, 
            'total_count': holidays.count(), 
            'stats': stats
        })

    holidays_page, paginator = paginate_queryset(request, holidays, per_page=10)
    
    holiday_list = [{
        'id': str(h.id),
        'name': h.name,
        'holiday_type': h.get_holiday_type_display(),
        'break_type': h.get_break_type_display() if h.break_type else None,
        'start_date': h.start_date.isoformat(),
        'end_date': h.end_date.isoformat() if h.end_date else None,
        'duration': h.duration,
        'description': h.description,
        'academic_session': h.academic_session.name if h.academic_session else None,
        'previous_session': h.previous_session.name if h.previous_session else None,
        'next_session': h.next_session.name if h.next_session else None,
    } for h in holidays_page]

    return JsonResponse({
        'holidays': holiday_list,
        'current_page': holidays_page.number,
        'total_pages': paginator.num_pages,
        'total_count': paginator.count,
        'has_previous': holidays_page.has_previous(),
        'has_next': holidays_page.has_next(),
        'start_index': holidays_page.start_index(),
        'end_index': holidays_page.end_index(),
        'stats': stats,
    })


# =============================================================================
# SUBJECT SEARCH
# =============================================================================

def subject_search(request):
    """
    AJAX view to return filtered subjects as JSON with statistics
    """
    filter_keys = ['q', 'subject_type', 'department', 'is_active', 'is_compulsory', 'difficulty_level', 'page']
    filters = parse_filters(request, filter_keys)

    subjects = Subject.objects.all().select_related('department').order_by('subject_type', 'abbreviation')

    # Apply filters
    if filters['q']:
        subjects = subjects.filter(
            Q(name__icontains=filters['q']) |
            Q(abbreviation__icontains=filters['q']) |
            Q(code__icontains=filters['q'])
        )
    if filters['subject_type']:
        subjects = subjects.filter(subject_type=filters['subject_type'])
    if filters['department']:
        subjects = subjects.filter(department_id=filters['department'])
    if filters['is_active'] is not None:
        subjects = subjects.filter(is_active=(filters['is_active'].lower() == 'true'))
    if filters['is_compulsory'] is not None:
        subjects = subjects.filter(is_compulsory=(filters['is_compulsory'].lower() == 'true'))
    if filters['difficulty_level']:
        subjects = subjects.filter(difficulty_level=filters['difficulty_level'])

    # Get comprehensive statistics using statistics module
    stats_filters = {}
    if filters['subject_type']:
        stats_filters['subject_type'] = filters['subject_type']
    if filters['department']:
        stats_filters['department'] = filters['department']
    if filters['is_active'] is not None:
        stats_filters['is_active'] = (filters['is_active'].lower() == 'true')
    if filters['is_compulsory'] is not None:
        stats_filters['is_compulsory'] = (filters['is_compulsory'].lower() == 'true')
    if filters['difficulty_level']:
        stats_filters['difficulty_level'] = filters['difficulty_level']
    
    stats = get_subject_statistics(filters=stats_filters if stats_filters else None)

    # Pagination
    if filters['page'] == 'all':
        subject_list = [{
            'id': str(s.id),
            'name': s.name,
            'abbreviation': s.abbreviation,
            'code': s.code,
            'full_display': s.get_full_display(),
            'subject_type': s.get_subject_type_display(),
            'department': s.department.name if s.department else None,
            'credit_hours': str(s.credit_hours),
            'is_active': s.is_active,
            'is_compulsory': s.is_compulsory,
            'pass_mark': str(s.pass_mark),
            'difficulty_level': s.get_difficulty_level_display(),
            'weight_factor': str(s.weight_factor),
            'textbook_required': s.textbook_required,
        } for s in subjects]
        return JsonResponse({
            'subjects': subject_list, 
            'total_count': subjects.count(), 
            'stats': stats
        })

    subjects_page, paginator = paginate_queryset(request, subjects, per_page=10)

    subject_list = [{
        'id': str(s.id),
        'name': s.name,
        'abbreviation': s.abbreviation,
        'code': s.code,
        'full_display': s.get_full_display(),
        'subject_type': s.get_subject_type_display(),
        'department': s.department.name if s.department else None,
        'credit_hours': str(s.credit_hours),
        'is_active': s.is_active,
        'is_compulsory': s.is_compulsory,
        'pass_mark': str(s.pass_mark),
        'difficulty_level': s.get_difficulty_level_display(),
        'weight_factor': str(s.weight_factor),
        'textbook_required': s.textbook_required,
    } for s in subjects_page]

    return JsonResponse({
        'subjects': subject_list,
        'current_page': subjects_page.number,
        'total_pages': paginator.num_pages,
        'total_count': paginator.count,
        'has_previous': subjects_page.has_previous(),
        'has_next': subjects_page.has_next(),
        'start_index': subjects_page.start_index(),
        'end_index': subjects_page.end_index(),
        'stats': stats,
    })


# =============================================================================
# ACADEMIC LEVEL SEARCH
# =============================================================================

def academic_level_search(request):
    """
    AJAX view to return filtered academic levels as JSON with statistics
    """
    filter_keys = ['q', 'is_active', 'has_sections', 'is_graduation_level', 'page']
    filters = parse_filters(request, filter_keys)

    levels = AcademicLevel.objects.all().select_related('next_level').order_by('order')

    # Apply filters
    if filters['q']:
        terms = filters['q'].split()
        q_objects = Q()
        for term in terms:
            q_objects &= Q(name__icontains=term) | Q(code__icontains=term)
        levels = levels.filter(q_objects)
    if filters['is_active'] is not None:
        levels = levels.filter(is_active=(filters['is_active'].lower() == 'true'))
    if filters['has_sections'] is not None:
        levels = levels.filter(has_sections=(filters['has_sections'].lower() == 'true'))
    if filters['is_graduation_level'] is not None:
        levels = levels.filter(is_graduation_level=(filters['is_graduation_level'].lower() == 'true'))

    # Get comprehensive statistics using statistics module
    stats_filters = {}
    if filters['is_active'] is not None:
        stats_filters['is_active'] = (filters['is_active'].lower() == 'true')
    if filters['has_sections'] is not None:
        stats_filters['has_sections'] = (filters['has_sections'].lower() == 'true')
    if filters['is_graduation_level'] is not None:
        stats_filters['is_graduation_level'] = (filters['is_graduation_level'].lower() == 'true')
    
    stats = get_academic_level_statistics(filters=stats_filters if stats_filters else None)

    # Pagination
    if filters['page'] == 'all':
        level_list = []
        try:
            from students.models import Student
            for l in levels:
                current_enrollment = Student.objects.filter(
                    current_academic_level=l, 
                    enrollment_status='active'
                ).count()
                active_classes_count = Class.objects.filter(
                    academic_level=l, 
                    is_active=True
                ).count()
                level_list.append({
                    'id': str(l.id),
                    'name': l.name,
                    'code': l.code,
                    'order': l.order,
                    'description': l.description,
                    'next_level': l.next_level.name if l.next_level else None,
                    'next_level_code': l.next_level.code if l.next_level else None,
                    'has_sections': l.has_sections,
                    'is_active': l.is_active,
                    'is_graduation_level': l.is_graduation_level,
                    'current_enrollment': current_enrollment,
                    'active_classes_count': active_classes_count,
                })
        except ImportError:
            # If Student model not available, return without enrollment data
            for l in levels:
                active_classes_count = Class.objects.filter(
                    academic_level=l, 
                    is_active=True
                ).count()
                level_list.append({
                    'id': str(l.id),
                    'name': l.name,
                    'code': l.code,
                    'order': l.order,
                    'description': l.description,
                    'next_level': l.next_level.name if l.next_level else None,
                    'next_level_code': l.next_level.code if l.next_level else None,
                    'has_sections': l.has_sections,
                    'is_active': l.is_active,
                    'is_graduation_level': l.is_graduation_level,
                    'active_classes_count': active_classes_count,
                })
        
        return JsonResponse({
            'levels': level_list, 
            'total_count': levels.count(), 
            'stats': stats
        })

    levels_page, paginator = paginate_queryset(request, levels, per_page=10)

    level_list = []
    try:
        from students.models import Student
        for l in levels_page:
            current_enrollment = Student.objects.filter(
                current_academic_level=l, 
                enrollment_status='active'
            ).count()
            active_classes_count = Class.objects.filter(
                academic_level=l, 
                is_active=True
            ).count()
            level_list.append({
                'id': str(l.id),
                'name': l.name,
                'code': l.code,
                'order': l.order,
                'description': l.description,
                'next_level': l.next_level.name if l.next_level else None,
                'next_level_code': l.next_level.code if l.next_level else None,
                'has_sections': l.has_sections,
                'is_active': l.is_active,
                'is_graduation_level': l.is_graduation_level,
                'current_enrollment': current_enrollment,
                'active_classes_count': active_classes_count,
            })
    except ImportError:
        for l in levels_page:
            active_classes_count = Class.objects.filter(
                academic_level=l, 
                is_active=True
            ).count()
            level_list.append({
                'id': str(l.id),
                'name': l.name,
                'code': l.code,
                'order': l.order,
                'description': l.description,
                'next_level': l.next_level.name if l.next_level else None,
                'next_level_code': l.next_level.code if l.next_level else None,
                'has_sections': l.has_sections,
                'is_active': l.is_active,
                'is_graduation_level': l.is_graduation_level,
                'active_classes_count': active_classes_count,
            })

    return JsonResponse({
        'levels': level_list,
        'current_page': levels_page.number,
        'total_pages': paginator.num_pages,
        'total_count': paginator.count,
        'has_previous': levels_page.has_previous(),
        'has_next': levels_page.has_next(),
        'start_index': levels_page.start_index(),
        'end_index': levels_page.end_index(),
        'stats': stats,
    })


# =============================================================================
# CLASSROOM SEARCH
# =============================================================================

def classroom_search(request):
    """
    AJAX view to return filtered classrooms as JSON with statistics
    """
    filter_keys = ['q', 'room_type', 'building', 'is_active', 'is_bookable', 'has_projector', 'min_capacity', 'page']
    filters = parse_filters(request, filter_keys)

    classrooms = ClassRoom.objects.all().order_by('building', 'floor', 'room_number')

    # Apply filters
    if filters['q']:
        classrooms = classrooms.filter(
            Q(name__icontains=filters['q']) |
            Q(room_number__icontains=filters['q']) |
            Q(building__icontains=filters['q'])
        )
    if filters['room_type']:
        classrooms = classrooms.filter(room_type=filters['room_type'])
    if filters['building']:
        classrooms = classrooms.filter(building__icontains=filters['building'])
    if filters['is_active'] is not None:
        classrooms = classrooms.filter(is_active=(filters['is_active'].lower() == 'true'))
    if filters['is_bookable'] is not None:
        classrooms = classrooms.filter(is_bookable=(filters['is_bookable'].lower() == 'true'))
    if filters['has_projector'] is not None:
        classrooms = classrooms.filter(has_projector=(filters['has_projector'].lower() == 'true'))
    if filters['min_capacity']:
        try:
            classrooms = classrooms.filter(capacity__gte=int(filters['min_capacity']))
        except ValueError:
            pass

    # Get comprehensive statistics using statistics module
    stats_filters = {}
    if filters['room_type']:
        stats_filters['room_type'] = filters['room_type']
    if filters['building']:
        stats_filters['building'] = filters['building']
    if filters['is_active'] is not None:
        stats_filters['is_active'] = (filters['is_active'].lower() == 'true')
    if filters['is_bookable'] is not None:
        stats_filters['is_bookable'] = (filters['is_bookable'].lower() == 'true')
    
    stats = get_classroom_statistics(filters=stats_filters if stats_filters else None)

    # Pagination
    if filters['page'] == 'all':
        classroom_list = [{
            'id': str(c.id),
            'name': c.name,
            'room_number': c.room_number,
            'full_location': c.get_full_location(),
            'building': c.building,
            'floor': c.floor,
            'wing': c.wing,
            'capacity': c.capacity,
            'room_type': c.get_room_type_display(),
            'has_projector': c.has_projector,
            'has_computer': c.has_computer,
            'has_air_conditioning': c.has_air_conditioning,
            'has_whiteboard': c.has_whiteboard,
            'has_smart_board': c.has_smart_board,
            'has_internet': c.has_internet,
            'is_accessible': c.is_accessible,
            'is_bookable': c.is_bookable,
            'is_active': c.is_active,
        } for c in classrooms]
        return JsonResponse({
            'classrooms': classroom_list, 
            'total_count': classrooms.count(), 
            'stats': stats
        })

    classrooms_page, paginator = paginate_queryset(request, classrooms, per_page=10)

    classroom_list = [{
        'id': str(c.id),
        'name': c.name,
        'room_number': c.room_number,
        'full_location': c.get_full_location(),
        'building': c.building,
        'floor': c.floor,
        'wing': c.wing,
        'capacity': c.capacity,
        'room_type': c.get_room_type_display(),
        'has_projector': c.has_projector,
        'has_computer': c.has_computer,
        'has_air_conditioning': c.has_air_conditioning,
        'has_whiteboard': c.has_whiteboard,
        'has_smart_board': c.has_smart_board,
        'has_internet': c.has_internet,
        'is_accessible': c.is_accessible,
        'is_bookable': c.is_bookable,
        'is_active': c.is_active,
    } for c in classrooms_page]

    return JsonResponse({
        'classrooms': classroom_list,
        'current_page': classrooms_page.number,
        'total_pages': paginator.num_pages,
        'total_count': paginator.count,
        'has_previous': classrooms_page.has_previous(),
        'has_next': classrooms_page.has_next(),
        'start_index': classrooms_page.start_index(),
        'end_index': classrooms_page.end_index(),
        'stats': stats,
    })


# =============================================================================
# CLASS SEARCH
# =============================================================================

def class_search(request):
    """
    AJAX view to return filtered classes as JSON with statistics
    """
    filter_keys = ['q', 'academic_level', 'academic_session', 'class_teacher', 'is_active', 'page']
    filters = parse_filters(request, filter_keys)

    classes = Class.objects.all().select_related(
        'academic_level', 'academic_session', 'class_teacher', 'classroom'
    ).order_by('academic_level__order', 'section')

    # Apply filters
    if filters['q']:
        classes = classes.filter(
            Q(academic_level__name__icontains=filters['q']) |
            Q(section__icontains=filters['q']) |
            Q(class_teacher__staff__first_name__icontains=filters['q']) |
            Q(class_teacher__staff__last_name__icontains=filters['q'])
        )
    if filters['academic_level']:
        classes = classes.filter(academic_level_id=filters['academic_level'])
    if filters['academic_session']:
        classes = classes.filter(academic_session_id=filters['academic_session'])
    if filters['class_teacher']:
        classes = classes.filter(class_teacher_id=filters['class_teacher'])
    if filters['is_active'] is not None:
        classes = classes.filter(is_active=(filters['is_active'].lower() == 'true'))

    # Get comprehensive statistics using statistics module
    stats_filters = {}
    if filters['academic_level']:
        stats_filters['academic_level'] = filters['academic_level']
    if filters['academic_session']:
        stats_filters['academic_session'] = filters['academic_session']
    if filters['class_teacher']:
        stats_filters['class_teacher'] = filters['class_teacher']
    if filters['is_active'] is not None:
        stats_filters['is_active'] = (filters['is_active'].lower() == 'true')
    
    stats = get_class_statistics(filters=stats_filters if stats_filters else None)

    # Pagination
    if filters['page'] == 'all':
        class_list = [{
            'id': str(c.id),
            'name': c.name,
            'display_name': c.get_display_name(),
            'academic_level': c.academic_level.name,
            'section': c.section,
            'academic_session': c.academic_session.name,
            'class_teacher': c.class_teacher.staff.full_name() if c.class_teacher else None,
            'assistant_teacher': c.assistant_teacher.staff.full_name() if c.assistant_teacher else None,
            'classroom': str(c.classroom) if c.classroom else None,
            'max_students': c.max_students,
            'current_enrollment': c.get_current_enrollment_count(),
            'available_capacity': c.get_available_capacity(),
            'occupancy_percentage': c.get_occupancy_percentage(),
            'class_average_score': str(c.class_average_score) if c.class_average_score else None,
            'attendance_rate': str(c.attendance_rate) if c.attendance_rate else None,
            'is_active': c.is_active,
        } for c in classes]
        return JsonResponse({
            'classes': class_list, 
            'total_count': classes.count(), 
            'stats': stats
        })

    classes_page, paginator = paginate_queryset(request, classes, per_page=10)

    class_list = [{
        'id': str(c.id),
        'name': c.name,
        'display_name': c.get_display_name(),
        'academic_level': c.academic_level.name,
        'section': c.section,
        'academic_session': c.academic_session.name,
        'class_teacher': c.class_teacher.staff.full_name() if c.class_teacher else None,
        'assistant_teacher': c.assistant_teacher.staff.full_name() if c.assistant_teacher else None,
        'classroom': str(c.classroom) if c.classroom else None,
        'max_students': c.max_students,
        'current_enrollment': c.get_current_enrollment_count(),
        'available_capacity': c.get_available_capacity(),
        'occupancy_percentage': c.get_occupancy_percentage(),
        'class_average_score': str(c.class_average_score) if c.class_average_score else None,
        'attendance_rate': str(c.attendance_rate) if c.attendance_rate else None,
        'is_active': c.is_active,
    } for c in classes_page]

    return JsonResponse({
        'classes': class_list,
        'current_page': classes_page.number,
        'total_pages': paginator.num_pages,
        'total_count': paginator.count,
        'has_previous': classes_page.has_previous(),
        'has_next': classes_page.has_next(),
        'start_index': classes_page.start_index(),
        'end_index': classes_page.end_index(),
        'stats': stats,
    })


# =============================================================================
# CLASS SUBJECT SEARCH
# =============================================================================

def class_subject_search(request):
    """
    AJAX view to return filtered class subjects as JSON with statistics
    """
    filter_keys = ['q', 'class_id', 'subject_id', 'teacher_id', 'is_optional', 'is_active', 'page']
    filters = parse_filters(request, filter_keys)

    class_subjects = ClassSubject.objects.all().select_related(
        'class_instance', 'subject', 'teacher', 'class_instance__academic_level'
    ).order_by('class_instance__academic_level__order', 'subject__name')

    # Apply filters
    if filters['q']:
        class_subjects = class_subjects.filter(
            Q(subject__name__icontains=filters['q']) |
            Q(subject__abbreviation__icontains=filters['q']) |
            Q(class_instance__academic_level__name__icontains=filters['q']) |
            Q(teacher__staff__first_name__icontains=filters['q']) |
            Q(teacher__staff__last_name__icontains=filters['q'])
        )
    if filters['class_id']:
        class_subjects = class_subjects.filter(class_instance_id=filters['class_id'])
    if filters['subject_id']:
        class_subjects = class_subjects.filter(subject_id=filters['subject_id'])
    if filters['teacher_id']:
        class_subjects = class_subjects.filter(teacher_id=filters['teacher_id'])
    if filters['is_optional'] is not None:
        class_subjects = class_subjects.filter(is_optional=(filters['is_optional'].lower() == 'true'))
    if filters['is_active'] is not None:
        class_subjects = class_subjects.filter(is_active=(filters['is_active'].lower() == 'true'))

    # Get comprehensive statistics using statistics module
    stats_filters = {}
    if filters['class_id']:
        stats_filters['class_instance'] = filters['class_id']
    if filters['subject_id']:
        stats_filters['subject'] = filters['subject_id']
    if filters['teacher_id']:
        stats_filters['teacher'] = filters['teacher_id']
    if filters['is_optional'] is not None:
        stats_filters['is_optional'] = (filters['is_optional'].lower() == 'true')
    if filters['is_active'] is not None:
        stats_filters['is_active'] = (filters['is_active'].lower() == 'true')
    
    stats = get_class_subject_statistics(filters=stats_filters if stats_filters else None)

    # Pagination
    if filters['page'] == 'all':
        class_subject_list = [{
            'id': str(cs.id),
            'class_name': cs.class_instance.name,
            'subject_name': cs.subject.name,
            'subject_abbreviation': cs.subject.abbreviation,
            'teacher': cs.teacher.staff.full_name() if cs.teacher else None,
            'is_optional': cs.is_optional,
            'hours_per_week': cs.hours_per_week,
            'total_hours': cs.total_hours,
            'continuous_assessment_weight': str(cs.continuous_assessment_weight),
            'final_exam_weight': str(cs.final_exam_weight),
            'class_average': str(cs.class_average) if cs.class_average else None,
            'pass_rate': str(cs.pass_rate) if cs.pass_rate else None,
            'is_active': cs.is_active,
            'schedule_display': cs.get_schedule_display(),
        } for cs in class_subjects]
        return JsonResponse({
            'class_subjects': class_subject_list, 
            'total_count': class_subjects.count(), 
            'stats': stats
        })

    class_subjects_page, paginator = paginate_queryset(request, class_subjects, per_page=10)

    class_subject_list = [{
        'id': str(cs.id),
        'class_name': cs.class_instance.name,
        'subject_name': cs.subject.name,
        'subject_abbreviation': cs.subject.abbreviation,
        'teacher': cs.teacher.staff.full_name() if cs.teacher else None,
        'is_optional': cs.is_optional,
        'hours_per_week': cs.hours_per_week,
        'total_hours': cs.total_hours,
        'continuous_assessment_weight': str(cs.continuous_assessment_weight),
        'final_exam_weight': str(cs.final_exam_weight),
        'class_average': str(cs.class_average) if cs.class_average else None,
        'pass_rate': str(cs.pass_rate) if cs.pass_rate else None,
        'is_active': cs.is_active,
        'schedule_display': cs.get_schedule_display(),
    } for cs in class_subjects_page]

    return JsonResponse({
        'class_subjects': class_subject_list,
        'current_page': class_subjects_page.number,
        'total_pages': paginator.num_pages,
        'total_count': paginator.count,
        'has_previous': class_subjects_page.has_previous(),
        'has_next': class_subjects_page.has_next(),
        'start_index': class_subjects_page.start_index(),
        'end_index': class_subjects_page.end_index(),
        'stats': stats,
    })