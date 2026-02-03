"""
URL Configuration for Finance Module
Organized into two main sections:

1. Regular Views (views.py) - Full page loads, list views (with HTMX support), and actions
2. Modal Views (modal_views.py) - HTMX modal content loaders

Key Architecture:
- List views handle BOTH full page loads AND HTMX requests
- Unified modals for create/edit operations (same modal, different mode)
- Action endpoints return HTMX responses with custom headers
- All URLs use UUID primary keys

Modal Pattern:
- GET /resource/add/modal/ → Load create modal
- GET /resource/<uuid:pk>/edit/modal/ → Load edit modal
- POST /resource/save/ → Create new resource
- POST /resource/<uuid:pk>/save/ → Update existing resource

Following the same pattern as loans module for consistency
"""

from django.urls import path
from . import views, modal_views

app_name = 'finance'

urlpatterns = [
    # =============================================================================
    # DASHBOARD
    # =============================================================================
    path('', views.finance_dashboard, name='dashboard'),

    # =============================================================================
    # ACCOUNT TYPES
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('account-types/', views.account_type_list, name='account_type_list'),

    # CRUD Views
    path('account-types/create/', views.account_type_create, name='account_type_create'),
    path('account-types/<uuid:pk>/', views.account_type_detail, name='account_type_detail'),
    path('account-types/<uuid:pk>/edit/', views.account_type_edit, name='account_type_edit'),

    # Action Views
    path('account-types/<uuid:pk>/delete/', views.account_type_delete, name='account_type_delete'),

    # Modal Views
    path('account-types/<uuid:pk>/modal/delete/', modal_views.account_type_delete_modal, name='account_type_delete_modal'),

    # =============================================================================
    # ACCOUNTS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('accounts/', views.account_list, name='account_list'),

    # CRUD Views
    path('accounts/create/', views.account_create, name='account_create'),
    path('accounts/<uuid:pk>/', views.account_detail, name='account_detail'),
    path('accounts/<uuid:pk>/edit/', views.account_edit, name='account_edit'),

    # Action Views
    path('accounts/<uuid:pk>/delete/', views.account_delete, name='account_delete'),
    path('accounts/<uuid:pk>/toggle-active/', views.account_toggle_active, name='account_toggle_active'),
    path('accounts/<uuid:pk>/reconcile/', views.account_reconcile, name='account_reconcile'),

    # Print & Export
    path('accounts/<uuid:pk>/print/', views.account_print_view, name='account_print_view'),
    path('accounts/export/excel/', views.export_accounts_excel, name='export_accounts_excel'),

    # Modal Views
    path('accounts/add/modal/', modal_views.account_form_modal, name='account_add_modal'),
    path('accounts/<uuid:pk>/edit/modal/', modal_views.account_form_modal, name='account_edit_modal'),
    path('accounts/quick-add/modal/', modal_views.account_quick_add_modal, name='account_quick_add_modal'),
    path('accounts/<uuid:pk>/modal/delete/', modal_views.account_delete_modal, name='account_delete_modal'),
    path('accounts/<uuid:pk>/modal/toggle-active/', modal_views.account_toggle_active_modal, name='account_toggle_active_modal'),
    path('accounts/<uuid:pk>/modal/quick-view/', modal_views.account_quick_view_modal, name='account_quick_view_modal'),
    path('accounts/<uuid:pk>/modal/reconcile/', modal_views.account_reconciliation_modal, name='account_reconciliation_modal'),
    path('accounts/<uuid:pk>/modal/move/', modal_views.account_move_modal, name='account_move_modal'),

    # =============================================================================
    # EXPENSE CATEGORIES
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('expense-categories/', views.expense_category_list, name='expense_category_list'),

    # CRUD Views
    path('expense-categories/create/', views.expense_category_create, name='expense_category_create'),
    path('expense-categories/<uuid:pk>/', views.expense_category_detail, name='expense_category_detail'),
    path('expense-categories/<uuid:pk>/edit/', views.expense_category_edit, name='expense_category_edit'),

    # Action Views
    path('expense-categories/<uuid:pk>/delete/', views.expense_category_delete, name='expense_category_delete'),
    path('expense-categories/<uuid:pk>/toggle-active/', views.expense_category_toggle_active, name='expense_category_toggle_active'),

    # Modal Views
    path('expense-categories/<uuid:pk>/modal/delete/', modal_views.expense_category_delete_modal, name='expense_category_delete_modal'),
    path('expense-categories/<uuid:pk>/modal/toggle-active/', modal_views.expense_category_toggle_active_modal, name='expense_category_toggle_active_modal'),

    # =============================================================================
    # EXPENSES
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('expenses/', views.expense_list, name='expense_list'),

    # CRUD Views
    path('expenses/create/', views.expense_create, name='expense_create'),
    path('expenses/<uuid:pk>/', views.expense_detail, name='expense_detail'),
    path('expenses/<uuid:pk>/edit/', views.expense_edit, name='expense_edit'),

    # Action Views
    path('expenses/<uuid:pk>/delete/', views.expense_delete, name='expense_delete'),
    path('expenses/<uuid:pk>/submit/', views.expense_submit, name='expense_submit'),
    path('expenses/<uuid:pk>/approve/', views.expense_approve, name='expense_approve'),

    # Print & Export
    path('expenses/<uuid:pk>/print/', views.expense_print_view, name='expense_print_view'),
    path('expenses/export/excel/', views.export_expenses_excel, name='export_expenses_excel'),

    # Modal Views
    path('expenses/add/modal/', modal_views.expense_form_modal, name='expense_add_modal'),
    path('expenses/<uuid:pk>/edit/modal/', modal_views.expense_form_modal, name='expense_edit_modal'),
    path('expenses/<uuid:pk>/modal/delete/', modal_views.expense_delete_modal, name='expense_delete_modal'),
    path('expenses/<uuid:pk>/modal/submit/', modal_views.expense_submit_modal, name='expense_submit_modal'),
    path('expenses/<uuid:pk>/modal/approve/', modal_views.expense_approve_modal, name='expense_approve_modal'),
    path('expenses/<uuid:pk>/modal/reject/', modal_views.expense_reject_modal, name='expense_reject_modal'),
    path('expenses/<uuid:pk>/modal/cancel/', modal_views.expense_cancel_modal, name='expense_cancel_modal'),
    path('expenses/<uuid:pk>/modal/quick-view/', modal_views.expense_quick_view_modal, name='expense_quick_view_modal'),

    # Expense Lines (Inline Management)
    path('expenses/<uuid:expense_pk>/lines/add/modal/', modal_views.expense_line_form_modal, name='expense_line_add_modal'),
    path('expenses/<uuid:expense_pk>/lines/<uuid:pk>/edit/modal/', modal_views.expense_line_form_modal, name='expense_line_edit_modal'),
    path('expense-lines/<uuid:pk>/modal/delete/', modal_views.expense_line_delete_modal, name='expense_line_delete_modal'),

    # Bulk Operations
    path('expenses/bulk/approve/modal/', modal_views.bulk_expense_approval_modal, name='bulk_expense_approval_modal'),
    path('expenses/bulk/payment/modal/', modal_views.bulk_expense_payment_modal, name='bulk_expense_payment_modal'),

    # =============================================================================
    # EXPENSE PAYMENTS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('expense-payments/', views.expense_payment_list, name='expense_payment_list'),

    # CRUD Views
    path('expense-payments/create/', views.expense_payment_create, name='expense_payment_create'),
    path('expenses/<uuid:expense_pk>/payments/create/', views.expense_payment_create, name='expense_payment_create_for_expense'),
    path('expense-payments/<uuid:pk>/', views.expense_payment_detail, name='expense_payment_detail'),
    path('expense-payments/<uuid:pk>/edit/', views.expense_payment_edit, name='expense_payment_edit'),

    # Action Views
    path('expense-payments/<uuid:pk>/delete/', views.expense_payment_delete, name='expense_payment_delete'),
    path('expense-payments/<uuid:pk>/verify/', views.expense_payment_verify, name='expense_payment_verify'),
    path('expense-payments/<uuid:pk>/reverse/', views.expense_payment_reverse, name='expense_payment_reverse'),

    # Bulk Operations
    path('expense-payments/bulk/verify/', views.bulk_expense_payment_verification, name='bulk_expense_payment_verification'),

    # Print & Export
    path('expense-payments/print/', views.expense_payment_print_view, name='expense_payment_print_view'),
    path('expense-payments/export/excel/', views.export_expense_payments_excel, name='export_expense_payments_excel'),

    # Modal Views
    path('expense-payments/add/modal/', modal_views.expense_payment_form_modal, name='expense_payment_add_modal'),
    path('expenses/<uuid:expense_pk>/payments/add/modal/', modal_views.expense_payment_form_modal, name='expense_payment_add_modal_for_expense'),
    path('expense-payments/<uuid:pk>/edit/modal/', modal_views.expense_payment_form_modal, name='expense_payment_edit_modal'),
    path('expense-payments/<uuid:pk>/modal/delete/', modal_views.expense_payment_delete_modal, name='expense_payment_delete_modal'),
    path('expense-payments/<uuid:pk>/modal/verify/', modal_views.expense_payment_verify_modal, name='expense_payment_verify_modal'),
    path('expense-payments/<uuid:pk>/modal/reverse/', modal_views.expense_payment_reverse_modal, name='expense_payment_reverse_modal'),
    path('expense-payments/<uuid:pk>/modal/detail/', modal_views.expense_payment_detail_modal, name='expense_payment_detail_modal'),
    path('expense-payments/bulk/verify/modal/', modal_views.bulk_payment_verification_modal, name='bulk_payment_verification_modal'),

    # =============================================================================
    # JOURNALS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('journals/', views.journal_list, name='journal_list'),

    # CRUD Views
    path('journals/create/', views.journal_create, name='journal_create'),
    path('journals/<uuid:pk>/', views.journal_detail, name='journal_detail'),
    path('journals/<uuid:pk>/edit/', views.journal_edit, name='journal_edit'),

    # Action Views
    path('journals/<uuid:pk>/delete/', views.journal_delete, name='journal_delete'),
    path('journals/<uuid:pk>/toggle-active/', views.journal_toggle_active, name='journal_toggle_active'),

    # Modal Views
    path('journals/<uuid:pk>/modal/delete/', modal_views.journal_delete_modal, name='journal_delete_modal'),
    path('journals/<uuid:pk>/modal/toggle-active/', modal_views.journal_toggle_active_modal, name='journal_toggle_active_modal'),

    # =============================================================================
    # JOURNAL ENTRIES
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('journal-entries/', views.journal_entry_list, name='journal_entry_list'),

    # CRUD Views
    path('journal-entries/create/', views.journal_entry_create, name='journal_entry_create'),
    path('journal-entries/<uuid:pk>/', views.journal_entry_detail, name='journal_entry_detail'),
    path('journal-entries/<uuid:pk>/edit/', views.journal_entry_edit, name='journal_entry_edit'),

    # Action Views
    path('journal-entries/<uuid:pk>/delete/', views.journal_entry_delete, name='journal_entry_delete'),
    path('journal-entries/<uuid:pk>/post/', views.journal_entry_post, name='journal_entry_post'),
    path('journal-entries/<uuid:pk>/reverse/', views.journal_entry_reverse, name='journal_entry_reverse'),

    # Print & Export
    path('journal-entries/<uuid:pk>/print/', views.journal_entry_print_view, name='journal_entry_print_view'),
    path('journal-entries/export/excel/', views.export_journal_entries_excel, name='export_journal_entries_excel'),

    # Modal Views
    path('journal-entries/add/modal/', modal_views.journal_entry_form_modal, name='journal_entry_add_modal'),
    path('journal-entries/<uuid:pk>/edit/modal/', modal_views.journal_entry_form_modal, name='journal_entry_edit_modal'),
    path('journal-entries/<uuid:pk>/modal/delete/', modal_views.journal_entry_delete_modal, name='journal_entry_delete_modal'),
    path('journal-entries/<uuid:pk>/modal/post/', modal_views.journal_entry_post_modal, name='journal_entry_post_modal'),
    path('journal-entries/<uuid:pk>/modal/reverse/', modal_views.journal_entry_reverse_modal, name='journal_entry_reverse_modal'),
    path('journal-entries/<uuid:pk>/modal/quick-view/', modal_views.journal_entry_quick_view_modal, name='journal_entry_quick_view_modal'),

    # Journal Transactions (Inline Management)
    path('journal-entries/<uuid:entry_pk>/transactions/add/modal/', modal_views.journal_transaction_form_modal, name='journal_transaction_add_modal'),
    path('journal-entries/<uuid:entry_pk>/transactions/<uuid:pk>/edit/modal/', modal_views.journal_transaction_form_modal, name='journal_transaction_edit_modal'),
    path('journal-transactions/<uuid:pk>/modal/delete/', modal_views.journal_transaction_delete_modal, name='journal_transaction_delete_modal'),

    # Bulk Operations
    path('journal-entries/bulk/post/modal/', modal_views.bulk_journal_entry_posting_modal, name='bulk_journal_entry_posting_modal'),

    # =============================================================================
    # BUDGETS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('budgets/', views.budget_list, name='budget_list'),

    # CRUD Views
    path('budgets/create/', views.budget_create, name='budget_create'),
    path('budgets/<uuid:pk>/', views.budget_detail, name='budget_detail'),
    path('budgets/<uuid:pk>/edit/', views.budget_edit, name='budget_edit'),

    # Action Views
    path('budgets/<uuid:pk>/delete/', views.budget_delete, name='budget_delete'),
    path('budgets/<uuid:pk>/approve/', views.budget_approve, name='budget_approve'),
    path('budgets/<uuid:pk>/activate/', views.budget_activate, name='budget_activate'),
    path('budgets/<uuid:pk>/close/', views.budget_close, name='budget_close'),

    # Print & Export
    path('budgets/<uuid:pk>/print/', views.budget_print_view, name='budget_print_view'),
    path('budgets/export/excel/', views.export_budgets_excel, name='export_budgets_excel'),

    # Modal Views
    path('budgets/add/modal/', modal_views.budget_form_modal, name='budget_add_modal'),
    path('budgets/<uuid:pk>/edit/modal/', modal_views.budget_form_modal, name='budget_edit_modal'),
    path('budgets/<uuid:pk>/modal/delete/', modal_views.budget_delete_modal, name='budget_delete_modal'),
    path('budgets/<uuid:pk>/modal/submit/', modal_views.budget_submit_modal, name='budget_submit_modal'),
    path('budgets/<uuid:pk>/modal/approve/', modal_views.budget_approve_modal, name='budget_approve_modal'),
    path('budgets/<uuid:pk>/modal/reject/', modal_views.budget_reject_modal, name='budget_reject_modal'),
    path('budgets/<uuid:pk>/modal/activate/', modal_views.budget_activate_modal, name='budget_activate_modal'),
    path('budgets/<uuid:pk>/modal/close/', modal_views.budget_close_modal, name='budget_close_modal'),
    path('budgets/<uuid:pk>/modal/quick-view/', modal_views.budget_quick_view_modal, name='budget_quick_view_modal'),

    # Budget Lines (Inline Management)
    path('budgets/<uuid:budget_pk>/lines/add/modal/', modal_views.budget_line_form_modal, name='budget_line_add_modal'),
    path('budgets/<uuid:budget_pk>/lines/<uuid:pk>/edit/modal/', modal_views.budget_line_form_modal, name='budget_line_edit_modal'),
    path('budget-lines/<uuid:pk>/modal/delete/', modal_views.budget_line_delete_modal, name='budget_line_delete_modal'),

    # =============================================================================
    # REPORTS
    # =============================================================================
    # Report Generation Modals
    path('reports/financial/modal/', modal_views.financial_report_modal, name='financial_report_modal'),
    path('reports/trial-balance/modal/', modal_views.trial_balance_modal, name='trial_balance_modal'),
    path('reports/income-statement/modal/', modal_views.income_statement_modal, name='income_statement_modal'),
    path('reports/balance-sheet/modal/', modal_views.balance_sheet_modal, name='balance_sheet_modal'),
    path('reports/cash-flow/modal/', modal_views.cash_flow_statement_modal, name='cash_flow_statement_modal'),
    path('reports/budget-variance/modal/', modal_views.budget_variance_report_modal, name='budget_variance_report_modal'),

    # =============================================================================
    # FISCAL PERIOD OPERATIONS
    # =============================================================================
    # Modal Views
    path('periods/<uuid:pk>/modal/close/', modal_views.period_close_modal, name='period_close_modal'),
    path('periods/<uuid:pk>/modal/reopen/', modal_views.period_reopen_modal, name='period_reopen_modal'),

    # =============================================================================
    # IMPORT/EXPORT
    # =============================================================================
    # Modal Views
    path('accounts/import/modal/', modal_views.import_accounts_modal, name='import_accounts_modal'),
    path('expenses/import/modal/', modal_views.import_expenses_modal, name='import_expenses_modal'),
    path('export/<str:resource_type>/options/modal/', modal_views.export_options_modal, name='export_options_modal'),

    # =============================================================================
    # SETTINGS & CONFIGURATION
    # =============================================================================
    # Modal Views
    path('settings/financial/modal/', modal_views.financial_settings_modal, name='financial_settings_modal'),
    path('settings/account-mapping/modal/', modal_views.account_mapping_modal, name='account_mapping_modal'),

    # =============================================================================
    # UTILITY ENDPOINTS
    # =============================================================================
    # Modal Views
    path('approval-history/<str:content_type>/<uuid:object_id>/modal/', modal_views.approval_history_modal, name='approval_history_modal'),
    path('confirm-action/modal/', modal_views.confirm_action_modal, name='confirm_action_modal'),
]