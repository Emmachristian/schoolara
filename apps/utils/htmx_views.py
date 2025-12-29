# utils/htmx_views.py

from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.db.models import Q, Count, Sum, Avg, F, Case, When
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from datetime import timedelta
from decimal import Decimal
import logging

from .models import AuditLog, FinancialAuditLog
from utils.utils import parse_filters, paginate_queryset

logger = logging.getLogger(__name__)


# =============================================================================
# AUDIT LOG SEARCH
# =============================================================================

def audit_log_search(request):
    """HTMX-compatible audit log search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'content_type', 'action', 'user_id', 'object_id',
        'start_datetime', 'end_datetime', 'ip_address', 'session_key'
    ])
    
    query = filters['q']
    content_type = filters['content_type']
    action = filters['action']
    user_id = filters['user_id']
    object_id = filters['object_id']
    start_datetime = filters['start_datetime']
    end_datetime = filters['end_datetime']
    ip_address = filters['ip_address']
    session_key = filters['session_key']
    
    # Build queryset
    logs = AuditLog.objects.all().order_by('-timestamp')
    
    # Apply text search
    if query:
        logs = logs.filter(
            Q(object_repr__icontains=query) |
            Q(user_name__icontains=query) |
            Q(user_email__icontains=query) |
            Q(change_reason__icontains=query) |
            Q(request_path__icontains=query)
        )
    
    # Apply filters
    if content_type:
        logs = logs.filter(content_type=content_type)
    
    if action:
        logs = logs.filter(action=action)
    
    if user_id:
        logs = logs.filter(user_id=user_id)
    
    if object_id:
        logs = logs.filter(object_id=object_id)
    
    if ip_address:
        logs = logs.filter(ip_address__icontains=ip_address)
    
    if session_key:
        logs = logs.filter(session_key=session_key)
    
    if start_datetime:
        logs = logs.filter(timestamp__gte=start_datetime)
    
    if end_datetime:
        logs = logs.filter(timestamp__lte=end_datetime)
    
    # Paginate
    logs_page, paginator = paginate_queryset(request, logs, per_page=20)
    
    # Calculate stats
    total = logs.count()
    
    stats = {
        'total': total,
        'creates': logs.filter(action='CREATE').count(),
        'updates': logs.filter(action='UPDATE').count(),
        'deletes': logs.filter(action='DELETE').count(),
        'unique_users': logs.values('user_id').distinct().count(),
        'unique_models': logs.values('content_type').distinct().count(),
        'unique_ips': logs.values('ip_address').distinct().count(),
    }
    
    return render(request, 'utils/audit_logs/_log_results.html', {
        'logs_page': logs_page,
        'stats': stats,
    })


# =============================================================================
# FINANCIAL AUDIT LOG SEARCH
# =============================================================================

def financial_audit_log_search(request):
    """HTMX-compatible financial audit log search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'action', 'user_id', 'student_id', 'academic_session_id',
        'risk_level', 'start_datetime', 'end_datetime', 'ip_address',
        'min_amount', 'max_amount', 'is_automated', 'batch_id'
    ])
    
    query = filters['q']
    action = filters['action']
    user_id = filters['user_id']
    student_id = filters['student_id']
    academic_session_id = filters['academic_session_id']
    risk_level = filters['risk_level']
    start_datetime = filters['start_datetime']
    end_datetime = filters['end_datetime']
    ip_address = filters['ip_address']
    min_amount = filters['min_amount']
    max_amount = filters['max_amount']
    is_automated = filters['is_automated']
    batch_id = filters['batch_id']
    
    # Build queryset
    logs = FinancialAuditLog.objects.select_related(
        'content_type'
    ).order_by('-timestamp')
    
    # Apply text search
    if query:
        logs = logs.filter(
            Q(user_name__icontains=query) |
            Q(student_name__icontains=query) |
            Q(student_admission_number__icontains=query) |
            Q(object_description__icontains=query) |
            Q(notes__icontains=query) |
            Q(changes_summary__icontains=query)
        )
    
    # Apply filters
    if action:
        logs = logs.filter(action=action)
    
    if user_id:
        logs = logs.filter(user_id=user_id)
    
    if student_id:
        logs = logs.filter(student_id=student_id)
    
    if academic_session_id:
        logs = logs.filter(academic_session_id=academic_session_id)
    
    if risk_level:
        logs = logs.filter(risk_level=risk_level)
    
    if ip_address:
        logs = logs.filter(ip_address__icontains=ip_address)
    
    if batch_id:
        logs = logs.filter(batch_id=batch_id)
    
    if is_automated is not None:
        logs = logs.filter(is_automated=(is_automated.lower() == 'true'))
    
    if start_datetime:
        logs = logs.filter(timestamp__gte=start_datetime)
    
    if end_datetime:
        logs = logs.filter(timestamp__lte=end_datetime)
    
    # Amount filters
    if min_amount:
        try:
            logs = logs.filter(amount_involved__gte=Decimal(min_amount))
        except:
            pass
    
    if max_amount:
        try:
            logs = logs.filter(amount_involved__lte=Decimal(max_amount))
        except:
            pass
    
    # Paginate
    logs_page, paginator = paginate_queryset(request, logs, per_page=20)
    
    # Calculate stats
    total = logs.count()
    
    stats = {
        'total': total,
        'low_risk': logs.filter(risk_level='LOW').count(),
        'medium_risk': logs.filter(risk_level='MEDIUM').count(),
        'high_risk': logs.filter(risk_level='HIGH').count(),
        'critical_risk': logs.filter(risk_level='CRITICAL').count(),
        'automated': logs.filter(is_automated=True).count(),
        'manual': logs.filter(is_automated=False).count(),
        'unique_users': logs.values('user_id').distinct().count(),
        'unique_students': logs.values('student_id').distinct().count(),
        'total_amount': logs.aggregate(Sum('amount_involved'))['amount_involved__sum'] or Decimal('0'),
    }
    
    return render(request, 'utils/financial_audit_logs/_log_results.html', {
        'logs_page': logs_page,
        'stats': stats,
    })


# =============================================================================
# AUDIT ACTIVITY BY MODEL
# =============================================================================

def audit_activity_by_model(request):
    """Get audit activity distribution by model type"""
    
    # Parse filters
    filters = parse_filters(request, ['days', 'action'])
    days = filters.get('days', '30')
    action = filters['action']
    
    try:
        days_back = int(days)
    except:
        days_back = 30
    
    cutoff_datetime = timezone.now() - timedelta(days=days_back)
    
    logs = AuditLog.objects.filter(timestamp__gte=cutoff_datetime)
    
    if action:
        logs = logs.filter(action=action)
    
    # Get distribution by model
    distribution = logs.values('content_type').annotate(
        count=Count('id')
    ).order_by('-count')
    
    data = {
        'distribution': list(distribution),
        'total': logs.count(),
        'period_days': days_back,
    }
    
    return JsonResponse(data)


# =============================================================================
# AUDIT ACTIVITY BY USER
# =============================================================================

def audit_activity_by_user(request):
    """Get audit activity distribution by user"""
    
    # Parse filters
    filters = parse_filters(request, ['days', 'action'])
    days = filters.get('days', '30')
    action = filters['action']
    
    try:
        days_back = int(days)
    except:
        days_back = 30
    
    cutoff_datetime = timezone.now() - timedelta(days=days_back)
    
    logs = AuditLog.objects.filter(timestamp__gte=cutoff_datetime)
    
    if action:
        logs = logs.filter(action=action)
    
    # Get distribution by user
    distribution = logs.values('user_id', 'user_name').annotate(
        count=Count('id')
    ).order_by('-count')[:20]  # Top 20 users
    
    data = {
        'distribution': list(distribution),
        'total': logs.count(),
        'period_days': days_back,
    }
    
    return JsonResponse(data)


# =============================================================================
# FINANCIAL ACTIVITY BY ACTION TYPE
# =============================================================================

def financial_activity_by_action(request):
    """Get financial audit activity distribution by action type"""
    
    # Parse filters
    filters = parse_filters(request, ['days', 'risk_level'])
    days = filters.get('days', '30')
    risk_level = filters['risk_level']
    
    try:
        days_back = int(days)
    except:
        days_back = 30
    
    cutoff_datetime = timezone.now() - timedelta(days=days_back)
    
    logs = FinancialAuditLog.objects.filter(timestamp__gte=cutoff_datetime)
    
    if risk_level:
        logs = logs.filter(risk_level=risk_level)
    
    # Get distribution by action with amounts
    distribution = logs.values('action').annotate(
        count=Count('id'),
        total_amount=Sum('amount_involved'),
        avg_amount=Avg('amount_involved')
    ).order_by('-count')
    
    data = {
        'distribution': list(distribution),
        'total': logs.count(),
        'period_days': days_back,
    }
    
    return JsonResponse(data)


# =============================================================================
# RISK LEVEL TRENDS
# =============================================================================

def risk_level_trends(request):
    """Get risk level trends over time"""
    
    # Parse filters
    filters = parse_filters(request, ['days'])
    days = filters.get('days', '30')
    
    try:
        days_back = int(days)
    except:
        days_back = 30
    
    cutoff_datetime = timezone.now() - timedelta(days=days_back)
    
    logs = FinancialAuditLog.objects.filter(timestamp__gte=cutoff_datetime)
    
    # Get trends by risk level
    trends = logs.values('risk_level').annotate(
        count=Count('id')
    ).order_by('risk_level')
    
    data = {
        'trends': list(trends),
        'period_start': cutoff_datetime.isoformat(),
        'period_end': timezone.now().isoformat(),
        'total': logs.count()
    }
    
    return JsonResponse(data)


# =============================================================================
# QUICK STATS ENDPOINTS
# =============================================================================

@require_http_methods(["GET"])
def audit_log_quick_stats(request):
    """Get quick statistics for audit logs"""
    
    today = timezone.now()
    last_24h = today - timedelta(hours=24)
    last_7d = today - timedelta(days=7)
    
    all_logs = AuditLog.objects.all()
    recent_24h = AuditLog.objects.filter(timestamp__gte=last_24h)
    recent_7d = AuditLog.objects.filter(timestamp__gte=last_7d)
    
    stats = {
        'total_logs': all_logs.count(),
        'last_24h': recent_24h.count(),
        'last_7d': recent_7d.count(),
        'creates_24h': recent_24h.filter(action='CREATE').count(),
        'updates_24h': recent_24h.filter(action='UPDATE').count(),
        'deletes_24h': recent_24h.filter(action='DELETE').count(),
        'unique_users_24h': recent_24h.values('user_id').distinct().count(),
        'unique_models_24h': recent_24h.values('content_type').distinct().count(),
        'most_active_user': all_logs.values('user_name').annotate(
            count=Count('id')
        ).order_by('-count').first(),
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def financial_audit_quick_stats(request):
    """Get quick statistics for financial audit logs"""
    
    today = timezone.now()
    last_24h = today - timedelta(hours=24)
    last_7d = today - timedelta(days=7)
    last_30d = today - timedelta(days=30)
    
    all_logs = FinancialAuditLog.objects.all()
    recent_24h = FinancialAuditLog.objects.filter(timestamp__gte=last_24h)
    recent_7d = FinancialAuditLog.objects.filter(timestamp__gte=last_7d)
    recent_30d = FinancialAuditLog.objects.filter(timestamp__gte=last_30d)
    
    stats = {
        'total_logs': all_logs.count(),
        'last_24h': recent_24h.count(),
        'last_7d': recent_7d.count(),
        'last_30d': recent_30d.count(),
        'high_risk_24h': recent_24h.filter(risk_level__in=['HIGH', 'CRITICAL']).count(),
        'high_risk_7d': recent_7d.filter(risk_level__in=['HIGH', 'CRITICAL']).count(),
        'automated_actions_24h': recent_24h.filter(is_automated=True).count(),
        'total_amount_24h': recent_24h.aggregate(
            total=Sum('amount_involved')
        )['total'] or Decimal('0'),
        'total_amount_7d': recent_7d.aggregate(
            total=Sum('amount_involved')
        )['total'] or Decimal('0'),
        'unique_users_24h': recent_24h.values('user_id').distinct().count(),
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def action_distribution_stats(request):
    """Get audit action distribution statistics"""
    
    # Parse optional filters
    filters = parse_filters(request, ['days'])
    days = filters.get('days', '7')
    
    try:
        days_back = int(days)
    except:
        days_back = 7
    
    cutoff_datetime = timezone.now() - timedelta(days=days_back)
    
    logs = AuditLog.objects.filter(timestamp__gte=cutoff_datetime)
    
    stats = {
        'total': logs.count(),
        'creates': logs.filter(action='CREATE').count(),
        'updates': logs.filter(action='UPDATE').count(),
        'deletes': logs.filter(action='DELETE').count(),
        'period_days': days_back,
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def user_activity_stats(request):
    """Get user activity statistics"""
    
    user_id = request.GET.get('user_id')
    
    if not user_id:
        return JsonResponse({'error': 'user_id required'}, status=400)
    
    # Parse optional filters
    filters = parse_filters(request, ['days'])
    days = filters.get('days', '30')
    
    try:
        days_back = int(days)
    except:
        days_back = 30
    
    cutoff_datetime = timezone.now() - timedelta(days=days_back)
    
    logs = AuditLog.objects.filter(
        user_id=user_id,
        timestamp__gte=cutoff_datetime
    )
    
    # Get action breakdown
    action_breakdown = logs.values('action').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Get model breakdown
    model_breakdown = logs.values('content_type').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    stats = {
        'total_actions': logs.count(),
        'action_breakdown': list(action_breakdown),
        'model_breakdown': list(model_breakdown),
        'unique_models': logs.values('content_type').distinct().count(),
        'period_days': days_back,
        'last_action': logs.order_by('-timestamp').first().timestamp.isoformat() if logs.exists() else None,
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def financial_risk_stats(request):
    """Get financial audit risk statistics"""
    
    # Parse optional filters
    filters = parse_filters(request, ['days'])
    days = filters.get('days', '30')
    
    try:
        days_back = int(days)
    except:
        days_back = 30
    
    cutoff_datetime = timezone.now() - timedelta(days=days_back)
    
    logs = FinancialAuditLog.objects.filter(timestamp__gte=cutoff_datetime)
    
    stats = {
        'total': logs.count(),
        'low_risk': logs.filter(risk_level='LOW').count(),
        'medium_risk': logs.filter(risk_level='MEDIUM').count(),
        'high_risk': logs.filter(risk_level='HIGH').count(),
        'critical_risk': logs.filter(risk_level='CRITICAL').count(),
        'period_days': days_back,
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def financial_amount_stats(request):
    """Get financial amount statistics"""
    
    # Parse optional filters
    filters = parse_filters(request, ['days', 'action'])
    days = filters.get('days', '30')
    action = filters['action']
    
    try:
        days_back = int(days)
    except:
        days_back = 30
    
    cutoff_datetime = timezone.now() - timedelta(days=days_back)
    
    logs = FinancialAuditLog.objects.filter(
        timestamp__gte=cutoff_datetime,
        amount_involved__isnull=False
    )
    
    if action:
        logs = logs.filter(action=action)
    
    # Calculate aggregates
    aggregates = logs.aggregate(
        total_amount=Sum('amount_involved'),
        avg_amount=Avg('amount_involved'),
        count=Count('id')
    )
    
    stats = {
        'total_amount': float(aggregates['total_amount'] or 0),
        'average_amount': float(aggregates['avg_amount'] or 0),
        'transaction_count': aggregates['count'],
        'period_days': days_back,
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def student_financial_history_stats(request):
    """Get financial history statistics for a student"""
    
    student_id = request.GET.get('student_id')
    
    if not student_id:
        return JsonResponse({'error': 'student_id required'}, status=400)
    
    logs = FinancialAuditLog.objects.filter(student_id=student_id)
    
    # Get action breakdown
    action_breakdown = logs.values('action').annotate(
        count=Count('id'),
        total_amount=Sum('amount_involved')
    ).order_by('-count')
    
    # Total amounts
    totals = logs.aggregate(
        total_amount=Sum('amount_involved'),
        avg_amount=Avg('amount_involved')
    )
    
    stats = {
        'total_actions': logs.count(),
        'action_breakdown': list(action_breakdown),
        'total_amount': float(totals['total_amount'] or 0),
        'average_amount': float(totals['avg_amount'] or 0),
        'high_risk_actions': logs.filter(risk_level__in=['HIGH', 'CRITICAL']).count(),
        'last_action': logs.order_by('-timestamp').first().timestamp.isoformat() if logs.exists() else None,
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def security_monitoring_stats(request):
    """Get security monitoring statistics"""
    
    # Parse optional filters
    filters = parse_filters(request, ['hours'])
    hours = filters.get('hours', '24')
    
    try:
        hours_back = int(hours)
    except:
        hours_back = 24
    
    cutoff_datetime = timezone.now() - timedelta(hours=hours_back)
    
    # General audit logs
    audit_logs = AuditLog.objects.filter(timestamp__gte=cutoff_datetime)
    
    # Financial audit logs
    financial_logs = FinancialAuditLog.objects.filter(timestamp__gte=cutoff_datetime)
    
    # Unique IPs
    unique_ips_audit = audit_logs.values('ip_address').distinct().count()
    unique_ips_financial = financial_logs.values('ip_address').distinct().count()
    
    # High risk financial actions
    high_risk = financial_logs.filter(risk_level__in=['HIGH', 'CRITICAL'])
    
    stats = {
        'total_audit_logs': audit_logs.count(),
        'total_financial_logs': financial_logs.count(),
        'unique_ips': unique_ips_audit + unique_ips_financial,
        'unique_users': audit_logs.values('user_id').distinct().count(),
        'high_risk_financial': high_risk.count(),
        'deletions': audit_logs.filter(action='DELETE').count(),
        'failed_actions': 0,  # Would need additional tracking
        'period_hours': hours_back,
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def model_activity_stats(request):
    """Get activity statistics for a specific model"""
    
    content_type = request.GET.get('content_type')
    
    if not content_type:
        return JsonResponse({'error': 'content_type required'}, status=400)
    
    # Parse optional filters
    filters = parse_filters(request, ['days'])
    days = filters.get('days', '30')
    
    try:
        days_back = int(days)
    except:
        days_back = 30
    
    cutoff_datetime = timezone.now() - timedelta(days=days_back)
    
    logs = AuditLog.objects.filter(
        content_type=content_type,
        timestamp__gte=cutoff_datetime
    )
    
    # Action breakdown
    action_breakdown = logs.values('action').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # User activity
    user_activity = logs.values('user_id', 'user_name').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    stats = {
        'total_actions': logs.count(),
        'action_breakdown': list(action_breakdown),
        'top_users': list(user_activity),
        'unique_objects': logs.values('object_id').distinct().count(),
        'unique_users': logs.values('user_id').distinct().count(),
        'period_days': days_back,
    }
    
    return JsonResponse(stats)