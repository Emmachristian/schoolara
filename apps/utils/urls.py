# utils/urls.py

from . import views, htmx_views
from django.urls import path

app_name = 'utils'

urlpatterns = [
    # =============================================================================
    # HTMX SEARCH ENDPOINTS
    # =============================================================================

    # Audit Logs
    path('htmx/audit-logs/search/', htmx_views.audit_log_search, name='audit_log_search'),
    path('htmx/audit-logs/quick-stats/', htmx_views.audit_log_quick_stats, name='audit_log_quick_stats'),

    # Financial Audit Logs
    path('htmx/financial-audit/search/', htmx_views.financial_audit_log_search, name='financial_audit_search'),
    path('htmx/financial-audit/quick-stats/', htmx_views.financial_audit_quick_stats, name='financial_audit_quick_stats'),

    # Activity and Distribution
    path('htmx/audit-activity-by-model/', htmx_views.audit_activity_by_model, name='audit_activity_by_model'),
    path('htmx/audit-activity-by-user/', htmx_views.audit_activity_by_user, name='audit_activity_by_user'),
    path('htmx/financial-activity-by-action/', htmx_views.financial_activity_by_action, name='financial_activity_by_action'),
    path('htmx/risk-level-trends/', htmx_views.risk_level_trends, name='risk_level_trends'),

    # Additional Stats
    path('htmx/action-distribution-stats/', htmx_views.action_distribution_stats, name='action_distribution_stats'),
    path('htmx/user-activity-stats/', htmx_views.user_activity_stats, name='user_activity_stats'),
    path('htmx/financial-risk-stats/', htmx_views.financial_risk_stats, name='financial_risk_stats'),
    path('htmx/financial-amount-stats/', htmx_views.financial_amount_stats, name='financial_amount_stats'),
    path('htmx/student-financial-history-stats/', htmx_views.student_financial_history_stats, name='student_financial_history_stats'),
    path('htmx/security-monitoring-stats/', htmx_views.security_monitoring_stats, name='security_monitoring_stats'),
    path('htmx/model-activity-stats/', htmx_views.model_activity_stats, name='model_activity_stats'),

]
