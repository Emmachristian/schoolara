# fees/urls.py

from django.urls import path
from . import views, htmx_views

app_name = 'fees'

urlpatterns = [
    # =============================================================================
    # DASHBOARD
    # =============================================================================
    path('', views.fees_dashboard, name='dashboard'),
    
    
    # =============================================================================
    # STUDENT ACCOUNT URLS
    # =============================================================================
    path('accounts/', views.student_account_list, name='student_account_list'),
    path('accounts/create/', views.student_account_create, name='student_account_create'),
    path('accounts/<int:pk>/', views.student_account_detail, name='student_account_detail'),
    path('accounts/<int:pk>/edit/', views.student_account_edit, name='student_account_edit'),
    
    
    # =============================================================================
    # DISPLAY GROUP URLS
    # =============================================================================
    path('display-groups/', views.display_group_list, name='display_group_list'),
    path('display-groups/create/', views.display_group_create, name='display_group_create'),
    path('display-groups/<int:pk>/edit/', views.display_group_edit, name='display_group_edit'),
    path('display-groups/<int:pk>/delete/', views.display_group_delete, name='display_group_delete'),
    
    
    # =============================================================================
    # FEE CATEGORY URLS
    # =============================================================================
    path('categories/', views.fee_category_list, name='fee_category_list'),
    path('categories/create/', views.fee_category_create, name='fee_category_create'),
    path('categories/<int:pk>/', views.fee_category_detail, name='fee_category_detail'),
    path('categories/<int:pk>/edit/', views.fee_category_edit, name='fee_category_edit'),
    path('categories/<int:pk>/delete/', views.fee_category_delete, name='fee_category_delete'),
    
    
    # =============================================================================
    # FEE STRUCTURE URLS
    # =============================================================================
    path('structures/', views.fee_structure_list, name='fee_structure_list'),
    path('structures/create/', views.fee_structure_create, name='fee_structure_create'),
    path('structures/<int:pk>/', views.fee_structure_detail, name='fee_structure_detail'),
    path('structures/<int:pk>/edit/', views.fee_structure_edit, name='fee_structure_edit'),
    path('structures/<int:pk>/delete/', views.fee_structure_delete, name='fee_structure_delete'),
    
    
    # =============================================================================
    # FEE INVOICE URLS
    # =============================================================================
    path('invoices/', views.fee_invoice_list, name='fee_invoice_list'),
    path('invoices/create/', views.fee_invoice_create, name='fee_invoice_create'),
    path('invoices/<int:pk>/', views.fee_invoice_detail, name='fee_invoice_detail'),
    path('invoices/<int:pk>/edit/', views.fee_invoice_edit, name='fee_invoice_edit'),
    path('invoices/<int:pk>/delete/', views.fee_invoice_delete, name='fee_invoice_delete'),
    
    
    # =============================================================================
    # PAYMENT URLS
    # =============================================================================
    path('payments/', views.payment_list, name='payment_list'),
    path('payments/create/', views.payment_create, name='payment_create'),
    path('payments/<int:pk>/', views.payment_detail, name='payment_detail'),
    path('payments/<int:pk>/edit/', views.payment_edit, name='payment_edit'),
    path('payments/<int:pk>/delete/', views.payment_delete, name='payment_delete'),
    path('payments/<int:pk>/verify/', views.payment_verify, name='payment_verify'),
    
    
    # =============================================================================
    # SCHOLARSHIP PROGRAM URLS
    # =============================================================================
    path('scholarships/programs/', views.scholarship_program_list, name='scholarship_program_list'),
    path('scholarships/programs/create/', views.scholarship_program_create, name='scholarship_program_create'),
    path('scholarships/programs/<int:pk>/', views.scholarship_program_detail, name='scholarship_program_detail'),
    path('scholarships/programs/<int:pk>/edit/', views.scholarship_program_edit, name='scholarship_program_edit'),
    path('scholarships/programs/<int:pk>/delete/', views.scholarship_program_delete, name='scholarship_program_delete'),
    
    
    # =============================================================================
    # STUDENT SCHOLARSHIP URLS
    # =============================================================================
    path('scholarships/awards/', views.student_scholarship_list, name='student_scholarship_list'),
    path('scholarships/awards/create/', views.student_scholarship_create, name='student_scholarship_create'),
    path('scholarships/awards/<int:pk>/', views.student_scholarship_detail, name='student_scholarship_detail'),
    path('scholarships/awards/<int:pk>/edit/', views.student_scholarship_edit, name='student_scholarship_edit'),
    
    
    # =============================================================================
    # SCHOLARSHIP APPLICATION URLS
    # =============================================================================
    path('scholarships/applications/', views.scholarship_application_list, name='scholarship_application_list'),
    path('scholarships/applications/create/', views.scholarship_application_create, name='scholarship_application_create'),
    path('scholarships/applications/<int:pk>/', views.scholarship_application_detail, name='scholarship_application_detail'),
    path('scholarships/applications/<int:pk>/review/', views.scholarship_application_review, name='scholarship_application_review'),
    
    
    # =============================================================================
    # DISCOUNT URLS
    # =============================================================================
    path('discounts/', views.discount_list, name='discount_list'),
    path('discounts/create/', views.discount_create, name='discount_create'),
    path('discounts/<int:pk>/', views.discount_detail, name='discount_detail'),
    path('discounts/<int:pk>/edit/', views.discount_edit, name='discount_edit'),
    path('discounts/<int:pk>/delete/', views.discount_delete, name='discount_delete'),
    
    
    # =============================================================================
    # REFUND URLS
    # =============================================================================
    path('refunds/', views.refund_list, name='refund_list'),
    path('refunds/create/', views.refund_create, name='refund_create'),
    path('refunds/<int:pk>/', views.refund_detail, name='refund_detail'),
    path('refunds/<int:pk>/edit/', views.refund_edit, name='refund_edit'),
    path('refunds/<int:pk>/delete/', views.refund_delete, name='refund_delete'),
    path('refunds/<int:pk>/approve/', views.refund_approve, name='refund_approve'),
    
    
    # =============================================================================
    # HTMX SEARCH ENDPOINTS
    # =============================================================================
    
    # Student Accounts
    path('htmx/accounts/search/', htmx_views.student_account_search, name='account_search'),
    
    # Account Transactions
    path('htmx/transactions/search/', htmx_views.account_transaction_search, name='transaction_search'),
    
    # Display Groups
    path('htmx/display-groups/search/', htmx_views.display_group_search, name='display_group_search'),
    
    # Fee Categories
    path('htmx/categories/search/', htmx_views.fee_category_search, name='category_search'),
    
    # Fee Structures
    path('htmx/structures/search/', htmx_views.fee_structure_search, name='structure_search'),
    
    # Invoices
    path('htmx/invoices/search/', htmx_views.fee_invoice_search, name='invoice_search'),
    path('htmx/invoices/quick-stats/', htmx_views.invoice_quick_stats, name='invoice_quick_stats'),
    
    # Payments
    path('htmx/payments/search/', htmx_views.payment_search, name='payment_search'),
    path('htmx/payments/quick-stats/', htmx_views.payment_quick_stats, name='payment_quick_stats'),
    
    # Scholarship Programs
    path('htmx/scholarships/programs/search/', htmx_views.scholarship_program_search, name='scholarship_program_search'),
    path('htmx/scholarships/quick-stats/', htmx_views.scholarship_quick_stats, name='scholarship_quick_stats'),
    
    # Scholarship Applications
    path('htmx/scholarships/applications/search/', htmx_views.scholarship_application_search, name='scholarship_application_search'),
    
    # Student Scholarships
    path('htmx/scholarships/awards/search/', htmx_views.student_scholarship_search, name='student_scholarship_search'),
    
    # Discounts
    path('htmx/discounts/search/', htmx_views.discount_search, name='discount_search'),
    
    # Refunds
    path('htmx/refunds/search/', htmx_views.refund_search, name='refund_search'),
]