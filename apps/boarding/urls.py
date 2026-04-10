# boarding/urls.py

"""
URL configuration for the boarding app.

ORGANISATION RULES
------------------
Within each resource section, paths are ordered:

  1. Collection routes   (no PK)     e.g. list, create, print, export
  2. Static sub-paths    (no PK)     e.g. bulk/step1, modal/add, api/*
  3. Instance routes     (<uuid:pk>) e.g. detail, edit, delete, action modals

Rule 3 uses the <uuid:pk> converter which only matches well-formed UUIDs, so
"print", "export", "bulk", etc. would never be captured by an instance route
regardless of order.  The ordering above is canonical Django style and guards
against future converter changes.

ALL primary keys are UUIDs (inherited from utils.models.BaseModel).

MODAL PATTERN
-------------
  GET  /resource/modal/add/            → load blank create-form modal
  GET  /resource/<uuid:pk>/modal/edit/ → load pre-filled edit-form modal
  POST /resource/create/               → process create  (views.py)
  POST /resource/<uuid:pk>/edit/       → process update  (views.py)

Modal views (modal_views.py) are GET-only; all write operations are handled
by action views in views.py.

CHANGES FROM PREVIOUS VERSION
------------------------------
- Added dormitory_residents_partial URL (HTMX endpoint for session-scoped
  resident table on the dormitory detail page)
"""

from django.urls import path
from . import views, modal_views

app_name = 'boarding'

urlpatterns = [

    # =========================================================================
    # DASHBOARD
    # =========================================================================

    path('', views.boarding_dashboard, name='dashboard'),


    # =========================================================================
    # DORMITORIES
    # =========================================================================

    # -- Collection & static routes (no PK) -----------------------------------

    path('dormitories/', views.dormitory_list, name='dormitory_list'),
    path('dormitories/create/', views.dormitory_create, name='dormitory_create'),
    path('dormitories/print/', views.dormitory_print_view, name='dormitory_print'),
    path('dormitories/export/excel/', views.export_dormitories_excel, name='dormitory_export_excel'),

    # -- Static modal route (no PK — create) ----------------------------------

    path('dormitories/modal/add/', modal_views.dormitory_form_modal, name='dormitory_create_modal'),

    # -- Instance routes (<uuid:pk>) ------------------------------------------

    path('dormitories/<uuid:pk>/', views.dormitory_detail, name='dormitory_detail'),
    path('dormitories/<uuid:pk>/edit/', views.dormitory_edit, name='dormitory_edit'),
    path('dormitories/<uuid:pk>/delete/', views.dormitory_delete, name='dormitory_delete'),
    path('dormitories/<uuid:pk>/activate/', views.dormitory_activate, name='dormitory_activate'),
    path('dormitories/<uuid:pk>/deactivate/', views.dormitory_deactivate, name='dormitory_deactivate'),
    path('dormitories/<uuid:pk>/update-maintenance/', views.dormitory_update_maintenance,name='dormitory_update_maintenance'),
    path('dormitories/<uuid:pk>/residents/', views.dormitory_residents_partial, name='dormitory_residents_partial'),

    # -- Instance modal routes (<uuid:pk>) ------------------------------------

    path('dormitories/<uuid:pk>/modal/edit/', modal_views.dormitory_form_modal, name='dormitory_edit_modal'),
    path('dormitories/<uuid:pk>/modal/delete/', modal_views.dormitory_delete_modal, name='dormitory_delete_modal'),
    path('dormitories/<uuid:pk>/modal/activate/', modal_views.dormitory_activate_modal, name='dormitory_activate_modal'),
    path('dormitories/<uuid:pk>/modal/deactivate/', modal_views.dormitory_deactivate_modal, name='dormitory_deactivate_modal'),
    path('dormitories/<uuid:pk>/modal/capacity/', modal_views.dormitory_capacity_check_modal, name='dormitory_capacity_modal'),
    path('dormitories/<uuid:pk>/modal/maintenance/', modal_views.dormitory_maintenance_schedule_modal, name='dormitory_maintenance_modal'),
    path('dormitories/<uuid:pk>/modal/update-maintenance/', modal_views.dormitory_update_maintenance_modal, name='dormitory_update_maintenance_modal'),


    # =========================================================================
    # BOARDING ENROLLMENTS
    # =========================================================================

    # -- Collection & static routes (no PK) -----------------------------------

    path('enrollments/create/', views.boarding_enrollment_create, name='enrollment_create'),
    path('enrollments/print/', views.boarding_enrollment_print_view, name='enrollment_print'),
    path('enrollments/export/excel/', views.export_boarding_enrollments_excel, name='enrollment_export_excel'),

    # -- Bulk enrollment (no PK) ----------------------------------------------

    path('enrollments/bulk/step1/', views.bulk_enrollment_step1, name='bulk_enrollment_step1'),
    path('enrollments/bulk/step2/', views.bulk_enrollment_step2, name='bulk_enrollment_step2'),
    path('enrollments/bulk/modal/preview/', modal_views.bulk_enrollment_preview_modal, name='bulk_enrollment_preview_modal'),
    path('enrollments/bulk/modal/confirm/', modal_views.bulk_enrollment_confirm_modal, name='bulk_enrollment_confirm_modal'),

    # -- Instance routes (<uuid:pk>) ------------------------------------------

    path('enrollments/<uuid:pk>/', views.boarding_enrollment_detail, name='enrollment_detail'),
    path('enrollments/<uuid:pk>/edit/', views.boarding_enrollment_edit, name='enrollment_edit'),
    path('enrollments/<uuid:pk>/approve/', views.boarding_enrollment_approve, name='enrollment_approve'),
    path('enrollments/<uuid:pk>/terminate/', views.boarding_enrollment_terminate, name='enrollment_terminate'),
    path('enrollments/<uuid:pk>/suspend/', views.boarding_enrollment_suspend, name='enrollment_suspend'),
    path('enrollments/<uuid:pk>/delete/', views.boarding_enrollment_delete, name='enrollment_delete'),

    # -- Instance modal routes (<uuid:pk>) ------------------------------------

    path('dormitories/<uuid:dormitory_pk>/modal/enroll/',  modal_views.boarding_enrollment_create_modal, name='dormitory_enroll_modal'),
    path('enrollments/<uuid:pk>/modal/edit/', modal_views.boarding_enrollment_edit_modal, name='enrollment_edit_modal'),
    path('enrollments/<uuid:pk>/modal/delete/', modal_views.boarding_enrollment_delete_modal, name='enrollment_delete_modal'),
    path('enrollments/<uuid:pk>/modal/approve/', modal_views.boarding_enrollment_approve_modal, name='enrollment_approve_modal'),
    path('enrollments/<uuid:pk>/modal/terminate/', modal_views.boarding_enrollment_terminate_modal, name='enrollment_terminate_modal'),
    path('enrollments/<uuid:pk>/modal/suspend/', modal_views.boarding_enrollment_suspend_modal, name='enrollment_suspend_modal'),
    path('enrollments/<uuid:pk>/modal/detail/', modal_views.boarding_enrollment_detail_modal, name='enrollment_detail_modal'),
    path('enrollments/<uuid:pk>/modal/assign-room/', modal_views.boarding_enrollment_assign_room_modal, name='enrollment_assign_room_modal'),
    path('enrollments/<uuid:pk>/modal/update-consent/', modal_views.boarding_enrollment_update_consent_modal, name='enrollment_update_consent_modal'),
    path('enrollments/<uuid:pk>/modal/change-dormitory/', modal_views.boarding_enrollment_change_dormitory_modal, name='enrollment_change_dormitory_modal'),
    path('enrollments/<uuid:pk>/modal/update-boarding-type/', modal_views.boarding_enrollment_update_boarding_type_modal, name='enrollment_update_boarding_type_modal'),
    path('enrollments/<uuid:pk>/modal/add-note/', modal_views.boarding_enrollment_add_note_modal, name='enrollment_add_note_modal'),


    # =========================================================================
    # CAPACITY PLANNING MODALS  (student-scoped, no enrollment PK)
    # =========================================================================

    path('students/<uuid:student_id>/modal/boarding-eligibility/', modal_views.student_boarding_eligibility_modal, name='student_boarding_eligibility_modal'),


    # =========================================================================
    # AJAX / JSON UTILITY ENDPOINTS
    # =========================================================================

    path('api/dormitory/<uuid:pk>/capacity-check/', views.check_dormitory_capacity_ajax, name='api_dormitory_capacity_check'),
    path('api/student/<uuid:student_id>/boarding-eligibility/', views.check_student_boarding_eligibility_ajax, name='api_student_boarding_eligibility'),
    path('api/students/<uuid:student_id>/guardians/', views.get_student_guardians_api, name='student_guardians_api'),
    path('api/quick-stats/', views.boarding_quick_stats_ajax, name='api_boarding_quick_stats'),


    # =========================================================================
    # REPORTS
    # =========================================================================

    path('reports/modal/occupancy/', modal_views.dormitory_occupancy_report_modal, name='report_occupancy_modal'),
    path('reports/modal/statistics/', modal_views.boarding_statistics_modal, name='report_statistics_modal'),
]


