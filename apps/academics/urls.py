# academics/urls.py

from django.urls import path
from . import views
from . import htmx_views

app_name = 'academics'

urlpatterns = [
    # =============================================================================
    # ACADEMIC SESSION URLS
    # =============================================================================
    path('sessions/', views.academic_session_list, name='academic_session_list'),
    path('sessions/create/', views.academic_session_create, name='academic_session_create'),
    path('sessions/<uuid:pk>/', views.academic_session_detail, name='academic_session_detail'),
    path('sessions/<uuid:pk>/update/', views.academic_session_update, name='academic_session_update'),
    path('sessions/<uuid:pk>/delete/', views.academic_session_delete, name='academic_session_delete'),
    
    # =============================================================================
    # HOLIDAY URLS
    # =============================================================================
    path('holidays/', views.holiday_list, name='holiday_list'),
    path('holidays/create/', views.holiday_create, name='holiday_create'),
    path('holidays/<uuid:pk>/update/', views.holiday_update, name='holiday_update'),
    path('holidays/<uuid:pk>/delete/', views.holiday_delete, name='holiday_delete'),
    path('holidays/break-analysis/', views.break_analysis, name='break_analysis'),
    path('holidays/sync-breaks/', views.sync_breaks, name='sync_breaks'),
    
    # =============================================================================
    # ACADEMIC LEVEL URLS
    # =============================================================================
    path('levels/', views.academic_level_list, name='academic_level_list'),
    path('levels/create/', views.academic_level_create, name='academic_level_create'),
    path('levels/<uuid:pk>/update/', views.academic_level_update, name='academic_level_update'),
    path('levels/<uuid:pk>/delete/', views.academic_level_delete, name='academic_level_delete'),
    
    # =============================================================================
    # SUBJECT URLS
    # =============================================================================
    path('subjects/', views.subject_list, name='subject_list'),
    path('subjects/create/', views.subject_create, name='subject_create'),
    path('subjects/<uuid:pk>/', views.subject_detail, name='subject_detail'),
    path('subjects/<uuid:pk>/update/', views.subject_update, name='subject_update'),
    path('subjects/<uuid:pk>/delete/', views.subject_delete, name='subject_delete'),
    
    # =============================================================================
    # CLASSROOM URLS
    # =============================================================================
    path('classrooms/', views.classroom_list, name='classroom_list'),
    path('classrooms/create/', views.classroom_create, name='classroom_create'),
    path('classrooms/<uuid:pk>/', views.classroom_detail, name='classroom_detail'),
    path('classrooms/<uuid:pk>/update/', views.classroom_update, name='classroom_update'),
    path('classrooms/<uuid:pk>/delete/', views.classroom_delete, name='classroom_delete'),
    
    # =============================================================================
    # CLASS URLS
    # =============================================================================
    path('classes/', views.class_list, name='class_list'),
    path('classes/create/', views.class_create, name='class_create'),
    path('classes/<uuid:pk>/', views.class_detail, name='class_detail'),
    path('classes/<uuid:pk>/update/', views.class_update, name='class_update'),
    path('classes/<uuid:pk>/delete/', views.class_delete, name='class_delete'),
    
    # =============================================================================
    # CLASS SUBJECT URLS
    # =============================================================================
    path('class-subjects/', views.class_subject_list, name='class_subject_list'),
    path('class-subjects/create/', views.class_subject_create, name='class_subject_create'),
    path('class-subjects/<uuid:pk>/update/', views.class_subject_update, name='class_subject_update'),
    path('class-subjects/<uuid:pk>/delete/', views.class_subject_delete, name='class_subject_delete'),
    
    # =============================================================================
    # STUDENT ENROLLMENT URLS
    # =============================================================================
    path('enrollments/', views.enrollment_list, name='enrollment_list'),
    path('enrollments/create/', views.enrollment_create, name='enrollment_create'),
    path('enrollments/<uuid:pk>/', views.enrollment_detail, name='enrollment_detail'),
    path('enrollments/<uuid:pk>/update/', views.enrollment_update, name='enrollment_update'),
    path('enrollments/<uuid:pk>/delete/', views.enrollment_delete, name='enrollment_delete'),
    
    # =============================================================================
    # ACADEMIC PROGRESS URLS
    # =============================================================================
    path('progress/', views.progress_list, name='progress_list'),
    path('progress/<uuid:pk>/', views.progress_detail, name='progress_detail'),
    path('progress/<uuid:pk>/update/', views.progress_update, name='progress_update'),
    path('progress/<uuid:pk>/finalize/', views.progress_finalize, name='progress_finalize'),
    
    # =============================================================================
    # HTMX SEARCH ENDPOINTS
    # =============================================================================
    # =============================================================================
    # HTMX SEARCH ENDPOINTS
    # =============================================================================

    # Academic Sessions
    path('htmx/sessions/search/', htmx_views.session_search, name='session_search'),
    path('htmx/sessions/quick-stats/', htmx_views.session_quick_stats, name='session_quick_stats'),

    # Holidays
    path('htmx/holidays/search/', htmx_views.holiday_search, name='holiday_search'),

    # Subjects
    path('htmx/subjects/search/', htmx_views.subject_search, name='subject_search'),

    # Academic Levels
    path('htmx/levels/search/', htmx_views.academic_level_search, name='level_search'),

    # Classrooms
    path('htmx/classrooms/search/', htmx_views.classroom_search, name='classroom_search'),

    # Classes
    path('htmx/classes/search/', htmx_views.class_search, name='class_search'),
    path('htmx/classes/quick-stats/', htmx_views.class_quick_stats, name='class_quick_stats'),

    # Class Subjects
    path('htmx/class-subjects/search/', htmx_views.class_subject_search, name='class_subject_search'),

    # Student Enrollments
    path('htmx/enrollments/search/', htmx_views.enrollment_search, name='enrollment_search'),
    path('htmx/enrollments/quick-stats/', htmx_views.enrollment_quick_stats, name='enrollment_quick_stats'),

    # Academic Progress
    path('htmx/progress/search/', htmx_views.progress_search, name='progress_search'),

    # =============================================================================
    # EXPORT ENDPOINTS
    # =============================================================================

    # Academic Levels
    path('levels/export/excel/', views.export_levels_excel, name='export_levels_excel'),
    path('levels/export/pdf/', views.export_levels_pdf, name='export_levels_pdf'),

]