# uniforms/urls.py

"""
URL Configuration for Uniforms Module

Architecture:
- List views handle BOTH full-page loads AND HTMX search/filter requests.
- Modal loaders (modal_views.py) return HTML partials only.
- Action endpoints (delete, cancel, issue, etc.) return HTMX response headers.
- All primary keys are UUIDs.

CHANGES FROM ORIGINAL:
- Removed entire MEASUREMENT SESSIONS section — MeasurementSession model removed.
- Removed measurements/bulk/entry/ — placeholder view removed.
- Removed export_measurement_types_excel and measurement_types_print_view —
  measurement types are now a settings-style page (no list print/export needed).
- Removed uniform_sizes_print_view, export_uniform_sizes_excel, and
  uniform_size_print_detail — sizes are a settings-style config table;
  no print or export is needed.
- Removed entire STUDENT UNIFORM SIZES section except create/detail/edit/delete
  and the two modals (delete_modal, quick_view_modal):
    student_uniform_size_list         → removed (no list view)
    bulk_size_recommendation          → removed (stub, no action)
    student_uniform_size_print_detail → removed
    student_uniform_sizes_print_view  → removed
    export_student_uniform_sizes_excel→ removed
    bulk_size_recommendation_modal    → removed (modal_views.py)
- Added five new tab partial URLs:
    uniform_item_stock_partial        items/<pk>/partials/stock/
    uniform_item_sales_partial        items/<pk>/partials/sales/
    uniform_item_size_recs_partial    items/<pk>/partials/size-recs/
    uniform_sale_items_partial        sales/<pk>/partials/items/
    uniform_sale_audit_partial        sales/<pk>/partials/audit/
- Items stock-transfer modal stays as uniform_item_transfer_modal(item_pk) to
  avoid conflict with stock-record-level stock_transfer_modal(stock_pk).
- uniform_care_guide_modal removed — care_instructions field removed from model.
"""

from django.urls import path
from . import views, modal_views

app_name = 'uniforms'

urlpatterns = [

    # =========================================================================
    # DASHBOARD
    # =========================================================================
    path('', views.uniforms_dashboard, name='dashboard'),

    # =========================================================================
    # MEASUREMENT TYPES  (settings-style — no list print or export)
    # =========================================================================

    path('measurement-types/', views.measurement_type_list, name='measurement_type_list'),
    path('measurement-types/create/', views.measurement_type_create, name='measurement_type_create'),
    path('measurement-types/<uuid:pk>/', views.measurement_type_detail, name='measurement_type_detail'),
    path('measurement-types/<uuid:pk>/edit/', views.measurement_type_edit, name='measurement_type_edit'),
    path('measurement-types/<uuid:pk>/delete/', views.measurement_type_delete, name='measurement_type_delete'),
    path('measurement-types/<uuid:pk>/toggle-active/', views.measurement_type_toggle_active, name='measurement_type_toggle_active'),

    # Single-item print only — no list print, no export
    path('measurement-types/<uuid:pk>/print/', views.measurement_type_print_detail, name='measurement_type_print_detail'),

    # Modals
    path('measurement-types/<uuid:type_pk>/modal/delete/', modal_views.measurement_type_delete_modal, name='measurement_type_delete_modal'),
    path('measurement-types/<uuid:type_pk>/modal/toggle-active/', modal_views.measurement_type_toggle_active_modal, name='measurement_type_toggle_active_modal'),
    path('measurement-types/<uuid:type_pk>/modal/quick-view/', modal_views.measurement_type_quick_view_modal, name='measurement_type_quick_view_modal'),

    # =========================================================================
    # STUDENT MEASUREMENTS
    # =========================================================================

    path('measurements/', views.student_measurement_list, name='student_measurement_list'),
    path('measurements/create/', views.student_measurement_create, name='student_measurement_create'),
    path('measurements/<uuid:pk>/', views.student_measurement_detail, name='student_measurement_detail'),
    path('measurements/<uuid:pk>/edit/', views.student_measurement_edit, name='student_measurement_edit'),
    path('measurements/<uuid:pk>/delete/', views.student_measurement_delete, name='student_measurement_delete'),
    path('measurements/<uuid:pk>/verify/', views.student_measurement_verify, name='student_measurement_verify'),
    path('measurements/bulk/create/', views.student_measurement_bulk_create, name='student_measurement_bulk_create'),

    # Print & export
    path('measurements/<uuid:pk>/print/', views.student_measurement_print_detail, name='student_measurement_print_detail'),
    path('measurements/print/', views.student_measurements_print_view, name='student_measurements_print_view'),
    path('measurements/export/excel/', views.export_measurements_excel, name='export_measurements_excel'),

    # Modals
    path('measurements/<uuid:measurement_pk>/modal/delete/', modal_views.student_measurement_delete_modal, name='student_measurement_delete_modal'),
    path('measurements/<uuid:measurement_pk>/modal/verify/', modal_views.student_measurement_verify_modal, name='student_measurement_verify_modal'),
    path('measurements/<uuid:measurement_pk>/modal/quick-view/', modal_views.student_measurement_quick_view_modal, name='student_measurement_quick_view_modal'),
    path('measurements/bulk/create/modal/', modal_views.bulk_measurement_modal, name='bulk_measurement_modal'),

    # =========================================================================
    # UNIFORM SIZES  (settings-style — no print, no export)
    # =========================================================================

    path('sizes/', views.uniform_size_list, name='uniform_size_list'),
    path('sizes/create/', views.uniform_size_create, name='uniform_size_create'),
    path('sizes/<uuid:pk>/', views.uniform_size_detail, name='uniform_size_detail'),
    path('sizes/<uuid:pk>/edit/', views.uniform_size_edit, name='uniform_size_edit'),
    path('sizes/<uuid:pk>/delete/', views.uniform_size_delete, name='uniform_size_delete'),
    path('sizes/<uuid:pk>/toggle-active/', views.uniform_size_toggle_active, name='uniform_size_toggle_active'),

    # Modals
    path('sizes/<uuid:size_pk>/modal/delete/', modal_views.uniform_size_delete_modal, name='uniform_size_delete_modal'),
    path('sizes/<uuid:size_pk>/modal/toggle-active/', modal_views.uniform_size_toggle_active_modal, name='uniform_size_toggle_active_modal'),
    path('sizes/<uuid:size_pk>/modal/quick-view/', modal_views.uniform_size_quick_view_modal, name='uniform_size_quick_view_modal'),

    # =========================================================================
    # UNIFORM ITEMS
    # =========================================================================

    path('items/', views.uniform_item_list, name='uniform_item_list'),
    path('items/create/', views.uniform_item_create, name='uniform_item_create'),
    path('items/<uuid:pk>/', views.uniform_item_detail, name='uniform_item_detail'),
    path('items/<uuid:pk>/edit/', views.uniform_item_edit, name='uniform_item_edit'),
    path('items/<uuid:pk>/delete/', views.uniform_item_delete, name='uniform_item_delete'),
    path('items/<uuid:pk>/toggle-active/', views.uniform_item_toggle_active, name='uniform_item_toggle_active'),
    path('items/<uuid:pk>/adjust-stock/', views.uniform_item_adjust_stock, name='uniform_item_adjust_stock'),
    path('items/<uuid:pk>/transfer-stock/', views.uniform_item_transfer_stock, name='uniform_item_transfer_stock'),

    # Detail tab partials (HTMX — loaded on demand by uniform_item_detail)
    path('items/<uuid:pk>/partials/stock/', views.uniform_item_stock_partial, name='uniform_item_stock_partial'),
    path('items/<uuid:pk>/partials/sales/', views.uniform_item_sales_partial, name='uniform_item_sales_partial'),
    path('items/<uuid:pk>/partials/size-recs/', views.uniform_item_size_recs_partial, name='uniform_item_size_recs_partial'),

    # Print & export
    path('items/<uuid:pk>/print/', views.uniform_item_print_detail, name='uniform_item_print_detail'),
    path('items/print/', views.uniform_items_print_view, name='uniform_items_print_view'),
    path('items/export/excel/', views.export_uniform_items_excel, name='export_uniform_items_excel'),

    # Modals
    path('items/<uuid:item_pk>/modal/delete/', modal_views.uniform_item_delete_modal, name='uniform_item_delete_modal'),
    path('items/<uuid:item_pk>/modal/toggle-active/', modal_views.uniform_item_toggle_active_modal, name='uniform_item_toggle_active_modal'),
    path('items/<uuid:item_pk>/modal/quick-view/', modal_views.uniform_item_quick_view_modal, name='uniform_item_quick_view_modal'),
    path('items/<uuid:item_pk>/modal/stock-adjustment/', modal_views.stock_adjustment_modal, name='stock_adjustment_modal'),
    # Renamed from stock_transfer_modal to avoid conflict with stock-record-level variant
    path('items/<uuid:item_pk>/modal/stock-transfer/', modal_views.uniform_item_transfer_modal, name='uniform_item_transfer_modal'),

    # =========================================================================
    # UNIFORM STOCK
    # =========================================================================

    path('stock/', views.uniform_stock_list, name='uniform_stock_list'),
    path('stock/create/', views.uniform_stock_create, name='uniform_stock_create'),
    path('stock/<uuid:pk>/', views.uniform_stock_detail, name='uniform_stock_detail'),
    path('stock/<uuid:pk>/edit/', views.uniform_stock_edit, name='uniform_stock_edit'),
    path('stock/<uuid:pk>/delete/', views.uniform_stock_delete, name='uniform_stock_delete'),
    path('stock/<uuid:stock_pk>/receive/', views.stock_receive, name='stock_receive'),
    path('stock/<uuid:stock_pk>/transfer/', views.stock_transfer, name='stock_transfer'),

    # Print & export
    path('stock/<uuid:pk>/print/', views.uniform_stock_print_detail, name='uniform_stock_print_detail'),
    path('stock/print/', views.uniform_stock_print_view, name='uniform_stock_print_view'),
    path('stock/export/excel/', views.export_uniform_stock_excel, name='export_uniform_stock_excel'),

    # Modals
    path('stock/<uuid:stock_pk>/modal/quick-view/', modal_views.uniform_stock_quick_view_modal, name='uniform_stock_quick_view_modal'),
    path('stock/<uuid:stock_pk>/modal/receive/', modal_views.stock_receive_modal, name='stock_receive_modal'),
    path('stock/<uuid:stock_pk>/modal/delete/', modal_views.uniform_stock_delete_modal, name='uniform_stock_delete_modal'),
    # Distinct from uniform_item_transfer_modal — operates on a stock record, not an item
    path('stock/<uuid:stock_pk>/modal/transfer/', modal_views.stock_transfer_modal, name='stock_transfer_modal'),

    # =========================================================================
    # PURCHASE ORDERS
    # =========================================================================

    path('purchase-orders/', views.purchase_order_list, name='purchase_order_list'),
    path('purchase-orders/create/', views.purchase_order_create, name='purchase_order_create'),
    path('purchase-orders/<uuid:pk>/', views.purchase_order_detail, name='purchase_order_detail'),
    path('purchase-orders/<uuid:pk>/edit/', views.purchase_order_edit, name='purchase_order_edit'),
    path('purchase-orders/<uuid:pk>/delete/', views.purchase_order_delete, name='purchase_order_delete'),
    path('purchase-orders/<uuid:pk>/submit/', views.purchase_order_submit, name='purchase_order_submit'),
    path('purchase-orders/<uuid:pk>/approve/', views.purchase_order_approve, name='purchase_order_approve'),
    path('purchase-orders/<uuid:pk>/receive/', views.purchase_order_receive, name='purchase_order_receive'),
    path('purchase-orders/<uuid:pk>/cancel/', views.purchase_order_cancel, name='purchase_order_cancel'),

    # Print & export
    path('purchase-orders/<uuid:pk>/print/', views.purchase_order_print_detail, name='purchase_order_print_detail'),
    path('purchase-orders/print/', views.purchase_orders_print_view, name='purchase_orders_print_view'),
    path('purchase-orders/export/excel/', views.export_purchase_orders_excel, name='export_purchase_orders_excel'),

    # Modals
    path('purchase-orders/<uuid:po_pk>/modal/delete/', modal_views.purchase_order_delete_modal, name='purchase_order_delete_modal'),
    path('purchase-orders/<uuid:po_pk>/modal/submit/', modal_views.purchase_order_submit_modal, name='purchase_order_submit_modal'),
    path('purchase-orders/<uuid:po_pk>/modal/approve/', modal_views.purchase_order_approve_modal, name='purchase_order_approve_modal'),
    path('purchase-orders/<uuid:po_pk>/modal/receive/', modal_views.purchase_order_receive_modal, name='purchase_order_receive_modal'),
    path('purchase-orders/<uuid:po_pk>/modal/cancel/', modal_views.purchase_order_cancel_modal, name='purchase_order_cancel_modal'),
    path('purchase-orders/<uuid:po_pk>/modal/quick-view/', modal_views.purchase_order_quick_view_modal, name='purchase_order_quick_view_modal'),

    # =========================================================================
    # UNIFORM SALES
    # =========================================================================

    path('sales/', views.uniform_sale_list, name='uniform_sale_list'),
    path('sales/create/', views.uniform_sale_create, name='uniform_sale_create'),
    path('sales/<uuid:pk>/', views.uniform_sale_detail, name='uniform_sale_detail'),
    path('sales/<uuid:pk>/edit/', views.uniform_sale_edit, name='uniform_sale_edit'),
    path('sales/<uuid:pk>/delete/', views.uniform_sale_delete, name='uniform_sale_delete'),
    path('sales/<uuid:pk>/finalize/', views.uniform_sale_finalize, name='uniform_sale_finalize'),
    path('sales/<uuid:pk>/issue/', views.uniform_sale_issue, name='uniform_sale_issue'),
    path('sales/<uuid:pk>/cancel/', views.uniform_sale_cancel, name='uniform_sale_cancel'),
    path('sales/<uuid:pk>/return/', views.uniform_sale_return, name='uniform_sale_return'),

    # Detail tab partials (HTMX — loaded on demand by uniform_sale_detail)
    path('sales/<uuid:pk>/partials/items/', views.uniform_sale_items_partial, name='uniform_sale_items_partial'),
    path('sales/<uuid:pk>/partials/audit/', views.uniform_sale_audit_partial, name='uniform_sale_audit_partial'),

    # Print & export
    path('sales/<uuid:pk>/print/', views.uniform_sale_print_detail, name='uniform_sale_print_detail'),
    path('sales/<uuid:pk>/invoice/', views.uniform_sale_print_invoice, name='uniform_sale_print_invoice'),
    path('sales/print/', views.uniform_sales_print_view, name='uniform_sales_print_view'),
    path('sales/export/excel/', views.export_uniform_sales_excel, name='export_uniform_sales_excel'),

    # Modals
    path('sales/<uuid:sale_pk>/modal/delete/', modal_views.uniform_sale_delete_modal, name='uniform_sale_delete_modal'),
    path('sales/<uuid:sale_pk>/modal/finalize/', modal_views.uniform_sale_finalize_modal, name='uniform_sale_finalize_modal'),
    path('sales/<uuid:sale_pk>/modal/issue/', modal_views.uniform_sale_issue_modal, name='uniform_sale_issue_modal'),
    path('sales/<uuid:sale_pk>/modal/cancel/', modal_views.uniform_sale_cancel_modal, name='uniform_sale_cancel_modal'),
    path('sales/<uuid:sale_pk>/modal/return/', modal_views.uniform_sale_return_modal, name='uniform_sale_return_modal'),
    path('sales/<uuid:sale_pk>/modal/quick-view/', modal_views.uniform_sale_quick_view_modal, name='uniform_sale_quick_view_modal'),

    # =========================================================================
    # STUDENT UNIFORM SIZES  (no list, no bulk, no print, no export)
    # =========================================================================

    path('student-sizes/create/', views.student_uniform_size_create, name='student_uniform_size_create'),
    path('student-sizes/<uuid:pk>/', views.student_uniform_size_detail, name='student_uniform_size_detail'),
    path('student-sizes/<uuid:pk>/edit/', views.student_uniform_size_edit, name='student_uniform_size_edit'),
    path('student-sizes/<uuid:pk>/delete/', views.student_uniform_size_delete, name='student_uniform_size_delete'),

    # Modals — no list modal, no bulk modal
    path('student-sizes/<uuid:size_rec_pk>/modal/delete/', modal_views.student_uniform_size_delete_modal, name='student_uniform_size_delete_modal'),
    path('student-sizes/<uuid:size_rec_pk>/modal/quick-view/', modal_views.student_uniform_size_quick_view_modal, name='student_uniform_size_quick_view_modal'),

    # =========================================================================
    # REPORTS
    # =========================================================================

    path('reports/inventory/', views.inventory_report, name='inventory_report'),
    path('reports/sales/', views.sales_report, name='sales_report'),
    path('reports/low-stock/', views.low_stock_report, name='low_stock_report'),
    path('reports/measurement-summary/', views.measurement_summary_report, name='measurement_summary_report'),
    path('reports/student-orders/', views.student_orders_report, name='student_orders_report'),

    # Report option modals
    path('reports/inventory/modal/', modal_views.inventory_report_options_modal, name='inventory_report_options_modal'),
    path('reports/sales/modal/', modal_views.sales_report_options_modal, name='sales_report_options_modal'),
    path('reports/measurement/modal/', modal_views.measurement_report_options_modal, name='measurement_report_options_modal'),
    path('reports/stock-valuation/modal/', modal_views.stock_valuation_modal, name='stock_valuation_modal'),

    # =========================================================================
    # UTILITY MODALS
    # =========================================================================

    path('utility/size-chart/modal/', modal_views.uniform_size_chart_modal, name='uniform_size_chart_modal'),
    path('utility/measurement-guide/modal/', modal_views.measurement_guide_modal, name='measurement_guide_modal'),

    # =========================================================================
    # AJAX ENDPOINTS
    # =========================================================================

    path('ajax/get-item-sizes/<uuid:item_pk>/', views.ajax_get_item_sizes, name='ajax_get_item_sizes'),
    path('ajax/get-item-price/<uuid:item_pk>/', views.ajax_get_item_price, name='ajax_get_item_price'),
    path('ajax/get-stock-quantity/<uuid:item_pk>/<uuid:size_pk>/', views.ajax_get_stock_quantity, name='ajax_get_stock_quantity'),
    path('ajax/get-item-stock/<uuid:item_pk>/', views.ajax_get_item_stock, name='ajax_get_item_stock'),
    path('ajax/get-student-measurements/<uuid:student_pk>/', views.ajax_get_student_measurements, name='ajax_get_student_measurements'),
    path('ajax/get-size-recommendation/<uuid:student_pk>/<uuid:item_pk>/', views.ajax_get_size_recommendation, name='ajax_get_size_recommendation'),
    path('ajax/check-po-number/', views.ajax_check_po_number, name='ajax_check_po_number'),
    path('ajax/calculate-sale-total/', views.ajax_calculate_sale_total, name='ajax_calculate_sale_total'),
]