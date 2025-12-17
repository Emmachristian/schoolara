# academics/urls.py

from django.urls import path
from . import views
from . import ajax_views

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
    # AJAX SEARCH ENDPOINTS
    # =============================================================================
    path('ajax/sessions/search/', ajax_views.academic_session_search, name='academic_session_search'),
    path('ajax/holidays/search/', ajax_views.holiday_search, name='holiday_search'),
    path('ajax/levels/search/', ajax_views.academic_level_search, name='academic_level_search'),
    path('ajax/subjects/search/', ajax_views.subject_search, name='subject_search'),
    path('ajax/classrooms/search/', ajax_views.classroom_search, name='classroom_search'),
    path('ajax/classes/search/', ajax_views.class_search, name='class_search'),
    path('ajax/class-subjects/search/', ajax_views.class_subject_search, name='class_subject_search'),
    
    # =============================================================================
    # EXPORT ENDPOINTS
    # =============================================================================
    # Academic Levels
    path('levels/export/excel/', views.export_levels_excel, name='export_levels_excel'),
    path('levels/export/pdf/', views.export_levels_pdf, name='export_levels_pdf'),
    
    # You can add more export endpoints for other models as needed:
    # path('sessions/export/excel/', views.export_sessions_excel, name='export_sessions_excel'),
    # path('subjects/export/excel/', views.export_subjects_excel, name='export_subjects_excel'),
    # path('classes/export/excel/', views.export_classes_excel, name='export_classes_excel'),
]