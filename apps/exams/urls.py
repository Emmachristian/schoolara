"""
exams/urls.py

URL configuration for the exams module.

Architecture:
  Regular views  (views.py)       — full page loads, HTMX partials, action endpoints
  Modal views    (modal_views.py) — HTMX partial content for modal containers

Results flow (2 pages + 1 modal):
  results/                  → results_by_class  (pick session + class)
  results/<class_pk>/       → class_marks       (category tabs + read-only grid)
  student_marks_edit_modal  → score entry per-student, per-category

Report cards:
  report-card/<student_pk>/          → student_report_card  (single student)
  report-cards/class/<class_pk>/     → class_report_cards   (bulk, one card per student)

Ordering convention within each section:
  1. Static-segment paths (list, create, bulk, print, export) — alphabetical where practical
  2. Dynamic <uuid:pk> paths (detail, edit, delete, toggle, …)
  3. Modal paths for that section
"""

from django.urls import path

from . import modal_views, views

app_name = 'exams'

urlpatterns = [

    # =========================================================================
    # DASHBOARD
    # =========================================================================
    path('', views.exams_dashboard, name='dashboard'),

    # =========================================================================
    # EXAM CATEGORIES
    # =========================================================================

    # Static
    path('categories/',                  views.exam_category_list,           name='category_list'),
    path('categories/create/',           views.exam_category_create,         name='category_create'),
    path('categories/print/',            views.exam_category_print_list,     name='categories_print_list'),
    path('categories/export/excel/',     views.export_exam_categories_excel, name='export_categories_excel'),

    # Dynamic
    path('categories/<uuid:pk>/',               views.exam_category_detail,        name='category_detail'),
    path('categories/<uuid:pk>/edit/',          views.exam_category_edit,          name='category_edit'),
    path('categories/<uuid:pk>/delete/',        views.exam_category_delete,        name='category_delete'),
    path('categories/<uuid:pk>/toggle-active/', views.exam_category_toggle_active, name='category_toggle_active'),
    path('categories/<uuid:pk>/examinations/',  views.category_examinations_partial, name='category_examinations_partial'),

    # Modals
    path('categories/<uuid:pk>/modal/delete/',        modal_views.exam_category_delete_modal,        name='category_delete_modal'),
    path('categories/<uuid:pk>/modal/toggle-active/', modal_views.exam_category_toggle_active_modal, name='category_toggle_active_modal'),
    path('categories/<uuid:pk>/modal/quick-view/',    modal_views.exam_category_quick_view_modal,    name='category_quick_view_modal'),

    # =========================================================================
    # GRADING SYSTEMS
    # =========================================================================

    # Static
    path('grading-systems/',              views.grading_system_list,          name='grading_system_list'),
    path('grading-systems/create/',       views.grading_system_create,        name='grading_system_create'),
    path('grading-systems/print/',        views.grading_system_print_list,    name='grading_systems_print_list'),
    path('grading-systems/export/excel/', views.export_grading_systems_excel, name='export_grading_systems_excel'),

    # Dynamic
    path('grading-systems/<uuid:pk>/',               views.grading_system_detail,        name='grading_system_detail'),
    path('grading-systems/<uuid:pk>/edit/',          views.grading_system_edit,          name='grading_system_edit'),
    path('grading-systems/<uuid:pk>/delete/',        views.grading_system_delete,        name='grading_system_delete'),
    path('grading-systems/<uuid:pk>/toggle-active/', views.grading_system_toggle_active, name='grading_system_toggle_active'),
    path('grading-systems/<uuid:pk>/set-default/',   views.grading_system_set_default,   name='grading_system_set_default'),

    # Modals
    path('grading-systems/<uuid:pk>/modal/delete/',        modal_views.grading_system_delete_modal,        name='grading_system_delete_modal'),
    path('grading-systems/<uuid:pk>/modal/toggle-active/', modal_views.grading_system_toggle_active_modal, name='grading_system_toggle_active_modal'),
    path('grading-systems/<uuid:pk>/modal/set-default/',   modal_views.grading_system_set_default_modal,   name='grading_system_set_default_modal'),
    path('grading-systems/<uuid:pk>/modal/quick-view/',    modal_views.grading_system_quick_view_modal,    name='grading_system_quick_view_modal'),

    # =========================================================================
    # GRADING RANGES  (CRUD managed via the GradingSystem formset — modal only)
    # =========================================================================
    path('grading-ranges/<uuid:pk>/modal/delete/',     modal_views.grading_range_delete_modal,     name='grading_range_delete_modal'),
    path('grading-ranges/<uuid:pk>/modal/quick-view/', modal_views.grading_range_quick_view_modal, name='grading_range_quick_view_modal'),

    # =========================================================================
    # CLASS GRADING SYSTEM ASSIGNMENTS
    # =========================================================================

    # Static
    path('class-grading-systems/',              views.class_grading_system_list,          name='class_grading_system_list'),
    path('class-grading-systems/create/',       views.class_grading_system_create,        name='class_grading_system_create'),
    path('class-grading-systems/bulk/assign/',  views.bulk_class_grading_system_assign,   name='bulk_class_grading_system_assign'),
    path('class-grading-systems/print/',        views.class_grading_system_print_list,    name='class_grading_systems_print_list'),
    path('class-grading-systems/export/excel/', views.export_class_grading_systems_excel, name='export_class_grading_systems_excel'),

    # Shortcut: create assignment scoped to a specific class
    path('classes/<uuid:class_pk>/grading-systems/create/', views.class_grading_system_create, name='class_grading_system_create_for_class'),

    # Dynamic
    path('class-grading-systems/<uuid:pk>/',               views.class_grading_system_detail,        name='class_grading_system_detail'),
    path('class-grading-systems/<uuid:pk>/edit/',          views.class_grading_system_edit,          name='class_grading_system_edit'),
    path('class-grading-systems/<uuid:pk>/delete/',        views.class_grading_system_delete,        name='class_grading_system_delete'),
    path('class-grading-systems/<uuid:pk>/toggle-active/', views.class_grading_system_toggle_active, name='class_grading_system_toggle_active'),

    # Modals
    path('class-grading-systems/<uuid:pk>/modal/delete/',        modal_views.class_grading_system_delete_modal,        name='class_grading_system_delete_modal'),
    path('class-grading-systems/<uuid:pk>/modal/toggle-active/', modal_views.class_grading_system_toggle_active_modal, name='class_grading_system_toggle_active_modal'),
    path('class-grading-systems/<uuid:pk>/modal/quick-view/',    modal_views.class_grading_system_quick_view_modal,    name='class_grading_system_quick_view_modal'),
    path('class-grading-systems/bulk/assign/modal/',             modal_views.bulk_class_grading_system_assign_modal,   name='bulk_class_grading_system_assign_modal'),

    # =========================================================================
    # EXAMINATIONS
    # =========================================================================

    # Static
    path('examinations/',              views.examination_list,          name='examination_list'),
    path('examinations/create/',       views.examination_create,        name='examination_create'),
    path('examinations/print/',        views.examination_print_list,    name='examinations_print_list'),
    path('examinations/export/excel/', views.export_examinations_excel, name='export_examinations_excel'),

    # Dynamic
    path('examinations/<uuid:pk>/',               views.examination_detail,        name='examination_detail'),
    path('examinations/<uuid:pk>/edit/',          views.examination_edit,          name='examination_edit'),
    path('examinations/<uuid:pk>/delete/',        views.examination_delete,        name='examination_delete'),
    path('examinations/<uuid:pk>/update-status/', views.examination_update_status, name='examination_update_status'),
    path('examinations/<uuid:pk>/publish/',       views.publish_results,           name='publish_results'),
    path('examinations/<uuid:pk>/unpublish/',     views.unpublish_results,         name='unpublish_results'),

    # Modals
    path('examinations/<uuid:pk>/modal/delete/',        modal_views.examination_delete_modal,            name='examination_delete_modal'),
    path('examinations/<uuid:pk>/modal/update-status/', modal_views.examination_update_status_modal,     name='examination_update_status_modal'),
    path('examinations/<uuid:pk>/modal/publish/',       modal_views.examination_publish_results_modal,   name='examination_publish_results_modal'),
    path('examinations/<uuid:pk>/modal/unpublish/',     modal_views.examination_unpublish_results_modal, name='examination_unpublish_results_modal'),
    path('examinations/<uuid:pk>/modal/quick-view/',    modal_views.examination_quick_view_modal,        name='examination_quick_view_modal'),
    path('examinations/<uuid:pk>/modal/statistics/',    modal_views.examination_statistics_modal,        name='examination_statistics_modal'),

    # =========================================================================
    # RESULTS  —  2-page flow
    # =========================================================================

    # Page 1: pick session + class
    path('results/', views.results_by_class, name='results_by_class'),

    # Page 2: category tabs + read-only marks grid
    # HTMX tab swap sends ?tab=<abbr> — same view returns a partial template
    path('results/<uuid:class_pk>/', views.class_marks, name='class_marks'),

    # Scoped print and export (session/category controlled via query params)
    path('results/<uuid:class_pk>/print/',        views.class_results_print_view,   name='class_results_print_view'),
    path('results/<uuid:class_pk>/export/excel/', views.export_class_results_excel, name='export_class_results_excel'),

    # Individual result — accessed from the grid or a report-card link
    path('results/<uuid:pk>/detail/',  views.result_detail, name='result_detail'),
    path('results/<uuid:pk>/lock/',    views.lock_grade,    name='lock_grade'),
    path('results/<uuid:pk>/unlock/',  views.unlock_grade,  name='unlock_grade'),

    # Result modals (opened from result_detail or a grid cell)
    path('results/<uuid:pk>/modal/delete/',        modal_views.student_result_delete_modal,     name='result_delete_modal'),
    path('results/<uuid:pk>/modal/lock/',          modal_views.lock_grade_modal,                name='lock_grade_modal'),
    path('results/<uuid:pk>/modal/unlock/',        modal_views.unlock_grade_modal,              name='unlock_grade_modal'),
    path('results/<uuid:pk>/modal/grade-history/', modal_views.grade_history_modal,             name='grade_history_modal'),
    path('results/<uuid:pk>/modal/quick-view/',    modal_views.student_result_quick_view_modal, name='result_quick_view_modal'),

    # Per-student score-entry modal (opened from each cell in the class_marks grid)
    path(
        'results/<uuid:class_pk>/category/<uuid:category_pk>/student/<uuid:student_pk>/marks/modal/',
        modal_views.student_marks_edit_modal,
        name='student_marks_edit_modal',
    ),

    # =========================================================================
    # REPORT CARDS
    # =========================================================================

    # Single student — ?session=<pk> and ?class=<pk> are optional overrides
    path('report-card/<uuid:student_pk>/', views.student_report_card, name='student_report_card'),

    # Bulk — one card per student in the class — ?session=<pk> optional override
    path('report-cards/class/<uuid:class_pk>/', views.class_report_cards, name='class_report_cards'),
    # Eligibility list — printable, opened from marks grid
    path('report-cards/class/<uuid:class_pk>/eligibility/', views.report_card_eligibility, name='report_card_eligibility'),

    # =========================================================================
    # REPORTS  (scoped to a specific examination — no global result list)
    # =========================================================================
    path('reports/grade-sheet/<uuid:examination_pk>/', views.grade_sheet_report, name='grade_sheet_report'),
    path('reports/mark-sheet/<uuid:examination_pk>/',  views.mark_sheet_report,  name='mark_sheet_report'),
    path('reports/rank-list/<uuid:examination_pk>/',   views.rank_list_report,   name='rank_list_report'),
    path('reports/merit-list/<uuid:examination_pk>/',  views.merit_list_report,  name='merit_list_report'),

    # Modals
    path('reports/grade-sheet/modal/', modal_views.grade_sheet_report_modal, name='grade_sheet_report_modal'),
    path('reports/mark-sheet/modal/',  modal_views.mark_sheet_report_modal,  name='mark_sheet_report_modal'),
    path('reports/rank-list/modal/',   modal_views.rank_list_report_modal,   name='rank_list_report_modal'),
    path('reports/merit-list/modal/',  modal_views.merit_list_report_modal,  name='merit_list_report_modal'),

    # =========================================================================
    # TIMETABLE
    # =========================================================================
    path('timetable/',                         views.exam_timetable,         name='exam_timetable'),
    path('timetable/<uuid:session_pk>/',        views.exam_timetable_session, name='exam_timetable_session'),
    path('timetable/<uuid:session_pk>/print/',  views.exam_timetable_print,   name='exam_timetable_print'),

    # Modals
    path('timetable/generate/modal/',           modal_views.generate_timetable_modal, name='generate_timetable_modal'),
    path('timetable/<uuid:session_pk>/modal/',  modal_views.exam_timetable_modal,     name='exam_timetable_modal'),

    # =========================================================================
    # IMPORT / EXPORT
    # =========================================================================
    path('templates/download/results/',      views.download_results_template,      name='download_results_template'),
    path('templates/download/examinations/', views.download_examinations_template, name='download_examinations_template'),

    # Modals
    path('import/results/modal/',      modal_views.import_results_modal,      name='import_results_modal'),
    path('import/examinations/modal/', modal_views.import_examinations_modal, name='import_examinations_modal'),
    path('export/<str:resource_type>/options/modal/', modal_views.export_options_modal, name='export_options_modal'),

    # =========================================================================
    # SETTINGS
    # =========================================================================
    path('settings/',               views.exam_settings,          name='exam_settings'),
    path('settings/grade-locking/', views.grade_locking_settings, name='grade_locking_settings'),

    # Modals
    path('settings/exam/modal/',          modal_views.exam_settings_modal,          name='exam_settings_modal'),
    path('settings/grading-scale/modal/', modal_views.grading_scale_settings_modal, name='grading_scale_settings_modal'),
    path('settings/grade-locking/modal/', modal_views.grade_locking_settings_modal, name='grade_locking_settings_modal'),

    # =========================================================================
    # STUDENT HISTORY MODALS  (opened from student profile or result_detail)
    # =========================================================================
    path('students/<uuid:student_pk>/exam-history/modal/',    modal_views.student_exam_history_modal,    name='student_exam_history_modal'),
    path('students/<uuid:student_pk>/results-summary/modal/', modal_views.student_results_summary_modal, name='student_results_summary_modal'),

    # =========================================================================
    # UTILITY MODALS
    # =========================================================================
    path('history/<str:content_type>/<uuid:object_id>/modal/', modal_views.history_modal,       name='history_modal'),
    path('confirm-action/modal/',                              modal_views.confirm_action_modal, name='confirm_action_modal'),

    # =========================================================================
    # AJAX ENDPOINTS
    # =========================================================================
    path('ajax/grading-system-ranges/<uuid:system_pk>/',     views.ajax_get_grading_system_ranges,    name='ajax_get_grading_system_ranges'),
    path('ajax/examinations-for-session/<uuid:session_pk>/', views.ajax_get_examinations_for_session, name='ajax_get_examinations_for_session'),
    path('ajax/calculate-grade/',                            views.ajax_calculate_grade,              name='ajax_calculate_grade'),
    path('ajax/exam-statistics/<uuid:examination_pk>/',      views.ajax_get_exam_statistics,          name='ajax_get_exam_statistics'),
    path('ajax/validate-grade-unlock/<uuid:result_pk>/',     views.ajax_validate_grade_unlock,        name='ajax_validate_grade_unlock'),
]