# fees/urls.py

"""
URL Configuration for Fees Management

Comprehensive URL patterns for:
- Dashboard
- Display Groups
- Fee Categories
- Fee Structures
- Student Accounts & Transactions
- Fee Invoices (CRUD + Actions)
- Payments (CRUD + Verification + Multi-Invoice + API)
- Scholarship Programs
- Scholarship Applications
- Student Scholarships (Awards)
- Discount Policies
- Student Discount Awards
- Discount Applications
- Refunds
- Reports & Exports
- Modal Views (HTMX)
- API Endpoints

Pattern: All views use UUID primary keys
HTMX Modals: GET /resource/<pk>/modal/action/ → Load modal
Action POST:  POST /resource/<pk>/action/     → Process action
"""

from django.urls import path
from . import views
from . import modal_views

app_name = 'fees'

urlpatterns = [

    # =========================================================================
    # DASHBOARD
    # =========================================================================
    path('', views.fees_dashboard, name='dashboard'),


    # =========================================================================
    # DISPLAY GROUPS
    # =========================================================================
    path('display-groups/',                                     views.display_group_list,                       name='display_group_list'),
    path('display-groups/create/',                              views.display_group_create,                     name='display_group_create'),
    path('display-groups/print/',                               views.display_group_list_print_view,            name='display_group_list_print'),
    path('display-groups/export/',                              views.export_display_groups_excel,              name='export_display_groups_excel'),
    path('display-groups/<uuid:pk>/',                           views.display_group_detail,                     name='display_group_detail'),
    path('display-groups/<uuid:pk>/edit/',                      views.display_group_edit,                       name='display_group_edit'),
    path('display-groups/<uuid:pk>/delete/',                    views.display_group_delete,                     name='display_group_delete'),
    path('display-groups/<uuid:pk>/toggle-active/',             views.display_group_toggle_active,              name='display_group_toggle_active'),

    # Display Group modals
    path('display-groups/<uuid:pk>/modal/delete/',              modal_views.display_group_delete_modal,         name='display_group_delete_modal'),
    path('display-groups/<uuid:pk>/modal/toggle-active/',       modal_views.display_group_toggle_active_modal,  name='display_group_toggle_active_modal'),


    # =========================================================================
    # FEE CATEGORIES
    # =========================================================================
    path('categories/',                                         views.fee_category_list,                        name='category_list'),
    path('categories/create/',                                  views.fee_category_create,                      name='category_create'),
    path('categories/print/',                                   views.fee_category_list_print_view,             name='category_list_print'),
    path('categories/export/',                                  views.export_fee_categories_excel,              name='export_fee_categories_excel'),
    path('categories/<uuid:pk>/',                               views.fee_category_detail,                      name='category_detail'),
    path('categories/<uuid:pk>/edit/',                          views.fee_category_edit,                        name='category_edit'),
    path('categories/<uuid:pk>/delete/',                        views.fee_category_delete,                      name='category_delete'),
    path('categories/<uuid:pk>/toggle-active/',                 views.fee_category_toggle_active,               name='category_toggle_active'),

    # Fee category modals
    path('categories/<uuid:pk>/modal/delete/',                  modal_views.fee_category_delete_modal,          name='category_delete_modal'),
    path('categories/<uuid:pk>/modal/toggle-active/',           modal_views.fee_category_toggle_active_modal,   name='category_toggle_active_modal'),


    # =========================================================================
    # FEE STRUCTURES
    # =========================================================================
    path('structures/',                                         views.fee_structure_list,                       name='structure_list'),
    path('structures/create/',                                  views.fee_structure_create,                     name='structure_create'),
    path('structures/<uuid:pk>/edit/',                          views.fee_structure_edit,                       name='structure_edit'),
    path('structures/print/',                                   views.fee_structure_list_print_view,            name='structure_list_print'),
    path('structures/export/',                                  views.export_fee_structures_excel,              name='export_fee_structures_excel'),
    path('structures/<uuid:pk>/',                               views.fee_structure_detail,                     name='structure_detail'),
    path('structures/<uuid:pk>/delete/',                        views.fee_structure_delete,                     name='structure_delete'),
    path('structures/<uuid:pk>/print/',                         views.fee_structure_print_view,                 name='structure_print'),
    path('structures/<uuid:pk>/clone/',                         views.fee_structure_clone,                      name='structure_clone'),
    path('structures/<uuid:pk>/activate/',                      views.fee_structure_activate,                   name='structure_activate'),
    path('structures/<uuid:pk>/deactivate/',                    views.fee_structure_deactivate,                 name='structure_deactivate'),

    # Fee structure modals
    path('structures/<uuid:pk>/modal/delete/',                  modal_views.fee_structure_delete_modal,         name='structure_delete_modal'),
    path('structures/<uuid:pk>/modal/clone/',                   modal_views.fee_structure_clone_modal,          name='structure_clone_modal'),
    path('structures/<uuid:pk>/modal/activate/',                modal_views.fee_structure_activate_modal,       name='structure_activate_modal'),
    path('structures/<uuid:pk>/modal/deactivate/',              modal_views.fee_structure_deactivate_modal,     name='structure_deactivate_modal'),
    path('structures/<uuid:pk>/modal/quick-view/',              modal_views.fee_structure_quick_view_modal,     name='structure_quick_view_modal'),


    # =========================================================================
    # STUDENT ACCOUNTS
    # =========================================================================
    path('accounts/',                                           views.student_account_list,                     name='account_list'),
    path('accounts/print/',                                     views.student_account_list_print_view,          name='account_list_print'),
    path('accounts/export/',                                    views.export_student_accounts_excel,            name='export_student_accounts_excel'),
    # Statement print — account_id passed as GET param, no pk in URL
    path('accounts/statement/',                                 views.student_account_print_view,               name='account_statement_print'),
    path('accounts/<uuid:pk>/',                                 views.student_account_detail,                   name='account_detail'),
    path('accounts/<uuid:pk>/edit/',                            views.student_account_edit,                     name='account_edit'),
    path('accounts/<uuid:pk>/adjust/',                          views.student_account_adjust,                   name='account_adjust'),

    # Student account modals
    path('accounts/<uuid:pk>/modal/adjust/',                    modal_views.student_account_adjust_modal,       name='account_adjust_modal'),
    path('accounts/<uuid:pk>/modal/quick-view/',                modal_views.student_account_quick_view_modal,   name='account_quick_view_modal'),


    # =========================================================================
    # ACCOUNT TRANSACTIONS
    # =========================================================================
    path('transactions/print/',                                 views.transaction_list_print_view,              name='transaction_list_print'),
    path('transactions/export/',                                views.export_account_transactions_excel,        name='export_account_transactions_excel'),
    path('transactions/<uuid:pk>/',                             views.transaction_detail,                       name='transaction_detail'),

    # Transaction modals
    path('transactions/<uuid:pk>/modal/detail/',                modal_views.account_transaction_detail_modal,   name='transaction_detail_modal'),


    # =========================================================================
    # FEE INVOICES
    # =========================================================================
    path('invoices/',                                           views.invoice_list,                             name='invoice_list'),
    path('invoices/print/',                                     views.invoice_list_print_view,                  name='invoice_list_print'),
    path('invoices/export/',                                    views.export_invoices_excel,                    name='export_invoices_excel'),
    path('invoices/<uuid:pk>/',                                 views.invoice_detail,                           name='invoice_detail'),
    path('invoices/<uuid:pk>/print/',                           views.invoice_print_view,                       name='invoice_print'),
    path('invoices/<uuid:pk>/delete/',                          views.invoice_delete,                           name='invoice_delete'),
    path('invoices/<uuid:pk>/void/',                            views.invoice_void,                             name='invoice_void'),
    path('invoices/<uuid:pk>/finalize/',                        views.invoice_finalize,                         name='invoice_finalize'),
    path('invoices/<uuid:pk>/revert-to-draft/',                 views.invoice_revert_to_draft,                  name='invoice_revert_to_draft'),
    path('invoices/<uuid:pk>/send-email/',                      views.invoice_send_email,                       name='invoice_send_email'),
    path('invoices/<uuid:pk>/send-reminder/',                   views.send_payment_reminder,                    name='send_payment_reminder'),
    # Discount applied at invoice level — policy_id comes from POST body
    path('invoices/<uuid:pk>/apply-discount/',                  views.apply_discount_to_invoice,                name='apply_discount_to_invoice'),
    path('invoices/bulk-finalize/',                             views.invoice_bulk_finalize,                    name='invoice_bulk_finalize'),

    # Fee invoice modals
    path('invoices/<uuid:pk>/modal/void/',                      modal_views.invoice_void_modal,                 name='invoice_void_modal'),
    path('invoices/<uuid:pk>/modal/delete/',                    modal_views.invoice_delete_modal,               name='invoice_delete_modal'),
    path('invoices/<uuid:pk>/modal/quick-view/',                modal_views.invoice_quick_view_modal,           name='invoice_quick_view_modal'),
    path('invoices/<uuid:pk>/modal/finalize/',                  modal_views.invoice_finalize_modal,             name='invoice_finalize_modal'),
    path('invoices/bulk-finalize/modal/',                       modal_views.invoice_bulk_finalize_modal,        name='invoice_bulk_finalize_modal'),
    path('invoices/<uuid:pk>/modal/revert-to-draft/',           modal_views.invoice_revert_to_draft_modal,      name='invoice_revert_to_draft_modal'),
    path('invoices/<uuid:pk>/modal/send-reminder/',             modal_views.send_payment_reminder_modal,        name='send_payment_reminder_modal'),
    path('invoices/<uuid:pk>/modal/send-email/',                modal_views.invoice_send_email_modal,           name='invoice_send_email_modal'),
    path('invoices/<uuid:pk>/modal/apply-penalty/',             modal_views.invoice_apply_penalty_modal,        name='invoice_apply_penalty_modal'),
    path('invoices/<uuid:pk>/modal/waive-late-fees/',           modal_views.invoice_waive_late_fees_modal,      name='invoice_waive_late_fees_modal'),
    path('invoices/<uuid:pk>/modal/adjust-amount/',             modal_views.invoice_adjust_amount_modal,        name='invoice_adjust_amount_modal'),
    # Apply-discount modal — invoice pk in URL, optional policy pk
    path('invoices/<uuid:invoice_pk>/modal/apply-discount/',                        modal_views.apply_discount_to_invoice_modal,                name='apply_discount_to_invoice_modal'),
    path('invoices/<uuid:invoice_pk>/modal/apply-discount/<uuid:discount_pk>/',     modal_views.apply_discount_to_invoice_modal,                name='apply_discount_to_invoice_with_policy_modal'),


    # =========================================================================
    # PAYMENTS
    # =========================================================================
    path('payments/',                                           views.payment_list,                             name='payment_list'),
    path('payments/create/',                                    views.payment_create,                           name='payment_create'),
    path('payments/multiple/',                                  views.multiple_invoice_payment_create,          name='multiple_payment_create'),
    path('payments/outstanding-invoices/',                      views.outstanding_invoices_for_student,         name='outstanding_invoices_for_student'),
    path('payments/print/',                                     views.payment_list_print_view,                  name='payment_list_print'),
    path('payments/export/',                                    views.export_payments_excel,                    name='export_payments_excel'),
    path('payments/bulk-verify/',                               views.payment_bulk_verify,                      name='payment_bulk_verify'),
    path('payments/<uuid:pk>/',                                 views.payment_detail,                           name='payment_detail'),
    path('payments/<uuid:pk>/delete/',                          views.payment_delete,                           name='payment_delete'),
    path('payments/<uuid:pk>/print/',                           views.payment_print_receipt,                    name='payment_print_receipt'),
    path('payments/<uuid:pk>/reverse/',                         views.payment_reverse,                          name='payment_reverse'),
    path('payments/<uuid:pk>/refund/',                          views.payment_refund,                           name='payment_refund'),
    path('payments/<uuid:pk>/verify/',                          views.payment_verify,                           name='payment_verify'),
    path('payments/<uuid:pk>/send-receipt/',                    views.payment_send_receipt,                     name='payment_send_receipt'),

    # Payment modals
    path('payments/modal/bulk-verify/',                         modal_views.bulk_payment_verification_modal,    name='bulk_payment_verification_modal'),
    path('payments/<uuid:pk>/modal/reverse/',                   modal_views.payment_reverse_modal,              name='payment_reverse_modal'),
    path('payments/<uuid:pk>/modal/refund/',                    modal_views.payment_refund_modal,               name='payment_refund_modal'),
    path('payments/<uuid:pk>/modal/verify/',                    modal_views.payment_verify_modal,               name='payment_verify_modal'),
    path('payments/<uuid:pk>/modal/delete/',                    modal_views.payment_delete_modal,               name='payment_delete_modal'),
    path('payments/<uuid:pk>/modal/quick-view/',                modal_views.payment_quick_view_modal,           name='payment_quick_view_modal'),
    path('payments/<uuid:pk>/modal/send-receipt/',              modal_views.payment_send_receipt_modal,         name='payment_send_receipt_modal'),


    # =========================================================================
    # SCHOLARSHIP PROGRAMS
    # =========================================================================
    path('scholarships/programs/',                              views.scholarship_program_list,                 name='scholarship_program_list'),
    path('scholarships/programs/create/',                       views.scholarship_program_create,               name='scholarship_program_create'),
    path('scholarships/programs/print/',                        views.scholarship_program_list_print_view,      name='scholarship_program_list_print'),
    path('scholarships/programs/export/',                       views.export_scholarship_programs_excel,        name='export_scholarship_programs_excel'),
    path('scholarships/programs/<uuid:pk>/',                    views.scholarship_program_detail,               name='scholarship_program_detail'),
    path('scholarships/programs/<uuid:pk>/edit/',               views.scholarship_program_edit,                 name='scholarship_program_edit'),
    path('scholarships/programs/<uuid:pk>/delete/',             views.scholarship_program_delete,               name='scholarship_program_delete'),
    path('scholarships/programs/<uuid:pk>/activate/',           views.scholarship_program_activate,             name='scholarship_program_activate'),
    path('scholarships/programs/<uuid:pk>/deactivate/',         views.scholarship_program_deactivate,           name='scholarship_program_deactivate'),
    path('scholarships/programs/<uuid:pk>/toggle-accepting/',   views.scholarship_toggle_accepting,             name='scholarship_toggle_accepting'),
    # HTMX partials for tabbed detail page
    path('scholarships/programs/<uuid:pk>/recipients/',         views.scholarship_program_recipients_partial,   name='scholarship_program_recipients_partial'),
    path('scholarships/programs/<uuid:pk>/applications/',       views.scholarship_program_applications_partial, name='scholarship_program_applications_partial'),

    # Scholarship program modals
    path('scholarships/programs/<uuid:pk>/modal/delete/',       modal_views.scholarship_program_delete_modal,   name='scholarship_program_delete_modal'),
    path('scholarships/programs/<uuid:pk>/modal/activate/',     modal_views.scholarship_program_activate_modal, name='scholarship_program_activate_modal'),
    path('scholarships/programs/<uuid:pk>/modal/deactivate/',   modal_views.scholarship_program_deactivate_modal, name='scholarship_program_deactivate_modal'),


    # =========================================================================
    # SCHOLARSHIP APPLICATIONS
    # =========================================================================
    path('scholarships/applications/',                          views.scholarship_application_list,             name='scholarship_application_list'),
    path('scholarships/applications/create/',                   views.scholarship_application_create,           name='scholarship_application_create'),
    path('scholarships/applications/print/',                    views.scholarship_application_list_print_view,  name='scholarship_application_list_print'),
    path('scholarships/applications/export/',                   views.export_scholarship_applications_excel,    name='export_scholarship_applications_excel'),
    path('scholarships/applications/<uuid:pk>/',                views.scholarship_application_detail,           name='scholarship_application_detail'),
    path('scholarships/applications/<uuid:pk>/edit/',           views.scholarship_application_edit,             name='scholarship_application_edit'),
    path('scholarships/applications/<uuid:pk>/delete/',         views.scholarship_application_delete,           name='scholarship_application_delete'),
    # Single review endpoint handles approve / reject / waitlist via POST decision field
    path('scholarships/applications/<uuid:pk>/review/',         views.scholarship_application_review,           name='scholarship_application_review'),

    # Scholarship application modals
    path('scholarships/applications/<uuid:pk>/modal/approve/',  modal_views.scholarship_application_approve_modal,  name='scholarship_application_approve_modal'),
    path('scholarships/applications/<uuid:pk>/modal/reject/',   modal_views.scholarship_application_reject_modal,   name='scholarship_application_reject_modal'),
    path('scholarships/applications/<uuid:pk>/modal/delete/',   modal_views.scholarship_application_delete_modal,   name='scholarship_application_delete_modal'),
    path('scholarships/applications/<uuid:pk>/modal/history/',  modal_views.scholarship_application_history_modal,  name='scholarship_application_history_modal'),


    # =========================================================================
    # STUDENT SCHOLARSHIPS (AWARDS)
    # =========================================================================
    path('scholarships/',                                       views.student_scholarship_list,                 name='student_scholarship_list'),
    path('scholarships/create/',                                views.student_scholarship_create,               name='student_scholarship_create'),
    path('scholarships/print/',                                 views.student_scholarship_list_print_view,      name='student_scholarship_list_print'),
    path('scholarships/export/',                                views.export_student_scholarships_excel,        name='export_student_scholarships_excel'),
    path('scholarships/<uuid:pk>/',                             views.student_scholarship_detail,               name='student_scholarship_detail'),
    path('scholarships/<uuid:pk>/edit/',                        views.student_scholarship_edit,                 name='student_scholarship_edit'),
    path('scholarships/<uuid:pk>/delete/',                      views.student_scholarship_delete,               name='student_scholarship_delete'),
    path('scholarships/<uuid:pk>/suspend/',                     views.student_scholarship_suspend,              name='student_scholarship_suspend'),
    path('scholarships/<uuid:pk>/terminate/',                   views.student_scholarship_terminate,            name='student_scholarship_terminate'),
    path('scholarships/<uuid:pk>/complete/',                     views.student_scholarship_complete,             name='student_scholarship_complete'),

    # Student scholarship modals
    path('scholarships/<uuid:pk>/modal/suspend/',               modal_views.student_scholarship_suspend_modal,      name='student_scholarship_suspend_modal'),
    path('scholarships/<uuid:pk>/modal/terminate/',             modal_views.student_scholarship_terminate_modal,    name='student_scholarship_terminate_modal'),
    path('scholarships/<uuid:pk>/modal/reactivate/',            modal_views.student_scholarship_reactivate_modal,   name='student_scholarship_reactivate_modal'),
    path('scholarships/<uuid:pk>/modal/complete/',              modal_views.student_scholarship_complete_modal,     name='student_scholarship_complete_modal'),
    path('scholarships/<uuid:pk>/modal/delete/',                modal_views.student_scholarship_delete_modal,       name='student_scholarship_delete_modal'),


    # =========================================================================
    # DISCOUNT POLICIES
    # =========================================================================
    path('discounts/',                                          views.discount_list,                            name='discount_list'),
    path('discounts/create/',                                   views.discount_create,                          name='discount_create'),
    path('discounts/print/',                                    views.discount_list_print_view,                 name='discount_list_print'),
    path('discounts/export/',                                   views.export_discounts_excel,                   name='export_discounts_excel'),
    path('discounts/<uuid:pk>/',                                views.discount_detail,                          name='discount_detail'),
    path('discounts/<uuid:pk>/edit/',                           views.discount_edit,                            name='discount_edit'),
    path('discounts/<uuid:pk>/delete/',                         views.discount_delete,                          name='discount_delete'),
    path('discounts/<uuid:pk>/toggle-active/',                  views.discount_toggle_active,                   name='discount_toggle_active'),

    # Discount policy modals
    path('discounts/<uuid:pk>/modal/delete/',                   modal_views.discount_delete_modal,              name='discount_delete_modal'),
    path('discounts/<uuid:pk>/modal/toggle-active/',            modal_views.discount_toggle_active_modal,       name='discount_toggle_active_modal'),


    # =========================================================================
    # STUDENT DISCOUNT AWARDS
    # =========================================================================
    path('discounts/awards/',                                   views.student_discount_list,                    name='student_discount_list'),
    path('discounts/awards/create/',                            views.student_discount_create,                  name='student_discount_create'),
    path('discounts/awards/print/',                             views.student_discount_list_print_view,         name='student_discount_list_print'),
    path('discounts/awards/export/',                            views.export_student_discounts_excel,           name='export_student_discounts_excel'),
    path('discounts/awards/<uuid:pk>/',                         views.student_discount_detail,                  name='student_discount_detail'),
    path('discounts/awards/<uuid:pk>/edit/',                    views.student_discount_edit,                    name='student_discount_edit'),
    path('discounts/awards/<uuid:pk>/delete/',                  views.student_discount_delete,                  name='student_discount_delete'),
    path('discounts/awards/<uuid:pk>/suspend/',                 views.student_discount_suspend,                 name='student_discount_suspend'),
    path('discounts/awards/<uuid:pk>/revoke/',                  views.student_discount_revoke,                  name='student_discount_revoke'),

    # Student discount award modals
    path('discounts/awards/<uuid:pk>/modal/delete/',            modal_views.student_discount_delete_modal,      name='student_discount_delete_modal'),
    path('discounts/awards/<uuid:pk>/modal/suspend/',           modal_views.student_discount_suspend_modal,     name='student_discount_suspend_modal'),
    path('discounts/awards/<uuid:pk>/modal/revoke/',            modal_views.student_discount_revoke_modal,      name='student_discount_revoke_modal'),
    path('discounts/awards/<uuid:pk>/modal/quick-view/',        modal_views.student_discount_quick_view_modal,  name='student_discount_quick_view_modal'),


    # =========================================================================
    # DISCOUNT APPLICATIONS
    # =========================================================================
    # Reverse a specific DiscountApplication record
    path('discounts/applications/<uuid:pk>/reverse/',           views.discount_application_reverse,             name='discount_application_reverse'),

    # Discount application modals
    path('discounts/applications/<uuid:pk>/modal/reverse/',     modal_views.discount_application_reverse_modal, name='discount_application_reverse_modal'),


    # =========================================================================
    # REFUNDS  (Payment.refunded=True — no separate Refund model)
    # =========================================================================
    path('refunds/',                                            views.refund_list,                              name='refund_list'),
    path('refunds/print/',                                      views.refund_list_print_view,                   name='refund_list_print'),
    path('refunds/export/',                                     views.export_refunds_excel,                     name='export_refunds_excel'),
    # Refund processing is done through payments/<pk>/refund/
    # No separate refund create/detail/delete/approve views exist


    # =========================================================================
    # REPORTS
    # =========================================================================
    path('reports/',                                            views.reports_index,                            name='reports_index'),
    path('reports/financial-summary/',                          views.financial_summary_report,                 name='financial_summary_report'),
    path('reports/collection/',                                 views.collection_report,                        name='collection_report'),
    path('reports/outstanding/',                                views.outstanding_report,                       name='outstanding_report'),
    path('reports/scholarships/',                               views.scholarship_report,                       name='scholarship_report'),
    path('reports/discounts/',                                  views.discount_report,                          name='discount_report'),


    # =========================================================================
    # API ENDPOINTS  (HTMX / AJAX)
    # =========================================================================
    path('api/student-invoices/',                               views.api_get_student_invoices,                 name='api_get_student_invoices'),
    path('api/validate-invoice-numbers/',                       views.api_validate_invoice_numbers,             name='api_validate_invoice_numbers'),
]