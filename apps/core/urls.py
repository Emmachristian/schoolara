# core/urls.py
"""
URL Configuration for Core Module

Organized into three main sections:
1. Regular Views (views.py) - Full page loads and redirects
2. Modal Views (modal_views.py) - HTMX modal actions without page refresh
3. HTMX Views (htmx_views.py) - Dynamic search and filtering

All URLs use UUID primary keys for security
Modern HTMX endpoints use clean RESTful patterns
Legacy endpoints maintained for backward compatibility
"""
from django.urls import path
from . import views, htmx_views, modal_views

app_name = 'core'

urlpatterns = [
    # =============================================================================
    # DASHBOARD
    # =============================================================================
    path('', views.core_dashboard, name='home'),
    
    # =============================================================================
    # SCHOOL CONFIGURATION
    # =============================================================================
    # Regular Views
    path('configuration/edit/', views.school_configuration_edit, name='configuration_edit'),
    
    # =============================================================================
    # FINANCIAL SETTINGS
    # =============================================================================
    # Regular Views
    path('financial-settings/edit/', views.financial_settings_edit, name='financial_settings_edit'),
    path('financial-settings/mappings/<str:mapping_type>/edit/', views.account_mappings_edit, name='account_mappings_edit'),
    
    # =============================================================================
    # FISCAL YEAR & PERIOD MANAGEMENT (COMBINED VIEW)
    # =============================================================================
    # Main combined management view
    path('fiscal-management/', views.fiscal_management_view, name='fiscal_management'),
    
    # =============================================================================
    # FISCAL YEARS
    # =============================================================================
    # Regular Views (Legacy - for backward compatibility)
    path('fiscal-years/', views.fiscal_year_list, name='fiscal_year_list'),
    path('fiscal-years/create/', views.fiscal_year_create, name='fiscal_year_create'),
    path('fiscal-years/<uuid:pk>/', views.fiscal_year_detail, name='fiscal_year_detail'),
    path('fiscal-years/<uuid:pk>/edit/', views.fiscal_year_edit, name='fiscal_year_edit'),
    path('fiscal-years/print/', views.fiscal_year_print_view, name='fiscal_year_print_view'),
    
    # Modern HTMX Modal Endpoints (Create/Edit Forms)
    path('fiscal-years/htmx/modal/create/', modal_views.fiscal_year_modal_form, name='fiscal_year_modal_create'),
    path('fiscal-years/htmx/modal/<uuid:pk>/edit/', modal_views.fiscal_year_modal_form, name='fiscal_year_modal_edit'),
    
    # Modern HTMX Quick Actions (Single endpoint for all actions)
    path('fiscal-years/htmx/<uuid:pk>/quick-action/<str:action>/', modal_views.fiscal_year_quick_action, name='fiscal_year_quick_action'),
    
    # Legacy Modal Views (for backward compatibility)
    path('fiscal-years/<uuid:pk>/modal/delete/', modal_views.fiscal_year_delete_modal, name='fiscal_year_delete_modal'),
    path('fiscal-years/<uuid:pk>/modal/delete/submit/', modal_views.fiscal_year_delete, name='fiscal_year_delete'),
    path('fiscal-years/<uuid:pk>/modal/set-active/', modal_views.fiscal_year_set_active_modal, name='fiscal_year_set_active_modal'),
    path('fiscal-years/<uuid:pk>/modal/set-active/submit/', modal_views.fiscal_year_set_active, name='fiscal_year_set_active'),
    path('fiscal-years/<uuid:pk>/modal/close/', modal_views.fiscal_year_close_modal, name='fiscal_year_close_modal'),
    path('fiscal-years/<uuid:pk>/close/', modal_views.fiscal_year_close, name='fiscal_year_close'),
    path('fiscal-years/<uuid:pk>/lock/', modal_views.fiscal_year_lock, name='fiscal_year_lock'),
    path('fiscal-years/<uuid:pk>/unlock/', modal_views.fiscal_year_unlock, name='fiscal_year_unlock'),
    
    # HTMX Search/Filter Views
    path('fiscal-years/htmx/search/', htmx_views.fiscal_year_search, name='fiscal_year_search'),
    
    # =============================================================================
    # FISCAL PERIODS
    # =============================================================================
    # Regular Views (Legacy - for backward compatibility)
    path('fiscal-periods/', views.fiscal_period_list, name='fiscal_period_list'),
    path('fiscal-periods/create/', views.fiscal_period_create, name='fiscal_period_create'),
    path('fiscal-periods/<uuid:pk>/', views.fiscal_period_detail, name='fiscal_period_detail'),
    path('fiscal-periods/<uuid:pk>/edit/', views.fiscal_period_edit, name='fiscal_period_edit'),
    path('fiscal-periods/print/', views.fiscal_period_print_view, name='fiscal_period_print_view'),
    
    # Modern HTMX Modal Endpoints (Create/Edit Forms)
    path('periods/htmx/modal/create/', modal_views.period_modal_form, name='period_modal_create'),
    path('periods/htmx/modal/<uuid:pk>/edit/', modal_views.period_modal_form, name='period_modal_edit'),
    
    # Modern HTMX Quick Actions (Single endpoint for all actions)
    path('periods/htmx/<uuid:pk>/quick-action/<str:action>/', modal_views.period_quick_action, name='period_quick_action'),
    
    # Legacy Modal Views (for backward compatibility)
    path('fiscal-periods/<uuid:pk>/modal/delete/', modal_views.fiscal_period_delete_modal, name='fiscal_period_delete_modal'),
    path('fiscal-periods/<uuid:pk>/modal/delete/submit/', modal_views.fiscal_period_delete, name='fiscal_period_delete'),
    path('fiscal-periods/<uuid:pk>/modal/close/', modal_views.fiscal_period_close_modal, name='fiscal_period_close_modal'),
    path('fiscal-periods/<uuid:pk>/modal/reopen/', modal_views.fiscal_period_reopen_modal, name='fiscal_period_reopen_modal'),
    path('fiscal-periods/<uuid:pk>/modal/reopen/submit/', modal_views.fiscal_period_reopen, name='fiscal_period_reopen'),
    path('fiscal-periods/<uuid:pk>/close/', modal_views.fiscal_period_close, name='fiscal_period_close'),
    
    # HTMX Search/Filter Views
    path('fiscal-periods/htmx/search/', htmx_views.fiscal_period_search, name='fiscal_period_search'),
    
    # =============================================================================
    # BULK OPERATIONS
    # =============================================================================
    path('fiscal-periods/modal/bulk-close/', modal_views.bulk_close_periods_modal, name='bulk_close_periods_modal'),
    path('fiscal-periods/modal/bulk-close/submit/', modal_views.bulk_close_periods, name='bulk_close_periods'),
    
    # =============================================================================
    # PAYMENT METHODS
    # =============================================================================
    # Regular Views
    path('payment-methods/', views.payment_method_list, name='payment_method_list'),
    path('payment-methods/create/', views.payment_method_create, name='payment_method_create'),
    path('payment-methods/<uuid:pk>/', views.payment_method_detail, name='payment_method_detail'),
    path('payment-methods/<uuid:pk>/edit/', views.payment_method_edit, name='payment_method_edit'),
    path('payment-methods/print/', views.payment_method_print_view, name='payment_method_print_view'),
    
    # Modal Views
    path('payment-methods/<uuid:pk>/modal/delete/', modal_views.payment_method_delete_modal, name='payment_method_delete_modal'),
    path('payment-methods/<uuid:pk>/modal/delete/submit/', modal_views.payment_method_delete, name='payment_method_delete'),
    path('payment-methods/<uuid:pk>/modal/toggle-status/', modal_views.payment_method_toggle_status_modal, name='payment_method_toggle_status_modal'),
    path('payment-methods/<uuid:pk>/modal/toggle-status/submit/', modal_views.payment_method_toggle_status, name='payment_method_toggle_status'),
    
    # HTMX Views
    path('payment-methods/htmx/search/', htmx_views.payment_method_search, name='payment_method_search'),
    
    # =============================================================================
    # TAX RATES
    # =============================================================================
    # Regular Views
    path('tax-rates/', views.tax_rate_list, name='tax_rate_list'),
    path('tax-rates/create/', views.tax_rate_create, name='tax_rate_create'),
    path('tax-rates/<uuid:pk>/', views.tax_rate_detail, name='tax_rate_detail'),
    path('tax-rates/<uuid:pk>/edit/', views.tax_rate_edit, name='tax_rate_edit'),
    path('tax-rates/print/', views.tax_rate_print_view, name='tax_rate_print_view'),
    
    # Modal Views
    path('tax-rates/<uuid:pk>/modal/delete/', modal_views.tax_rate_delete_modal, name='tax_rate_delete_modal'),
    path('tax-rates/<uuid:pk>/modal/delete/submit/', modal_views.tax_rate_delete, name='tax_rate_delete'),
    
    # HTMX Views
    path('tax-rates/htmx/search/', htmx_views.tax_rate_search, name='tax_rate_search'),
    
    # =============================================================================
    # UNITS OF MEASURE
    # =============================================================================
    # Regular Views
    path('units/', views.unit_of_measure_list, name='unit_of_measure_list'),
    path('units/create/', views.unit_of_measure_create, name='unit_of_measure_create'),
    path('units/<uuid:pk>/', views.unit_of_measure_detail, name='unit_of_measure_detail'),
    path('units/<uuid:pk>/edit/', views.unit_of_measure_edit, name='unit_of_measure_edit'),
    path('units/print/', views.unit_of_measure_print_view, name='unit_of_measure_print_view'),
    
    # Modal Views
    path('units/<uuid:pk>/modal/delete/', modal_views.unit_of_measure_delete_modal, name='unit_of_measure_delete_modal'),
    path('units/<uuid:pk>/modal/delete/submit/', modal_views.unit_of_measure_delete, name='unit_of_measure_delete'),
    path('units/modal/create-standard/', modal_views.create_standard_units_modal, name='create_standard_units_modal'),
    path('units/modal/create-standard/submit/', modal_views.create_standard_units, name='create_standard_units'),
    
    # HTMX Views
    path('units/htmx/search/', htmx_views.unit_of_measure_search, name='unit_of_measure_search'),
]