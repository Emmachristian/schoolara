# documents/htmx_views.py

from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.db.models import Q, Count, Sum, Avg, F, Case, When
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from datetime import timedelta
from decimal import Decimal
import logging

from .models import StudentDocument, DocumentAccessLog
from utils.utils import parse_filters, paginate_queryset

logger = logging.getLogger(__name__)


# =============================================================================
# STUDENT DOCUMENT SEARCH
# =============================================================================

def student_document_search(request):
    """HTMX-compatible student document search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'student', 'document_type', 'status', 'is_verified',
        'is_required', 'is_active', 'confidentiality_level',
        'upload_start_date', 'upload_end_date', 'issue_start_date',
        'issue_end_date', 'expiry_start_date', 'expiry_end_date',
        'expired', 'expiring_soon', 'pending_verification',
        'issuing_authority', 'tags'
    ])
    
    query = filters['q']
    student = filters['student']
    document_type = filters['document_type']
    status = filters['status']
    is_verified = filters['is_verified']
    is_required = filters['is_required']
    is_active = filters['is_active']
    confidentiality_level = filters['confidentiality_level']
    upload_start_date = filters['upload_start_date']
    upload_end_date = filters['upload_end_date']
    issue_start_date = filters['issue_start_date']
    issue_end_date = filters['issue_end_date']
    expiry_start_date = filters['expiry_start_date']
    expiry_end_date = filters['expiry_end_date']
    expired = filters['expired']
    expiring_soon = filters['expiring_soon']
    pending_verification = filters['pending_verification']
    issuing_authority = filters['issuing_authority']
    tags = filters['tags']
    
    # Build queryset
    documents = StudentDocument.objects.select_related(
        'student__current_academic_level'
    ).annotate(
        access_log_count=Count('access_logs', distinct=True)
    ).order_by('-upload_date')
    
    # Apply text search
    if query:
        documents = documents.filter(
            Q(document_name__icontains=query) |
            Q(document_number__icontains=query) |
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__admission_number__icontains=query) |
            Q(issuing_authority__icontains=query) |
            Q(description__icontains=query) |
            Q(tags__icontains=query)
        )
    
    # Apply filters
    if student:
        documents = documents.filter(student_id=student)
    
    if document_type:
        documents = documents.filter(document_type=document_type)
    
    if status:
        documents = documents.filter(status=status)
    
    if confidentiality_level:
        documents = documents.filter(confidentiality_level=confidentiality_level)
    
    if issuing_authority:
        documents = documents.filter(issuing_authority__icontains=issuing_authority)
    
    if tags:
        documents = documents.filter(tags__icontains=tags)
    
    if is_verified is not None:
        documents = documents.filter(is_verified=(is_verified.lower() == 'true'))
    
    if is_required is not None:
        documents = documents.filter(is_required=(is_required.lower() == 'true'))
    
    if is_active is not None:
        documents = documents.filter(is_active=(is_active.lower() == 'true'))
    
    # Date filters
    if upload_start_date:
        documents = documents.filter(upload_date__gte=upload_start_date)
    
    if upload_end_date:
        documents = documents.filter(upload_date__lte=upload_end_date)
    
    if issue_start_date:
        documents = documents.filter(issue_date__gte=issue_start_date)
    
    if issue_end_date:
        documents = documents.filter(issue_date__lte=issue_end_date)
    
    if expiry_start_date:
        documents = documents.filter(expiry_date__gte=expiry_start_date)
    
    if expiry_end_date:
        documents = documents.filter(expiry_date__lte=expiry_end_date)
    
    # Special filters
    if expired and expired.lower() == 'true':
        documents = documents.filter(
            expiry_date__lt=timezone.now().date()
        )
    
    if expiring_soon and expiring_soon.lower() == 'true':
        cutoff_date = timezone.now().date() + timedelta(days=30)
        documents = documents.filter(
            expiry_date__lte=cutoff_date,
            expiry_date__gt=timezone.now().date()
        )
    
    if pending_verification and pending_verification.lower() == 'true':
        documents = documents.filter(
            status='pending_review',
            is_verified=False
        )
    
    # Paginate
    documents_page, paginator = paginate_queryset(request, documents, per_page=20)
    
    # Calculate stats
    total = documents.count()
    today = timezone.now().date()
    thirty_days_from_now = today + timedelta(days=30)
    
    stats = {
        'total': total,
        'verified': documents.filter(is_verified=True).count(),
        'pending_verification': documents.filter(
            status='pending_review',
            is_verified=False
        ).count(),
        'approved': documents.filter(status='approved').count(),
        'rejected': documents.filter(status='rejected').count(),
        'expired': documents.filter(expiry_date__lt=today).count(),
        'expiring_soon': documents.filter(
            expiry_date__lte=thirty_days_from_now,
            expiry_date__gt=today
        ).count(),
        'required_documents': documents.filter(is_required=True).count(),
        'unique_students': documents.values('student').distinct().count(),
        'total_file_size': documents.aggregate(
            total=Sum('file_size')
        )['total'] or 0,
    }
    
    return render(request, 'documents/student_documents/_document_results.html', {
        'documents_page': documents_page,
        'stats': stats,
    })


# =============================================================================
# DOCUMENT ACCESS LOG SEARCH
# =============================================================================

def document_access_log_search(request):
    """HTMX-compatible document access log search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'document', 'student', 'access_type', 'was_successful',
        'start_datetime', 'end_datetime', 'ip_address', 'accessed_by'
    ])
    
    query = filters['q']
    document = filters['document']
    student = filters['student']
    access_type = filters['access_type']
    was_successful = filters['was_successful']
    start_datetime = filters['start_datetime']
    end_datetime = filters['end_datetime']
    ip_address = filters['ip_address']
    accessed_by = filters['accessed_by']
    
    # Build queryset
    logs = DocumentAccessLog.objects.select_related(
        'document',
        'document__student'
    ).order_by('-access_datetime')
    
    # Apply text search
    if query:
        logs = logs.filter(
            Q(document__document_name__icontains=query) |
            Q(document__student__first_name__icontains=query) |
            Q(document__student__last_name__icontains=query) |
            Q(ip_address__icontains=query) |
            Q(notes__icontains=query)
        )
    
    # Apply filters
    if document:
        logs = logs.filter(document_id=document)
    
    if student:
        logs = logs.filter(document__student_id=student)
    
    if access_type:
        logs = logs.filter(access_type=access_type)
    
    if ip_address:
        logs = logs.filter(ip_address__icontains=ip_address)
    
    if accessed_by:
        logs = logs.filter(created_by_id=accessed_by)
    
    if was_successful is not None:
        logs = logs.filter(was_successful=(was_successful.lower() == 'true'))
    
    if start_datetime:
        logs = logs.filter(access_datetime__gte=start_datetime)
    
    if end_datetime:
        logs = logs.filter(access_datetime__lte=end_datetime)
    
    # Paginate
    logs_page, paginator = paginate_queryset(request, logs, per_page=20)
    
    # Calculate stats
    total = logs.count()
    
    stats = {
        'total': total,
        'successful': logs.filter(was_successful=True).count(),
        'failed': logs.filter(was_successful=False).count(),
        'views': logs.filter(access_type='view').count(),
        'downloads': logs.filter(access_type='download').count(),
        'edits': logs.filter(access_type='edit').count(),
        'unique_documents': logs.values('document').distinct().count(),
        'unique_users': logs.values('created_by_id').distinct().count(),
        'unique_ips': logs.values('ip_address').distinct().count(),
    }
    
    return render(request, 'documents/access_logs/_log_results.html', {
        'logs_page': logs_page,
        'stats': stats,
    })


# =============================================================================
# DOCUMENT TYPE DISTRIBUTION
# =============================================================================

def document_type_distribution(request):
    """Get distribution of documents by type"""
    
    # Parse filters
    filters = parse_filters(request, ['student', 'status', 'is_verified'])
    student = filters['student']
    status = filters['status']
    is_verified = filters['is_verified']
    
    documents = StudentDocument.objects.filter(is_active=True)
    
    if student:
        documents = documents.filter(student_id=student)
    
    if status:
        documents = documents.filter(status=status)
    
    if is_verified is not None:
        documents = documents.filter(is_verified=(is_verified.lower() == 'true'))
    
    # Get distribution
    distribution = documents.values('document_type').annotate(
        count=Count('id')
    ).order_by('-count')
    
    data = {
        'distribution': list(distribution),
        'total': documents.count()
    }
    
    return JsonResponse(data)


# =============================================================================
# EXPIRY TIMELINE
# =============================================================================

def expiry_timeline(request):
    """Get timeline of document expirations"""
    
    today = timezone.now().date()
    
    # Documents expiring in next 30, 60, 90 days
    expiring_30 = StudentDocument.objects.filter(
        expiry_date__lte=today + timedelta(days=30),
        expiry_date__gt=today,
        is_active=True
    ).count()
    
    expiring_60 = StudentDocument.objects.filter(
        expiry_date__lte=today + timedelta(days=60),
        expiry_date__gt=today + timedelta(days=30),
        is_active=True
    ).count()
    
    expiring_90 = StudentDocument.objects.filter(
        expiry_date__lte=today + timedelta(days=90),
        expiry_date__gt=today + timedelta(days=60),
        is_active=True
    ).count()
    
    already_expired = StudentDocument.objects.filter(
        expiry_date__lt=today,
        is_active=True
    ).count()
    
    data = {
        'already_expired': already_expired,
        'expiring_30_days': expiring_30,
        'expiring_60_days': expiring_60,
        'expiring_90_days': expiring_90,
        'total_with_expiry': StudentDocument.objects.filter(
            expiry_date__isnull=False,
            is_active=True
        ).count()
    }
    
    return JsonResponse(data)


# =============================================================================
# VERIFICATION QUEUE
# =============================================================================

def verification_queue_stats(request):
    """Get statistics on verification queue"""
    
    pending = StudentDocument.objects.filter(
        status='pending_review',
        is_verified=False,
        is_active=True
    )
    
    # Get by document type
    by_type = pending.values('document_type').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Get by priority (required documents first)
    required_pending = pending.filter(is_required=True).count()
    optional_pending = pending.filter(is_required=False).count()
    
    data = {
        'total_pending': pending.count(),
        'required_pending': required_pending,
        'optional_pending': optional_pending,
        'by_type': list(by_type),
        'oldest_pending': pending.order_by('upload_date').first().upload_date.isoformat() if pending.exists() else None
    }
    
    return JsonResponse(data)


# =============================================================================
# QUICK STATS ENDPOINTS
# =============================================================================

@require_http_methods(["GET"])
def document_quick_stats(request):
    """Get quick statistics for student documents"""
    
    today = timezone.now().date()
    thirty_days_from_now = today + timedelta(days=30)
    
    active_documents = StudentDocument.objects.filter(is_active=True)
    
    stats = {
        'total_documents': active_documents.count(),
        'verified': active_documents.filter(is_verified=True).count(),
        'pending_verification': active_documents.filter(
            status='pending_review',
            is_verified=False
        ).count(),
        'expired': active_documents.filter(expiry_date__lt=today).count(),
        'expiring_soon': active_documents.filter(
            expiry_date__lte=thirty_days_from_now,
            expiry_date__gt=today
        ).count(),
        'unique_students': active_documents.values('student').distinct().count(),
        'required_missing': 0,  # Would need more complex logic to determine
        'total_file_size_mb': round(
            (active_documents.aggregate(total=Sum('file_size'))['total'] or 0) / (1024 * 1024),
            2
        ),
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def document_status_stats(request):
    """Get document status distribution statistics"""
    
    # Parse optional filters
    filters = parse_filters(request, ['document_type', 'days'])
    document_type = filters['document_type']
    days = filters.get('days', '30')
    
    try:
        days_back = int(days)
    except:
        days_back = 30
    
    cutoff_date = timezone.now() - timedelta(days=days_back)
    
    documents = StudentDocument.objects.filter(
        is_active=True,
        upload_date__gte=cutoff_date
    )
    
    if document_type:
        documents = documents.filter(document_type=document_type)
    
    stats = {
        'total': documents.count(),
        'pending_review': documents.filter(status='pending_review').count(),
        'approved': documents.filter(status='approved').count(),
        'rejected': documents.filter(status='rejected').count(),
        'expired': documents.filter(status='expired').count(),
        'requires_update': documents.filter(status='requires_update').count(),
        'period_days': days_back,
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def confidentiality_stats(request):
    """Get confidentiality level distribution"""
    
    documents = StudentDocument.objects.filter(is_active=True)
    
    stats = {
        'total': documents.count(),
        'public': documents.filter(confidentiality_level='public').count(),
        'internal': documents.filter(confidentiality_level='internal').count(),
        'confidential': documents.filter(confidentiality_level='confidential').count(),
        'restricted': documents.filter(confidentiality_level='restricted').count(),
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def access_activity_stats(request):
    """Get document access activity statistics"""
    
    # Parse optional filters
    filters = parse_filters(request, ['days'])
    days = filters.get('days', '7')
    
    try:
        days_back = int(days)
    except:
        days_back = 7
    
    cutoff_datetime = timezone.now() - timedelta(days=days_back)
    
    logs = DocumentAccessLog.objects.filter(
        access_datetime__gte=cutoff_datetime
    )
    
    # Get access type distribution
    access_distribution = logs.values('access_type').annotate(
        count=Count('id')
    ).order_by('-count')
    
    stats = {
        'total_accesses': logs.count(),
        'successful': logs.filter(was_successful=True).count(),
        'failed': logs.filter(was_successful=False).count(),
        'unique_documents': logs.values('document').distinct().count(),
        'unique_users': logs.values('created_by_id').distinct().count(),
        'access_distribution': list(access_distribution),
        'period_days': days_back,
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def student_document_profile_stats(request):
    """Get statistics for a specific student's documents"""
    
    student_id = request.GET.get('student_id')
    
    if not student_id:
        return JsonResponse({'error': 'student_id required'}, status=400)
    
    documents = StudentDocument.objects.filter(
        student_id=student_id,
        is_active=True
    )
    
    today = timezone.now().date()
    thirty_days_from_now = today + timedelta(days=30)
    
    stats = {
        'total_documents': documents.count(),
        'verified': documents.filter(is_verified=True).count(),
        'pending_verification': documents.filter(
            status='pending_review',
            is_verified=False
        ).count(),
        'document_types': list(documents.values('document_type').annotate(
            count=Count('id')
        ).order_by('-count')),
        'expired': documents.filter(expiry_date__lt=today).count(),
        'expiring_soon': documents.filter(
            expiry_date__lte=thirty_days_from_now,
            expiry_date__gt=today
        ).count(),
        'required_documents': documents.filter(is_required=True).count(),
        'total_file_size_mb': round(
            (documents.aggregate(total=Sum('file_size'))['total'] or 0) / (1024 * 1024),
            2
        ),
        'most_accessed': documents.order_by('-access_count').first().document_name if documents.exists() else None,
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def document_storage_stats(request):
    """Get storage usage statistics"""
    
    documents = StudentDocument.objects.filter(is_active=True)
    
    # Get storage by document type
    by_type = documents.values('document_type').annotate(
        count=Count('id'),
        total_size=Sum('file_size')
    ).order_by('-total_size')
    
    # Convert to MB for readability
    for item in by_type:
        item['total_size_mb'] = round((item['total_size'] or 0) / (1024 * 1024), 2)
    
    total_size = documents.aggregate(total=Sum('file_size'))['total'] or 0
    
    stats = {
        'total_documents': documents.count(),
        'total_size_bytes': total_size,
        'total_size_mb': round(total_size / (1024 * 1024), 2),
        'total_size_gb': round(total_size / (1024 * 1024 * 1024), 2),
        'by_type': list(by_type),
        'average_file_size_mb': round(
            (documents.aggregate(avg=Avg('file_size'))['avg'] or 0) / (1024 * 1024),
            2
        ),
        'largest_file_mb': round(
            (documents.aggregate(max=Sum('file_size'))['max'] or 0) / (1024 * 1024),
            2
        ),
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def recent_uploads_stats(request):
    """Get statistics on recent uploads"""
    
    # Parse optional filters
    filters = parse_filters(request, ['days'])
    days = filters.get('days', '7')
    
    try:
        days_back = int(days)
    except:
        days_back = 7
    
    cutoff_date = timezone.now() - timedelta(days=days_back)
    
    recent = StudentDocument.objects.filter(
        upload_date__gte=cutoff_date,
        is_active=True
    )
    
    # Get uploads by day
    by_day = recent.extra(
        select={'day': 'DATE(upload_date)'}
    ).values('day').annotate(
        count=Count('id')
    ).order_by('day')
    
    stats = {
        'total_uploads': recent.count(),
        'verified': recent.filter(is_verified=True).count(),
        'pending_verification': recent.filter(
            status='pending_review',
            is_verified=False
        ).count(),
        'by_day': list(by_day),
        'by_type': list(recent.values('document_type').annotate(
            count=Count('id')
        ).order_by('-count')),
        'period_days': days_back,
    }
    
    return JsonResponse(stats)