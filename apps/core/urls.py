# core/urls.py
from django.urls import path
from . import views, htmx_views

app_name = 'core'

urlpatterns = [
     path("home/", views.home, name="home"),

     # =============================================================================
     # HTMX SEARCH ENDPOINTS
     # =============================================================================

     # Fiscal Years
     path('htmx/fiscal-years/search/', htmx_views.fiscal_year_search, name='fiscal_year_search'),
     path('htmx/fiscal-years/quick-stats/', htmx_views.fiscal_year_quick_stats, name='fiscal_year_quick_stats'),

     # Fiscal Periods
     path('htmx/fiscal-periods/search/', htmx_views.fiscal_period_search, name='fiscal_period_search'),
     path('htmx/fiscal-periods/quick-stats/', htmx_views.fiscal_period_quick_stats, name='fiscal_period_quick_stats'),

     # Payment Methods
     path('htmx/payment-methods/search/', htmx_views.payment_method_search, name='payment_method_search'),
     path('htmx/payment-methods/quick-stats/', htmx_views.payment_method_quick_stats, name='payment_method_quick_stats'),

     # Tax Rates
     path('htmx/tax-rates/search/', htmx_views.tax_rate_search, name='tax_rate_search'),
     path('htmx/tax-rates/quick-stats/', htmx_views.tax_rate_quick_stats, name='tax_rate_quick_stats'),

     # Units of Measure
     path('htmx/units/search/', htmx_views.unit_of_measure_search, name='unit_search'),
     path('htmx/units/quick-stats/', htmx_views.unit_of_measure_quick_stats, name='unit_quick_stats'),

     # System Configuration
     path('htmx/system/quick-stats/', htmx_views.system_configuration_stats, name='system_configuration_stats'),

]
