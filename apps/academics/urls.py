# academics/urls.py

"""
URL Configuration for Academics Module
Organized into two main sections:

1. Regular Views (views.py) - Full page loads, list views (with HTMX support), and actions
2. Modal Views (modal_views.py) - HTMX modal content loaders

Key Architecture:
- List views handle BOTH full page loads AND HTMX requests
- Unified modals for create/edit operations (same modal, different mode)
- Action endpoints return HTMX responses with custom headers
- All URLs use UUID primary keys (pk)

Modal Pattern:
- POST /resource/save/ → Create new resource
- POST /resource/<uuid:pk>/save/ → Update existing resource

Following the same pattern as loans and finance modules for consistency
"""

from django.urls import path
from . import views, modal_views

app_name = 'academics'

urlpatterns = [
    # =============================================================================
    # DASHBOARD
    # =============================================================================
    path('', views.academics_dashboard, name='dashboard'),

    # =============================================================================
    # ACADEMIC SESSIONS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('sessions/', views.academic_session_list, name='session_list'),

    # CRUD Views
    path('sessions/create/', views.academic_session_create, name='session_create'),
    path('sessions/<uuid:pk>/', views.academic_session_detail, name='session_detail'),
    path('sessions/<uuid:pk>/edit/', views.academic_session_edit, name='session_edit'),

    # Action Views
    path('sessions/<uuid:pk>/delete/', views.academic_session_delete, name='session_delete'),
    path('sessions/<uuid:pk>/close/', views.academic_session_close, name='session_close'),
    path('sessions/<uuid:pk>/reopen/', views.academic_session_reopen, name='session_reopen'),
    path('sessions/<uuid:pk>/set-current/', views.academic_session_set_current, name='session_set_current'),
    path('sessions/<uuid:pk>/toggle-active/', views.academic_session_toggle_active, name='session_toggle_active'),

    # Print & Export
    path('sessions/<uuid:pk>/print/', views.academic_session_print_detail, name='session_print_detail'),
    path('sessions/<uuid:pk>/print-detail/', views.academic_session_print_detail, name='session_print_view'),
    path('sessions/print/', views.academic_session_print_view, name='sessions_print_view'),
    path('sessions/export/excel/', views.export_academic_sessions_excel, name='export_sessions_excel'),

    # Modal Views
    path('sessions/<uuid:session_pk>/modal/delete/', modal_views.academic_session_delete_modal, name='session_delete_modal'),
    path('sessions/<uuid:session_pk>/modal/close/', modal_views.academic_session_close_modal, name='session_close_modal'),
    path('sessions/<uuid:session_pk>/modal/reopen/', modal_views.academic_session_reopen_modal, name='session_reopen_modal'),
    path('sessions/<uuid:session_pk>/modal/set-current/', modal_views.academic_session_set_current_modal, name='session_set_current_modal'),
    path('sessions/<uuid:session_pk>/modal/toggle-active/', modal_views.academic_session_toggle_active_modal, name='session_toggle_active_modal'),
    path('sessions/<uuid:session_pk>/modal/quick-view/', modal_views.academic_session_quick_view_modal, name='session_quick_view_modal'),

    # =============================================================================
    # SUBJECTS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('subjects/', views.subject_list, name='subject_list'),

    # CRUD Views
    path('subjects/create/', views.subject_create, name='subject_create'),
    path('subjects/<uuid:pk>/', views.subject_detail, name='subject_detail'),
    path('subjects/<uuid:pk>/edit/', views.subject_edit, name='subject_edit'),

    # Action Views
    path('subjects/<uuid:pk>/delete/', views.subject_delete, name='subject_delete'),
    path('subjects/<uuid:pk>/toggle-active/', views.subject_toggle_active, name='subject_toggle_active'),

    # Print & Export
    path('subjects/<uuid:pk>/print/', views.subject_print_detail, name='subject_print_detail'),
    path('subjects/<uuid:pk>/print-detail/', views.subject_print_detail, name='subject_print_view'),
    path('subjects/print/', views.subject_print_view, name='subjects_print_view'),
    path('subjects/export/excel/', views.export_subjects_excel, name='export_subjects_excel'),

    # Modal Views
    path('subjects/<uuid:subject_pk>/modal/delete/', modal_views.subject_delete_modal, name='subject_delete_modal'),
    path('subjects/<uuid:subject_pk>/modal/toggle-active/', modal_views.subject_toggle_active_modal, name='subject_toggle_active_modal'),
    path('subjects/<uuid:subject_pk>/modal/quick-view/', modal_views.subject_quick_view_modal, name='subject_quick_view_modal'),

    # =============================================================================
    # ACADEMIC LEVELS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('levels/', views.academic_level_list, name='level_list'),

    # CRUD Views
    path('levels/create/', views.academic_level_create, name='level_create'),
    path('levels/<uuid:pk>/', views.academic_level_detail, name='level_detail'),
    path('levels/<uuid:pk>/edit/', views.academic_level_edit, name='level_edit'),

    # Action Views
    path('levels/<uuid:pk>/delete/', views.academic_level_delete, name='level_delete'),
    path('levels/<uuid:pk>/toggle-active/', views.academic_level_toggle_active, name='level_toggle_active'),

    # Print & Export
    path('levels/<uuid:pk>/print/', views.academic_level_print_detail, name='level_print_detail'),
    path('levels/print/', views.academic_level_print_view, name='levels_print_view'),
    path('levels/export/excel/', views.export_academic_levels_excel, name='export_levels_excel'),

    # Modal Views
    path('levels/<uuid:level_pk>/modal/delete/', modal_views.academic_level_delete_modal, name='level_delete_modal'),
    path('levels/<uuid:level_pk>/modal/toggle-active/', modal_views.academic_level_toggle_active_modal, name='level_toggle_active_modal'),
    path('levels/<uuid:level_pk>/modal/quick-view/', modal_views.academic_level_quick_view_modal, name='level_quick_view_modal'),

    # =============================================================================
    # CLASSROOMS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('classrooms/', views.classroom_list, name='classroom_list'),

    # CRUD Views
    path('classrooms/create/', views.classroom_create, name='classroom_create'),
    path('classrooms/<uuid:pk>/', views.classroom_detail, name='classroom_detail'),
    path('classrooms/<uuid:pk>/edit/', views.classroom_edit, name='classroom_edit'),

    # Action Views
    path('classrooms/<uuid:pk>/delete/', views.classroom_delete, name='classroom_delete'),
    path('classrooms/<uuid:pk>/toggle-active/', views.classroom_toggle_active, name='classroom_toggle_active'),
    path('classrooms/<uuid:pk>/toggle-bookable/', views.classroom_toggle_bookable, name='classroom_toggle_bookable'),

    # Print & Export
    path('classrooms/<uuid:pk>/print/', views.classroom_print_detail, name='classroom_print_detail'),
    path('classrooms/print/', views.classroom_print_view, name='classrooms_print_view'),
    path('classrooms/export/excel/', views.export_classrooms_excel, name='export_classrooms_excel'),

    # Modal Views
    path('classrooms/<uuid:classroom_pk>/modal/delete/', modal_views.classroom_delete_modal, name='classroom_delete_modal'),
    path('classrooms/<uuid:classroom_pk>/modal/toggle-active/', modal_views.classroom_toggle_active_modal, name='classroom_toggle_active_modal'),
    path('classrooms/<uuid:classroom_pk>/modal/toggle-bookable/', modal_views.classroom_toggle_bookable_modal, name='classroom_toggle_bookable_modal'),
    path('classrooms/<uuid:classroom_pk>/modal/quick-view/', modal_views.classroom_quick_view_modal, name='classroom_quick_view_modal'),

    # =============================================================================
    # CLASSES
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('classes/', views.class_list, name='class_list'),

    # CRUD Views
    path('classes/create/', views.class_create, name='class_create'),
    path('classes/<uuid:pk>/', views.class_detail, name='class_detail'),
    path('classes/<uuid:pk>/edit/', views.class_edit, name='class_edit'),

    # Action Views
    path('classes/<uuid:pk>/delete/', views.class_delete, name='class_delete'),
    path('classes/<uuid:pk>/toggle-active/', views.class_toggle_active, name='class_toggle_active'),
    path('classes/<uuid:pk>/assign-teacher/', views.class_assign_teacher, name='class_assign_teacher'),
    path('classes/<uuid:pk>/assign-classroom/', views.class_assign_classroom, name='class_assign_classroom'),

    # Print & Export
    path('classes/<uuid:pk>/print/', views.class_print_detail, name='class_print_detail'),
    path('classes/print/', views.class_print_view, name='classes_print_view'),
    path('classes/<uuid:pk>/export/excel/', views.export_classes_excel, name='export_classes_excel'),

    # Modal Views
    path('classes/<uuid:class_pk>/modal/delete/', modal_views.class_delete_modal, name='class_delete_modal'),
    path('classes/<uuid:class_pk>/modal/toggle-active/', modal_views.class_toggle_active_modal, name='class_toggle_active_modal'),
    path('classes/<uuid:class_pk>/modal/assign-teacher/', modal_views.class_assign_teacher_modal, name='class_assign_teacher_modal'),
    path('classes/<uuid:class_pk>/modal/assign-classroom/', modal_views.class_assign_classroom_modal, name='class_assign_classroom_modal'),
    path('classes/<uuid:class_pk>/modal/quick-view/', modal_views.class_quick_view_modal, name='class_quick_view_modal'),

    # =============================================================================
    # STUDENT ENROLLMENTS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('enrollments/', views.enrollment_list, name='enrollment_list'),

    # CRUD Views
    path('enrollments/create/', views.enrollment_create, name='enrollment_create'),
    path('students/<uuid:student_pk>/enrollments/create/', views.enrollment_create, name='enrollment_create_for_student'),
    path('classes/<uuid:class_pk>/enrollments/create/', views.enrollment_create, name='enrollment_create_for_class'),
    path('enrollments/<uuid:pk>/', views.enrollment_detail, name='enrollment_detail'),
    path('enrollments/<uuid:pk>/edit/', views.enrollment_edit, name='enrollment_edit'),

    # Action Views
    path('enrollments/<uuid:pk>/delete/', views.enrollment_delete, name='enrollment_delete'),
    path('enrollments/<uuid:pk>/toggle-active/', views.enrollment_toggle_active, name='enrollment_toggle_active'),
    path('enrollments/<uuid:pk>/update-status/', views.enrollment_update_status, name='enrollment_update_status'),
    path('enrollments/<uuid:pk>/assign-roll-number/', views.enrollment_assign_roll_number, name='enrollment_assign_roll_number'),
    path('enrollments/<uuid:pk>/create-invoice/', views.enrollment_create_invoice, name='enrollment_create_invoice'),

    # Bulk Operations
    path('enrollments/bulk/create/', views.bulk_enrollment_create, name='bulk_enrollment_create'),
    path('enrollments/bulk/step1/', views.bulk_enrollment_create, name='bulk_enrollment_step1'),
    path('enrollments/bulk/step2/', views.bulk_enrollment_step2, name='bulk_enrollment_step2'),
    path('enrollments/bulk/search/', views.bulk_enrollment_student_search, name='bulk_enrollment_student_search'),
    path('enrollments/bulk/update-status/', views.bulk_enrollment_update_status, name='bulk_enrollment_update_status'),
    path('enrollments/bulk/assign-roll-numbers/', views.bulk_assign_roll_numbers, name='bulk_assign_roll_numbers'),

    # Print & Export
    path('enrollments/<uuid:pk>/print/', views.enrollment_print_detail, name='enrollment_print_detail'),
    path('enrollments/print/', views.enrollment_print_view, name='enrollments_print_view'),
    path('enrollments/export/excel/', views.export_enrollments_excel, name='export_enrollments_excel'),

    # Modal Views
    path('enrollments/<uuid:enrollment_pk>/modal/delete/', modal_views.enrollment_delete_modal, name='enrollment_delete_modal'),
    path('enrollments/<uuid:enrollment_pk>/modal/toggle-active/', modal_views.enrollment_toggle_active_modal, name='enrollment_toggle_active_modal'),
    path('enrollments/<uuid:enrollment_pk>/modal/update-status/', modal_views.enrollment_update_status_modal, name='enrollment_update_status_modal'),
    path('enrollments/<uuid:enrollment_pk>/modal/assign-roll-number/', modal_views.enrollment_assign_roll_number_modal, name='enrollment_assign_roll_number_modal'),
    path('enrollments/<uuid:enrollment_pk>/modal/create-invoice/', modal_views.enrollment_create_invoice_modal, name='enrollment_create_invoice_modal'),
    path('enrollments/<uuid:enrollment_pk>/modal/quick-view/', modal_views.enrollment_quick_view_modal, name='enrollment_quick_view_modal'),
    path('enrollments/bulk/create/modal/', modal_views.bulk_enrollment_modal, name='bulk_enrollment_modal'),
    path('enrollments/bulk/update-status/modal/', modal_views.bulk_enrollment_status_update_modal, name='bulk_enrollment_status_update_modal'),

    # =============================================================================
    # CLASS SUBJECTS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('class-subjects/', views.class_subject_list, name='class_subject_list'),

    # CRUD Views
    path('class-subjects/create/', views.class_subject_create, name='class_subject_create'),
    path('classes/<uuid:class_pk>/subjects/create/', views.class_subject_create, name='class_subject_create_for_class'),
    path('class-subjects/<uuid:pk>/', views.class_subject_detail, name='class_subject_detail'),
    path('class-subjects/<uuid:pk>/edit/', views.class_subject_edit, name='class_subject_edit'),

    # Action Views
    path('class-subjects/<uuid:pk>/delete/', views.class_subject_delete, name='class_subject_delete'),
    path('class-subjects/<uuid:pk>/toggle-active/', views.class_subject_toggle_active, name='class_subject_toggle_active'),
    path('class-subjects/<uuid:pk>/assign-teacher/', views.class_subject_assign_teacher, name='class_subject_assign_teacher'),

    # Bulk Operations
    path('class-subjects/bulk/assign/', views.bulk_class_subject_assign, name='bulk_class_subject_assign'),
    path('class-subjects/bulk/assign-to-multiple/', views.bulk_class_subject_assign_to_multiple, name='bulk_class_subject_assign_to_multiple'),
    path('class-subjects/bulk/assign-teachers/', views.bulk_assign_subject_teachers, name='bulk_assign_subject_teachers'),

    # Print & Export
    path('class-subjects/<uuid:pk>/print/', views.class_subject_print_detail, name='class_subject_print_detail'),
    path('class-subjects/print/', views.class_subject_print_view, name='class_subjects_print_view'),
    path('class-subjects/export/excel/', views.export_class_subjects_excel, name='export_class_subjects_excel'),

    # Modal Views
    path('class-subjects/<uuid:class_subject_pk>/modal/delete/', modal_views.class_subject_delete_modal, name='class_subject_delete_modal'),
    path('class-subjects/<uuid:class_subject_pk>/modal/toggle-active/', modal_views.class_subject_toggle_active_modal, name='class_subject_toggle_active_modal'),
    path('class-subjects/<uuid:class_subject_pk>/modal/assign-teacher/', modal_views.class_subject_assign_teacher_modal, name='class_subject_assign_teacher_modal'),
    path('class-subjects/<uuid:class_subject_pk>/modal/quick-view/', modal_views.class_subject_quick_view_modal, name='class_subject_quick_view_modal'),
    path('class-subjects/bulk/assign/modal/', modal_views.bulk_class_subject_assign_modal, name='bulk_class_subject_assign_modal'),

    # =============================================================================
    # ACADEMIC PROGRESS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('progress/', views.academic_progress_list, name='progress_list'),

    # CRUD Views
    path('progress/create/', views.academic_progress_create, name='progress_create'),
    path('students/<uuid:student_pk>/progress/create/', views.academic_progress_create, name='progress_create_for_student'),
    path('progress/<uuid:pk>/', views.academic_progress_detail, name='progress_detail'),
    path('progress/<uuid:pk>/edit/', views.academic_progress_edit, name='progress_edit'),

    # Action Views
    path('progress/<uuid:pk>/delete/', views.academic_progress_delete, name='progress_delete'),
    path('progress/<uuid:pk>/finalize/', views.academic_progress_finalize, name='progress_finalize'),
    path('progress/<uuid:pk>/update-promotion/', views.academic_progress_update_promotion, name='progress_update_promotion'),

    # Bulk Operations
    path('progress/bulk/finalize/', views.bulk_progress_finalize, name='bulk_progress_finalize'),
    path('progress/bulk/calculate/', views.bulk_progress_calculate, name='bulk_progress_calculate'),

    # Print & Export
    path('progress/<uuid:pk>/print/', views.academic_progress_print_detail, name='progress_print_detail'),
    path('progress/<uuid:pk>/report-card/', views.academic_progress_report_card, name='progress_report_card'),
    path('progress/print/', views.academic_progress_list_print_view, name='progress_list_print_view'),
    path('progress/export/excel/', views.export_academic_progress_excel, name='export_progress_excel'),

    # Modal Views
    path('progress/<uuid:progress_pk>/modal/delete/', modal_views.academic_progress_delete_modal, name='progress_delete_modal'),
    path('progress/<uuid:progress_pk>/modal/finalize/', modal_views.academic_progress_finalize_modal, name='progress_finalize_modal'),
    path('progress/<uuid:progress_pk>/modal/promotion/', modal_views.academic_progress_promotion_modal, name='progress_promotion_modal'),
    path('progress/<uuid:progress_pk>/modal/quick-view/', modal_views.academic_progress_quick_view_modal, name='progress_quick_view_modal'),
    path('progress/bulk/finalize/modal/', modal_views.bulk_progress_finalize_modal, name='bulk_progress_finalize_modal'),

    # =============================================================================
    # HOLIDAYS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('holidays/', views.holiday_list, name='holiday_list'),

    # CRUD Views
    path('holidays/create/', views.holiday_create, name='holiday_create'),
    path('holidays/<uuid:pk>/', views.holiday_detail, name='holiday_detail'),
    path('holidays/<uuid:pk>/edit/', views.holiday_edit, name='holiday_edit'),

    # Action Views
    path('holidays/<uuid:pk>/delete/', views.holiday_delete, name='holiday_delete'),

    # Print & Export
    path('holidays/<uuid:pk>/print/', views.holiday_print_detail, name='holiday_print_detail'),
    path('holidays/print/', views.holiday_print_view, name='holidays_print_view'),
    path('holidays/export/excel/', views.export_holidays_excel, name='export_holidays_excel'),
    path('holidays/calendar/export/', views.export_holidays_calendar, name='export_holidays_calendar'),

    # Modal Views
    path('holidays/<uuid:holiday_pk>/modal/delete/', modal_views.holiday_delete_modal, name='holiday_delete_modal'),
    path('holidays/<uuid:holiday_pk>/modal/quick-view/', modal_views.holiday_quick_view_modal, name='holiday_quick_view_modal'),

    # =============================================================================
    # STUDENT PROMOTIONS
    # =============================================================================
    path('promotions/', views.promotion_dashboard, name='promotion_dashboard'),
    path('promotions/single/', views.promote_student, name='promote_student'),
    path('promotions/bulk/', views.bulk_promote_students, name='bulk_promote_students'),
    
    # =============================================================================
    # REPORTS
    # =============================================================================
    # Report Generation Modals
    path('reports/session-summary/modal/', modal_views.session_summary_report_modal, name='session_summary_report_modal'),
    path('reports/enrollment/modal/', modal_views.enrollment_report_modal, name='enrollment_report_modal'),
    path('reports/attendance/modal/', modal_views.attendance_report_modal, name='attendance_report_modal'),
    path('reports/grade-distribution/modal/', modal_views.grade_distribution_report_modal, name='grade_distribution_report_modal'),
    path('reports/class-roster/modal/', modal_views.class_roster_report_modal, name='class_roster_report_modal'),
    path('reports/teacher-assignment/modal/', modal_views.teacher_assignment_report_modal, name='teacher_assignment_report_modal'),
    path('reports/promotion-analysis/modal/', modal_views.promotion_analysis_report_modal, name='promotion_analysis_report_modal'),

    # Report Generation Views
    path('reports/session-summary/', views.session_summary_report, name='session_summary_report'),
    path('reports/enrollment/', views.enrollment_report, name='enrollment_report'),
    path('reports/class-roster/<uuid:class_pk>/', views.class_roster_report, name='class_roster_report'),
    path('reports/teacher-assignment/', views.teacher_assignment_report, name='teacher_assignment_report'),

    # =============================================================================
    # ACADEMIC CALENDAR
    # =============================================================================
    # Calendar Views
    path('calendar/', views.academic_calendar, name='academic_calendar'),
    path('calendar/<int:year>/<int:month>/', views.academic_calendar, name='academic_calendar_month'),
    path('calendar/events/modal/', modal_views.calendar_events_modal, name='calendar_events_modal'),

    # =============================================================================
    # IMPORT/EXPORT
    # =============================================================================
    # Modal Views
    path('students/import/modal/', modal_views.import_students_modal, name='import_students_modal'),
    path('enrollments/import/modal/', modal_views.import_enrollments_modal, name='import_enrollments_modal'),
    path('subjects/import/modal/', modal_views.import_subjects_modal, name='import_subjects_modal'),
    path('export/<str:resource_type>/options/modal/', modal_views.export_options_modal, name='export_options_modal'),

    # =============================================================================
    # SETTINGS & CONFIGURATION
    # =============================================================================
    # Modal Views
    path('settings/academic/modal/', modal_views.academic_settings_modal, name='academic_settings_modal'),
    path('settings/grading-scale/modal/', modal_views.grading_scale_modal, name='grading_scale_modal'),
    path('settings/promotion-rules/modal/', modal_views.promotion_rules_modal, name='promotion_rules_modal'),

    # =============================================================================
    # UTILITY ENDPOINTS
    # =============================================================================
    # Modal Views
    path('history/<str:content_type>/<uuid:object_id>/modal/', modal_views.history_modal, name='history_modal'),
    path('confirm-action/modal/', modal_views.confirm_action_modal, name='confirm_action_modal'),
    path('students/<uuid:student_pk>/enrollment-history/modal/', modal_views.student_enrollment_history_modal, name='student_enrollment_history_modal'),
    path('classes/<uuid:class_pk>/students/modal/', modal_views.class_students_modal, name='class_students_modal'),
    path('teachers/<uuid:teacher_pk>/classes/modal/', modal_views.teacher_classes_modal, name='teacher_classes_modal'),

    # =============================================================================
    # AJAX ENDPOINTS (for dynamic form field loading)
    # =============================================================================
    path('ajax/get-subjects-for-level/<uuid:level_pk>/', views.ajax_get_subjects_for_level, name='ajax_get_subjects_for_level'),
    path('ajax/get-classes-for-session/<uuid:session_pk>/', views.ajax_get_classes_for_session, name='ajax_get_classes_for_session'),
    path('ajax/get-next-roll-number/<uuid:class_pk>/', views.ajax_get_next_roll_number, name='ajax_get_next_roll_number'),
    path('ajax/check-enrollment-duplicate/', views.ajax_check_enrollment_duplicate, name='ajax_check_enrollment_duplicate'),
    path('ajax/get-class-subjects/<uuid:class_pk>/', views.ajax_get_class_subjects, name='ajax_get_class_subjects'),
]