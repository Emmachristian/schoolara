# exams/urls.py

"""
URL Configuration for Exams Module
Organized into two main sections:

1. Regular Views (views.py) - Full page loads, list views (with HTMX support), and actions
2. Modal Views (modal_views.py) - HTMX modal content loaders

Key Architecture:
- List views handle BOTH full page loads AND HTMX requests
- Action endpoints return HTMX responses with custom headers
- All URLs use UUIDs as primary keys (pk)
- Grade locking/unlocking with permission checks
- Result publication with auto-locking support

Modal Pattern:
- POST /resource/save/ → Create new resource
- POST /resource/<uuid:pk>/save/ → Update existing resource

Following the same pattern as academics module for consistency
"""

from django.urls import path
from . import views, modal_views

app_name = 'exams'

urlpatterns = [
    # =============================================================================
    # DASHBOARD
    # =============================================================================
    path('', views.exams_dashboard, name='dashboard'),

    # =============================================================================
    # EXAM CATEGORIES
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('categories/', views.exam_category_list, name='category_list'),

    # CRUD Views
    path('categories/create/', views.exam_category_create, name='category_create'),
    path('categories/<uuid:pk>/', views.exam_category_detail, name='category_detail'),
    path('categories/<uuid:pk>/edit/', views.exam_category_edit, name='category_edit'),

    # Action Views
    path('categories/<uuid:pk>/delete/', views.exam_category_delete, name='category_delete'),
    path('categories/<uuid:pk>/toggle-active/', views.exam_category_toggle_active, name='category_toggle_active'),

    # Print & Export
    path('categories/<uuid:pk>/print/', views.exam_category_print_detail, name='category_print_detail'),
    path('categories/print/', views.exam_category_print_view, name='categories_print_view'),
    path('categories/export/excel/', views.export_exam_categories_excel, name='export_categories_excel'),

    # Modal Views
    path('categories/<uuid:pk>/modal/delete/', modal_views.exam_category_delete_modal, name='category_delete_modal'),
    path('categories/<uuid:pk>/modal/toggle-active/', modal_views.exam_category_toggle_active_modal, name='category_toggle_active_modal'),
    path('categories/<uuid:pk>/modal/quick-view/', modal_views.exam_category_quick_view_modal, name='category_quick_view_modal'),

    # =============================================================================
    # GRADING SYSTEMS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('grading-systems/', views.grading_system_list, name='grading_system_list'),

    # CRUD Views
    path('grading-systems/create/', views.grading_system_create, name='grading_system_create'),
    path('grading-systems/<uuid:pk>/', views.grading_system_detail, name='grading_system_detail'),
    path('grading-systems/<uuid:pk>/edit/', views.grading_system_edit, name='grading_system_edit'),

    # Action Views
    path('grading-systems/<uuid:pk>/delete/', views.grading_system_delete, name='grading_system_delete'),
    path('grading-systems/<uuid:pk>/toggle-active/', views.grading_system_toggle_active, name='grading_system_toggle_active'),
    path('grading-systems/<uuid:pk>/set-default/', views.grading_system_set_default, name='grading_system_set_default'),

    # Print & Export
    path('grading-systems/<uuid:pk>/print/', views.grading_system_print_detail, name='grading_system_print_detail'),
    path('grading-systems/print/', views.grading_system_print_view, name='grading_systems_print_view'),
    path('grading-systems/export/excel/', views.export_grading_systems_excel, name='export_grading_systems_excel'),

    # Modal Views
    path('grading-systems/<uuid:pk>/modal/delete/', modal_views.grading_system_delete_modal, name='grading_system_delete_modal'),
    path('grading-systems/<uuid:pk>/modal/toggle-active/', modal_views.grading_system_toggle_active_modal, name='grading_system_toggle_active_modal'),
    path('grading-systems/<uuid:pk>/modal/set-default/', modal_views.grading_system_set_default_modal, name='grading_system_set_default_modal'),
    path('grading-systems/<uuid:pk>/modal/quick-view/', modal_views.grading_system_quick_view_modal, name='grading_system_quick_view_modal'),

    # =============================================================================
    # GRADING RANGES
    # =============================================================================
    # CRUD Views (nested under grading system)
    path('grading-systems/<uuid:system_pk>/ranges/create/', views.grading_range_create, name='grading_range_create'),
    path('grading-ranges/<uuid:pk>/edit/', views.grading_range_edit, name='grading_range_edit'),

    # Action Views
    path('grading-ranges/<uuid:pk>/delete/', views.grading_range_delete, name='grading_range_delete'),

    # Modal Views
    path('grading-ranges/<uuid:pk>/modal/delete/', modal_views.grading_range_delete_modal, name='grading_range_delete_modal'),
    path('grading-ranges/<uuid:pk>/modal/quick-view/', modal_views.grading_range_quick_view_modal, name='grading_range_quick_view_modal'),

    # =============================================================================
    # CLASS GRADING SYSTEM ASSIGNMENTS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('class-grading-systems/', views.class_grading_system_list, name='class_grading_system_list'),

    # CRUD Views
    path('class-grading-systems/create/', views.class_grading_system_create, name='class_grading_system_create'),
    path('classes/<uuid:class_pk>/grading-systems/create/', views.class_grading_system_create, name='class_grading_system_create_for_class'),
    path('class-grading-systems/<uuid:pk>/', views.class_grading_system_detail, name='class_grading_system_detail'),
    path('class-grading-systems/<uuid:pk>/edit/', views.class_grading_system_edit, name='class_grading_system_edit'),

    # Action Views
    path('class-grading-systems/<uuid:pk>/delete/', views.class_grading_system_delete, name='class_grading_system_delete'),
    path('class-grading-systems/<uuid:pk>/toggle-active/', views.class_grading_system_toggle_active, name='class_grading_system_toggle_active'),

    # Bulk Operations
    path('class-grading-systems/bulk/assign/', views.bulk_class_grading_system_assign, name='bulk_class_grading_system_assign'),

    # Print & Export
    path('class-grading-systems/print/', views.class_grading_system_print_view, name='class_grading_systems_print_view'),
    path('class-grading-systems/export/excel/', views.export_class_grading_systems_excel, name='export_class_grading_systems_excel'),

    # Modal Views
    path('class-grading-systems/<uuid:pk>/modal/delete/', modal_views.class_grading_system_delete_modal, name='class_grading_system_delete_modal'),
    path('class-grading-systems/<uuid:pk>/modal/toggle-active/', modal_views.class_grading_system_toggle_active_modal, name='class_grading_system_toggle_active_modal'),
    path('class-grading-systems/<uuid:pk>/modal/quick-view/', modal_views.class_grading_system_quick_view_modal, name='class_grading_system_quick_view_modal'),
    path('class-grading-systems/bulk/assign/modal/', modal_views.bulk_class_grading_system_assign_modal, name='bulk_class_grading_system_assign_modal'),

    # =============================================================================
    # EXAMINATIONS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('examinations/', views.examination_list, name='examination_list'),

    # CRUD Views
    path('examinations/create/', views.examination_create, name='examination_create'),
    path('examinations/<uuid:pk>/', views.examination_detail, name='examination_detail'),
    path('examinations/<uuid:pk>/edit/', views.examination_edit, name='examination_edit'),

    # Action Views
    path('examinations/<uuid:pk>/delete/', views.examination_delete, name='examination_delete'),
    path('examinations/<uuid:pk>/toggle-active/', views.examination_toggle_active, name='examination_toggle_active'),
    path('examinations/<uuid:pk>/update-status/', views.examination_update_status, name='examination_update_status'),
    path('examinations/<uuid:pk>/publish-results/', views.publish_results, name='publish_results'),
    path('examinations/<uuid:pk>/unpublish-results/', views.unpublish_results, name='unpublish_results'),

    # Print & Export
    path('examinations/<uuid:pk>/print/', views.examination_print_detail, name='examination_print_detail'),
    path('examinations/<uuid:pk>/print-timetable/', views.examination_print_timetable, name='examination_print_timetable'),
    path('examinations/<uuid:pk>/print-answer-sheet/', views.examination_print_answer_sheet, name='examination_print_answer_sheet'),
    path('examinations/print/', views.examination_print_view, name='examinations_print_view'),
    path('examinations/export/excel/', views.export_examinations_excel, name='export_examinations_excel'),

    # Modal Views
    path('examinations/<uuid:pk>/modal/delete/', modal_views.examination_delete_modal, name='examination_delete_modal'),
    path('examinations/<uuid:pk>/modal/toggle-active/', modal_views.examination_toggle_active_modal, name='examination_toggle_active_modal'),
    path('examinations/<uuid:pk>/modal/update-status/', modal_views.examination_update_status_modal, name='examination_update_status_modal'),
    path('examinations/<uuid:pk>/modal/publish-results/', modal_views.examination_publish_results_modal, name='examination_publish_results_modal'),
    path('examinations/<uuid:pk>/modal/unpublish-results/', modal_views.examination_unpublish_results_modal, name='examination_unpublish_results_modal'),
    path('examinations/<uuid:pk>/modal/quick-view/', modal_views.examination_quick_view_modal, name='examination_quick_view_modal'),

    # =============================================================================
    # EXAM REGISTRATIONS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('registrations/', views.exam_registration_list, name='registration_list'),

    # CRUD Views
    path('registrations/create/', views.exam_registration_create, name='registration_create'),
    path('examinations/<uuid:examination_pk>/registrations/create/', views.exam_registration_create, name='registration_create_for_examination'),
    path('students/<uuid:student_pk>/registrations/create/', views.exam_registration_create, name='registration_create_for_student'),
    path('registrations/<uuid:pk>/', views.exam_registration_detail, name='registration_detail'),
    path('registrations/<uuid:pk>/edit/', views.exam_registration_edit, name='registration_edit'),

    # Action Views
    path('registrations/<uuid:pk>/delete/', views.exam_registration_delete, name='registration_delete'),
    path('registrations/<uuid:pk>/update-status/', views.exam_registration_update_status, name='registration_update_status'),
    path('registrations/<uuid:pk>/verify-payment/', views.exam_registration_verify_payment, name='registration_verify_payment'),

    # Bulk Operations
    path('registrations/bulk/create/', views.bulk_exam_registration_create, name='bulk_registration_create'),
    path('registrations/bulk/update-status/', views.bulk_exam_registration_update_status, name='bulk_registration_update_status'),

    # Print & Export
    path('registrations/<uuid:pk>/print/', views.exam_registration_print_detail, name='registration_print_detail'),
    path('registrations/print/', views.exam_registration_print_view, name='registrations_print_view'),
    path('registrations/export/excel/', views.export_exam_registrations_excel, name='export_registrations_excel'),

    # Modal Views
    path('registrations/<uuid:pk>/modal/delete/', modal_views.exam_registration_delete_modal, name='registration_delete_modal'),
    path('registrations/<uuid:pk>/modal/update-status/', modal_views.exam_registration_update_status_modal, name='registration_update_status_modal'),
    path('registrations/<uuid:pk>/modal/verify-payment/', modal_views.exam_registration_verify_payment_modal, name='registration_verify_payment_modal'),
    path('registrations/<uuid:pk>/modal/quick-view/', modal_views.exam_registration_quick_view_modal, name='registration_quick_view_modal'),
    path('registrations/bulk/create/modal/', modal_views.bulk_exam_registration_modal, name='bulk_registration_modal'),

    # =============================================================================
    # STUDENT EXAM RESULTS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    # Class results selector (landing page)
    path('results/by-class/', views.class_results_selector, name='results_by_class'),

    # ✅ Single unified class results view (handles both dashboard and list modes)
    path('classes/<uuid:class_pk>/results/', views.class_results_dashboard, name='class_results_dashboard'),

    # CRUD Views
    path('results/create/', views.student_result_create, name='result_create'),
    path('examinations/<uuid:examination_pk>/results/create/', views.student_result_create, name='result_create_for_examination'),
    path('students/<uuid:student_pk>/results/create/', views.student_result_create, name='result_create_for_student'),
    path('results/<uuid:pk>/', views.student_result_detail, name='result_detail'),
    path('results/<uuid:pk>/edit/', views.student_result_edit, name='result_edit'),

    # Action Views
    path('results/<uuid:pk>/delete/', views.student_result_delete, name='result_delete'),
    path('results/<uuid:pk>/verify/', views.student_result_verify, name='result_verify'),
    path('results/<uuid:pk>/moderate/', views.student_result_moderate, name='result_moderate'),

    # Grade Locking/Unlocking
    path('results/<uuid:pk>/lock-grade/', views.lock_grade, name='lock_grade'),
    path('results/<uuid:pk>/unlock-grade/', views.unlock_grade, name='unlock_grade'),

    # Bulk Operations
    path('results/bulk/entry/', views.bulk_result_entry, name='bulk_result_entry'),
    path('results/bulk/entry/step1/', views.bulk_result_entry, name='bulk_result_entry_step1'),
    path('results/bulk/entry/step2/', views.bulk_result_entry_step2, name='bulk_result_entry_step2'),
    path('results/bulk/lock-grades/', views.bulk_lock_grades, name='bulk_lock_grades'),
    path('results/bulk/unlock-grades/', views.bulk_unlock_grades, name='bulk_unlock_grades'),
    path('results/bulk/verify/', views.bulk_verify_results, name='bulk_verify_results'),
    path('results/bulk/publish/', views.bulk_publish_results, name='bulk_publish_results'),

    # Print & Export
    path('results/<uuid:pk>/print/', views.student_result_print_detail, name='result_print_detail'),
    path('results/<uuid:pk>/print-certificate/', views.student_result_print_certificate, name='result_print_certificate'),
    path('results/<uuid:pk>/report-card/', views.student_result_report_card, name='result_report_card'),
    path('results/print/', views.student_result_print_view, name='results_print_view'),
    path('results/export/excel/', views.export_results_excel, name='export_results_excel'),

    # Modal Views
    path('results/<uuid:pk>/modal/delete/', modal_views.student_result_delete_modal, name='result_delete_modal'),
    path('results/<uuid:pk>/modal/verify/', modal_views.student_result_verify_modal, name='result_verify_modal'),
    path('results/<uuid:pk>/modal/moderate/', modal_views.student_result_moderate_modal, name='result_moderate_modal'),
    path('results/<uuid:pk>/modal/lock-grade/', modal_views.lock_grade_modal, name='lock_grade_modal'),
    path('results/<uuid:pk>/modal/unlock-grade/', modal_views.unlock_grade_modal, name='unlock_grade_modal'),
    path('results/<uuid:pk>/modal/quick-view/', modal_views.student_result_quick_view_modal, name='result_quick_view_modal'),
    path('results/<uuid:pk>/modal/grade-history/', modal_views.grade_history_modal, name='grade_history_modal'),
    path('results/bulk/entry/modal/', modal_views.bulk_result_entry_modal, name='bulk_result_entry_modal'),
    path('results/bulk/lock-grades/modal/', modal_views.bulk_lock_grades_modal, name='bulk_lock_grades_modal'),
    path('results/bulk/unlock-grades/modal/', modal_views.bulk_unlock_grades_modal, name='bulk_unlock_grades_modal'),
    path('results/bulk/publish/modal/', modal_views.bulk_publish_results_modal, name='bulk_publish_results_modal'),

    # =============================================================================
    # EXAM ANALYTICS
    # =============================================================================
    # Analytics Views
    path('analytics/', views.exam_analytics_dashboard, name='analytics_dashboard'),
    path('examinations/<uuid:examination_pk>/analytics/', views.examination_analytics, name='examination_analytics'),
    path('examinations/<uuid:examination_pk>/analytics/generate/', views.generate_exam_analytics, name='generate_exam_analytics'),
    path('analytics/grade-distribution/', views.grade_distribution_analysis, name='grade_distribution_analysis'),
    path('analytics/performance-trends/', views.performance_trends_analysis, name='performance_trends_analysis'),
    path('analytics/subject-performance/', views.subject_performance_analysis, name='subject_performance_analysis'),

    # Analytics Reports
    path('analytics/reports/exam-performance/', views.exam_performance_report, name='exam_performance_report'),
    path('analytics/reports/student-comparison/', views.student_comparison_report, name='student_comparison_report'),
    path('analytics/reports/class-comparison/', views.class_comparison_report, name='class_comparison_report'),

    # Modal Views
    path('examinations/<uuid:examination_pk>/analytics/modal/', modal_views.examination_analytics_modal, name='examination_analytics_modal'),
    path('analytics/grade-distribution/modal/', modal_views.grade_distribution_modal, name='grade_distribution_modal'),
    path('analytics/performance-trends/modal/', modal_views.performance_trends_modal, name='performance_trends_modal'),

    # =============================================================================
    # REPORTS
    # =============================================================================
    # Report Generation Modals
    path('reports/exam-summary/modal/', modal_views.exam_summary_report_modal, name='exam_summary_report_modal'),
    path('reports/result-summary/modal/', modal_views.result_summary_report_modal, name='result_summary_report_modal'),
    path('reports/grade-sheet/modal/', modal_views.grade_sheet_report_modal, name='grade_sheet_report_modal'),
    path('reports/mark-sheet/modal/', modal_views.mark_sheet_report_modal, name='mark_sheet_report_modal'),
    path('reports/pass-fail/modal/', modal_views.pass_fail_report_modal, name='pass_fail_report_modal'),
    path('reports/rank-list/modal/', modal_views.rank_list_report_modal, name='rank_list_report_modal'),
    path('reports/merit-list/modal/', modal_views.merit_list_report_modal, name='merit_list_report_modal'),

    # Report Generation Views
    path('reports/exam-summary/', views.exam_summary_report, name='exam_summary_report'),
    path('reports/result-summary/', views.result_summary_report, name='result_summary_report'),
    path('reports/grade-sheet/<uuid:examination_pk>/', views.grade_sheet_report, name='grade_sheet_report'),
    path('reports/mark-sheet/<uuid:examination_pk>/', views.mark_sheet_report, name='mark_sheet_report'),
    path('reports/rank-list/<uuid:examination_pk>/', views.rank_list_report, name='rank_list_report'),
    path('reports/merit-list/<uuid:examination_pk>/', views.merit_list_report, name='merit_list_report'),

    # =============================================================================
    # EXAM TIMETABLE
    # =============================================================================
    # Timetable Views
    path('timetable/', views.exam_timetable, name='exam_timetable'),
    path('timetable/<uuid:session_pk>/', views.exam_timetable_session, name='exam_timetable_session'),
    path('timetable/<uuid:session_pk>/print/', views.exam_timetable_print, name='exam_timetable_print'),
    path('timetable/<uuid:session_pk>/export/pdf/', views.exam_timetable_export_pdf, name='exam_timetable_export_pdf'),

    # Modal Views
    path('timetable/generate/modal/', modal_views.generate_timetable_modal, name='generate_timetable_modal'),
    path('timetable/<uuid:session_pk>/modal/', modal_views.exam_timetable_modal, name='exam_timetable_modal'),

    # =============================================================================
    # IMPORT/EXPORT
    # =============================================================================
    # Modal Views
    path('results/import/modal/', modal_views.import_results_modal, name='import_results_modal'),
    path('examinations/import/modal/', modal_views.import_examinations_modal, name='import_examinations_modal'),
    path('grading-systems/import/modal/', modal_views.import_grading_systems_modal, name='import_grading_systems_modal'),
    path('export/<str:resource_type>/options/modal/', modal_views.export_options_modal, name='export_options_modal'),

    # Import Views
    path('results/import/', views.import_results, name='import_results'),
    path('examinations/import/', views.import_examinations, name='import_examinations'),

    # Template Downloads
    path('templates/download/results-template/', views.download_results_template, name='download_results_template'),
    path('templates/download/examinations-template/', views.download_examinations_template, name='download_examinations_template'),

    # =============================================================================
    # SETTINGS & CONFIGURATION
    # =============================================================================
    # Modal Views
    path('settings/exam/modal/', modal_views.exam_settings_modal, name='exam_settings_modal'),
    path('settings/grading-scale/modal/', modal_views.grading_scale_settings_modal, name='grading_scale_settings_modal'),
    path('settings/grade-locking/modal/', modal_views.grade_locking_settings_modal, name='grade_locking_settings_modal'),

    # Settings Views
    path('settings/', views.exam_settings, name='exam_settings'),
    path('settings/grading-scale/', views.grading_scale_settings, name='grading_scale_settings'),
    path('settings/grade-locking/', views.grade_locking_settings, name='grade_locking_settings'),

    # =============================================================================
    # UTILITY ENDPOINTS
    # =============================================================================
    # Modal Views
    path('history/<str:content_type>/<uuid:object_id>/modal/', modal_views.history_modal, name='history_modal'),
    path('confirm-action/modal/', modal_views.confirm_action_modal, name='confirm_action_modal'),
    path('students/<uuid:student_pk>/exam-history/modal/', modal_views.student_exam_history_modal, name='student_exam_history_modal'),
    path('students/<uuid:student_pk>/results-summary/modal/', modal_views.student_results_summary_modal, name='student_results_summary_modal'),
    path('examinations/<uuid:examination_pk>/statistics/modal/', modal_views.examination_statistics_modal, name='examination_statistics_modal'),

    # =============================================================================
    # AJAX ENDPOINTS (for dynamic form field loading)
    # =============================================================================
    path('ajax/get-grading-system-ranges/<uuid:system_pk>/', views.ajax_get_grading_system_ranges, name='ajax_get_grading_system_ranges'),
    path('ajax/get-examinations-for-session/<uuid:session_pk>/', views.ajax_get_examinations_for_session, name='ajax_get_examinations_for_session'),
    path('ajax/get-students-for-examination/<uuid:examination_pk>/', views.ajax_get_students_for_examination, name='ajax_get_students_for_examination'),
    path('ajax/calculate-grade/', views.ajax_calculate_grade, name='ajax_calculate_grade'),
    path('ajax/check-result-duplicate/', views.ajax_check_result_duplicate, name='ajax_check_result_duplicate'),
    path('ajax/get-exam-statistics/<uuid:examination_pk>/', views.ajax_get_exam_statistics, name='ajax_get_exam_statistics'),
    path('ajax/validate-grade-unlock/<uuid:result_pk>/', views.ajax_validate_grade_unlock, name='ajax_validate_grade_unlock'),
]