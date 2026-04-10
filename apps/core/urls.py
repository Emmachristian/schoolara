# core/urls.py

"""
URL Configuration for Core Module

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
  <entity>_list             → full list page
  <entity>_create           → create form page
  <entity>_detail           → detail page
  <entity>_edit             → edit form page
  <entity>_delete           → POST-only delete action
  <entity>_print_view       → filtered list print view (no pk)
  export_<entity>_excel     → filtered list Excel export (no pk)
  <entity>_<action>_modal   → HTMX modal partial loader
  <entity>_quick_stats      → JSON quick-stats endpoint

Entities
--------
  - dashboard
  - configuration (school + financial + account mappings)
  - fiscal_management  (combined accordion page)
  - fiscal_year
  - fiscal_period
  - payment_method
  - tax_rate
  - unit_of_measure
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

    path('configuration/', views.school_configuration_edit, name='school_configuration_edit'),

    # =========================================================================
    # FINANCIAL SETTINGS
    # =========================================================================

    path('financial-settings/',                                views.financial_settings_edit, name='financial_settings_edit'),
    path('financial-settings/mappings/<str:mapping_type>/',    views.account_mappings_edit,   name='account_mappings_edit'),

    # =========================================================================
    # FISCAL MANAGEMENT — combined accordion
    # =========================================================================

    path('fiscal/', views.fiscal_management_view, name='fiscal_management'),

    # =========================================================================
    # FISCAL YEARS
    # =========================================================================

    # Static — print / export / stats / bulk (must come before <uuid:pk>)
    path('fiscal/years/print/',                          views.fiscal_year_print_view,              name='fiscal_year_print_view'),
    path('fiscal/years/export/excel/',                   views.fiscal_year_export_excel,            name='export_fiscal_years_excel'),
    path('fiscal/years/ajax/quick-stats/',               views.fiscal_year_quick_stats,             name='fiscal_year_quick_stats'),
    path('fiscal/years/bulk/close-periods/modal/',       modal_views.bulk_close_periods_modal,      name='bulk_close_periods_modal'),
    path('fiscal/years/bulk/close-periods/',             modal_views.bulk_close_periods,            name='bulk_close_periods'),

    # Static modals — create (no pk; must come before <uuid:pk>)
    path('fiscal/years/modal/create/',                   modal_views.fiscal_year_modal_form,        name='fiscal_year_create_modal'),

    # Dynamic — detail + delete
    path('fiscal/years/<uuid:pk>/',                      views.fiscal_year_detail,                  name='fiscal_year_detail'),
    path('fiscal/years/<uuid:pk>/delete/',               modal_views.fiscal_year_delete,            name='fiscal_year_delete'),

    # Dynamic modals
    path('fiscal/years/<uuid:pk>/modal/edit/',           modal_views.fiscal_year_modal_form,        name='fiscal_year_edit_modal'),
    path('fiscal/years/<uuid:pk>/modal/delete/',         modal_views.fiscal_year_delete_modal,      name='fiscal_year_delete_modal'),
    path('fiscal/years/<uuid:pk>/modal/set-active/',     modal_views.fiscal_year_set_active_modal,  name='fiscal_year_set_active_modal'),
    path('fiscal/years/<uuid:pk>/modal/close/',          modal_views.fiscal_year_close_modal,       name='fiscal_year_close_modal'),

    # Quick action POST — activate / close / lock / unlock
    path('fiscal/years/<uuid:pk>/action/<str:action>/',  modal_views.fiscal_year_quick_action,      name='fiscal_year_quick_action'),

    # Legacy direct-POST (backward-compat; prefer quick_action above)
    path('fiscal/years/<uuid:pk>/set-active/',           modal_views.fiscal_year_set_active,        name='fiscal_year_set_active'),
    path('fiscal/years/<uuid:pk>/close/',                modal_views.fiscal_year_close,             name='fiscal_year_close'),
    path('fiscal/years/<uuid:pk>/lock/',                 modal_views.fiscal_year_lock,              name='fiscal_year_lock'),
    path('fiscal/years/<uuid:pk>/unlock/',               modal_views.fiscal_year_unlock,            name='fiscal_year_unlock'),

    # =========================================================================
    # FISCAL PERIODS
    # =========================================================================

    # Static — print / export / stats (must come before <uuid:pk>)
    path('fiscal/periods/print/',                        views.fiscal_period_print_view,            name='fiscal_period_print_view'),
    path('fiscal/periods/export/excel/',                 views.fiscal_period_export_excel,          name='export_fiscal_periods_excel'),
    path('fiscal/periods/ajax/quick-stats/',             views.fiscal_period_quick_stats,           name='fiscal_period_quick_stats'),

    # Static modals — create (no pk; must come before <uuid:pk>)
    path('fiscal/periods/modal/create/',                 modal_views.period_modal_form,             name='fiscal_period_create_modal'),

    # Dynamic — detail + delete
    path('fiscal/periods/<uuid:pk>/',                    views.fiscal_period_detail,                name='fiscal_period_detail'),
    path('fiscal/periods/<uuid:pk>/delete/',             modal_views.fiscal_period_delete,          name='fiscal_period_delete'),

    # Dynamic modals
    path('fiscal/periods/<uuid:pk>/modal/edit/',         modal_views.period_modal_form,             name='fiscal_period_edit_modal'),
    path('fiscal/periods/<uuid:pk>/modal/delete/',       modal_views.fiscal_period_delete_modal,    name='fiscal_period_delete_modal'),
    path('fiscal/periods/<uuid:pk>/modal/close/',        modal_views.fiscal_period_close_modal,     name='fiscal_period_close_modal'),
    path('fiscal/periods/<uuid:pk>/modal/reopen/',       modal_views.fiscal_period_reopen_modal,    name='fiscal_period_reopen_modal'),

    # Quick action POST — activate / close / lock / unlock / reopen
    path('fiscal/periods/<uuid:pk>/action/<str:action>/',modal_views.period_quick_action,           name='fiscal_period_quick_action'),

    # Legacy direct-POST (backward-compat; prefer quick_action above)
    path('fiscal/periods/<uuid:pk>/close/',              modal_views.fiscal_period_close,           name='fiscal_period_close'),
    path('fiscal/periods/<uuid:pk>/reopen/',             modal_views.fiscal_period_reopen,          name='fiscal_period_reopen'),

    # =========================================================================
    # PAYMENT METHODS
    # =========================================================================

    # Static — list / print / export / stats / create (must come before <uuid:pk>)
    path('payment-methods/',                             views.payment_method_list,                 name='payment_method_list'),
    path('payment-methods/print/',                       views.payment_method_print_view,           name='payment_method_print_view'),
    path('payment-methods/export/excel/',                views.payment_method_export_excel,         name='export_payment_methods_excel'),
    path('payment-methods/create/',                      views.payment_method_create,               name='payment_method_create'),
    path('payment-methods/ajax/quick-stats/',            views.payment_method_quick_stats,          name='payment_method_quick_stats'),

    # Static modals — create (no pk; must come before <uuid:pk>)
    path('payment-methods/modal/create/',                modal_views.payment_method_modal_form,     name='payment_method_create_modal'),

    # Dynamic — detail + CRUD
    path('payment-methods/<uuid:pk>/',                   views.payment_method_detail,               name='payment_method_detail'),
    path('payment-methods/<uuid:pk>/edit/',              views.payment_method_edit,                 name='payment_method_edit'),
    path('payment-methods/<uuid:pk>/delete/',            modal_views.payment_method_delete,         name='payment_method_delete'),
    path('payment-methods/<uuid:pk>/toggle-status/',     modal_views.payment_method_toggle_status,  name='payment_method_toggle_status'),

    # Dynamic modals
    path('payment-methods/<uuid:pk>/modal/edit/',        modal_views.payment_method_modal_form,     name='payment_method_edit_modal'),
    path('payment-methods/<uuid:pk>/modal/delete/',      modal_views.payment_method_delete_modal,   name='payment_method_delete_modal'),
    path('payment-methods/<uuid:pk>/modal/toggle-status/', modal_views.payment_method_toggle_status_modal, name='payment_method_toggle_status_modal'),

    # =========================================================================
    # TAX RATES
    # =========================================================================

    # Static — list / print / export / stats / create (must come before <uuid:pk>)
    path('tax-rates/',                                   views.tax_rate_list,                       name='tax_rate_list'),
    path('tax-rates/print/',                             views.tax_rate_print_view,                 name='tax_rate_print_view'),
    path('tax-rates/export/excel/',                      views.tax_rate_export_excel,               name='export_tax_rates_excel'),
    path('tax-rates/create/',                            views.tax_rate_create,                     name='tax_rate_create'),
    path('tax-rates/ajax/quick-stats/',                  views.tax_rate_quick_stats,                name='tax_rate_quick_stats'),

    # Static modals — create (no pk; must come before <uuid:pk>)
    path('tax-rates/modal/create/',                      modal_views.tax_rate_modal_form,           name='tax_rate_create_modal'),

    # Dynamic — detail + CRUD
    path('tax-rates/<uuid:pk>/',                         views.tax_rate_detail,                     name='tax_rate_detail'),
    path('tax-rates/<uuid:pk>/edit/',                    views.tax_rate_edit,                       name='tax_rate_edit'),
    path('tax-rates/<uuid:pk>/delete/',                  modal_views.tax_rate_delete,               name='tax_rate_delete'),

    # Dynamic modals
    path('tax-rates/<uuid:pk>/modal/edit/',              modal_views.tax_rate_modal_form,           name='tax_rate_edit_modal'),
    path('tax-rates/<uuid:pk>/modal/delete/',            modal_views.tax_rate_delete_modal,         name='tax_rate_delete_modal'),

    # =========================================================================
    # UNITS OF MEASURE
    # =========================================================================

    # Static — list / print / export / stats / create (must come before <uuid:pk>)
    path('units/',                                       views.unit_of_measure_list,                name='unit_of_measure_list'),
    path('units/print/',                                 views.unit_of_measure_print_view,          name='unit_of_measure_print_view'),
    path('units/export/excel/',                          views.unit_of_measure_export_excel,        name='export_units_excel'),
    path('units/create/',                                views.unit_of_measure_create,              name='unit_of_measure_create'),
    path('units/ajax/quick-stats/',                      views.unit_of_measure_quick_stats,         name='unit_of_measure_quick_stats'),

    # Static modals — create / standard (no pk; must come before <uuid:pk>)
    path('units/modal/create/',                          modal_views.unit_of_measure_modal_form,    name='unit_of_measure_create_modal'),
    path('units/modal/create-standard/',                 modal_views.create_standard_units_modal,   name='create_standard_units_modal'),
    path('units/create-standard/',                       modal_views.create_standard_units,         name='create_standard_units'),

    # Dynamic — detail + CRUD
    path('units/<uuid:pk>/',                             views.unit_of_measure_detail,              name='unit_of_measure_detail'),
    path('units/<uuid:pk>/edit/',                        views.unit_of_measure_edit,                name='unit_of_measure_edit'),
    path('units/<uuid:pk>/delete/',                      modal_views.unit_of_measure_delete,        name='unit_of_measure_delete'),

    # Dynamic modals
    path('units/<uuid:pk>/modal/edit/',                  modal_views.unit_of_measure_modal_form,    name='unit_of_measure_edit_modal'),
    path('units/<uuid:pk>/modal/delete/',                modal_views.unit_of_measure_delete_modal,  name='unit_of_measure_delete_modal'),

    # =========================================================================
    # SYSTEM STATS — JSON endpoint
    # =========================================================================

    path('ajax/system-stats/', views.system_configuration_stats, name='system_configuration_stats'),
]