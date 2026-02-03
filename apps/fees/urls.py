# fees/urls.py

"""
URL Configuration for Fees Management

Comprehensive URL patterns for:
- Dashboard
- Student Accounts & Transactions
- Fee Invoices (CRUD + Bulk Operations)
- Payments (CRUD + Verification + Multi-Invoice)
- Scholarships (Programs, Applications, Awards)
- Discounts & Refunds
- Fee Categories, Structures, Display Groups
- Reports & Exports
- Modal Views (HTMX)
- API Endpoints

Pattern: All views use UUID primary keys
HTMX Modals: GET /resource/<pk>/modal/action/ → Load modal
Action POST: POST /resource/<pk>/action/ → Process action
"""

from django.urls import path
from . import views
from . import modal_views

app_name = 'fees'

urlpatterns = [
    
    # =============================================================================
    # DASHBOARD
    # =============================================================================
    path('', views.fees_dashboard, name='dashboard'),
    
    
    # =============================================================================
    # STUDENT ACCOUNTS
    # =============================================================================
    path('accounts/', views.student_account_list, name='account_list'),
    path('accounts/<uuid:pk>/', views.student_account_detail, name='account_detail'),
    path('accounts/<uuid:pk>/edit/', views.student_account_edit, name='account_edit'),
    path('accounts/print/', views.student_account_list_print_view, name='account_list_print'),
    path('accounts/<uuid:pk>/print/', views.student_account_print_view, name='account_print'),
    
    # Account Actions
    path('accounts/<uuid:pk>/adjust/', views.student_account_adjust, name='account_adjust'),
    
    # Account Modals
    path('accounts/<uuid:pk>/modal/adjust/', modal_views.student_account_adjust_modal, name='account_adjust_modal'),
    path('accounts/<uuid:pk>/modal/quick-view/', modal_views.student_account_quick_view_modal, name='account_quick_view_modal'),
    
    
    # =============================================================================
    # ACCOUNT TRANSACTIONS
    # =============================================================================
    path('transactions/', views.account_transaction_list, name='transaction_list'),
    path('transactions/<uuid:pk>/', views.transaction_detail, name='transaction_detail'),
    path('transactions/print/', views.transaction_list_print_view, name='transaction_list_print'),
    
    # Transaction Modals
    path('transactions/<uuid:pk>/modal/detail/', modal_views.account_transaction_detail_modal, name='transaction_detail_modal'),
    
    
    # =============================================================================
    # FEE INVOICES
    # =============================================================================
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/create/', views.invoice_create, name='invoice_create'),
    path('invoices/<uuid:pk>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/<uuid:pk>/delete/', views.invoice_delete, name='invoice_delete'),
    path('invoices/<uuid:pk>/print/', views.invoice_print_view, name='invoice_print'),
    path('invoices/print/', views.invoice_list_print_view, name='invoice_list_print'),
    
    # Bulk Invoice Generation
    path('invoices/bulk-generate/', views.invoice_bulk_generate, name='invoice_bulk_generate'),
    path('invoices/bulk-generate/preview-search/', views.invoice_bulk_preview_search, name='invoice_bulk_preview_search'),
    path('invoices/bulk-generate/preview-fees/', views.invoice_bulk_preview_fees, name='invoice_bulk_preview_fees'),
    path('invoices/bulk-generate/preview-breakdown/', views.invoice_bulk_preview_breakdown, name='invoice_bulk_preview_breakdown'),
    
    # Single Invoice Generation
    path('enrollments/<uuid:enrollment_id>/generate-invoice/', views.invoice_single_generate, name='invoice_single_generate'),
    # Form-based invoice generation (recommended for manual use)
    path(
        'enrollments/<uuid:enrollment_id>/generate-invoice/',
        views.invoice_single_generate_form,
        name='invoice_single_generate'
    ),
    
    # Quick invoice generation (for programmatic/bulk use)
    path(
        'enrollments/<uuid:enrollment_id>/generate-invoice/quick/',
        views.invoice_single_generate_quick,
        name='invoice_single_generate_quick'
    ),

    # Full invoice edit page (form with formset)
    # Full invoice edit page (form with formset)
    path(
        'invoices/<uuid:invoice_id>/edit/',
        views.invoice_edit,
        name='invoice_edit'
    ),
    
    # Re-apply scholarships and discounts (POST action)
    path(
        'invoices/<uuid:invoice_id>/reapply-scholarships/',
        views.invoice_reapply_scholarships,
        name='invoice_reapply_scholarships'
    ),
    
    # Quick edit single item (AJAX)
    path(
        'invoices/<uuid:invoice_id>/items/<uuid:item_id>/quick-edit/',
        views.invoice_item_quick_edit,
        name='invoice_item_quick_edit'
    ),
    
    # Add item to invoice
    path(
        'invoices/<uuid:invoice_id>/items/add/',
        views.invoice_add_item,
        name='invoice_add_item'
    ),
    
    # Remove item from invoice
    path(
        'invoices/<uuid:invoice_id>/items/<uuid:item_id>/remove/',
        views.invoice_remove_item,
        name='invoice_remove_item'
    ),
    
    # Preview changes (AJAX)
    path(
        'invoices/<uuid:invoice_id>/preview-changes/',
        views.invoice_preview_changes,
        name='invoice_preview_changes'
    ),
    
    # Invoice Actions
    path('invoices/<uuid:pk>/regenerate/', views.invoice_regenerate, name='invoice_regenerate'),
    path('invoices/<uuid:pk>/void/', views.invoice_void, name='invoice_void'),
    path('invoices/<uuid:pk>/apply-penalty/', views.invoice_apply_penalty, name='invoice_apply_penalty'),
    path('invoices/<uuid:pk>/waive-late-fees/', views.invoice_waive_late_fees, name='invoice_waive_late_fees'),
    path('invoices/<uuid:pk>/adjust-amount/', views.invoice_adjust_amount, name='invoice_adjust_amount'),
    path('invoices/<uuid:pk>/send-email/', views.invoice_send_email, name='invoice_send_email'),
    path('invoices/<uuid:pk>/send-reminder/', views.send_payment_reminder, name='send_payment_reminder'),
    path('invoices/<uuid:pk>/clone-to-student/', views.invoice_clone_to_student, name='invoice_clone_to_student'),
    path('invoices/merge/', views.invoice_merge, name='invoice_merge'),
    path('invoices/<uuid:pk>/split/', views.invoice_split, name='invoice_split'),
    path('invoices/<uuid:pk>/finalize/', views.invoice_finalize, name='invoice_finalize'),
    path('invoices/<uuid:pk>/revert-to-draft/', views.invoice_revert_to_draft, name='invoice_revert_to_draft'),
    
    # Invoice Modals
    path('invoices/<uuid:pk>/modal/void/', modal_views.invoice_void_modal, name='invoice_void_modal'),
    path('invoices/<uuid:pk>/modal/delete/', modal_views.invoice_delete_modal, name='invoice_delete_modal'),
    path('invoices/<uuid:pk>/modal/regenerate/', modal_views.invoice_regenerate_modal, name='invoice_regenerate_modal'),
    path('invoices/<uuid:pk>/modal/quick-view/', modal_views.invoice_quick_view_modal, name='invoice_quick_view_modal'),
    path('invoices/<uuid:pk>/modal/send-reminder/', modal_views.send_payment_reminder_modal, name='send_payment_reminder_modal'),
    path('invoices/<uuid:pk>/modal/send-email/', modal_views.invoice_send_email_modal, name='invoice_send_email_modal'),
    path('invoices/<uuid:pk>/modal/apply-penalty/', modal_views.invoice_apply_penalty_modal, name='invoice_apply_penalty_modal'),
    path('invoices/<uuid:pk>/modal/waive-late-fees/', modal_views.invoice_waive_late_fees_modal, name='invoice_waive_late_fees_modal'),
    path('invoices/<uuid:pk>/modal/adjust-amount/', modal_views.invoice_adjust_amount_modal, name='invoice_adjust_amount_modal'),
    path('invoices/<uuid:pk>/modal/clone-to-student/', modal_views.invoice_clone_to_student_modal, name='invoice_clone_to_student_modal'),
    path('invoices/modal/merge/', modal_views.invoice_merge_modal, name='invoice_merge_modal'),
    path('invoices/<uuid:pk>/modal/split/', modal_views.invoice_split_modal, name='invoice_split_modal'),
    path('invoices/<uuid:pk>/modals/finalize/', modal_views.invoice_finalize_modal, name='invoice_finalize_modal'),
    path('invoices/<uuid:pk>/modals/revert-to-draft/', modal_views.invoice_revert_to_draft_modal, name='invoice_revert_to_draft_modal'),
    
    
    # =============================================================================
    # PAYMENTS
    # =============================================================================
    path('payments/', views.payment_list, name='payment_list'),
    path('payments/create/', views.payment_create, name='payment_create'),
    path('payments/multiple/', views.multiple_invoice_payment_create, name='multiple_payment_create'),
    path('payments/<uuid:pk>/', views.payment_detail, name='payment_detail'),
    path('payments/<uuid:pk>/edit/', views.payment_update, name='payment_update'),
    path('payments/<uuid:pk>/delete/', views.payment_delete, name='payment_delete'),
    path('payments/<uuid:pk>/print/', views.payment_print_receipt, name='payment_print_receipt'),
    path('payments/print/', views.payment_list_print_view, name='payment_list_print'),
    
    # Payment Actions
    path('payments/<uuid:pk>/reverse/', views.payment_reverse, name='payment_reverse'),
    path('payments/<uuid:pk>/refund/', views.payment_refund, name='payment_refund'),
    path('payments/<uuid:pk>/verify/', views.payment_verify, name='payment_verify'),
    path('payments/bulk-verify/', views.payment_bulk_verify, name='payment_bulk_verify'),
    path('payments/<uuid:pk>/send-receipt/', views.payment_send_receipt, name='payment_send_receipt'),
    
    # Payment Modals
    path('payments/<uuid:pk>/modal/reverse/', modal_views.payment_reverse_modal, name='payment_reverse_modal'),
    path('payments/<uuid:pk>/modal/refund/', modal_views.payment_refund_modal, name='payment_refund_modal'),
    path('payments/<uuid:pk>/modal/verify/', modal_views.payment_verify_modal, name='payment_verify_modal'),
    path('payments/<uuid:pk>/modal/delete/', modal_views.payment_delete_modal, name='payment_delete_modal'),
    path('payments/<uuid:pk>/modal/quick-view/', modal_views.payment_quick_view_modal, name='payment_quick_view_modal'),
    path('payments/modal/bulk-verify/', modal_views.bulk_payment_verification_modal, name='bulk_payment_verification_modal'),
    path('payments/<uuid:pk>/modal/send-receipt/', modal_views.payment_send_receipt_modal, name='payment_send_receipt_modal'),
    path('payments/<uuid:pk>/modal/allocation-detail/', modal_views.payment_allocation_detail_modal, name='payment_allocation_detail_modal'),
    
    
    # =============================================================================
    # SCHOLARSHIP PROGRAMS
    # =============================================================================
    path('scholarships/programs/', views.scholarship_program_list, name='scholarship_program_list'),
    path('scholarships/programs/create/', views.scholarship_program_create, name='scholarship_program_create'),
    path('scholarships/programs/<uuid:pk>/', views.scholarship_program_detail, name='scholarship_program_detail'),
    path('scholarships/programs/<uuid:pk>/edit/', views.scholarship_program_edit, name='scholarship_program_edit'),
    path('scholarships/programs/<uuid:pk>/delete/', views.scholarship_program_delete, name='scholarship_program_delete'),
    path('scholarships/programs/print/', views.scholarship_program_list_print_view, name='scholarship_program_list_print'),
    
    # Scholarship Program Actions
    path('scholarships/programs/<uuid:pk>/activate/', views.scholarship_program_activate, name='scholarship_program_activate'),
    path('scholarships/programs/<uuid:pk>/deactivate/', views.scholarship_program_deactivate, name='scholarship_program_deactivate'),
    path('scholarships/programs/<uuid:pk>/toggle-accepting/', views.scholarship_toggle_accepting, name='scholarship_toggle_accepting'),
    
    # Scholarship Program Modals
    path('scholarships/programs/<uuid:pk>/modal/delete/', modal_views.scholarship_program_delete_modal, name='scholarship_program_delete_modal'),
    path('scholarships/programs/<uuid:pk>/modal/activate/', modal_views.scholarship_program_activate_modal, name='scholarship_program_activate_modal'),
    path('scholarships/programs/<uuid:pk>/modal/deactivate/', modal_views.scholarship_program_deactivate_modal, name='scholarship_program_deactivate_modal'),
    path('scholarships/programs/<uuid:pk>/modal/toggle-accepting/', modal_views.scholarship_toggle_accepting_modal, name='scholarship_toggle_accepting_modal'),
    
    
    # =============================================================================
    # SCHOLARSHIP APPLICATIONS
    # =============================================================================
    path('scholarships/applications/', views.scholarship_application_list, name='scholarship_application_list'),
    path('scholarships/applications/create/', views.scholarship_application_create, name='scholarship_application_create'),
    path('scholarships/applications/<uuid:pk>/', views.scholarship_application_detail, name='scholarship_application_detail'),
    path('scholarships/applications/<uuid:pk>/delete/', views.scholarship_application_delete, name='scholarship_application_delete'),
    path('scholarships/applications/print/', views.scholarship_application_list_print_view, name='scholarship_application_list_print'),
    
    # Application Actions
    path('scholarships/applications/<uuid:pk>/approve/', views.scholarship_application_approve, name='scholarship_application_approve'),
    
    # Application Modals
    path('scholarships/applications/<uuid:pk>/modal/approve/', modal_views.scholarship_application_approve_modal, name='scholarship_application_approve_modal'),
    path('scholarships/applications/<uuid:pk>/modal/reject/', modal_views.scholarship_application_reject_modal, name='scholarship_application_reject_modal'),
    path('scholarships/applications/<uuid:pk>/modal/delete/', modal_views.scholarship_application_delete_modal, name='scholarship_application_delete_modal'),
    path('scholarships/applications/<uuid:pk>/modal/history/', modal_views.scholarship_application_history_modal, name='scholarship_application_history_modal'),
    
    
    # =============================================================================
    # STUDENT SCHOLARSHIPS (AWARDS)
    # =============================================================================
    path('scholarships/', views.student_scholarship_list, name='student_scholarship_list'),
    path('scholarships/create/', views.student_scholarship_create, name='student_scholarship_create'),
    path('scholarships/<uuid:pk>/', views.student_scholarship_detail, name='student_scholarship_detail'),
    path('scholarships/<uuid:pk>/edit/', views.student_scholarship_edit, name='student_scholarship_edit'),
    path('scholarships/<uuid:pk>/delete/', views.student_scholarship_delete, name='student_scholarship_delete'),
    path('scholarships/print/', views.student_scholarship_list_print_view, name='student_scholarship_list_print'),
    
    # Scholarship Actions
    path('scholarships/<uuid:pk>/suspend/', views.student_scholarship_suspend, name='student_scholarship_suspend'),
    path('scholarships/<uuid:pk>/terminate/', views.student_scholarship_terminate, name='student_scholarship_terminate'),
    path('scholarships/<uuid:pk>/reactivate/', views.student_scholarship_reactivate, name='student_scholarship_reactivate'),
    path('scholarships/<uuid:pk>/complete/', views.student_scholarship_complete, name='student_scholarship_complete'),
    
    # Scholarship Modals
    path('scholarships/<uuid:pk>/modal/suspend/', modal_views.student_scholarship_suspend_modal, name='student_scholarship_suspend_modal'),
    path('scholarships/<uuid:pk>/modal/terminate/', modal_views.student_scholarship_terminate_modal, name='student_scholarship_terminate_modal'),
    path('scholarships/<uuid:pk>/modal/reactivate/', modal_views.student_scholarship_reactivate_modal, name='student_scholarship_reactivate_modal'),
    path('scholarships/<uuid:pk>/modal/complete/', modal_views.student_scholarship_complete_modal, name='student_scholarship_complete_modal'),
    path('scholarships/<uuid:pk>/modal/delete/', modal_views.student_scholarship_delete_modal, name='student_scholarship_delete_modal'),
    
    
    # =============================================================================
    # INVOICE SCHOLARSHIP MANAGEMENT (NEW SECTION)
    # =============================================================================
    
    # Apply Scholarship to Invoice
    path('invoices/<uuid:invoice_pk>/scholarships/apply/', 
         views.apply_scholarship_to_invoice, 
         name='apply_scholarship_to_invoice'),
    path('invoices/<uuid:invoice_pk>/scholarships/apply/modal/', 
         modal_views.apply_scholarship_to_invoice_modal, 
         name='apply_scholarship_to_invoice_modal'),
    
    # Remove Scholarship from Invoice
    path('invoices/<uuid:invoice_pk>/scholarships/remove/', 
         views.remove_scholarship_from_invoice, 
         name='remove_scholarship_from_invoice'),
    path('invoices/<uuid:invoice_pk>/scholarships/remove/modal/', 
         modal_views.remove_scholarship_from_invoice_modal, 
         name='remove_scholarship_from_invoice_modal'),
    
    # Remove Specific Scholarship from Invoice
    path('invoices/<uuid:invoice_pk>/scholarships/<uuid:scholarship_pk>/remove/modal/', 
         modal_views.remove_scholarship_from_invoice_modal, 
         name='remove_specific_scholarship_from_invoice_modal'),
    
    
    # =============================================================================
    # DISCOUNTS
    # =============================================================================
    path('discounts/', views.discount_list, name='discount_list'),
    path('discounts/create/', views.discount_create, name='discount_create'),
    path('discounts/<uuid:pk>/', views.discount_detail, name='discount_detail'),
    path('discounts/<uuid:pk>/edit/', views.discount_edit, name='discount_edit'),
    path('discounts/<uuid:pk>/delete/', views.discount_delete, name='discount_delete'),
    path('discounts/print/', views.discount_list_print_view, name='discount_list_print'),
    
    # Discount Actions
    path('discounts/<uuid:pk>/toggle-active/', views.discount_toggle_active, name='discount_toggle_active'),
    path('discounts/<uuid:discount_pk>/apply-to-invoice/<uuid:invoice_pk>/', views.apply_discount_to_invoice, name='apply_discount_to_invoice'),
    path('discounts/apply-to-invoice/<uuid:invoice_pk>/', views.apply_discount_to_invoice, name='apply_discount_to_invoice_select'),
    
    # Discount Modals
    path('discounts/<uuid:pk>/modal/delete/', modal_views.discount_delete_modal, name='discount_delete_modal'),
    path('discounts/<uuid:pk>/modal/toggle-active/', modal_views.discount_toggle_active_modal, name='discount_toggle_active_modal'),
    path('discounts/<uuid:discount_pk>/modal/apply-to-invoice/<uuid:invoice_pk>/', modal_views.apply_discount_to_invoice_modal, name='apply_discount_to_invoice_modal'),
    path('discounts/modal/apply-to-invoice/<uuid:invoice_pk>/', modal_views.apply_discount_to_invoice_modal, name='apply_discount_to_invoice_select_modal'),
    
    
    # =============================================================================
    # REFUNDS
    # =============================================================================
    path('refunds/', views.refund_list, name='refund_list'),
    path('refunds/create/', views.refund_create, name='refund_create'),
    path('refunds/<uuid:pk>/', views.refund_detail, name='refund_detail'),
    path('refunds/<uuid:pk>/delete/', views.refund_delete, name='refund_delete'),
    path('refunds/print/', views.refund_list_print_view, name='refund_list_print'),
    
    # Refund Actions
    path('refunds/<uuid:pk>/approve/', views.refund_approve, name='refund_approve'),
    path('refunds/<uuid:pk>/process/', views.refund_process, name='refund_process'),
    
    # Refund Modals
    path('refunds/<uuid:pk>/modal/approve/', modal_views.refund_approve_modal, name='refund_approve_modal'),
    path('refunds/<uuid:pk>/modal/process/', modal_views.refund_process_modal, name='refund_process_modal'),
    path('refunds/<uuid:pk>/modal/delete/', modal_views.refund_delete_modal, name='refund_delete_modal'),
    
    
    # =============================================================================
    # DISPLAY GROUPS
    # =============================================================================
    path('display-groups/', views.display_group_list, name='display_group_list'),
    path('display-groups/create/', views.display_group_create, name='display_group_create'),
    path('display-groups/<uuid:pk>/', views.display_group_detail, name='display_group_detail'),
    path('display-groups/<uuid:pk>/edit/', views.display_group_edit, name='display_group_edit'),
    path('display-groups/<uuid:pk>/delete/', views.display_group_delete, name='display_group_delete'),
    path('display-groups/print/', views.display_group_list_print_view, name='display_group_list_print'),
    
    # Display Group Actions
    path('display-groups/<uuid:pk>/toggle-active/', views.display_group_toggle_active, name='display_group_toggle_active'),
    
    # Display Group Modals
    path('display-groups/<uuid:pk>/modal/delete/', modal_views.display_group_delete_modal, name='display_group_delete_modal'),
    path('display-groups/<uuid:pk>/modal/toggle-active/', modal_views.display_group_toggle_active_modal, name='display_group_toggle_active_modal'),
    
    
    # =============================================================================
    # FEE CATEGORIES
    # =============================================================================
    path('categories/', views.fee_category_list, name='category_list'),
    path('categories/create/', views.fee_category_create, name='category_create'),
    path('categories/<uuid:pk>/', views.fee_category_detail, name='category_detail'),
    path('categories/<uuid:pk>/edit/', views.fee_category_edit, name='category_edit'),
    path('categories/<uuid:pk>/delete/', views.fee_category_delete, name='category_delete'),
    path('categories/print/', views.fee_category_list_print_view, name='category_list_print'),
    
    # Category Actions
    path('categories/<uuid:pk>/toggle-active/', views.fee_category_toggle_active, name='category_toggle_active'),
    
    # Category Modals
    path('categories/<uuid:pk>/modal/delete/', modal_views.fee_category_delete_modal, name='category_delete_modal'),
    path('categories/<uuid:pk>/modal/toggle-active/', modal_views.fee_category_toggle_active_modal, name='category_toggle_active_modal'),
    
    
    # =============================================================================
    # FEE STRUCTURES
    # =============================================================================
    path('structures/', views.fee_structure_list, name='structure_list'),
    path('structures/create/', views.fee_structure_create, name='structure_create'),
    path('structures/<uuid:pk>/', views.fee_structure_detail, name='structure_detail'),
    path('structures/<uuid:pk>/edit/', views.fee_structure_edit, name='structure_edit'),
    path('structures/<uuid:pk>/delete/', views.fee_structure_delete, name='structure_delete'),
    path('structures/<uuid:pk>/print/', views.fee_structure_print_view, name='structure_print'),
    path('structures/print/', views.fee_structure_list_print_view, name='structure_list_print'),
    
    # Structure Actions
    path('structures/<uuid:pk>/clone/', views.fee_structure_clone, name='structure_clone'),
    path('structures/<uuid:pk>/activate/', views.fee_structure_activate, name='structure_activate'),
    path('structures/<uuid:pk>/deactivate/', views.fee_structure_deactivate, name='structure_deactivate'),
    
    # Structure Modals
    path('structures/<uuid:pk>/modal/delete/', modal_views.fee_structure_delete_modal, name='structure_delete_modal'),
    path('structures/<uuid:pk>/modal/clone/', modal_views.fee_structure_clone_modal, name='structure_clone_modal'),
    path('structures/<uuid:pk>/modal/activate/', modal_views.fee_structure_activate_modal, name='structure_activate_modal'),
    path('structures/<uuid:pk>/modal/deactivate/', modal_views.fee_structure_deactivate_modal, name='structure_deactivate_modal'),
    path('structures/<uuid:pk>/modal/quick-view/', modal_views.fee_structure_quick_view_modal, name='structure_quick_view_modal'),
    path('structures/modal/compare/', modal_views.fee_structure_compare_modal, name='structure_compare_modal'),
    
    
    # =============================================================================
    # REPORTS
    # =============================================================================
    path('reports/collection/', views.fee_collection_report, name='collection_report'),
    path('reports/outstanding/', views.outstanding_fees_report, name='outstanding_report'),
    path('reports/scholarships/', views.scholarship_report, name='scholarship_report'),
    path('reports/discounts/', views.discount_report, name='discount_report'),
    path('reports/student-account/<uuid:pk>/', views.student_account_report, name='student_account_report'),
    path('reports/aging/', views.aging_report, name='aging_report'),
    path('reports/payment-methods/', views.payment_methods_report, name='payment_methods_report'),
    
    
    # =============================================================================
    # EXCEL EXPORTS
    # =============================================================================
    # List Exports
    path('export/student-accounts/', views.export_student_accounts_excel, name='export_student_accounts_excel'),
    path('export/account-transactions/', views.export_account_transactions_excel, name='export_account_transactions_excel'),
    path('export/invoices/', views.export_invoices_excel, name='export_invoices_excel'),
    path('export/payments/', views.export_payments_excel, name='export_payments_excel'),
    path('export/scholarship-programs/', views.export_scholarship_programs_excel, name='export_scholarship_programs_excel'),
    path('export/scholarship-applications/', views.export_scholarship_applications_excel, name='export_scholarship_applications_excel'),
    path('export/student-scholarships/', views.export_student_scholarships_excel, name='export_student_scholarships_excel'),
    path('export/discounts/', views.export_discounts_excel, name='export_discounts_excel'),
    path('export/refunds/', views.export_refunds_excel, name='export_refunds_excel'),
    path('export/display-groups/', views.export_display_groups_excel, name='export_display_groups_excel'),
    path('export/fee-categories/', views.export_fee_categories_excel, name='export_fee_categories_excel'),
    path('export/fee-structures/', views.export_fee_structures_excel, name='export_fee_structures_excel'),
    
    # Report Exports
    path('export/collection-report/', views.export_collection_report_excel, name='export_collection_report_excel'),
    path('export/outstanding-report/', views.export_outstanding_report_excel, name='export_outstanding_report_excel'),
    path('export/aging-report/', views.export_aging_report_excel, name='export_aging_report_excel'),
    path('export/payment-methods-report/', views.export_payment_methods_report_excel, name='export_payment_methods_report_excel'),
    
    
    # =============================================================================
    # API ENDPOINTS (For HTMX and AJAX)
    # =============================================================================
    path('api/student-invoices/', views.api_get_student_invoices, name='api_get_student_invoices'),
    path('api/validate-invoice-numbers/', views.api_validate_invoice_numbers, name='api_validate_invoice_numbers'),
    
    
    # =============================================================================
    # BULK OPERATIONS MODALS
    # =============================================================================
    path('modal/bulk-late-fees/', modal_views.bulk_late_fee_application_modal, name='bulk_late_fee_application_modal'),
]