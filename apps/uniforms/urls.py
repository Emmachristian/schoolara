# uniforms/urls.py
from django.urls import path
from . import views, htmx_views

app_name = 'uniforms'

urlpatterns = [
    # =============================================================================
    # HTMX SEARCH ENDPOINTS
    # =============================================================================

    # Measurement Types
    path('htmx/measurement-types/search/', htmx_views.measurement_type_search, name='measurement_type_search'),

    # Student Measurements
    path('htmx/measurements/search/', htmx_views.student_measurement_search, name='measurement_search'),
    path('htmx/measurements/quick-stats/', htmx_views.measurement_quick_stats, name='measurement_quick_stats'),

    # Uniform Sizes
    path('htmx/sizes/search/', htmx_views.uniform_size_search, name='size_search'),

    # Uniform Items
    path('htmx/items/search/', htmx_views.uniform_item_search, name='item_search'),
    path('htmx/items/quick-stats/', htmx_views.inventory_quick_stats, name='inventory_quick_stats'),

    # Uniform Stock
    path('htmx/stock/search/', htmx_views.uniform_stock_search, name='stock_search'),

    # Purchase Orders
    path('htmx/purchase-orders/search/', htmx_views.purchase_order_search, name='purchase_order_search'),
    path('htmx/purchase-orders/quick-stats/', htmx_views.purchase_order_quick_stats, name='purchase_order_quick_stats'),

    # Uniform Sales
    path('htmx/sales/search/', htmx_views.uniform_sale_search, name='sale_search'),
    path('htmx/sales/quick-stats/', htmx_views.sales_quick_stats, name='sales_quick_stats'),

    # Student Uniform Sizes
    path('htmx/student-sizes/search/', htmx_views.student_uniform_size_search, name='student_size_search'),

    # Measurement Sessions
    path('htmx/measurement-sessions/search/', htmx_views.measurement_session_search, name='measurement_session_search'),

]
