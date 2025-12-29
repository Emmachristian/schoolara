# discipline/htmx_views.py

from django.http import JsonResponse
from django.shortcuts import render
from django.db.models import Q, Count
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from datetime import timedelta
import logging

from .models import DisciplinaryRecord
from utils.utils import parse_filters, paginate_queryset

logger = logging.getLogger(__name__)


# =============================================================================
# DISCIPLINARY RECORD SEARCH
# =============================================================================

def disciplinary_record_search(request):
    """HTMX-compatible disciplinary record search with pagination and stats"""
    
    filters = parse_filters(request, [
        'q', 'student', 'incident_type', 'severity_level', 'action_taken',
        'record_status', 'is_resolved', 'academic_session',
        'parent_notified', 'appealed', 'follow_up_required',
        'active_suspension', 'start_date', 'end_date'
    ])
    
    query = filters['q']
    student = filters['student']
    incident_type = filters['incident_type']
    severity_level = filters['severity_level']
    action_taken = filters['action_taken']
    record_status = filters['record_status']
    is_resolved = filters['is_resolved']
    academic_session = filters['academic_session']
    parent_notified = filters['parent_notified']
    appealed = filters['appealed']
    follow_up_required = filters['follow_up_required']
    active_suspension = filters['active_suspension']
    start_date = filters['start_date']
    end_date = filters['end_date']
    
    records = DisciplinaryRecord.objects.select_related(
        'student__current_academic_level',
        'academic_session'
    ).order_by('-incident_date')
    
    if query:
        records = records.filter(
            Q(incident_number__icontains=query) |
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(incident_description__icontains=query)
        )
    
    if student:
        records = records.filter(student_id=student)
    if incident_type:
        records = records.filter(incident_type=incident_type)
    if severity_level:
        records = records.filter(severity_level=severity_level)
    if action_taken:
        records = records.filter(action_taken=action_taken)
    if record_status:
        records = records.filter(record_status=record_status)
    if academic_session:
        records = records.filter(academic_session_id=academic_session)
    if is_resolved is not None:
        records = records.filter(is_resolved=(is_resolved.lower() == 'true'))
    if parent_notified is not None:
        records = records.filter(parent_notified=(parent_notified.lower() == 'true'))
    if appealed is not None:
        records = records.filter(appealed=(appealed.lower() == 'true'))
    if follow_up_required is not None:
        records = records.filter(follow_up_required=(follow_up_required.lower() == 'true'))
    
    if active_suspension and active_suspension.lower() == 'true':
        today = timezone.now().date()
        records = records.filter(
            action_taken__in=['in_school_suspension', 'out_of_school_suspension'],
            action_start_date__lte=today,
            action_end_date__gte=today
        )
    
    if start_date:
        records = records.filter(incident_date__gte=start_date)
    if end_date:
        records = records.filter(incident_date__lte=end_date)
    
    records_page, paginator = paginate_queryset(request, records, per_page=20)
    
    stats = {
        'total': records.count(),
        'resolved': records.filter(is_resolved=True).count(),
        'unresolved': records.filter(is_resolved=False).count(),
        'minor': records.filter(severity_level='minor').count(),
        'moderate': records.filter(severity_level='moderate').count(),
        'major': records.filter(severity_level='major').count(),
        'severe': records.filter(severity_level='severe').count(),
    }
    
    return render(request, 'discipline/records/_record_results.html', {
        'records_page': records_page,
        'stats': stats,
    })


@require_http_methods(["GET"])
def disciplinary_quick_stats(request):
    """Get quick statistics for disciplinary records"""
    
    today = timezone.now().date()
    
    stats = {
        'total': DisciplinaryRecord.objects.count(),
        'unresolved': DisciplinaryRecord.objects.filter(is_resolved=False).count(),
        'active_suspensions': DisciplinaryRecord.objects.filter(
            action_taken__in=['in_school_suspension', 'out_of_school_suspension'],
            action_start_date__lte=today,
            action_end_date__gte=today
        ).count(),
        'pending_action': DisciplinaryRecord.objects.filter(
            record_status__in=['reported', 'investigating', 'action_pending']
        ).count(),
    }
    
    return JsonResponse(stats)
