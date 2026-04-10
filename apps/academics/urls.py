# academics/urls.py

"""
URL Configuration for Academics Module

Architecture
------------
- List views handle BOTH full page loads AND HTMX search/filter requests.
- Modal views (modal_views.py) return lightweight HTML partials only.
- Action endpoints return HTMX response headers; no dedicated confirmation pages.
- All primary keys are UUIDs.
- Static path segments (create, print, export, bulk, ajax) always come BEFORE
  dynamic <uuid:pk> patterns to avoid shadowing.

URL name conventions
--------------------
  <entity>_list               → full list page
  <entity>_create             → create form page
  <entity>_detail             → detail page
  <entity>_edit               → edit form page
  <entity>_delete             → POST-only delete action
  <entity>_toggle_active      → POST-only toggle action
  <entity>_print_view         → filtered list print view (no pk)
  <entity>_print_detail       → single-object print view (with pk)
  export_<entity>_excel       → filtered list Excel export (no pk)
  <entity>_<action>_modal     → HTMX modal partial loader
"""

from django.urls import path
from . import views, modal_views

app_name = 'academics'

urlpatterns = [

    # =========================================================================
    # DASHBOARD
    # =========================================================================
    path('', views.academics_dashboard, name='dashboard'),

    # =========================================================================
    # ACADEMIC SESSIONS
    # =========================================================================

    path('sessions/', views.academic_session_list, name='session_list'),

    path('sessions/print/',        views.academic_session_print_view,    name='session_print_view'),
    path('sessions/export/excel/', views.export_academic_sessions_excel, name='export_sessions_excel'),
    path('sessions/create/',       views.academic_session_create,        name='session_create'),

    path('sessions/<uuid:pk>/',               views.academic_session_detail,        name='session_detail'),
    path('sessions/<uuid:pk>/edit/',          views.academic_session_edit,          name='session_edit'),
    path('sessions/<uuid:pk>/delete/',        views.academic_session_delete,        name='session_delete'),
    path('sessions/<uuid:pk>/close/',         views.academic_session_close,         name='session_close'),
    path('sessions/<uuid:pk>/reopen/',        views.academic_session_reopen,        name='session_reopen'),
    path('sessions/<uuid:pk>/set-current/',   views.academic_session_set_current,   name='session_set_current'),
    path('sessions/<uuid:pk>/toggle-active/', views.academic_session_toggle_active, name='session_toggle_active'),
    path('sessions/<uuid:pk>/print/',         views.academic_session_print_detail,  name='session_print_detail'),

    path('sessions/<uuid:session_pk>/modal/delete/',        modal_views.academic_session_delete_modal,        name='session_delete_modal'),
    path('sessions/<uuid:session_pk>/modal/close/',         modal_views.academic_session_close_modal,         name='session_close_modal'),
    path('sessions/<uuid:session_pk>/modal/reopen/',        modal_views.academic_session_reopen_modal,        name='session_reopen_modal'),
    path('sessions/<uuid:session_pk>/modal/set-current/',   modal_views.academic_session_set_current_modal,   name='session_set_current_modal'),
    path('sessions/<uuid:session_pk>/modal/toggle-active/', modal_views.academic_session_toggle_active_modal, name='session_toggle_active_modal'),
    path('sessions/<uuid:session_pk>/modal/quick-view/',    modal_views.academic_session_quick_view_modal,    name='session_quick_view_modal'),

    # =========================================================================
    # SUBJECTS
    # =========================================================================

    path('subjects/', views.subject_list, name='subject_list'),

    path('subjects/print/',        views.subject_print_view,    name='subject_print_view'),
    path('subjects/export/excel/', views.export_subjects_excel, name='export_subjects_excel'),
    path('subjects/create/',       views.subject_create,        name='subject_create'),

    path('subjects/<uuid:pk>/',               views.subject_detail,        name='subject_detail'),
    path('subjects/<uuid:pk>/edit/',          views.subject_edit,          name='subject_edit'),
    path('subjects/<uuid:pk>/delete/',        views.subject_delete,        name='subject_delete'),
    path('subjects/<uuid:pk>/toggle-active/', views.subject_toggle_active, name='subject_toggle_active'),
    path('subjects/<uuid:pk>/print/',         views.subject_print_detail,  name='subject_print_detail'),

    path('subjects/<uuid:subject_pk>/modal/delete/',        modal_views.subject_delete_modal,        name='subject_delete_modal'),
    path('subjects/<uuid:subject_pk>/modal/toggle-active/', modal_views.subject_toggle_active_modal, name='subject_toggle_active_modal'),
    path('subjects/<uuid:subject_pk>/modal/quick-view/',    modal_views.subject_quick_view_modal,    name='subject_quick_view_modal'),

    # =========================================================================
    # ACADEMIC LEVELS
    # =========================================================================

    path('levels/', views.academic_level_list, name='level_list'),

    path('levels/print/',        views.academic_level_print_view,    name='level_print_view'),
    path('levels/export/excel/', views.export_academic_levels_excel, name='export_levels_excel'),
    path('levels/create/',       views.academic_level_create,        name='level_create'),

    path('levels/<uuid:pk>/',               views.academic_level_detail,        name='level_detail'),
    path('levels/<uuid:pk>/classes/',       views.level_classes_partial,        name='level_classes_partial'),
    path('levels/<uuid:pk>/edit/',          views.academic_level_edit,          name='level_edit'),
    path('levels/<uuid:pk>/delete/',        views.academic_level_delete,        name='level_delete'),
    path('levels/<uuid:pk>/toggle-active/', views.academic_level_toggle_active, name='level_toggle_active'),
    path('levels/<uuid:pk>/print/',         views.academic_level_print_detail,  name='level_print_detail'),

    path('levels/<uuid:level_pk>/modal/delete/',        modal_views.academic_level_delete_modal,        name='level_delete_modal'),
    path('levels/<uuid:level_pk>/modal/toggle-active/', modal_views.academic_level_toggle_active_modal, name='level_toggle_active_modal'),
    path('levels/<uuid:level_pk>/modal/quick-view/',    modal_views.academic_level_quick_view_modal,    name='level_quick_view_modal'),

    # =========================================================================
    # CLASSROOMS
    # =========================================================================

    path('classrooms/', views.classroom_list, name='classroom_list'),

    path('classrooms/print/',        views.classroom_print_view,    name='classroom_print_view'),
    path('classrooms/export/excel/', views.export_classrooms_excel, name='export_classrooms_excel'),
    path('classrooms/create/',       views.classroom_create,        name='classroom_create'),

    path('classrooms/<uuid:pk>/',                 views.classroom_detail,          name='classroom_detail'),
    path('classrooms/<uuid:pk>/edit/',            views.classroom_edit,            name='classroom_edit'),
    path('classrooms/<uuid:pk>/delete/',          views.classroom_delete,          name='classroom_delete'),
    path('classrooms/<uuid:pk>/toggle-active/',   views.classroom_toggle_active,   name='classroom_toggle_active'),
    path('classrooms/<uuid:pk>/toggle-bookable/', views.classroom_toggle_bookable, name='classroom_toggle_bookable'),
    path('classrooms/<uuid:pk>/print/',           views.classroom_print_detail,    name='classroom_print_detail'),

    path('classrooms/<uuid:classroom_pk>/modal/delete/',          modal_views.classroom_delete_modal,          name='classroom_delete_modal'),
    path('classrooms/<uuid:classroom_pk>/modal/toggle-active/',   modal_views.classroom_toggle_active_modal,   name='classroom_toggle_active_modal'),
    path('classrooms/<uuid:classroom_pk>/modal/toggle-bookable/', modal_views.classroom_toggle_bookable_modal, name='classroom_toggle_bookable_modal'),
    path('classrooms/<uuid:classroom_pk>/modal/quick-view/',      modal_views.classroom_quick_view_modal,      name='classroom_quick_view_modal'),

    # =========================================================================
    # CLASSES
    # =========================================================================

    path('classes/print/',        views.class_print_view,     name='class_print_view'),
    path('classes/export/excel/', views.export_classes_excel, name='export_classes_excel'),
    path('classes/create/',       views.class_create,         name='class_create'),

    # Class create modal (static — must come before <uuid:class_pk>)
    path('classes/modal/create/', modal_views.class_create_modal, name='class_create_modal'),

    path('classes/<uuid:pk>/',                   views.class_detail,                           name='class_detail'),
    path('classes/<uuid:pk>/subjects/',          views.class_subjects_partial,                 name='class_subjects_partial'),
    path('classes/<uuid:pk>/enrollments/',       views.class_enrollments_partial,              name='class_enrollments_partial'),
    path('classes/<uuid:pk>/edit/',              views.class_edit,                             name='class_edit'),
    path('classes/<uuid:pk>/delete/',            views.class_delete,                           name='class_delete'),
    path('classes/<uuid:pk>/toggle-active/',     views.class_toggle_active,                    name='class_toggle_active'),
    path('classes/<uuid:pk>/assign-teacher/',    views.class_assign_teacher,                   name='class_assign_teacher'),
    path('classes/<uuid:pk>/assign-classroom/',  views.class_assign_classroom,                 name='class_assign_classroom'),
    path('classes/<uuid:pk>/print/',             views.class_print_detail,                     name='class_print_detail'),

    # ✅ NEW: Bulk invoice generation for a class
    path('classes/<uuid:pk>/generate-invoices/',        views.class_generate_missing_invoices,        name='class_generate_missing_invoices'),
    path('classes/<uuid:pk>/generate-invoices/modal/',  views.class_generate_missing_invoices_modal,  name='class_generate_missing_invoices_modal'),

    path('classes/<uuid:class_pk>/modal/fee-structure/',    modal_views.class_fee_structure_modal,    name='class_fee_structure_modal'),
    path('classes/<uuid:class_pk>/modal/edit/',             modal_views.class_edit_modal,             name='class_edit_modal'),
    path('classes/<uuid:class_pk>/modal/delete/',           modal_views.class_delete_modal,           name='class_delete_modal'),
    path('classes/<uuid:class_pk>/modal/toggle-active/',    modal_views.class_toggle_active_modal,    name='class_toggle_active_modal'),
    path('classes/<uuid:class_pk>/modal/assign-teacher/',   modal_views.class_assign_teacher_modal,   name='class_assign_teacher_modal'),
    path('classes/<uuid:class_pk>/modal/assign-classroom/', modal_views.class_assign_classroom_modal, name='class_assign_classroom_modal'),
    path('classes/<uuid:class_pk>/modal/quick-view/',       modal_views.class_quick_view_modal,       name='class_quick_view_modal'),
    path('classes/<uuid:class_pk>/modal/students/',         modal_views.class_students_modal,         name='class_students_modal'),

    # =========================================================================
    # CLASS SUBJECTS
    # =========================================================================

    # create & edit → views.py (save logic; modal templates hx-post here)
    path('class-subjects/create/',         views.class_subject_create, name='class_subject_create'),
    path('class-subjects/<uuid:pk>/edit/', views.class_subject_edit,   name='class_subject_edit'),

    # Modal triggers (GET-only; load the form partial for HTMX injection)
    path('class-subjects/modal/create/',                              modal_views.class_subject_create_modal, name='class_subject_create_modal'),
    path('class-subjects/<uuid:class_subject_pk>/modal/edit/',        modal_views.class_subject_edit_modal,   name='class_subject_edit_modal'),

    path('class-subjects/<uuid:pk>/',                views.class_subject_detail,         name='class_subject_detail'),
    path('class-subjects/<uuid:pk>/delete/',         views.class_subject_delete,         name='class_subject_delete'),
    path('class-subjects/<uuid:pk>/toggle-active/',  views.class_subject_toggle_active,  name='class_subject_toggle_active'),
    path('class-subjects/<uuid:pk>/assign-teacher/', views.class_subject_assign_teacher, name='class_subject_assign_teacher'),
    path('class-subjects/<uuid:pk>/print/',          views.class_subject_print_detail,   name='class_subject_print_detail'),

    path('class-subjects/<uuid:class_subject_pk>/modal/delete/',         modal_views.class_subject_delete_modal,         name='class_subject_delete_modal'),
    path('class-subjects/<uuid:class_subject_pk>/modal/toggle-active/',  modal_views.class_subject_toggle_active_modal,  name='class_subject_toggle_active_modal'),
    path('class-subjects/<uuid:class_subject_pk>/modal/assign-teacher/', modal_views.class_subject_assign_teacher_modal, name='class_subject_assign_teacher_modal'),
    path('class-subjects/<uuid:class_subject_pk>/modal/quick-view/',     modal_views.class_subject_quick_view_modal,     name='class_subject_quick_view_modal'),

    # =========================================================================
    # STUDENT ENROLLMENTS
    # =========================================================================

    # create → views.py (save logic; modal template hx-post here)
    path('enrollments/create/', views.enrollment_create, name='enrollment_create'),

    # Modal trigger (GET-only; load the form partial for HTMX injection)
    path('enrollments/modal/create/', modal_views.enrollment_create_modal, name='enrollment_create_modal'),

    # Bulk wizard (class-context; class_pk passed as param)
    path('enrollments/bulk/create/',  views.bulk_enrollment_create,         name='bulk_enrollment_create'),
    path('enrollments/bulk/step1/',   views.bulk_enrollment_create,         name='bulk_enrollment_step1'),
    path('enrollments/bulk/step2/',   views.bulk_enrollment_step2,          name='bulk_enrollment_step2'),
    path('enrollments/bulk/search/',  views.bulk_enrollment_student_search, name='bulk_enrollment_student_search'),

    # Context shortcut from class detail page
    path('classes/<uuid:class_pk>/enrollments/create/', views.enrollment_create, name='enrollment_create_for_class'),

    # Detail / CRUD
    path('enrollments/<uuid:pk>/',                views.enrollment_detail,         name='enrollment_detail'),
    path('enrollments/<uuid:pk>/edit/',           views.enrollment_edit,           name='enrollment_edit'),
    path('enrollments/<uuid:pk>/delete/',         views.enrollment_delete,         name='enrollment_delete'),
    path('enrollments/<uuid:pk>/toggle-active/',  views.enrollment_toggle_active,  name='enrollment_toggle_active'),
    path('enrollments/<uuid:pk>/create-invoice/', views.enrollment_create_invoice, name='enrollment_create_invoice'),
    path('enrollments/<uuid:pk>/print/',          views.enrollment_print_detail,   name='enrollment_print_detail'),

    # Modals
    path('enrollments/<uuid:enrollment_pk>/modal/delete/',         modal_views.enrollment_delete_modal,        name='enrollment_delete_modal'),
    path('enrollments/<uuid:enrollment_pk>/modal/edit/',           modal_views.enrollment_edit_modal,          name='enrollment_edit_modal'),
    path('enrollments/<uuid:enrollment_pk>/modal/toggle-active/',  modal_views.enrollment_toggle_active_modal, name='enrollment_toggle_active_modal'),
    path('enrollments/<uuid:enrollment_pk>/modal/quick-view/',     modal_views.enrollment_quick_view_modal,    name='enrollment_quick_view_modal'),

    path('enrollments/<uuid:enrollment_pk>/modal/create-invoice/', modal_views.enrollment_create_invoice_modal, name='enrollment_create_invoice_modal'),

    # =========================================================================
    # ACADEMIC PROGRESS
    # =========================================================================

    path('progress/', views.academic_progress_list, name='progress_list'),

    path('progress/print/',        views.academic_progress_list_print_view, name='progress_list_print_view'),
    path('progress/export/excel/', views.export_academic_progress_excel,    name='export_progress_excel'),
    path('progress/create/',       views.academic_progress_create,          name='progress_create'),

    path('progress/bulk/finalize/',       views.bulk_progress_finalize,             name='bulk_progress_finalize'),
    path('progress/bulk/calculate/',      views.bulk_progress_calculate,            name='bulk_progress_calculate'),
    path('progress/bulk/finalize/modal/', modal_views.bulk_progress_finalize_modal, name='bulk_progress_finalize_modal'),

    path('students/<uuid:student_pk>/progress/create/', views.academic_progress_create, name='progress_create_for_student'),

    path('progress/<uuid:pk>/',                  views.academic_progress_detail,           name='progress_detail'),
    path('progress/<uuid:pk>/edit/',             views.academic_progress_edit,             name='progress_edit'),
    path('progress/<uuid:pk>/delete/',           views.academic_progress_delete,           name='progress_delete'),
    path('progress/<uuid:pk>/finalize/',         views.academic_progress_finalize,         name='progress_finalize'),
    path('progress/<uuid:pk>/update-promotion/', views.academic_progress_update_promotion, name='progress_update_promotion'),
    path('progress/<uuid:pk>/print/',            views.academic_progress_print_detail,     name='progress_print_detail'),
    path('progress/<uuid:pk>/report-card/',      views.academic_progress_report_card,      name='progress_report_card'),

    path('progress/<uuid:progress_pk>/modal/delete/',     modal_views.academic_progress_delete_modal,    name='progress_delete_modal'),
    path('progress/<uuid:progress_pk>/modal/finalize/',   modal_views.academic_progress_finalize_modal,  name='progress_finalize_modal'),
    path('progress/<uuid:progress_pk>/modal/promotion/',  modal_views.academic_progress_promotion_modal, name='progress_promotion_modal'),
    path('progress/<uuid:progress_pk>/modal/quick-view/', modal_views.academic_progress_quick_view_modal, name='progress_quick_view_modal'),

    # =========================================================================
    # HOLIDAYS
    # =========================================================================

    path('holidays/', views.holiday_list, name='holiday_list'),

    path('holidays/print/',           views.holiday_print_view,      name='holiday_print_view'),
    path('holidays/export/excel/',    views.export_holidays_excel,    name='export_holidays_excel'),
    path('holidays/export/calendar/', views.export_holidays_calendar, name='export_holidays_calendar'),
    path('holidays/create/',          views.holiday_create,           name='holiday_create'),

    path('holidays/<uuid:pk>/',        views.holiday_detail,       name='holiday_detail'),
    path('holidays/<uuid:pk>/edit/',   views.holiday_edit,         name='holiday_edit'),
    path('holidays/<uuid:pk>/delete/', views.holiday_delete,       name='holiday_delete'),
    path('holidays/<uuid:pk>/print/',  views.holiday_print_detail, name='holiday_print_detail'),

    path('holidays/<uuid:holiday_pk>/modal/delete/',     modal_views.holiday_delete_modal,     name='holiday_delete_modal'),
    path('holidays/<uuid:holiday_pk>/modal/quick-view/', modal_views.holiday_quick_view_modal, name='holiday_quick_view_modal'),

    # =========================================================================
    # STUDENT PROMOTIONS
    # =========================================================================

    path('promotions/',        views.promotion_dashboard,   name='promotion_dashboard'),
    path('promotions/single/', views.promote_student,       name='promote_student'),
    path('promotions/bulk/',   views.bulk_promote_students, name='bulk_promote_students'),

    # =========================================================================
    # REPORTS
    # =========================================================================

    path('reports/session-summary/',              views.session_summary_report,    name='session_summary_report'),
    path('reports/class-roster/<uuid:class_pk>/', views.class_roster_report,       name='class_roster_report'),
    path('reports/teacher-assignment/',           views.teacher_assignment_report, name='teacher_assignment_report'),

    path('reports/session-summary/modal/',    modal_views.session_summary_report_modal,    name='session_summary_report_modal'),
    path('reports/attendance/modal/',         modal_views.attendance_report_modal,         name='attendance_report_modal'),
    path('reports/grade-distribution/modal/', modal_views.grade_distribution_report_modal, name='grade_distribution_report_modal'),
    path('reports/class-roster/modal/',       modal_views.class_roster_report_modal,       name='class_roster_report_modal'),
    path('reports/teacher-assignment/modal/', modal_views.teacher_assignment_report_modal, name='teacher_assignment_report_modal'),
    path('reports/promotion-analysis/modal/', modal_views.promotion_analysis_report_modal, name='promotion_analysis_report_modal'),

    # =========================================================================
    # ACADEMIC CALENDAR
    # =========================================================================

    path('calendar/',                        views.academic_calendar,           name='academic_calendar'),
    path('calendar/<int:year>/<int:month>/', views.academic_calendar,           name='academic_calendar_month'),
    path('calendar/events/modal/',           modal_views.calendar_events_modal, name='calendar_events_modal'),

    # =========================================================================
    # IMPORT / EXPORT MODALS
    # =========================================================================

    path('import/students/modal/',            modal_views.import_students_modal,    name='import_students_modal'),
    path('import/subjects/modal/',            modal_views.import_subjects_modal,    name='import_subjects_modal'),
    path('import/enrollments/modal/',         modal_views.import_enrollments_modal, name='import_enrollments_modal'),
    path('export/<str:resource_type>/modal/', modal_views.export_options_modal,     name='export_options_modal'),

    # =========================================================================
    # SETTINGS MODALS
    # =========================================================================

    path('settings/academic/modal/',        modal_views.academic_settings_modal, name='academic_settings_modal'),
    path('settings/grading-scale/modal/',   modal_views.grading_scale_modal,     name='grading_scale_modal'),
    path('settings/promotion-rules/modal/', modal_views.promotion_rules_modal,   name='promotion_rules_modal'),

    # =========================================================================
    # UTILITY MODALS
    # =========================================================================

    path('modal/confirm/', modal_views.confirm_action_modal, name='confirm_action_modal'),
    path('modal/history/', modal_views.history_modal,        name='history_modal'),

    path('students/<uuid:student_pk>/enrollment-history/modal/', modal_views.student_enrollment_history_modal, name='student_enrollment_history_modal'),
    path('teachers/<uuid:teacher_pk>/classes/modal/',            modal_views.teacher_classes_modal,            name='teacher_classes_modal'),

    # =========================================================================
    # AJAX ENDPOINTS
    # =========================================================================

    path('ajax/subjects-for-level/<uuid:level_pk>/',    views.ajax_get_subjects_for_level,     name='ajax_get_subjects_for_level'),
    path('ajax/classes-for-session/<uuid:session_pk>/', views.ajax_get_classes_for_session,    name='ajax_get_classes_for_session'),
    path('ajax/next-roll-number/<uuid:class_pk>/',      views.ajax_get_next_roll_number,       name='ajax_get_next_roll_number'),
    path('ajax/check-enrollment-duplicate/',             views.ajax_check_enrollment_duplicate, name='ajax_check_enrollment_duplicate'),
    path('ajax/class-subjects/<uuid:class_pk>/',         views.ajax_get_class_subjects,         name='ajax_get_class_subjects'),
]