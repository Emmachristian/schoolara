# boarding/urls.py

"""
URL Configuration for Boarding Module

Organized into logical sections matching savings module pattern:
1. Regular Views (views.py) - Full page loads, list views (with HTMX support), and actions
2. Modal Views (modal_views.py) - HTMX modal content loaders

Key Architecture:
- List views handle BOTH full page loads AND HTMX requests
- Unified modals for create/edit operations (same modal, different mode)
- Action endpoints return HTMX responses with custom headers
- All URLs use UUID/integer primary keys as appropriate

Modal Pattern (following savings/members modules):
- GET /resource/add/ → Load create modal
- GET /resource/<pk>/edit/ → Load edit modal
- POST /resource/save/ → Create new resource
- POST /resource/<pk>/save/ → Update existing resource
"""

from django.urls import path
from . import views, modal_views

app_name = 'boarding'

urlpatterns = [
    # =============================================================================
    # DASHBOARD
    # =============================================================================
    path('', views.boarding_dashboard, name='dashboard'),
    
    
    # =============================================================================
    # DORMITORIES
    # =============================================================================
    
    # List View (handles BOTH full page AND HTMX search/filter)
    path('dormitories/', views.dormitory_list, name='dormitory_list'),
    
    # CRUD Views
    path('dormitories/create/', views.dormitory_create, name='dormitory_create'),
    path('dormitories/<uuid:pk>/', views.dormitory_detail, name='dormitory_detail'),
    path('dormitories/<uuid:pk>/edit/', views.dormitory_edit, name='dormitory_edit'),
    
    # Action Views
    path('dormitories/<uuid:pk>/delete/', views.dormitory_delete, name='dormitory_delete'),
    path('dormitories/<uuid:pk>/activate/', views.dormitory_activate, name='dormitory_activate'),
    path('dormitories/<uuid:pk>/deactivate/', views.dormitory_deactivate, name='dormitory_deactivate'),
    
    # Modal Views (load modal HTML only)
    path('dormitories/<uuid:pk>/modal/delete/', modal_views.dormitory_delete_modal, name='dormitory_delete_modal'),
    path('dormitories/<uuid:pk>/modal/activate/', modal_views.dormitory_activate_modal, name='dormitory_activate_modal'),
    path('dormitories/<uuid:pk>/modal/deactivate/', modal_views.dormitory_deactivate_modal, name='dormitory_deactivate_modal'),
    path('dormitories/modal/add/', modal_views.dormitory_form_modal, name='dormitory_create_modal'),
    path('dormitories/<uuid:pk>/modal/edit/', modal_views.dormitory_form_modal, name='dormitory_edit_modal'),
    
    # Capacity & Planning Modal Views
    path('dormitories/<uuid:pk>/modal/capacity/', modal_views.dormitory_capacity_check_modal, name='dormitory_capacity_modal'),
    path('dormitories/<uuid:pk>/modal/maintenance/', modal_views.dormitory_maintenance_schedule_modal, name='dormitory_maintenance_modal'),
    path('dormitories/<uuid:pk>/modal/update-maintenance/', modal_views.dormitory_update_maintenance_modal, name='dormitory_update_maintenance_modal'),
    
    # Print & Export
    path('dormitories/print/', views.dormitory_print_view, name='dormitory_print'),
    path('dormitories/export/excel/', views.export_dormitories_excel, name='dormitory_export_excel'),
    
    
    # =============================================================================
    # BOARDING ENROLLMENTS
    # =============================================================================
    
    # List View (handles BOTH full page AND HTMX search/filter)
    path('enrollments/', views.boarding_enrollment_list, name='enrollment_list'),
    
    # CRUD Views
    path('enrollments/create/', views.boarding_enrollment_create, name='enrollment_create'),
    path('enrollments/<uuid:pk>/', views.boarding_enrollment_detail, name='enrollment_detail'),
    path('enrollments/<uuid:pk>/edit/', views.boarding_enrollment_edit, name='enrollment_edit'),
    
    # Enrollment Action Views
    path('enrollments/<uuid:pk>/approve/', views.boarding_enrollment_approve, name='enrollment_approve'),
    path('enrollments/<uuid:pk>/terminate/', views.boarding_enrollment_terminate, name='enrollment_terminate'),
    path('enrollments/<uuid:pk>/suspend/', views.boarding_enrollment_suspend, name='enrollment_suspend'),
    path('enrollments/<uuid:pk>/delete/', views.boarding_enrollment_delete, name='enrollment_delete'),
    
    # Enrollment Action Modal Views
    path('enrollments/<uuid:pk>/modal/approve/', modal_views.boarding_enrollment_approve_modal, name='enrollment_approve_modal'),
    path('enrollments/<uuid:pk>/modal/terminate/', modal_views.boarding_enrollment_terminate_modal, name='enrollment_terminate_modal'),
    path('enrollments/<uuid:pk>/modal/suspend/', modal_views.boarding_enrollment_suspend_modal, name='enrollment_suspend_modal'),
    path('enrollments/<uuid:pk>/modal/delete/', modal_views.boarding_enrollment_delete_modal, name='enrollment_delete_modal'),
    path('enrollments/<uuid:pk>/modal/detail/', modal_views.boarding_enrollment_detail_modal, name='enrollment_detail_modal'),
    
    # Enrollment Management Modal Views
    path('enrollments/<uuid:pk>/modal/assign-room/', modal_views.boarding_enrollment_assign_room_modal, name='enrollment_assign_room_modal'),
    path('enrollments/<uuid:pk>/modal/update-consent/', modal_views.boarding_enrollment_update_consent_modal, name='enrollment_update_consent_modal'),
    path('enrollments/<uuid:pk>/modal/change-dormitory/', modal_views.boarding_enrollment_change_dormitory_modal, name='enrollment_change_dormitory_modal'),
    path('enrollments/<uuid:pk>/modal/update-boarding-type/', modal_views.boarding_enrollment_update_boarding_type_modal, name='enrollment_update_boarding_type_modal'),
    path('enrollments/<uuid:pk>/modal/add-note/', modal_views.boarding_enrollment_add_note_modal, name='enrollment_add_note_modal'),
    
    # Print & Export
    path('enrollments/print/', views.boarding_enrollment_print_view, name='enrollment_print'),
    path('enrollments/export/excel/', views.export_boarding_enrollments_excel, name='enrollment_export_excel'),
    
    
    # =============================================================================
    # BULK ENROLLMENT
    # =============================================================================
    
    # Step-by-step bulk enrollment process
    path('enrollments/bulk/step1/', views.bulk_enrollment_step1, name='bulk_enrollment_step1'),
    path('enrollments/bulk/step2/', views.bulk_enrollment_step2, name='bulk_enrollment_step2'),
    
    # Bulk Enrollment Modal Views
    path('enrollments/bulk/modal/preview/', modal_views.bulk_enrollment_preview_modal, name='bulk_enrollment_preview_modal'),
    path('enrollments/bulk/modal/confirm/', modal_views.bulk_enrollment_confirm_modal, name='bulk_enrollment_confirm_modal'),
    
    
    # =============================================================================
    # AJAX/JSON UTILITY ENDPOINTS
    # =============================================================================
    
    # Real-time capacity checking
    path('api/dormitory/<uuid:pk>/capacity-check/', views.check_dormitory_capacity_ajax, name='api_dormitory_capacity_check'),
    
    # Student eligibility checking
    path('api/student/<uuid:student_id>/boarding-eligibility/', views.check_student_boarding_eligibility_ajax, name='api_student_boarding_eligibility'),
    path('students/<uuid:student_id>/modal/boarding-eligibility/', modal_views.student_boarding_eligibility_modal, name='student_boarding_eligibility_modal'),
    # Get guardians for a specific student (for AJAX calls)
    path('api/students/<uuid:student_id>/guardians/', views.get_student_guardians_api, name='student_guardians_api'),
    
    # Quick statistics endpoint
    path('api/boarding/quick-stats/', views.boarding_quick_stats_ajax, name='api_boarding_quick_stats'),
    
    
    # =============================================================================
    # REPORTS
    # =============================================================================
    
    # Report Modal Views
    path('reports/modal/occupancy/', modal_views.dormitory_occupancy_report_modal, name='report_occupancy_modal'),
    path('reports/modal/statistics/', modal_views.boarding_statistics_modal, name='report_statistics_modal'),
]