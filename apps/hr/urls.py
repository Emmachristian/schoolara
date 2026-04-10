"""
hr/urls.py

URL Configuration for HR Module

Organisation
────────────
Each section mirrors the entity order in views.py:
  Dashboard → Departments → Designations → Staff → Contracts
  → Teachers → Attendance → Payroll → Salary History
  → Bulk Operations → Reports

Within each section:
  List  →  CRUD  →  Actions  →  Print/Export  →  Modals

Architecture
────────────
• List views handle BOTH full page loads AND HTMX requests.
• Form pages are full templates rendered by views.py (not modal views).
• modal_views.py is GET-only — confirmation dialogs and quick-views only.
• Action endpoints (delete, activate, etc.) are POST-only in views.py
  and return HTMX response headers.
• All object URLs use UUID primary keys.
"""

from django.urls import path
from . import views, modal_views

app_name = 'hr'

urlpatterns = [

    # =========================================================================
    # DASHBOARD
    # =========================================================================

    path('', views.hr_dashboard, name='hr_dashboard'),
    path('dashboard/', views.hr_dashboard, name='dashboard'),  # backwards compat alias


    # =========================================================================
    # DEPARTMENTS
    # =========================================================================

    # List
    path('departments/', views.department_list, name='department_list'),

    # CRUD
    path('departments/create/', views.department_create, name='department_create'),
    path('departments/<uuid:pk>/edit/', views.department_edit, name='department_edit'),

    # Actions (POST-only)
    path('departments/<uuid:pk>/delete/', views.department_delete, name='department_delete'),

    # Modals (GET-only)
    path('departments/<uuid:pk>/modal/delete/', modal_views.department_delete_modal, name='department_delete_modal'),
    path('departments/<uuid:pk>/modal/quick-view/', modal_views.department_quick_view_modal, name='department_quick_view_modal'),


    # =========================================================================
    # DESIGNATIONS
    # =========================================================================

    # List
    path('designations/', views.designation_list, name='designation_list'),

    # CRUD
    path('designations/create/', views.designation_create, name='designation_create'),
    path('designations/<uuid:pk>/', views.designation_detail, name='designation_detail'),
    path('designations/<uuid:pk>/edit/', views.designation_edit, name='designation_edit'),

    # Actions (POST-only)
    path('designations/<uuid:pk>/delete/', views.designation_delete, name='designation_delete'),

    # Modals (GET-only)
    path('designations/<uuid:pk>/modal/delete/', modal_views.designation_delete_modal, name='designation_delete_modal'),
    path('designations/<uuid:pk>/modal/quick-view/', modal_views.designation_quick_view_modal, name='designation_quick_view_modal'),


    # =========================================================================
    # STAFF
    # =========================================================================

    # List
    path('staff/', views.staff_list, name='staff_list'),

    # CRUD
    path('staff/create/', views.staff_create, name='staff_create'),
    path('staff/<uuid:pk>/edit/', views.staff_edit, name='staff_edit'),
    path('staff/<uuid:pk>/', views.staff_profile, name='staff_profile'),
    # Staff partials (HTMX tab content)
    path('staff/<uuid:pk>/partials/payrolls/', views.staff_payrolls_partial, name='staff_payrolls_partial'),
    path('staff/<uuid:pk>/partials/attendance/', views.staff_attendance_partial, name='staff_attendance_partial'),

    # Actions (POST-only)
    path('staff/<uuid:pk>/delete/', views.staff_delete, name='staff_delete'),
    path('staff/<uuid:pk>/activate/', views.staff_activate, name='staff_activate'),
    path('staff/<uuid:pk>/deactivate/', views.staff_deactivate, name='staff_deactivate'),

    # Print & Export
    path('staff/print/', views.staff_print_view, name='staff_print_view'),
    path('staff/export/excel/', views.export_staff_excel, name='export_staff_excel'),

    # Modals (GET-only)
    path('staff/<uuid:pk>/modal/delete/', modal_views.staff_delete_modal, name='staff_delete_modal'),
    path('staff/<uuid:pk>/modal/activate/', modal_views.staff_activate_modal, name='staff_activate_modal'),
    path('staff/<uuid:pk>/modal/deactivate/', modal_views.staff_deactivate_modal, name='staff_deactivate_modal'),
    path('staff/<uuid:pk>/modal/quick-view/', modal_views.staff_quick_view_modal, name='staff_quick_view_modal'),


    # =========================================================================
    # STAFF DESIGNATION ASSIGNMENTS  (staff context — no standalone list)
    # =========================================================================

    # CRUD
    path('staff/<uuid:staff_pk>/designations/assign/', views.staff_assign_designation, name='staff_assign_designation'),
    path('staff/designations/<uuid:pk>/edit/', views.staff_designation_edit, name='staff_designation_edit'),

    # Actions (POST-only)
    path('staff/designations/<uuid:pk>/delete/', views.staff_designation_delete, name='staff_designation_delete'),
    path('staff/designations/<uuid:pk>/activate/', views.staff_designation_activate, name='staff_designation_activate'),
    path('staff/designations/<uuid:pk>/deactivate/', views.staff_designation_deactivate, name='staff_designation_deactivate'),
    path('staff/designations/<uuid:pk>/set-primary/', views.staff_designation_set_primary, name='staff_designation_set_primary'),

    # Modals (GET-only)
    path('staff/<uuid:staff_pk>/designations/modal/assign/', modal_views.staff_assign_designation_modal, name='staff_assign_designation_modal'),
    path('staff/designations/<uuid:pk>/modal/edit/', modal_views.staff_designation_edit_modal, name='staff_designation_edit_modal'),
    path('staff/designations/<uuid:pk>/modal/delete/', modal_views.staff_designation_delete_modal, name='staff_designation_delete_modal'),
    path('staff/designations/<uuid:pk>/modal/activate/', modal_views.staff_designation_activate_modal, name='staff_designation_activate_modal'),
    path('staff/designations/<uuid:pk>/modal/deactivate/', modal_views.staff_designation_deactivate_modal, name='staff_designation_deactivate_modal'),
    path('staff/designations/<uuid:pk>/modal/set-primary/', modal_views.staff_designation_set_primary_modal, name='staff_designation_set_primary_modal'),


    # =========================================================================
    # CONTRACTS
    # =========================================================================

    # List
    path('contracts/', views.contract_list, name='contract_list'),

    # CRUD
    path('contracts/create/', views.contract_create, name='contract_create'),
    path('contracts/<uuid:pk>/', views.contract_detail, name='contract_detail'),
    path('contracts/<uuid:pk>/edit/', views.contract_edit, name='contract_edit'),

    # Actions (POST-only)
    path('contracts/<uuid:pk>/delete/', views.contract_delete, name='contract_delete'),
    path('contracts/<uuid:pk>/activate/', views.contract_activate, name='contract_activate'),
    path('contracts/<uuid:pk>/terminate/', views.contract_terminate, name='contract_terminate'),
    path('contracts/<uuid:pk>/renew/', views.contract_renew, name='contract_renew'),

    # Modals (GET-only)
    path('contracts/<uuid:pk>/modal/delete/', modal_views.contract_delete_modal, name='contract_delete_modal'),
    path('contracts/<uuid:pk>/modal/activate/', modal_views.contract_activate_modal, name='contract_activate_modal'),
    path('contracts/<uuid:pk>/modal/terminate/', modal_views.contract_terminate_modal, name='contract_terminate_modal'),
    path('contracts/<uuid:pk>/modal/renew/', modal_views.contract_renew_modal, name='contract_renew_modal'),
    path('contracts/<uuid:pk>/modal/quick-view/', modal_views.contract_quick_view_modal, name='contract_quick_view_modal'),


    # =========================================================================
    # TEACHERS
    # =========================================================================

    # List
    path('teachers/', views.teacher_list, name='teacher_list'),

    # CRUD
    path('teachers/<uuid:pk>/edit/', views.teacher_edit, name='teacher_edit'),

    # Actions (POST-only)
    path('teachers/<uuid:pk>/delete/', views.teacher_delete, name='teacher_delete'),
    path('teachers/<uuid:pk>/activate/', views.teacher_activate, name='teacher_activate'),
    path('teachers/<uuid:pk>/deactivate/', views.teacher_deactivate, name='teacher_deactivate'),

    # Modals (GET-only)
    path('teachers/<uuid:pk>/modal/edit/', modal_views.teacher_edit_modal, name='teacher_edit_modal'),
    path('teachers/<uuid:pk>/modal/delete/', modal_views.teacher_delete_modal, name='teacher_delete_modal'),
    path('teachers/<uuid:pk>/modal/activate/', modal_views.teacher_reactivate_modal, name='teacher_reactivate_modal'),
    path('teachers/<uuid:pk>/modal/deactivate/', modal_views.teacher_deactivate_modal, name='teacher_deactivate_modal'),
    path('teachers/<uuid:pk>/modal/quick-view/', modal_views.teacher_quick_view_modal, name='teacher_quick_view_modal'),


    # =========================================================================
    # ATTENDANCE
    # =========================================================================

    # List
    path('attendance/', views.attendance_list, name='attendance_list'),

    # CRUD
    path('attendance/create/', views.attendance_create, name='attendance_create'),
    path('attendance/<uuid:pk>/', views.attendance_detail, name='attendance_detail'),
    path('attendance/<uuid:pk>/edit/', views.attendance_edit, name='attendance_edit'),

    # Actions (POST-only)
    path('attendance/<uuid:pk>/delete/', views.attendance_delete, name='attendance_delete'),
    path('attendance/bulk-record/', views.bulk_attendance_record, name='bulk_attendance_record'),

    # Modals (GET-only)
    path('attendance/<uuid:pk>/modal/delete/', modal_views.attendance_delete_modal, name='attendance_delete_modal'),
    path('attendance/<uuid:pk>/modal/detail/', modal_views.attendance_detail_modal, name='attendance_detail_modal'),
    path('attendance/modal/bulk-record/', modal_views.bulk_attendance_modal, name='bulk_attendance_modal'),


    # =========================================================================
    # PAYROLL
    # =========================================================================

    # List
    path('payroll/', views.payroll_list, name='payroll_list'),

    # CRUD
    path('payroll/staff-defaults/', views.payroll_staff_defaults, name='payroll_staff_defaults'),
    path('payroll/create/', views.payroll_create, name='payroll_create'),
    path('payroll/<uuid:pk>/', views.payroll_detail, name='payroll_detail'),
    path('payroll/<uuid:pk>/edit/', views.payroll_edit, name='payroll_edit'),


    # Actions (POST-only)
    path('payroll/<uuid:pk>/delete/', views.payroll_delete, name='payroll_delete'),
    path('payroll/<uuid:pk>/approve/', views.payroll_approve, name='payroll_approve'),
    path('payrolls/<uuid:pk>/payments/', views.payroll_record_payment, name='payroll_record_payment'),
    path('payroll/<uuid:pk>/reverse/', views.payroll_reverse, name='payroll_reverse'),
    path('payroll/<uuid:pk>/recalculate/', views.payroll_recalculate, name='payroll_recalculate'),

    # Modals (GET-only)
    path('payroll/<uuid:pk>/modal/delete/', modal_views.payroll_delete_modal, name='payroll_delete_modal'),
    path('payroll/<uuid:pk>/modal/approve/', modal_views.payroll_approve_modal, name='payroll_approve_modal'),
    path('payroll/<uuid:pk>/modal/process-payment/', modal_views.payroll_process_payment_modal, name='payroll_process_payment_modal'),
    path('payrolls/<uuid:pk>/payments/modal/', modal_views.payroll_record_payment_modal, name='payroll_record_payment_modal'),
    path('payroll/<uuid:pk>/modal/reverse/', modal_views.payroll_reverse_modal, name='payroll_reverse_modal'),
    path('payroll/<uuid:pk>/modal/detail/', modal_views.payroll_detail_modal, name='payroll_detail_modal'),
    path('payroll/modal/bulk-generate/', modal_views.bulk_payroll_generation_modal, name='bulk_payroll_generation_modal'),


    # =========================================================================
    # SALARY HISTORY
    # =========================================================================

    # List
    path('salary-history/', views.salary_history_list, name='salary_history_list'),

    # CRUD
    path('salary-history/create/', views.salary_history_create, name='salary_history_create'),


    # =========================================================================
    # BULK OPERATIONS
    # =========================================================================

    # Actions (POST-only)
    path('staff/bulk-action/', views.bulk_staff_action, name='bulk_staff_action'),

    # Modals (GET-only)
    path('staff/modal/bulk-action/', modal_views.bulk_staff_action_modal, name='bulk_staff_action_modal'),


    # =========================================================================
    # REPORTS
    # =========================================================================

    path('reports/', views.hr_reports, name='hr_reports'),
    path('reports/staff/', views.staff_report, name='staff_report'),
    path('reports/contracts/', views.contract_report, name='contract_report'),
    path('reports/teachers/', views.teacher_report, name='teacher_report'),

]