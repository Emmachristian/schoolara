# students/urls.py

"""
URL Configuration for Students Module

Organized into two main sections:
1. Regular Views (views.py) - Full page loads, list views (with HTMX support), and actions
2. Modal Views (modal_views.py) - HTMX modal content loaders

Key Architecture:
- List views handle BOTH full page loads AND HTMX requests
- Unified modals for create/edit operations (same modal, different mode)
- Action endpoints return HTMX responses with custom headers
- All URLs use UUID primary keys for security

Modal Pattern:
- GET /resource/add/ → Load create modal
- GET /resource/<pk>/edit/ → Load edit modal
- POST /resource/save/ → Create new resource
- POST /resource/<pk>/save/ → Update existing resource
"""

from django.urls import path
from . import views, modal_views

app_name = 'students'

urlpatterns = [
    # =============================================================================
    # DASHBOARD
    # =============================================================================
    path('', views.students_dashboard, name='dashboard'),
    
    # =============================================================================
    # STUDENTS
    # =============================================================================

    # List View (handles BOTH full page AND HTMX search/filter)
    path('students/', views.student_list, name='student_list'),
    
    # CRUD Views
    path('students/create/', views.student_create, name='student_create'),  # Wizard view
    path('students/<uuid:pk>/', views.student_profile, name='student_profile'),
    path('students/<uuid:pk>/edit/', views.student_edit, name='student_edit'),
    
    # Action Views
    path('students/<uuid:pk>/delete/', views.student_delete, name='student_delete'),
    path('students/<uuid:pk>/activate/', views.student_activate, name='student_activate'),
    path('students/<uuid:pk>/suspend/', views.student_suspend, name='student_suspend'),
    
    # Print & Export
    path('students/print/', views.student_print_view, name='student_print_view'),
    path('students/export/excel/', views.export_students_excel, name='export_students_excel'),

    # Modal Views (load modal HTML only)
    path('students/<uuid:pk>/modal/delete/', modal_views.student_delete_modal, name='student_delete_modal'),
    path('students/<uuid:pk>/modal/activate/', modal_views.student_activate_modal, name='student_activate_modal'),
    path('students/<uuid:pk>/modal/suspend/', modal_views.student_suspend_modal, name='student_suspend_modal'),
    path('students/<uuid:pk>/modal/status-change/', modal_views.student_status_change_modal, name='student_status_change_modal'),
    
    # =============================================================================
    # GUARDIANS
    # =============================================================================

    # List View (handles BOTH full page AND HTMX search/filter)
    path('guardians/', views.guardian_list, name='guardian_list'),
    
    # CRUD Views
    path('guardians/create/', views.guardian_create, name='guardian_create'),
    path('guardians/<uuid:pk>/', views.guardian_profile, name='guardian_profile'),
    path('guardians/<uuid:pk>/edit/', views.guardian_edit, name='guardian_edit'),
    
    # Action Views
    path('guardians/<uuid:pk>/delete/', views.guardian_delete, name='guardian_delete'),
    
    # Print & Export
    path('guardians/print/', views.guardian_print_view, name='guardian_print_view'),
    path('guardians/export/excel/', views.export_guardians_excel, name='export_guardians_excel'),

    # Modal Views (load modal HTML only)
    path('guardians/<uuid:pk>/modal/delete/', modal_views.guardian_delete_modal, name='guardian_delete_modal'),
    
    # =============================================================================
    # STUDENT-GUARDIAN RELATIONSHIPS (UNIFIED MODAL APPROACH)
    # =============================================================================
    
    # Unified Modal Views (GET - load modal HTML)
    path('students/<uuid:student_pk>/guardians/add/', modal_views.student_guardian_form_modal, name='student_guardian_create_modal'),
    path('students/<uuid:student_pk>/guardians/<uuid:relationship_pk>/edit/', modal_views.student_guardian_form_modal, name='student_guardian_edit_modal'),
    
    # Unified Save Views (POST - handle form submissions)
    path('students/<uuid:student_pk>/guardians/save/', views.student_guardian_save, name='student_guardian_create'),
    path('students/<uuid:student_pk>/guardians/<uuid:relationship_pk>/save/', views.student_guardian_save, name='student_guardian_update'),
    
    # Action Views
    path('student-guardians/<uuid:pk>/delete/', views.student_guardian_delete, name='student_guardian_delete'),
    path('student-guardians/<uuid:pk>/set-primary/', views.student_guardian_set_primary, name='student_guardian_set_primary'),
    
    # Action Modal Views
    path('student-guardians/<uuid:pk>/modal/delete/', modal_views.student_guardian_delete_modal, name='student_guardian_delete_modal'),
    path('student-guardians/<uuid:pk>/modal/set-primary/', modal_views.student_guardian_set_primary_modal, name='student_guardian_set_primary_modal'),
    
    # Quick Add Guardian Modal (from student profile)
    path('students/<uuid:student_pk>/modal/add-guardian/', modal_views.add_guardian_modal, name='add_guardian_modal'),
    
    # =============================================================================
    # SIBLING RELATIONSHIPS (UNIFIED MODAL APPROACH)
    # =============================================================================
    
    # Unified Modal Views (GET - load modal HTML)
    path('students/<uuid:student_pk>/siblings/add/', modal_views.sibling_form_modal, name='sibling_create_modal'),
    path('students/<uuid:student_pk>/siblings/<uuid:sibling_pk>/edit/', modal_views.sibling_form_modal, name='sibling_edit_modal'),
    
    # Unified Save Views (POST - handle form submissions)
    path('students/<uuid:student_pk>/siblings/save/', views.sibling_save, name='sibling_create'),
    path('students/<uuid:student_pk>/siblings/<uuid:sibling_pk>/save/', views.sibling_save, name='sibling_update'),
    
    # Action Views
    path('siblings/<uuid:pk>/delete/', views.sibling_delete, name='sibling_delete'),
    
    # Action Modal Views
    path('siblings/<uuid:pk>/modal/delete/', modal_views.sibling_delete_modal, name='sibling_delete_modal'),
    
    # Quick Add Sibling Modal (from student profile)
    path('students/<uuid:student_pk>/modal/add-sibling/', modal_views.add_sibling_modal, name='add_sibling_modal'),
    
    # =============================================================================
    # ENROLLMENT STATUS HISTORY
    # =============================================================================
    
    # List View (if needed for separate page)
    path('enrollment-history/', views.enrollment_history_list, name='enrollment_history_list'),
    
    # Detail View
    path('enrollment-history/<uuid:pk>/', views.enrollment_history_detail, name='enrollment_history_detail'),
    
    # Modal View
    path('enrollment-history/<uuid:pk>/modal/detail/', modal_views.enrollment_status_history_detail_modal, name='enrollment_history_detail_modal'),
    
    # =============================================================================
    # REPORTS & ANALYTICS
    # =============================================================================
    
    path('reports/', views.student_reports_dashboard, name='reports_dashboard'),
    path('reports/demographics/', views.demographics_report, name='demographics_report'),
    path('reports/health/', views.health_report, name='health_report'),
    path('reports/guardians/', views.guardian_report, name='guardian_report'),
    path('reports/siblings/', views.sibling_report, name='sibling_report'),
    path('reports/birthdays/', views.birthday_report, name='birthday_report'),
    
    # =============================================================================
    # BULK ACTIONS
    # =============================================================================
    
    # Bulk Status Change
    path('students/bulk/status-change/', views.bulk_status_change, name='bulk_status_change'),
    path('students/modal/bulk/status-change/', modal_views.bulk_status_change_modal, name='bulk_status_change_modal'),
    
    # Bulk Guardian Assignment
    path('students/bulk/assign-guardian/', views.bulk_assign_guardian, name='bulk_assign_guardian'),
    path('students/modal/bulk/assign-guardian/', modal_views.bulk_assign_guardian_modal, name='bulk_assign_guardian_modal'),
    
    # =============================================================================
    # PRINT & EXPORT OPTIONS MODALS
    # =============================================================================
    
    path('students/modal/print-options/', modal_views.student_print_options_modal, name='student_print_options_modal'),
    path('guardians/modal/print-options/', modal_views.guardian_print_options_modal, name='guardian_print_options_modal'),
    path('modal/export-options/', modal_views.export_options_modal, name='export_options_modal'),
    
    # =============================================================================
    # QUICK STATS API ENDPOINTS (JSON responses for AJAX/dashboard widgets)
    # =============================================================================
    
    path('api/stats/students/', views.student_quick_stats, name='student_quick_stats'),
    path('api/stats/guardians/', views.guardian_quick_stats, name='guardian_quick_stats'),
    path('api/stats/medical-alerts/', views.medical_alerts_quick_stats, name='medical_alerts_quick_stats'),
]