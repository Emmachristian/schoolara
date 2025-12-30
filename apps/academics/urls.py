# academics/urls.py
"""
URL Configuration for Academics Module
Organized into three main sections:
1. Regular Views (views.py) - Full page loads and redirects
2. Modal Views (modal_views.py) - HTMX modal actions without page refresh
3. HTMX Views (htmx_views.py) - Dynamic search and filtering
All URLs use UUID primary keys for security
"""
from django.urls import path
from . import views, htmx_views, modal_views

app_name = 'academics'

urlpatterns = [
    # =============================================================================
    # DASHBOARD
    # =============================================================================
    path('', views.academics_dashboard, name='dashboard'),
    
    # =============================================================================
    # ACADEMIC SESSIONS
    # =============================================================================
    # Regular Views
    path('sessions/', views.academic_session_list, name='session_list'),
    path('sessions/create/', views.academic_session_create, name='session_create'),
    path('sessions/<uuid:pk>/', views.academic_session_detail, name='session_detail'),
    path('sessions/<uuid:pk>/edit/', views.academic_session_edit, name='session_edit'),
    path('sessions/<uuid:pk>/close/', views.academic_session_close, name='session_close'),
    path('sessions/<uuid:pk>/reopen/', views.academic_session_reopen, name='session_reopen'),
    path('sessions/print/', views.academic_session_print_view, name='session_print_view'),
    
    # Modal Views
    path('sessions/<uuid:pk>/modal/delete/', modal_views.academic_session_delete_modal, name='session_delete_modal'),
    path('sessions/<uuid:pk>/modal/delete/submit/', modal_views.academic_session_delete, name='session_delete'),
    path('sessions/<uuid:pk>/modal/set-current/', modal_views.session_set_current_modal, name='session_set_current_modal'),
    path('sessions/<uuid:pk>/modal/set-current/submit/', modal_views.session_set_current, name='session_set_current'),
    
    # HTMX Views
    path('sessions/htmx/search/', htmx_views.session_search, name='session_search'),
    path('sessions/htmx/quick-stats/', htmx_views.session_quick_stats, name='session_quick_stats'),
    
    # =============================================================================
    # SUBJECTS
    # =============================================================================
    # Regular Views
    path('subjects/', views.subject_list, name='subject_list'),
    path('subjects/create/', views.subject_create, name='subject_create'),
    path('subjects/<uuid:pk>/', views.subject_detail, name='subject_detail'),
    path('subjects/<uuid:pk>/edit/', views.subject_edit, name='subject_edit'),
    path('subjects/print/', views.subject_print_view, name='subject_print_view'),
    
    # Modal Views
    path('subjects/<uuid:pk>/modal/delete/', modal_views.subject_delete_modal, name='subject_delete_modal'),
    path('subjects/<uuid:pk>/modal/delete/submit/', modal_views.subject_delete, name='subject_delete'),
    
    # HTMX Views
    path('subjects/htmx/search/', htmx_views.subject_search, name='subject_search'),
    
    # =============================================================================
    # ACADEMIC LEVELS
    # =============================================================================
    # Regular Views
    path('levels/', views.academic_level_list, name='level_list'),
    path('levels/create/', views.academic_level_create, name='level_create'),
    path('levels/<uuid:pk>/', views.academic_level_detail, name='level_detail'),
    path('levels/<uuid:pk>/edit/', views.academic_level_edit, name='level_edit'),
    path('levels/print/', views.academic_level_print_view, name='level_print_view'),
    
    # Modal Views
    path('levels/<uuid:pk>/modal/delete/', modal_views.academic_level_delete_modal, name='level_delete_modal'),
    path('levels/<uuid:pk>/modal/delete/submit/', modal_views.academic_level_delete, name='level_delete'),
    
    # HTMX Views
    path('levels/htmx/search/', htmx_views.academic_level_search, name='level_search'),
    
    # =============================================================================
    # CLASSROOMS
    # =============================================================================
    # Regular Views
    path('classrooms/', views.classroom_list, name='classroom_list'),
    path('classrooms/create/', views.classroom_create, name='classroom_create'),
    path('classrooms/<uuid:pk>/', views.classroom_detail, name='classroom_detail'),
    path('classrooms/<uuid:pk>/edit/', views.classroom_edit, name='classroom_edit'),
    path('classrooms/print/', views.classroom_print_view, name='classroom_print_view'),
    
    # Modal Views
    path('classrooms/<uuid:pk>/modal/delete/', modal_views.classroom_delete_modal, name='classroom_delete_modal'),
    path('classrooms/<uuid:pk>/modal/delete/submit/', modal_views.classroom_delete, name='classroom_delete'),
    
    # HTMX Views
    path('classrooms/htmx/search/', htmx_views.classroom_search, name='classroom_search'),
    
    # =============================================================================
    # CLASSES
    # =============================================================================
    # Regular Views
    path('classes/', views.class_list, name='class_list'),
    path('classes/create/', views.class_create, name='class_create'),
    path('classes/<uuid:pk>/', views.class_detail, name='class_detail'),
    path('classes/<uuid:pk>/edit/', views.class_edit, name='class_edit'),
    path('classes/print/', views.class_print_view, name='class_print_view'),
    
    # Modal Views
    path('classes/<uuid:pk>/modal/delete/', modal_views.class_delete_modal, name='class_delete_modal'),
    path('classes/<uuid:pk>/modal/delete/submit/', modal_views.class_delete, name='class_delete'),
    
    # HTMX Views
    path('classes/htmx/search/', htmx_views.class_search, name='class_search'),
    path('classes/htmx/quick-stats/', htmx_views.class_quick_stats, name='class_quick_stats'),
    
    # =============================================================================
    # STUDENT CLASS ENROLLMENTS
    # =============================================================================
    # Regular Views
    path('enrollments/', views.student_enrollment_list, name='enrollment_list'),
    path('enrollments/create/', views.student_enrollment_create, name='enrollment_create'),
    path('enrollments/<uuid:pk>/', views.student_enrollment_detail, name='enrollment_detail'),
    path('enrollments/<uuid:pk>/edit/', views.student_enrollment_edit, name='enrollment_edit'),
    path('enrollments/<uuid:pk>/transfer/', views.student_enrollment_transfer, name='enrollment_transfer'),
    path('enrollments/<uuid:pk>/withdraw/', views.student_enrollment_withdraw, name='enrollment_withdraw'),
    path('enrollments/bulk/', views.bulk_student_enrollment, name='bulk_enrollment'),
    path('enrollments/bulk/preview/', views.bulk_enrollment_preview, name='bulk_enrollment_preview'),
    path('enrollments/print/', views.student_enrollment_print_view, name='enrollment_print_view'),
    
    # Modal Views
    path('enrollments/<uuid:pk>/modal/delete/', modal_views.enrollment_delete_modal, name='enrollment_delete_modal'),
    path('enrollments/<uuid:pk>/modal/delete/submit/', modal_views.enrollment_delete, name='enrollment_delete'),
    path('enrollments/<uuid:pk>/modal/status-change/', modal_views.enrollment_status_change_modal, name='enrollment_status_change_modal'),
    path('enrollments/<uuid:pk>/modal/status-change/submit/', modal_views.enrollment_status_change, name='enrollment_status_change'),
    path('enrollments/<uuid:pk>/modal/roll-number/', modal_views.enrollment_roll_number_modal, name='enrollment_roll_number_modal'),
    path('enrollments/<uuid:pk>/modal/roll-number/submit/', modal_views.enrollment_roll_number_update, name='enrollment_roll_number_update'),
    path('enrollments/modal/bulk/', modal_views.bulk_enrollment_modal, name='bulk_enrollment_modal'),
    path('enrollments/modal/bulk/submit/', modal_views.bulk_enrollment_process, name='bulk_enrollment_process'),
    
    # HTMX Views
    path('enrollments/htmx/search/', htmx_views.enrollment_search, name='enrollment_search'),
    path('enrollments/htmx/quick-stats/', htmx_views.enrollment_quick_stats, name='enrollment_quick_stats'),
    
    # =============================================================================
    # CLASS SUBJECTS
    # =============================================================================
    # Regular Views
    path('class-subjects/', views.class_subject_list, name='class_subject_list'),
    path('class-subjects/create/', views.class_subject_create, name='class_subject_create'),
    path('class-subjects/<uuid:pk>/', views.class_subject_detail, name='class_subject_detail'),
    path('class-subjects/<uuid:pk>/edit/', views.class_subject_edit, name='class_subject_edit'),
    path('class-subjects/print/', views.class_subject_print_view, name='class_subject_print_view'),
    
    # Modal Views
    path('class-subjects/<uuid:pk>/modal/delete/', modal_views.class_subject_delete_modal, name='class_subject_delete_modal'),
    path('class-subjects/<uuid:pk>/modal/delete/submit/', modal_views.class_subject_delete, name='class_subject_delete'),
    
    # HTMX Views
    path('class-subjects/htmx/search/', htmx_views.class_subject_search, name='class_subject_search'),
    
    # =============================================================================
    # ACADEMIC PROGRESS
    # =============================================================================
    # Regular Views
    path('progress/', views.academic_progress_list, name='progress_list'),
    path('progress/create/', views.academic_progress_create, name='progress_create'),
    path('progress/<uuid:pk>/', views.academic_progress_detail, name='progress_detail'),
    path('progress/<uuid:pk>/edit/', views.academic_progress_edit, name='progress_edit'),
    path('progress/print/', views.academic_progress_print_view, name='progress_print_view'),
    
    # Modal Views
    path('progress/<uuid:pk>/modal/delete/', modal_views.academic_progress_delete_modal, name='progress_delete_modal'),
    path('progress/<uuid:pk>/modal/delete/submit/', modal_views.academic_progress_delete, name='progress_delete'),
    path('progress/<uuid:pk>/modal/finalize/', modal_views.academic_progress_finalize_modal, name='progress_finalize_modal'),
    path('progress/<uuid:pk>/modal/finalize/submit/', modal_views.academic_progress_finalize, name='progress_finalize'),
    
    # HTMX Views
    path('progress/htmx/search/', htmx_views.progress_search, name='progress_search'),
    
    # =============================================================================
    # HOLIDAYS
    # =============================================================================
    # Regular Views
    path('holidays/', views.holiday_list, name='holiday_list'),
    path('holidays/create/', views.holiday_create, name='holiday_create'),
    path('holidays/<uuid:pk>/', views.holiday_detail, name='holiday_detail'),
    path('holidays/<uuid:pk>/edit/', views.holiday_edit, name='holiday_edit'),
    path('holidays/print/', views.holiday_print_view, name='holiday_print_view'),
    
    # Modal Views
    path('holidays/<uuid:pk>/modal/delete/', modal_views.holiday_delete_modal, name='holiday_delete_modal'),
    path('holidays/<uuid:pk>/modal/delete/submit/', modal_views.holiday_delete, name='holiday_delete'),
    
    # HTMX Views
    path('holidays/htmx/search/', htmx_views.holiday_search, name='holiday_search'),
    
    # =============================================================================
    # BULK OPERATIONS & UTILITIES
    # =============================================================================
    # Bulk Operations
    #path('bulk/promote-students/', views.bulk_promote_students, name='bulk_promote_students'),
    #path('bulk/generate-reports/', views.bulk_generate_reports, name='bulk_generate_reports'),
    #path('bulk/assign-subjects/', views.bulk_assign_subjects, name='bulk_assign_subjects'),
    
    # API Endpoints for HTMX/AJAX
    #path('api/class-capacity/<uuid:class_id>/', htmx_views.class_capacity_info, name='class_capacity_info'),
    #path('api/student-availability/', htmx_views.student_availability_check, name='student_availability_check'),
    #path('api/session-calendar/<uuid:session_id>/', htmx_views.session_calendar_data, name='session_calendar_data'),
    
    # Reports & Analytics
    #path('reports/', views.academic_reports_dashboard, name='reports_dashboard'),
    #path('reports/enrollment-summary/', views.enrollment_summary_report, name='enrollment_summary_report'),
    #path('reports/class-utilization/', views.class_utilization_report, name='class_utilization_report'),
    #path('reports/academic-progress/', views.academic_progress_report, name='academic_progress_report'),
    #path('reports/session-overview/', views.session_overview_report, name='session_overview_report'),

]