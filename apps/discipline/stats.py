# discipline/stats.py

from django.db.models import Count, Avg, Q, Max, Min, Sum, F
from django.db.models.functions import TruncMonth, TruncWeek, TruncDay
from datetime import timedelta

# Import centralized utilities
from core.utils import (
    get_school_today,
    get_school_current_time,
    get_active_academic_session,
)

# =============================================================================
# DISCIPLINARY STATISTICS UTILITIES
# =============================================================================

def get_discipline_statistics():
    """
    Get comprehensive statistics for disciplinary system
    Returns a dictionary with various disciplinary statistics
    
    Returns:
        dict: Dictionary containing disciplinary statistics including:
            - total_incidents: Total count of all disciplinary records
            - incident_type_counts: Dictionary with counts for each incident type
            - severity_level_counts: Counts for each severity level
            - action_taken_counts: Counts for each action type
            - status_counts: Counts for each record status
            - pending_actions: Number of records pending action
            - unresolved_count: Number of unresolved records
            - resolution_rate: Percentage of resolved records
            - parent_notification_rate: Percentage of incidents with parent notification
            - appeal_rate: Percentage of appealed records
    """
    from .models import DisciplinaryRecord
    
    records = DisciplinaryRecord.objects.all()
    
    # Total incidents
    total_incidents = records.count()
    
    # Incident type breakdown
    incident_type_counts = {}
    for type_code, type_name in DisciplinaryRecord.INCIDENT_TYPE_CHOICES:
        incident_type_counts[type_code] = records.filter(
            incident_type=type_code
        ).count()
    
    # Severity level breakdown
    severity_level_counts = {}
    for severity_code, severity_name in DisciplinaryRecord.SEVERITY_LEVEL_CHOICES:
        severity_level_counts[severity_code] = records.filter(
            severity_level=severity_code
        ).count()
    
    # Action taken breakdown
    action_taken_counts = {}
    for action_code, action_name in DisciplinaryRecord.ACTION_TAKEN_CHOICES:
        action_taken_counts[action_code] = records.filter(
            action_taken=action_code
        ).count()
    
    # Status breakdown
    status_counts = {}
    for status_code, status_name in DisciplinaryRecord.RECORD_STATUS_CHOICES:
        status_counts[status_code] = records.filter(
            record_status=status_code
        ).count()
    
    # Resolution statistics
    resolved_count = records.filter(is_resolved=True).count()
    unresolved_count = records.filter(is_resolved=False).count()
    resolution_rate = (resolved_count / total_incidents * 100) if total_incidents > 0 else 0
    
    # Parent notification statistics
    parent_notified_count = records.filter(parent_notified=True).count()
    parent_notification_rate = (parent_notified_count / total_incidents * 100) if total_incidents > 0 else 0
    
    # Appeal statistics
    appealed_count = records.filter(appealed=True).count()
    appeal_rate = (appealed_count / total_incidents * 100) if total_incidents > 0 else 0
    
    # Pending actions
    pending_actions = records.filter(
        record_status__in=['reported', 'investigating', 'action_pending'],
        is_resolved=False
    ).count()
    
    # Active suspensions (using school timezone)
    active_suspensions = get_active_suspensions_count()
    
    # Follow-up required
    follow_up_required = records.filter(
        follow_up_required=True,
        follow_up_completed=False
    ).count()
    
    return {
        'total_incidents': total_incidents,
        'incident_type_counts': incident_type_counts,
        'severity_level_counts': severity_level_counts,
        'action_taken_counts': action_taken_counts,
        'status_counts': status_counts,
        'resolved_count': resolved_count,
        'unresolved_count': unresolved_count,
        'resolution_rate': round(resolution_rate, 1),
        'parent_notified_count': parent_notified_count,
        'parent_notification_rate': round(parent_notification_rate, 1),
        'appealed_count': appealed_count,
        'appeal_rate': round(appeal_rate, 1),
        'pending_actions': pending_actions,
        'active_suspensions': active_suspensions,
        'follow_up_required': follow_up_required,
    }


def get_discipline_statistics_by_session(academic_session=None):
    """
    Get disciplinary statistics for a specific academic session
    
    Args:
        academic_session: FiscalPeriod/AcademicSession instance or ID (defaults to current session)
        
    Returns:
        dict: Dictionary containing session-specific disciplinary statistics
    """
    from .models import DisciplinaryRecord
    
    # Default to current session if not provided
    if academic_session is None:
        academic_session = get_active_academic_session()
        if academic_session is None:
            return {
                'error': 'No academic session provided and no active session found',
                'total_incidents': 0,
            }
    
    # Get records for the session
    if hasattr(academic_session, 'id'):
        records = DisciplinaryRecord.objects.filter(academic_session=academic_session)
    else:
        records = DisciplinaryRecord.objects.filter(academic_session_id=academic_session)
    
    total_incidents = records.count()
    
    # Incident type breakdown
    incident_type_counts = {}
    for type_code, type_name in DisciplinaryRecord.INCIDENT_TYPE_CHOICES:
        incident_type_counts[type_code] = records.filter(
            incident_type=type_code
        ).count()
    
    # Severity level breakdown
    severity_level_counts = {}
    for severity_code, severity_name in DisciplinaryRecord.SEVERITY_LEVEL_CHOICES:
        severity_level_counts[severity_code] = records.filter(
            severity_level=severity_code
        ).count()
    
    # Action taken breakdown
    action_taken_counts = {}
    for action_code, action_name in DisciplinaryRecord.ACTION_TAKEN_CHOICES:
        action_taken_counts[action_code] = records.filter(
            action_taken=action_code
        ).count()
    
    # Resolution statistics
    resolved_count = records.filter(is_resolved=True).count()
    resolution_rate = (resolved_count / total_incidents * 100) if total_incidents > 0 else 0
    
    return {
        'total_incidents': total_incidents,
        'incident_type_counts': incident_type_counts,
        'severity_level_counts': severity_level_counts,
        'action_taken_counts': action_taken_counts,
        'resolved_count': resolved_count,
        'unresolved_count': records.filter(is_resolved=False).count(),
        'resolution_rate': round(resolution_rate, 1),
        'pending_actions': records.filter(
            record_status__in=['reported', 'investigating', 'action_pending'],
            is_resolved=False
        ).count(),
    }


def get_student_discipline_summary(student):
    """
    Get comprehensive disciplinary summary for a specific student
    
    Args:
        student: Student instance or ID
        
    Returns:
        dict: Dictionary with student's disciplinary record summary
    """
    from .models import DisciplinaryRecord
    
    if hasattr(student, 'id'):
        records = DisciplinaryRecord.objects.filter(student=student)
    else:
        records = DisciplinaryRecord.objects.filter(student_id=student)
    
    total_incidents = records.count()
    
    # Severity breakdown
    severity_counts = {}
    for severity_code, severity_name in DisciplinaryRecord.SEVERITY_LEVEL_CHOICES:
        severity_counts[severity_code] = records.filter(
            severity_level=severity_code
        ).count()
    
    # Most common incident types
    incident_type_counts = records.values('incident_type').annotate(
        count=Count('id')
    ).order_by('-count')[:5]
    
    # Recent incidents (last 30 days) - using school timezone
    today = get_school_today()
    recent_cutoff = today - timedelta(days=30)
    recent_incidents = records.filter(incident_date__gte=recent_cutoff).count()
    
    # Active suspensions - using school timezone
    active_suspensions = records.filter(
        action_taken__in=['in_school_suspension', 'out_of_school_suspension'],
        action_start_date__lte=today,
        action_end_date__gte=today
    ).count()
    
    # Unresolved incidents
    unresolved = records.filter(is_resolved=False).count()
    
    # Appeals
    appeals = records.filter(appealed=True).count()
    appeals_upheld = records.filter(appeal_outcome='upheld').count()
    appeals_overturned = records.filter(appeal_outcome='overturned').count()
    
    return {
        'total_incidents': total_incidents,
        'severity_counts': severity_counts,
        'top_incident_types': list(incident_type_counts),
        'recent_incidents': recent_incidents,
        'active_suspensions': active_suspensions,
        'unresolved': unresolved,
        'total_appeals': appeals,
        'appeals_upheld': appeals_upheld,
        'appeals_overturned': appeals_overturned,
        'last_incident_date': records.order_by('-incident_date').first().incident_date if total_incidents > 0 else None,
    }


def get_incident_trends(days=30, group_by='day'):
    """
    Get disciplinary incident trends over specified time period
    
    Args:
        days (int): Number of days to analyze (default: 30)
        group_by (str): Grouping period - 'day', 'week', or 'month' (default: 'day')
        
    Returns:
        list: List of dictionaries with period and incident count
    """
    from .models import DisciplinaryRecord
    
    # Use school timezone for date calculations
    today = get_school_today()
    start_date = today - timedelta(days=days)
    records = DisciplinaryRecord.objects.filter(incident_date__gte=start_date)
    
    if group_by == 'month':
        trends = records.annotate(
            period=TruncMonth('incident_date')
        ).values('period').annotate(
            count=Count('id')
        ).order_by('period')
    elif group_by == 'week':
        trends = records.annotate(
            period=TruncWeek('incident_date')
        ).values('period').annotate(
            count=Count('id')
        ).order_by('period')
    else:  # day
        trends = records.annotate(
            period=TruncDay('incident_date')
        ).values('period').annotate(
            count=Count('id')
        ).order_by('period')
    
    return list(trends)


def get_severity_trends(months=6):
    """
    Get trends in incident severity over specified months
    
    Args:
        months (int): Number of months to analyze (default: 6)
        
    Returns:
        list: List of dictionaries with month and severity breakdown
    """
    from .models import DisciplinaryRecord
    
    # Use school timezone for date calculations
    today = get_school_today()
    start_date = today - timedelta(days=months * 30)
    records = DisciplinaryRecord.objects.filter(incident_date__gte=start_date)
    
    trends = records.annotate(
        month=TruncMonth('incident_date')
    ).values('month', 'severity_level').annotate(
        count=Count('id')
    ).order_by('month', 'severity_level')
    
    return list(trends)


def get_active_suspensions():
    """
    Get all currently active suspensions (using school timezone)
    
    Returns:
        QuerySet: Active suspension records
    """
    from .models import DisciplinaryRecord
    
    # Use school timezone to determine "today"
    today = get_school_today()
    return DisciplinaryRecord.objects.filter(
        action_taken__in=['in_school_suspension', 'out_of_school_suspension'],
        action_start_date__lte=today,
        action_end_date__gte=today
    )


def get_active_suspensions_count():
    """
    Get count of currently active suspensions
    
    Returns:
        int: Number of active suspensions
    """
    return get_active_suspensions().count()


def get_pending_actions():
    """
    Get all disciplinary records pending action
    
    Returns:
        QuerySet: Records pending action
    """
    from .models import DisciplinaryRecord
    
    return DisciplinaryRecord.objects.filter(
        record_status__in=['reported', 'investigating', 'action_pending'],
        is_resolved=False
    )


def get_pending_actions_count():
    """
    Get count of records pending action
    
    Returns:
        int: Number of pending actions
    """
    return get_pending_actions().count()


def get_records_requiring_followup():
    """
    Get records that require follow-up
    
    Returns:
        QuerySet: Records requiring follow-up
    """
    from .models import DisciplinaryRecord
    
    return DisciplinaryRecord.objects.filter(
        follow_up_required=True,
        follow_up_completed=False
    ).order_by('follow_up_date')


def get_records_requiring_followup_count():
    """
    Get count of records requiring follow-up
    
    Returns:
        int: Number of records requiring follow-up
    """
    return get_records_requiring_followup().count()


def get_incident_type_statistics():
    """
    Get detailed statistics for each incident type
    
    Returns:
        list: List of dictionaries with incident type statistics
    """
    from .models import DisciplinaryRecord
    
    stats = []
    
    for type_code, type_name in DisciplinaryRecord.INCIDENT_TYPE_CHOICES:
        type_records = DisciplinaryRecord.objects.filter(incident_type=type_code)
        total_count = type_records.count()
        
        if total_count > 0:
            # Severity breakdown
            severity_breakdown = {}
            for severity_code, severity_name in DisciplinaryRecord.SEVERITY_LEVEL_CHOICES:
                severity_breakdown[severity_code] = type_records.filter(
                    severity_level=severity_code
                ).count()
            
            # Most common actions
            common_actions = type_records.values('action_taken').annotate(
                count=Count('id')
            ).order_by('-count')[:3]
            
            # Resolution rate
            resolved = type_records.filter(is_resolved=True).count()
            resolution_rate = (resolved / total_count * 100)
            
            stats.append({
                'incident_type': type_code,
                'incident_type_display': type_name,
                'total_count': total_count,
                'severity_breakdown': severity_breakdown,
                'common_actions': list(common_actions),
                'resolution_rate': round(resolution_rate, 1),
                'parent_notification_rate': round(
                    (type_records.filter(parent_notified=True).count() / total_count * 100), 1
                ),
            })
    
    # Sort by total count descending
    stats.sort(key=lambda x: x['total_count'], reverse=True)
    
    return stats


def get_action_effectiveness_report():
    """
    Analyze effectiveness of different disciplinary actions
    
    Returns:
        list: List of dictionaries with action effectiveness statistics
    """
    from .models import DisciplinaryRecord
    
    report = []
    
    for action_code, action_name in DisciplinaryRecord.ACTION_TAKEN_CHOICES:
        action_records = DisciplinaryRecord.objects.filter(action_taken=action_code)
        total_count = action_records.count()
        
        if total_count > 0:
            # Students who received this action
            students = action_records.values('student_id').distinct().count()
            
            # Average time to resolution (using school timezone for date comparisons)
            resolved_records = action_records.filter(
                is_resolved=True,
                resolution_date__isnull=False
            )
            
            total_resolution_time = 0
            resolution_count = 0
            for record in resolved_records:
                # Use localize_datetime if needed for timezone conversion
                resolution_date = record.resolution_date.date()
                resolution_time = (resolution_date - record.incident_date).days
                total_resolution_time += resolution_time
                resolution_count += 1
            
            avg_resolution_days = (
                total_resolution_time / resolution_count
            ) if resolution_count > 0 else 0
            
            report.append({
                'action_taken': action_code,
                'action_display': action_name,
                'total_count': total_count,
                'unique_students': students,
                'avg_resolution_days': round(avg_resolution_days, 1),
                'resolution_rate': round(
                    (resolved_records.count() / total_count * 100), 1
                ),
                'appeal_rate': round(
                    (action_records.filter(appealed=True).count() / total_count * 100), 1
                ),
            })
    
    # Sort by total count descending
    report.sort(key=lambda x: x['total_count'], reverse=True)
    
    return report


def get_parent_notification_statistics():
    """
    Get detailed statistics on parent notifications
    
    Returns:
        dict: Dictionary with parent notification statistics
    """
    from .models import DisciplinaryRecord
    
    records = DisciplinaryRecord.objects.all()
    total_records = records.count()
    
    # Notification status
    notified = records.filter(parent_notified=True)
    notified_count = notified.count()
    not_notified_count = records.filter(parent_notified=False).count()
    
    notification_rate = (notified_count / total_records * 100) if total_records > 0 else 0
    
    # Notification methods
    method_counts = {}
    for method_code, method_name in DisciplinaryRecord.NOTIFICATION_METHOD_CHOICES:
        method_counts[method_code] = notified.filter(
            notification_method=method_code
        ).count()
    
    # Parent meetings
    meetings_scheduled = notified.filter(parent_meeting_scheduled=True).count()
    meetings_rate = (meetings_scheduled / notified_count * 100) if notified_count > 0 else 0
    
    # Response statistics
    with_response = notified.exclude(parent_response='').count()
    response_rate = (with_response / notified_count * 100) if notified_count > 0 else 0
    
    # Average time to notify (from incident to notification)
    total_notify_time = 0
    notify_count = 0
    for record in notified.filter(parent_notification_date__isnull=False):
        notify_date = record.parent_notification_date.date()
        notify_time = (notify_date - record.incident_date).days
        total_notify_time += notify_time
        notify_count += 1
    
    avg_notify_days = (total_notify_time / notify_count) if notify_count > 0 else 0
    
    return {
        'total_records': total_records,
        'notified_count': notified_count,
        'not_notified_count': not_notified_count,
        'notification_rate': round(notification_rate, 1),
        'method_counts': method_counts,
        'meetings_scheduled': meetings_scheduled,
        'meetings_rate': round(meetings_rate, 1),
        'with_response': with_response,
        'response_rate': round(response_rate, 1),
        'avg_notify_days': round(avg_notify_days, 1),
    }


def get_appeal_statistics():
    """
    Get detailed statistics on disciplinary appeals
    
    Returns:
        dict: Dictionary with appeal statistics
    """
    from .models import DisciplinaryRecord
    
    records = DisciplinaryRecord.objects.all()
    total_records = records.count()
    
    appealed = records.filter(appealed=True)
    appealed_count = appealed.count()
    
    appeal_rate = (appealed_count / total_records * 100) if total_records > 0 else 0
    
    # Appeal outcomes
    outcome_counts = {}
    for outcome_code, outcome_name in DisciplinaryRecord.APPEAL_OUTCOME_CHOICES:
        outcome_counts[outcome_code] = appealed.filter(
            appeal_outcome=outcome_code
        ).count()
    
    # Success rate (overturned / total resolved appeals)
    resolved_appeals = appealed.exclude(appeal_outcome='pending').count()
    overturned = outcome_counts.get('overturned', 0)
    success_rate = (overturned / resolved_appeals * 100) if resolved_appeals > 0 else 0
    
    # Most appealed incident types
    most_appealed_types = appealed.values('incident_type').annotate(
        count=Count('id')
    ).order_by('-count')[:5]
    
    # Most appealed actions
    most_appealed_actions = appealed.values('action_taken').annotate(
        count=Count('id')
    ).order_by('-count')[:5]
    
    return {
        'total_records': total_records,
        'appealed_count': appealed_count,
        'appeal_rate': round(appeal_rate, 1),
        'outcome_counts': outcome_counts,
        'resolved_appeals': resolved_appeals,
        'pending_appeals': outcome_counts.get('pending', 0),
        'success_rate': round(success_rate, 1),
        'most_appealed_types': list(most_appealed_types),
        'most_appealed_actions': list(most_appealed_actions),
    }


def get_students_with_multiple_incidents(min_incidents=3, days=None):
    """
    Get students with multiple disciplinary incidents
    
    Args:
        min_incidents (int): Minimum number of incidents (default: 3)
        days (int): Time period in days (default: None for all time)
        
    Returns:
        list: List of dictionaries with student info and incident counts
    """
    from .models import DisciplinaryRecord
    from students.models import Student
    
    records = DisciplinaryRecord.objects.all()
    
    if days:
        # Use school timezone for date calculations
        today = get_school_today()
        cutoff_date = today - timedelta(days=days)
        records = records.filter(incident_date__gte=cutoff_date)
    
    # Group by student and count
    student_incidents = records.values('student_id').annotate(
        incident_count=Count('id')
    ).filter(incident_count__gte=min_incidents).order_by('-incident_count')
    
    results = []
    for item in student_incidents:
        try:
            student = Student.objects.get(id=item['student_id'])
            student_records = records.filter(student_id=item['student_id'])
            
            results.append({
                'student_id': item['student_id'],
                'student_name': student.get_full_name(),
                'student_class': str(student.current_class) if student.current_class else 'N/A',
                'incident_count': item['incident_count'],
                'unresolved_count': student_records.filter(is_resolved=False).count(),
                'last_incident_date': student_records.order_by('-incident_date').first().incident_date,
            })
        except Student.DoesNotExist:
            continue
    
    return results


def get_discipline_hotspots():
    """
    Identify locations with frequent disciplinary incidents
    
    Returns:
        list: List of dictionaries with location and incident counts
    """
    from .models import DisciplinaryRecord
    
    locations = DisciplinaryRecord.objects.exclude(
        location=''
    ).values('location').annotate(
        incident_count=Count('id')
    ).order_by('-incident_count')[:10]
    
    return list(locations)


def get_time_of_day_analysis():
    """
    Analyze incidents by time of day
    
    Returns:
        dict: Dictionary with time period breakdowns
    """
    from .models import DisciplinaryRecord
    
    records = DisciplinaryRecord.objects.filter(incident_time__isnull=False)
    
    time_periods = {
        'morning': records.filter(incident_time__hour__lt=12).count(),
        'afternoon': records.filter(
            incident_time__hour__gte=12,
            incident_time__hour__lt=17
        ).count(),
        'evening': records.filter(incident_time__hour__gte=17).count(),
    }
    
    # Peak hours
    hourly_counts = records.extra(
        select={'hour': 'EXTRACT(hour FROM incident_time)'}
    ).values('hour').annotate(
        count=Count('id')
    ).order_by('-count')[:5]
    
    return {
        'time_periods': time_periods,
        'peak_hours': list(hourly_counts),
    }


def get_monthly_comparison_report(months=12):
    """
    Compare disciplinary incidents across months
    
    Args:
        months (int): Number of months to include (default: 12)
        
    Returns:
        list: List of dictionaries with monthly statistics
    """
    from .models import DisciplinaryRecord
    
    # Use school timezone for date calculations
    today = get_school_today()
    start_date = today - timedelta(days=months * 30)
    
    monthly_data = DisciplinaryRecord.objects.filter(
        incident_date__gte=start_date
    ).annotate(
        month=TruncMonth('incident_date')
    ).values('month').annotate(
        total_incidents=Count('id'),
        minor_incidents=Count('id', filter=Q(severity_level='minor')),
        moderate_incidents=Count('id', filter=Q(severity_level='moderate')),
        major_incidents=Count('id', filter=Q(severity_level='major')),
        severe_incidents=Count('id', filter=Q(severity_level='severe')),
        resolved=Count('id', filter=Q(is_resolved=True)),
    ).order_by('month')
    
    return list(monthly_data)