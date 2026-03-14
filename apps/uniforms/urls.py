# uniforms/urls.py

"""
URL Configuration for Uniforms Module
Organized into two main sections:

1. Regular Views (views.py) - Full page loads, list views (with HTMX support), and actions
2. Modal Views (modal_views.py) - HTMX modal content loaders

Key Architecture:
- List views handle BOTH full page loads AND HTMX requests
- Unified modals for create/edit operations (same modal, different mode)
- Action endpoints return HTMX responses with custom headers
- All URLs use UUID primary keys (pk)

Following the same pattern as academics and finance modules for consistency
"""

from django.urls import path
from . import views, modal_views

app_name = 'uniforms'

urlpatterns = [
    # =============================================================================
    # DASHBOARD
    # =============================================================================
    path('', views.uniforms_dashboard, name='dashboard'),

    # =============================================================================
    # MEASUREMENT TYPES
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('measurement-types/', views.measurement_type_list, name='measurement_type_list'),

    # CRUD Views
    path('measurement-types/create/', views.measurement_type_create, name='measurement_type_create'),
    path('measurement-types/<uuid:pk>/', views.measurement_type_detail, name='measurement_type_detail'),
    path('measurement-types/<uuid:pk>/edit/', views.measurement_type_edit, name='measurement_type_edit'),

    # Action Views
    path('measurement-types/<uuid:pk>/delete/', views.measurement_type_delete, name='measurement_type_delete'),
    path('measurement-types/<uuid:pk>/toggle-active/', views.measurement_type_toggle_active, name='measurement_type_toggle_active'),

    # Print & Export
    path('measurement-types/<uuid:pk>/print/', views.measurement_type_print_detail, name='measurement_type_print_detail'),
    path('measurement-types/print/', views.measurement_type_print_view, name='measurement_types_print_view'),
    path('measurement-types/export/excel/', views.export_measurement_types_excel, name='export_measurement_types_excel'),

    # Modal Views
    path('measurement-types/<uuid:type_pk>/modal/delete/', modal_views.measurement_type_delete_modal, name='measurement_type_delete_modal'),
    path('measurement-types/<uuid:type_pk>/modal/toggle-active/', modal_views.measurement_type_toggle_active_modal, name='measurement_type_toggle_active_modal'),
    path('measurement-types/<uuid:type_pk>/modal/quick-view/', modal_views.measurement_type_quick_view_modal, name='measurement_type_quick_view_modal'),

    # =============================================================================
    # STUDENT MEASUREMENTS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('measurements/', views.student_measurement_list, name='student_measurement_list'),

    # CRUD Views
    path('measurements/create/', views.student_measurement_create, name='student_measurement_create'),
    path('measurements/<uuid:pk>/', views.student_measurement_detail, name='student_measurement_detail'),
    path('measurements/<uuid:pk>/edit/', views.student_measurement_edit, name='student_measurement_edit'),

    # Action Views
    path('measurements/<uuid:pk>/delete/', views.student_measurement_delete, name='student_measurement_delete'),
    path('measurements/<uuid:pk>/verify/', views.student_measurement_verify, name='student_measurement_verify'),

    # Bulk Operations
    path('measurements/bulk/create/', views.student_measurement_bulk_create, name='student_measurement_bulk_create'),
    path('measurements/bulk/entry/', views.student_measurement_bulk_entry, name='student_measurement_bulk_entry'),

    # Print & Export
    path('measurements/<uuid:pk>/print/', views.student_measurement_print_detail, name='student_measurement_print_detail'),
    path('measurements/print/', views.student_measurements_print_view, name='student_measurements_print_view'),
    path('measurements/export/excel/', views.export_measurements_excel, name='export_measurements_excel'),

    # Modal Views
    path('measurements/<uuid:measurement_pk>/modal/delete/', modal_views.student_measurement_delete_modal, name='student_measurement_delete_modal'),
    path('measurements/<uuid:measurement_pk>/modal/verify/', modal_views.student_measurement_verify_modal, name='student_measurement_verify_modal'),
    path('measurements/<uuid:measurement_pk>/modal/quick-view/', modal_views.student_measurement_quick_view_modal, name='student_measurement_quick_view_modal'),
    path('measurements/bulk/create/modal/', modal_views.bulk_measurement_modal, name='bulk_measurement_modal'),

    # =============================================================================
    # UNIFORM SIZES
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('sizes/', views.uniform_size_list, name='uniform_size_list'),

    # CRUD Views
    path('sizes/create/', views.uniform_size_create, name='uniform_size_create'),
    path('sizes/<uuid:pk>/', views.uniform_size_detail, name='uniform_size_detail'),
    path('sizes/<uuid:pk>/edit/', views.uniform_size_edit, name='uniform_size_edit'),

    # Action Views
    path('sizes/<uuid:pk>/delete/', views.uniform_size_delete, name='uniform_size_delete'),
    path('sizes/<uuid:pk>/toggle-active/', views.uniform_size_toggle_active, name='uniform_size_toggle_active'),

    # Print & Export
    path('sizes/<uuid:pk>/print/', views.uniform_size_print_detail, name='uniform_size_print_detail'),
    path('sizes/print/', views.uniform_sizes_print_view, name='uniform_sizes_print_view'),
    path('sizes/export/excel/', views.export_uniform_sizes_excel, name='export_uniform_sizes_excel'),

    # Modal Views
    path('sizes/<uuid:size_pk>/modal/delete/', modal_views.uniform_size_delete_modal, name='uniform_size_delete_modal'),
    path('sizes/<uuid:size_pk>/modal/toggle-active/', modal_views.uniform_size_toggle_active_modal, name='uniform_size_toggle_active_modal'),
    path('sizes/<uuid:size_pk>/modal/quick-view/', modal_views.uniform_size_quick_view_modal, name='uniform_size_quick_view_modal'),

    # =============================================================================
    # UNIFORM ITEMS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('items/', views.uniform_item_list, name='uniform_item_list'),

    # CRUD Views
    path('items/create/', views.uniform_item_create, name='uniform_item_create'),
    path('items/<uuid:pk>/', views.uniform_item_detail, name='uniform_item_detail'),
    path('items/<uuid:pk>/edit/', views.uniform_item_edit, name='uniform_item_edit'),

    # Action Views
    path('items/<uuid:pk>/delete/', views.uniform_item_delete, name='uniform_item_delete'),
    path('items/<uuid:pk>/toggle-active/', views.uniform_item_toggle_active, name='uniform_item_toggle_active'),
    path('items/<uuid:pk>/adjust-stock/', views.uniform_item_adjust_stock, name='uniform_item_adjust_stock'),
    path('items/<uuid:pk>/transfer-stock/', views.uniform_item_transfer_stock, name='uniform_item_transfer_stock'),

    # Print & Export
    path('items/<uuid:pk>/print/', views.uniform_item_print_detail, name='uniform_item_print_detail'),
    path('items/print/', views.uniform_items_print_view, name='uniform_items_print_view'),
    path('items/export/excel/', views.export_uniform_items_excel, name='export_uniform_items_excel'),

    # Modal Views
    path('items/<uuid:item_pk>/modal/delete/', modal_views.uniform_item_delete_modal, name='uniform_item_delete_modal'),
    path('items/<uuid:item_pk>/modal/toggle-active/', modal_views.uniform_item_toggle_active_modal, name='uniform_item_toggle_active_modal'),
    path('items/<uuid:item_pk>/modal/quick-view/', modal_views.uniform_item_quick_view_modal, name='uniform_item_quick_view_modal'),
    path('items/<uuid:item_pk>/modal/stock-adjustment/', modal_views.stock_adjustment_modal, name='stock_adjustment_modal'),
    path('items/<uuid:item_pk>/modal/stock-transfer/', modal_views.stock_transfer_modal, name='stock_transfer_modal'),

    # =============================================================================
    # UNIFORM STOCK
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('stock/', views.uniform_stock_list, name='uniform_stock_list'),

    # CRUD Views
    path('stock/create/', views.uniform_stock_create, name='uniform_stock_create'),
    path('stock/<uuid:pk>/', views.uniform_stock_detail, name='uniform_stock_detail'),
    path('stock/<uuid:pk>/edit/', views.uniform_stock_edit, name='uniform_stock_edit'),

    # Action Views
    path('stock/<uuid:stock_pk>/receive/',  views.stock_receive,  name='stock_receive'),
    path('stock/<uuid:stock_pk>/transfer/', views.stock_transfer, name='stock_transfer'),
    path('stock/<uuid:pk>/delete/', views.uniform_stock_delete, name='uniform_stock_delete'),

    # Modal Views
    path('stock/<uuid:stock_pk>/modal/quick-view/', modal_views.uniform_stock_quick_view_modal, name='uniform_stock_quick_view_modal'),
    path('stock/<uuid:stock_pk>/modal/receive/',    modal_views.stock_receive_modal, name='stock_receive_modal'),
    path('stock/<uuid:stock_pk>/modal/delete/',     modal_views.uniform_stock_delete_modal, name='uniform_stock_delete_modal'),
    path('stock/<uuid:stock_pk>/modal/transfer/',   modal_views.stock_transfer_modal, name='stock_transfer_modal'),


    # Print & Export
    path('stock/<uuid:pk>/print/', views.uniform_stock_print_detail, name='uniform_stock_print_detail'),
    path('stock/print/', views.uniform_stock_print_view, name='uniform_stock_print_view'),
    path('stock/export/excel/', views.export_uniform_stock_excel, name='export_uniform_stock_excel'),

    # =============================================================================
    # PURCHASE ORDERS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('purchase-orders/', views.purchase_order_list, name='purchase_order_list'),

    # CRUD Views
    path('purchase-orders/create/', views.purchase_order_create, name='purchase_order_create'),
    path('purchase-orders/<uuid:pk>/', views.purchase_order_detail, name='purchase_order_detail'),
    path('purchase-orders/<uuid:pk>/edit/', views.purchase_order_edit, name='purchase_order_edit'),

    # Action Views
    path('purchase-orders/<uuid:pk>/delete/', views.purchase_order_delete, name='purchase_order_delete'),
    path('purchase-orders/<uuid:pk>/submit/', views.purchase_order_submit, name='purchase_order_submit'),
    path('purchase-orders/<uuid:pk>/approve/', views.purchase_order_approve, name='purchase_order_approve'),
    path('purchase-orders/<uuid:pk>/receive/', views.purchase_order_receive, name='purchase_order_receive'),
    path('purchase-orders/<uuid:pk>/cancel/', views.purchase_order_cancel, name='purchase_order_cancel'),

    # Print & Export
    path('purchase-orders/<uuid:pk>/print/', views.purchase_order_print_detail, name='purchase_order_print_detail'),
    path('purchase-orders/print/', views.purchase_orders_print_view, name='purchase_orders_print_view'),
    path('purchase-orders/export/excel/', views.export_purchase_orders_excel, name='export_purchase_orders_excel'),

    # Modal Views
    path('purchase-orders/<uuid:po_pk>/modal/delete/', modal_views.purchase_order_delete_modal, name='purchase_order_delete_modal'),
    path('purchase-orders/<uuid:po_pk>/modal/submit/', modal_views.purchase_order_submit_modal, name='purchase_order_submit_modal'),
    path('purchase-orders/<uuid:po_pk>/modal/approve/', modal_views.purchase_order_approve_modal, name='purchase_order_approve_modal'),
    path('purchase-orders/<uuid:po_pk>/modal/receive/', modal_views.purchase_order_receive_modal, name='purchase_order_receive_modal'),
    path('purchase-orders/<uuid:po_pk>/modal/cancel/', modal_views.purchase_order_cancel_modal, name='purchase_order_cancel_modal'),
    path('purchase-orders/<uuid:po_pk>/modal/quick-view/', modal_views.purchase_order_quick_view_modal, name='purchase_order_quick_view_modal'),

    # =============================================================================
    # UNIFORM SALES
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('sales/', views.uniform_sale_list, name='uniform_sale_list'),

    # CRUD Views
    path('sales/create/', views.uniform_sale_create, name='uniform_sale_create'),
    path('sales/<uuid:pk>/', views.uniform_sale_detail, name='uniform_sale_detail'),
    path('sales/<uuid:pk>/edit/', views.uniform_sale_edit, name='uniform_sale_edit'),

    # Action Views
    path('sales/<uuid:pk>/delete/', views.uniform_sale_delete, name='uniform_sale_delete'),
    path('sales/<uuid:pk>/cancel/', views.uniform_sale_cancel, name='uniform_sale_cancel'),
    path('sales/<uuid:pk>/return/', views.uniform_sale_return, name='uniform_sale_return'),
    path('sales/<uuid:pk>/finalize/', views.uniform_sale_finalize, name='uniform_sale_finalize'),
    path('sales/<uuid:pk>/issue/', views.uniform_sale_issue, name='uniform_sale_issue'),

    # Print & Export
    path('sales/<uuid:pk>/print/', views.uniform_sale_print_detail, name='uniform_sale_print_detail'),
    path('sales/<uuid:pk>/invoice/', views.uniform_sale_print_invoice, name='uniform_sale_print_invoice'),
    path('sales/print/', views.uniform_sales_print_view, name='uniform_sales_print_view'),
    path('sales/export/excel/', views.export_uniform_sales_excel, name='export_uniform_sales_excel'),

    # Modal Views
    path('sales/<uuid:sale_pk>/modal/delete/', modal_views.uniform_sale_delete_modal, name='uniform_sale_delete_modal'),
    path('sales/<uuid:sale_pk>/modal/cancel/', modal_views.uniform_sale_cancel_modal, name='uniform_sale_cancel_modal'),
    path('sales/<uuid:sale_pk>/modal/return/', modal_views.uniform_sale_return_modal, name='uniform_sale_return_modal'),
    path('sales/<uuid:sale_pk>/modal/issue/', modal_views.uniform_sale_issue_modal, name='uniform_sale_issue_modal'),
    path('sales/<uuid:sale_pk>/modal/quick-view/', modal_views.uniform_sale_quick_view_modal, name='uniform_sale_quick_view_modal'),

    # =============================================================================
    # STUDENT UNIFORM SIZES
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('student-sizes/', views.student_uniform_size_list, name='student_uniform_size_list'),

    # CRUD Views
    path('student-sizes/create/', views.student_uniform_size_create, name='student_uniform_size_create'),
    path('student-sizes/<uuid:pk>/', views.student_uniform_size_detail, name='student_uniform_size_detail'),
    path('student-sizes/<uuid:pk>/edit/', views.student_uniform_size_edit, name='student_uniform_size_edit'),

    # Action Views
    path('student-sizes/<uuid:pk>/delete/', views.student_uniform_size_delete, name='student_uniform_size_delete'),

    # Bulk Operations
    path('student-sizes/bulk/recommend/', views.bulk_size_recommendation, name='bulk_size_recommendation'),

    # Print & Export
    path('student-sizes/<uuid:pk>/print/', views.student_uniform_size_print_detail, name='student_uniform_size_print_detail'),
    path('student-sizes/print/', views.student_uniform_sizes_print_view, name='student_uniform_sizes_print_view'),
    path('student-sizes/export/excel/', views.export_student_uniform_sizes_excel, name='export_student_uniform_sizes_excel'),

    # Modal Views
    path('student-sizes/<uuid:size_rec_pk>/modal/delete/', modal_views.student_uniform_size_delete_modal, name='student_uniform_size_delete_modal'),
    path('student-sizes/<uuid:size_rec_pk>/modal/quick-view/', modal_views.student_uniform_size_quick_view_modal, name='student_uniform_size_quick_view_modal'),
    path('student-sizes/bulk/recommend/modal/', modal_views.bulk_size_recommendation_modal, name='bulk_size_recommendation_modal'),

    # =============================================================================
    # MEASUREMENT SESSIONS
    # =============================================================================
    # List View (handles BOTH full page AND HTMX search/filter)
    path('measurement-sessions/', views.measurement_session_list, name='measurement_session_list'),

    # CRUD Views
    path('measurement-sessions/create/', views.measurement_session_create, name='measurement_session_create'),
    path('measurement-sessions/<uuid:pk>/', views.measurement_session_detail, name='measurement_session_detail'),
    path('measurement-sessions/<uuid:pk>/edit/', views.measurement_session_edit, name='measurement_session_edit'),

    # Action Views
    path('measurement-sessions/<uuid:pk>/delete/', views.measurement_session_delete, name='measurement_session_delete'),
    path('measurement-sessions/<uuid:pk>/start/', views.measurement_session_start, name='measurement_session_start'),
    path('measurement-sessions/<uuid:pk>/complete/', views.measurement_session_complete, name='measurement_session_complete'),
    path('measurement-sessions/<uuid:pk>/cancel/', views.measurement_session_cancel, name='measurement_session_cancel'),

    # Print & Export
    path('measurement-sessions/<uuid:pk>/print/', views.measurement_session_print_detail, name='measurement_session_print_detail'),
    path('measurement-sessions/print/', views.measurement_sessions_print_view, name='measurement_sessions_print_view'),
    path('measurement-sessions/export/excel/', views.export_measurement_sessions_excel, name='export_measurement_sessions_excel'),

    # Modal Views
    path('measurement-sessions/<uuid:session_pk>/modal/delete/', modal_views.measurement_session_delete_modal, name='measurement_session_delete_modal'),
    path('measurement-sessions/<uuid:session_pk>/modal/start/', modal_views.measurement_session_start_modal, name='measurement_session_start_modal'),
    path('measurement-sessions/<uuid:session_pk>/modal/complete/', modal_views.measurement_session_complete_modal, name='measurement_session_complete_modal'),
    path('measurement-sessions/<uuid:session_pk>/modal/cancel/', modal_views.measurement_session_cancel_modal, name='measurement_session_cancel_modal'),
    path('measurement-sessions/<uuid:session_pk>/modal/quick-view/', modal_views.measurement_session_quick_view_modal, name='measurement_session_quick_view_modal'),

    # =============================================================================
    # REPORTS
    # =============================================================================
    path('reports/inventory/', views.inventory_report, name='inventory_report'),
    path('reports/sales/', views.sales_report, name='sales_report'),
    path('reports/low-stock/', views.low_stock_report, name='low_stock_report'),
    path('reports/measurement-summary/', views.measurement_summary_report, name='measurement_summary_report'),
    path('reports/student-orders/', views.student_orders_report, name='student_orders_report'),

    # Report Generation Modals
    path('reports/inventory/modal/', modal_views.inventory_report_options_modal, name='inventory_report_options_modal'),
    path('reports/sales/modal/', modal_views.sales_report_options_modal, name='sales_report_options_modal'),
    path('reports/measurement/modal/', modal_views.measurement_report_options_modal, name='measurement_report_options_modal'),
    path('reports/stock-valuation/modal/', modal_views.stock_valuation_modal, name='stock_valuation_modal'),

    # =============================================================================
    # UTILITY MODALS
    # =============================================================================
    path('utility/size-chart/modal/', modal_views.uniform_size_chart_modal, name='uniform_size_chart_modal'),
    path('utility/measurement-guide/modal/', modal_views.measurement_guide_modal, name='measurement_guide_modal'),
    path('utility/care-guide/<uuid:item_pk>/modal/', modal_views.uniform_care_guide_modal, name='uniform_care_guide_modal'),

    # =============================================================================
    # AJAX ENDPOINTS (for dynamic form field loading)
    # =============================================================================
    path('ajax/get-item-sizes/<uuid:item_pk>/', views.ajax_get_item_sizes, name='ajax_get_item_sizes'),
    path('ajax/get-item-price/<uuid:item_pk>/', views.ajax_get_item_price, name='ajax_get_item_price'),
    path('ajax/get-stock-quantity/<uuid:item_pk>/<uuid:size_pk>/', views.ajax_get_stock_quantity, name='ajax_get_stock_quantity'),
    path('ajax/get-item-stock/<uuid:item_pk>/', views.ajax_get_item_stock, name='ajax_get_item_stock'),
    path('ajax/get-student-measurements/<uuid:student_pk>/', views.ajax_get_student_measurements, name='ajax_get_student_measurements'),
    path('ajax/get-size-recommendation/<uuid:student_pk>/<uuid:item_pk>/', views.ajax_get_size_recommendation, name='ajax_get_size_recommendation'),
    path('ajax/check-po-number/', views.ajax_check_po_number, name='ajax_check_po_number'),
    path('ajax/calculate-sale-total/', views.ajax_calculate_sale_total, name='ajax_calculate_sale_total'),
]