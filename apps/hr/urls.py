# hr/urls.py
"""
URL Configuration for HR Module

Organized into two main sections:
1. Regular Views (views.py) - Full page loads, list views (with HTMX support), and actions
2. Modal Views (modal_views.py) - HTMX modal content loaders (ACTION/CONFIRMATION modals only)

Key Architecture:
- List views handle BOTH full page loads AND HTMX requests
- Form templates are rendered directly (NOT through modal views)
- Modal views ONLY for confirmations/actions (delete, activate, deactivate, etc.)
- Action endpoints return HTMX responses with custom headers
- All URLs use UUID primary keys for security

Note: Form modals (create/edit) are NOT handled via modal_views - they use dedicated templates
"""

from django.urls import path
from . import views, modal_views

app_name = 'hr'

urlpatterns = [
    # =============================================================================
    # DASHBOARD
    # =============================================================================
    path('', views.hr_dashboard, name='hr_dashboard'),  # ⭐ CHANGED: Added 'hr_' prefix for consistency
    path('dashboard/', views.hr_dashboard, name='dashboard'),  # Keep old URL for backwards compatibility
    
    # =============================================================================
    # STAFF
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('staff/', views.staff_list, name='staff_list'),
    
    # CRUD Views
    path('staff/create/', views.staff_create, name='staff_create'),  # Wizard view
    path('staff/<uuid:pk>/', views.staff_profile, name='staff_profile'),
    path('staff/<uuid:pk>/edit/', views.staff_edit, name='staff_edit'),
    
    # Action Views
    path('staff/<uuid:pk>/delete/', views.staff_delete, name='staff_delete'),
    path('staff/<uuid:pk>/activate/', views.staff_activate, name='staff_activate'),
    path('staff/<uuid:pk>/deactivate/', views.staff_deactivate, name='staff_deactivate'),
    
    # Print & Export
    path('staff/print/', views.staff_print_view, name='staff_print_view'),
    path('staff/export/excel/', views.export_staff_excel, name='export_staff_excel'),
    
    # Modal Views (confirmation/action modals ONLY - no forms)
    path('staff/<uuid:pk>/modal/delete/', modal_views.staff_delete_modal, name='staff_delete_modal'),
    path('staff/<uuid:pk>/modal/activate/', modal_views.staff_activate_modal, name='staff_activate_modal'),
    path('staff/<uuid:pk>/modal/deactivate/', modal_views.staff_deactivate_modal, name='staff_deactivate_modal'),
    
    # =============================================================================
    # DEPARTMENTS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('departments/', views.department_list, name='department_list'),
    
    # CRUD Views
    path('departments/create/', views.department_create, name='department_create'),
    path('departments/<uuid:pk>/edit/', views.department_edit, name='department_edit'),
    
    # Action Views
    path('departments/<uuid:pk>/delete/', views.department_delete, name='department_delete'),
    
    # Modal Views (confirmation/action modals ONLY - no forms)
    path('departments/<uuid:pk>/modal/delete/', modal_views.department_delete_modal, name='department_delete_modal'),
    
    # =============================================================================
    # DESIGNATIONS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('designations/', views.designation_list, name='designation_list'),
    
    # CRUD Views
    path('designations/create/', views.designation_create, name='designation_create'),
    path('designations/<uuid:pk>/', views.designation_detail, name='designation_detail'),
    path('designations/<uuid:pk>/edit/', views.designation_edit, name='designation_edit'),
    
    # Action Views
    path('designations/<uuid:pk>/delete/', views.designation_delete, name='designation_delete'),
    
    # Modal Views (confirmation/action modals ONLY - no forms)
    path('designations/<uuid:pk>/modal/delete/', modal_views.designation_delete_modal, name='designation_delete_modal'),
    
    # =============================================================================
    # CONTRACTS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('contracts/', views.contract_list, name='contract_list'),
    
    # CRUD Views
    path('contracts/create/', views.contract_create, name='contract_create'),
    path('contracts/<uuid:pk>/', views.contract_detail, name='contract_detail'),
    path('contracts/<uuid:pk>/edit/', views.contract_edit, name='contract_edit'),
    
    # Action Views
    path('contracts/<uuid:pk>/delete/', views.contract_delete, name='contract_delete'),
    path('contracts/<uuid:pk>/activate/', views.contract_activate, name='contract_activate'),
    path('contracts/<uuid:pk>/terminate/', views.contract_terminate, name='contract_terminate'),
    path('contracts/<uuid:pk>/renew/', views.contract_renew, name='contract_renew'),
    
    # Modal Views (confirmation/action modals ONLY - no forms)
    path('contracts/<uuid:pk>/modal/delete/', modal_views.contract_delete_modal, name='contract_delete_modal'),
    path('contracts/<uuid:pk>/modal/activate/', modal_views.contract_activate_modal, name='contract_activate_modal'),
    path('contracts/<uuid:pk>/modal/terminate/', modal_views.contract_terminate_modal, name='contract_terminate_modal'),
    path('contracts/<uuid:pk>/modal/renew/', modal_views.contract_renew_modal, name='contract_renew_modal'),
    
    # =============================================================================
    # STAFF DESIGNATIONS (Assignment of designations to staff)
    # =============================================================================
    # CRUD Views
    path('staff/<uuid:staff_pk>/designations/assign/', views.staff_assign_designation, name='staff_assign_designation'),
    path('staff/designations/<uuid:pk>/edit/', views.staff_designation_edit, name='staff_designation_edit'),
    
    # Action Views
    path('staff/designations/<uuid:pk>/delete/', views.staff_designation_delete, name='staff_designation_delete'),
    path('staff/designations/<uuid:pk>/deactivate/', views.staff_designation_deactivate, name='staff_designation_deactivate'),
    path('staff/designations/<uuid:pk>/activate/', views.staff_designation_activate, name='staff_designation_activate'),
    path('staff/designations/<uuid:pk>/set-primary/', views.staff_designation_set_primary, name='staff_designation_set_primary'),
    
    # Modal Views (confirmation/action modals ONLY - no forms)
    path('staff/designations/<uuid:pk>/modal/delete/', modal_views.staff_designation_delete_modal, name='staff_designation_delete_modal'),
    path('staff/designations/<uuid:pk>/modal/deactivate/', modal_views.staff_designation_deactivate_modal, name='staff_designation_deactivate_modal'),
    path('staff/designations/<uuid:pk>/modal/activate/', modal_views.staff_designation_activate_modal, name='staff_designation_activate_modal'),
    path('staff/designations/<uuid:pk>/modal/set-primary/', modal_views.staff_designation_set_primary_modal, name='staff_designation_set_primary_modal'),
    
    # =============================================================================
    # TEACHERS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('teachers/', views.teacher_list, name='teacher_list'),
 
    # CRUD Views
    path('teachers/create/', views.teacher_create, name='teacher_create'),
    path('teachers/<uuid:pk>/', views.teacher_profile, name='teacher_profile'),
    path('teachers/<uuid:pk>/edit/', views.teacher_edit, name='teacher_edit'),
 
    # Action Views
    path('teachers/<uuid:pk>/delete/', views.teacher_delete, name='teacher_delete'),
    path('teachers/<uuid:pk>/reactivate/', views.teacher_reactivate, name='teacher_reactivate'),
    path('teachers/<uuid:pk>/deactivate/', views.teacher_deactivate, name='teacher_deactivate'),
 
    # Print & Export
    path('teachers/print/', views.teacher_print_view, name='teacher_print_view'),
    path('teachers/export/excel/', views.export_teachers_excel, name='export_teachers_excel'),
 
    # Modal Views (confirmation/action modals ONLY - no forms)
    path('teachers/<uuid:pk>/modal/delete/', modal_views.teacher_delete_modal, name='teacher_delete_modal'),
    path('teachers/<uuid:pk>/modal/reactivate/', modal_views.teacher_reactivate_modal, name='teacher_reactivate_modal'),
    path('teachers/<uuid:pk>/modal/deactivate/', modal_views.teacher_deactivate_modal, name='teacher_deactivate_modal'),
 
    
    # =============================================================================
    # ATTENDANCE
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('attendance/', views.attendance_list, name='attendance_list'),
    
    # CRUD Views
    path('attendance/create/', views.attendance_create, name='attendance_create'),
    path('attendance/<uuid:pk>/', views.attendance_detail, name='attendance_detail'),
    path('attendance/<uuid:pk>/edit/', views.attendance_edit, name='attendance_edit'),
    
    # Action Views
    path('attendance/<uuid:pk>/delete/', views.attendance_delete, name='attendance_delete'),
    
    # Modal Views (confirmation/action modals ONLY - no forms)
    path('attendance/<uuid:pk>/modal/delete/', modal_views.attendance_delete_modal, name='attendance_delete_modal'),
    path('attendance/<uuid:pk>/modal/detail/', modal_views.attendance_detail_modal, name='attendance_detail_modal'),
    
    # =============================================================================
    # PAYROLL
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('payroll/', views.payroll_list, name='payroll_list'),
    
    # CRUD Views
    path('payroll/create/', views.payroll_create, name='payroll_create'),
    path('payroll/<uuid:pk>/', views.payroll_detail, name='payroll_detail'),
    path('payroll/<uuid:pk>/edit/', views.payroll_edit, name='payroll_edit'),
    
    # Action Views
    path('payroll/<uuid:pk>/delete/', views.payroll_delete, name='payroll_delete'),
    path('payroll/<uuid:pk>/approve/', views.payroll_approve, name='payroll_approve'),
    path('payroll/<uuid:pk>/process-payment/', views.payroll_process_payment, name='payroll_process_payment'),
    path('payroll/<uuid:pk>/reverse/', views.payroll_reverse, name='payroll_reverse'),  # ⭐ NEW: Reversal action
    
    # Modal Views (confirmation/action modals ONLY - no forms)
    path('payroll/<uuid:pk>/modal/delete/', modal_views.payroll_delete_modal, name='payroll_delete_modal'),
    path('payroll/<uuid:pk>/modal/approve/', modal_views.payroll_approve_modal, name='payroll_approve_modal'),
    path('payroll/<uuid:pk>/modal/process-payment/', modal_views.payroll_process_payment_modal, name='payroll_process_payment_modal'),
    path('payroll/<uuid:pk>/modal/reverse/', modal_views.payroll_reverse_modal, name='payroll_reverse_modal'),  # ⭐ NEW: Reversal modal
    path('payroll/<uuid:pk>/modal/detail/', modal_views.payroll_detail_modal, name='payroll_detail_modal'),
    
    # =============================================================================
    # SALARY HISTORY
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('salary-history/', views.salary_history_list, name='salary_history_list'),
    
    # CRUD Views
    path('salary-history/create/', views.salary_history_create, name='salary_history_create'),
    
    # =============================================================================
    # BULK OPERATIONS
    # =============================================================================
    # Action Views
    path('staff/bulk-action/', views.bulk_staff_action, name='bulk_staff_action'),
    path('attendance/bulk-record/', views.bulk_attendance_record, name='bulk_attendance_record'),
    path('payroll/bulk-generate/', views.payroll_bulk_create, name='bulk_payroll_generation'),
    
    # Modal Views (confirmation/action modals ONLY)
    path('staff/modal/bulk-action/', modal_views.bulk_staff_action_modal, name='bulk_staff_action_modal'),
    path('attendance/modal/bulk-record/', modal_views.bulk_attendance_modal, name='bulk_attendance_modal'),
    path('payroll/modal/bulk-generate/', modal_views.bulk_payroll_generation_modal, name='bulk_payroll_generation_modal'),
    
    # =============================================================================
    # REPORTS
    # =============================================================================
    path('reports/', views.hr_reports, name='hr_reports'),
    path('reports/staff/', views.staff_report, name='staff_report'),
    path('reports/contracts/', views.contract_report, name='contract_report'),
    path('reports/teachers/', views.teacher_report, name='teacher_report'),
]