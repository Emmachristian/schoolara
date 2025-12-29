# documents/urls.py
from django.urls import path
from . import views, htmx_views

app_name = 'documents'

urlpatterns = [

    # =============================================================================
    # HTMX SEARCH ENDPOINTS
    # =============================================================================

    # Student Documents
    path('htmx/documents/search/', htmx_views.student_document_search, name='document_search'),
    path('htmx/documents/quick-stats/', htmx_views.document_quick_stats, name='document_quick_stats'),

    # Access Logs
    path('htmx/access-logs/search/', htmx_views.document_access_log_search, name='access_log_search'),

    # Analytics and Distribution
    path('htmx/document-type-distribution/', htmx_views.document_type_distribution, name='document_type_distribution'),
    path('htmx/expiry-timeline/', htmx_views.expiry_timeline, name='expiry_timeline'),
    path('htmx/verification-queue-stats/', htmx_views.verification_queue_stats, name='verification_queue_stats'),

    # Additional Stats
    path('htmx/document-status-stats/', htmx_views.document_status_stats, name='document_status_stats'),
    path('htmx/confidentiality-stats/', htmx_views.confidentiality_stats, name='confidentiality_stats'),
    path('htmx/access-activity-stats/', htmx_views.access_activity_stats, name='access_activity_stats'),
    path('htmx/student-profile-stats/', htmx_views.student_document_profile_stats, name='student_profile_stats'),
    path('htmx/storage-stats/', htmx_views.document_storage_stats, name='storage_stats'),
    path('htmx/recent-uploads-stats/', htmx_views.recent_uploads_stats, name='recent_uploads_stats'),

]