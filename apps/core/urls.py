# core/urls.py
"""
URL Configuration for Core Module

Fiscal year / period CRUD
--------------------------
List, create, and edit for fiscal years and periods are handled entirely
by fiscal_management_view (accordion) + modal endpoints.
Only detail and print pages remain as standalone full-page routes.

Search / filter
---------------
Each list view detects the HX-Request header and returns the results
partial when called by HTMX, so *_search aliases point to the same view.

Quick-stats JSON
----------------
Lightweight endpoints for dashboard widgets at /stats/…
"""

from django.urls import path
from . import views, modal_views

app_name = 'core'

urlpatterns = [

    # =========================================================================
    # DASHBOARD
    # =========================================================================
    path('', views.core_dashboard, name='home'),

    # =========================================================================
    # SCHOOL CONFIGURATION
    # =========================================================================
    path(
        'configuration/edit/',
        views.school_configuration_edit,
        name='configuration_edit',
    ),

    # =========================================================================
    # FINANCIAL SETTINGS
    # =========================================================================
    path(
        'financial-settings/edit/',
        views.financial_settings_edit,
        name='financial_settings_edit',
    ),
    path(
        'financial-settings/mappings/<str:mapping_type>/edit/',
        views.account_mappings_edit,
        name='account_mappings_edit',
    ),

    # =========================================================================
    # FISCAL MANAGEMENT — single accordion page
    # =========================================================================
    path(
        'fiscal-management/',
        views.fiscal_management_view,
        name='fiscal_management',
    ),

    # =========================================================================
    # FISCAL YEARS
    # detail + print are the only standalone full-page routes;
    # list / create / edit are replaced by fiscal_management + modal endpoints.
    # =========================================================================
    path('fiscal-years/print/',         views.fiscal_year_print_view, name='fiscal_year_print_view'),
    path('fiscal-years/<uuid:pk>/',     views.fiscal_year_detail,     name='fiscal_year_detail'),

    # HTMX modal — create / edit
    path(
        'fiscal-years/htmx/modal/create/',
        modal_views.fiscal_year_modal_form,
        name='fiscal_year_modal_create',
    ),
    path(
        'fiscal-years/htmx/modal/<uuid:pk>/edit/',
        modal_views.fiscal_year_modal_form,
        name='fiscal_year_modal_edit',
    ),

    # HTMX quick action (activate / close / lock / unlock)
    path(
        'fiscal-years/htmx/<uuid:pk>/quick-action/<str:action>/',
        modal_views.fiscal_year_quick_action,
        name='fiscal_year_quick_action',
    ),

    # Delete modal (GET = confirmation, POST = execute)
    path(
        'fiscal-years/<uuid:pk>/modal/delete/',
        modal_views.fiscal_year_delete_modal,
        name='fiscal_year_delete_modal',
    ),

    # Legacy endpoints kept for backward compatibility
    path(
        'fiscal-years/<uuid:pk>/modal/delete/submit/',
        modal_views.fiscal_year_delete,
        name='fiscal_year_delete',
    ),
    path(
        'fiscal-years/<uuid:pk>/modal/set-active/',
        modal_views.fiscal_year_set_active_modal,
        name='fiscal_year_set_active_modal',
    ),
    path(
        'fiscal-years/<uuid:pk>/modal/set-active/submit/',
        modal_views.fiscal_year_set_active,
        name='fiscal_year_set_active',
    ),
    path(
        'fiscal-years/<uuid:pk>/modal/close/',
        modal_views.fiscal_year_close_modal,
        name='fiscal_year_close_modal',
    ),
    path(
        'fiscal-years/<uuid:pk>/close/',
        modal_views.fiscal_year_close,
        name='fiscal_year_close',
    ),
    path(
        'fiscal-years/<uuid:pk>/lock/',
        modal_views.fiscal_year_lock,
        name='fiscal_year_lock',
    ),
    path(
        'fiscal-years/<uuid:pk>/unlock/',
        modal_views.fiscal_year_unlock,
        name='fiscal_year_unlock',
    ),

    # =========================================================================
    # FISCAL PERIODS
    # detail + print are the only standalone full-page routes.
    # =========================================================================
    path('fiscal-periods/print/',         views.fiscal_period_print_view, name='fiscal_period_print_view'),
    path('fiscal-periods/<uuid:pk>/',     views.fiscal_period_detail,     name='fiscal_period_detail'),

    # HTMX modal — create / edit
    path(
        'periods/htmx/modal/create/',
        modal_views.period_modal_form,
        name='period_modal_create',
    ),
    path(
        'periods/htmx/modal/<uuid:pk>/edit/',
        modal_views.period_modal_form,
        name='period_modal_edit',
    ),

    # HTMX quick action (activate / close / lock / unlock / reopen)
    path(
        'periods/htmx/<uuid:pk>/quick-action/<str:action>/',
        modal_views.period_quick_action,
        name='period_quick_action',
    ),

    # Delete modal
    path(
        'fiscal-periods/<uuid:pk>/modal/delete/',
        modal_views.fiscal_period_delete_modal,
        name='fiscal_period_delete_modal',
    ),

    # Legacy endpoints
    path(
        'fiscal-periods/<uuid:pk>/modal/delete/submit/',
        modal_views.fiscal_period_delete,
        name='fiscal_period_delete',
    ),
    path(
        'fiscal-periods/<uuid:pk>/modal/close/',
        modal_views.fiscal_period_close_modal,
        name='fiscal_period_close_modal',
    ),
    path(
        'fiscal-periods/<uuid:pk>/modal/reopen/',
        modal_views.fiscal_period_reopen_modal,
        name='fiscal_period_reopen_modal',
    ),
    path(
        'fiscal-periods/<uuid:pk>/modal/reopen/submit/',
        modal_views.fiscal_period_reopen,
        name='fiscal_period_reopen',
    ),
    path(
        'fiscal-periods/<uuid:pk>/close/',
        modal_views.fiscal_period_close,
        name='fiscal_period_close',
    ),

    # =========================================================================
    # BULK OPERATIONS
    # =========================================================================
    path(
        'fiscal-periods/modal/bulk-close/',
        modal_views.bulk_close_periods_modal,
        name='bulk_close_periods_modal',
    ),
    path(
        'fiscal-periods/modal/bulk-close/submit/',
        modal_views.bulk_close_periods,
        name='bulk_close_periods',
    ),

    # =========================================================================
    # PAYMENT METHODS — full CRUD
    # =========================================================================
    path('payment-methods/',                views.payment_method_list,       name='payment_method_list'),
    path('payment-methods/create/',         views.payment_method_create,     name='payment_method_create'),
    path('payment-methods/print/',          views.payment_method_print_view, name='payment_method_print_view'),
    path('payment-methods/<uuid:pk>/',      views.payment_method_detail,     name='payment_method_detail'),
    path('payment-methods/<uuid:pk>/edit/', views.payment_method_edit,       name='payment_method_edit'),

    # HTMX search alias
    path(
        'payment-methods/htmx/search/',
        views.payment_method_list,
        name='payment_method_search',
    ),

    # Modals
    path(
        'payment-methods/<uuid:pk>/modal/delete/',
        modal_views.payment_method_delete_modal,
        name='payment_method_delete_modal',
    ),
    path(
        'payment-methods/<uuid:pk>/modal/delete/submit/',
        modal_views.payment_method_delete,
        name='payment_method_delete',
    ),
    path(
        'payment-methods/<uuid:pk>/modal/toggle-status/',
        modal_views.payment_method_toggle_status_modal,
        name='payment_method_toggle_status_modal',
    ),
    path(
        'payment-methods/<uuid:pk>/modal/toggle-status/submit/',
        modal_views.payment_method_toggle_status,
        name='payment_method_toggle_status',
    ),

    # =========================================================================
    # TAX RATES — full CRUD
    # =========================================================================
    path('tax-rates/',                views.tax_rate_list,       name='tax_rate_list'),
    path('tax-rates/create/',         views.tax_rate_create,     name='tax_rate_create'),
    path('tax-rates/print/',          views.tax_rate_print_view, name='tax_rate_print_view'),
    path('tax-rates/<uuid:pk>/',      views.tax_rate_detail,     name='tax_rate_detail'),
    path('tax-rates/<uuid:pk>/edit/', views.tax_rate_edit,       name='tax_rate_edit'),

    # HTMX search alias
    path(
        'tax-rates/htmx/search/',
        views.tax_rate_list,
        name='tax_rate_search',
    ),

    # Modals
    path(
        'tax-rates/<uuid:pk>/modal/delete/',
        modal_views.tax_rate_delete_modal,
        name='tax_rate_delete_modal',
    ),
    path(
        'tax-rates/<uuid:pk>/modal/delete/submit/',
        modal_views.tax_rate_delete,
        name='tax_rate_delete',
    ),

    # =========================================================================
    # UNITS OF MEASURE — full CRUD
    # =========================================================================
    path('units/',                views.unit_of_measure_list,       name='unit_of_measure_list'),
    path('units/create/',         views.unit_of_measure_create,     name='unit_of_measure_create'),
    path('units/print/',          views.unit_of_measure_print_view, name='unit_of_measure_print_view'),
    path('units/<uuid:pk>/',      views.unit_of_measure_detail,     name='unit_of_measure_detail'),
    path('units/<uuid:pk>/edit/', views.unit_of_measure_edit,       name='unit_of_measure_edit'),

    # HTMX search alias
    path(
        'units/htmx/search/',
        views.unit_of_measure_list,
        name='unit_of_measure_search',
    ),

    # Modals
    path(
        'units/<uuid:pk>/modal/delete/',
        modal_views.unit_of_measure_delete_modal,
        name='unit_of_measure_delete_modal',
    ),
    path(
        'units/<uuid:pk>/modal/delete/submit/',
        modal_views.unit_of_measure_delete,
        name='unit_of_measure_delete',
    ),
    path(
        'units/modal/create-standard/',
        modal_views.create_standard_units_modal,
        name='create_standard_units_modal',
    ),
    path(
        'units/modal/create-standard/submit/',
        modal_views.create_standard_units,
        name='create_standard_units',
    ),

    # =========================================================================
    # JSON QUICK-STATS
    # =========================================================================
    path('stats/fiscal-years/',    views.fiscal_year_quick_stats,        name='fiscal_year_quick_stats'),
    path('stats/fiscal-periods/',  views.fiscal_period_quick_stats,      name='fiscal_period_quick_stats'),
    path('stats/payment-methods/', views.payment_method_quick_stats,     name='payment_method_quick_stats'),
    path('stats/tax-rates/',       views.tax_rate_quick_stats,           name='tax_rate_quick_stats'),
    path('stats/units/',           views.unit_of_measure_quick_stats,    name='unit_of_measure_quick_stats'),
    path('stats/system/',          views.system_configuration_stats,     name='system_configuration_stats'),
]