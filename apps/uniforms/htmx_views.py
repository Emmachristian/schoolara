# uniforms/htmx_views.py

from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.db.models import Q, Count, Sum, Avg, F, DecimalField, Case, When, Max, Min
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from datetime import timedelta, date
from decimal import Decimal
import logging

from .models import (
    MeasurementType,
    StudentMeasurement,
    UniformSize,
    UniformItem,
    UniformStock,
    UniformPurchaseOrder,
    UniformPurchaseOrderItem,
    UniformSale,
    UniformSaleItem,
    StudentUniformSize,
    MeasurementSession
)
from utils.utils import parse_filters, paginate_queryset

logger = logging.getLogger(__name__)


# =============================================================================
# MEASUREMENT TYPE SEARCH
# =============================================================================

def measurement_type_search(request):
    """HTMX-compatible measurement type search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'category', 'is_active', 'is_required', 'unit'
    ])
    
    query = filters['q']
    category = filters['category']
    is_active = filters['is_active']
    is_required = filters['is_required']
    unit = filters['unit']
    
    # Build queryset
    measurement_types = MeasurementType.objects.select_related(
        'unit'
    ).annotate(
        measurement_count=Count('student_measurements', distinct=True)
    ).order_by('category', 'display_order', 'name')
    
    # Apply text search
    if query:
        measurement_types = measurement_types.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply filters
    if category:
        measurement_types = measurement_types.filter(category=category)
    
    if unit:
        measurement_types = measurement_types.filter(unit_id=unit)
    
    if is_active is not None:
        measurement_types = measurement_types.filter(is_active=(is_active.lower() == 'true'))
    
    if is_required is not None:
        measurement_types = measurement_types.filter(is_required=(is_required.lower() == 'true'))
    
    # Paginate
    measurement_types_page, paginator = paginate_queryset(request, measurement_types, per_page=20)
    
    # Calculate stats
    total = measurement_types.count()
    
    stats = {
        'total': total,
        'active': measurement_types.filter(is_active=True).count(),
        'required': measurement_types.filter(is_required=True).count(),
        'uniform': measurement_types.filter(category='UNIFORM').count(),
        'sports': measurement_types.filter(category='SPORTS').count(),
        'health': measurement_types.filter(category='HEALTH').count(),
        'total_measurements': sum(mt.measurement_count for mt in measurement_types),
    }
    
    return render(request, 'uniforms/measurement_types/_type_results.html', {
        'measurement_types_page': measurement_types_page,
        'stats': stats,
    })


# =============================================================================
# STUDENT MEASUREMENT SEARCH
# =============================================================================

def student_measurement_search(request):
    """HTMX-compatible student measurement search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'student', 'measurement_type', 'academic_session',
        'measurement_context', 'measurement_method', 'is_verified',
        'is_current', 'start_date', 'end_date'
    ])
    
    query = filters['q']
    student = filters['student']
    measurement_type = filters['measurement_type']
    academic_session = filters['academic_session']
    measurement_context = filters['measurement_context']
    measurement_method = filters['measurement_method']
    is_verified = filters['is_verified']
    is_current = filters['is_current']
    start_date = filters['start_date']
    end_date = filters['end_date']
    
    # Build queryset
    measurements = StudentMeasurement.objects.select_related(
        'student__current_academic_level',
        'measurement_type__unit',
        'academic_session'
    ).order_by('-measurement_date', 'student__first_name')
    
    # Apply text search
    if query:
        measurements = measurements.filter(
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__admission_number__icontains=query) |
            Q(notes__icontains=query)
        )
    
    # Apply filters
    if student:
        measurements = measurements.filter(student_id=student)
    
    if measurement_type:
        measurements = measurements.filter(measurement_type_id=measurement_type)
    
    if academic_session:
        measurements = measurements.filter(academic_session_id=academic_session)
    
    if measurement_context:
        measurements = measurements.filter(measurement_context=measurement_context)
    
    if measurement_method:
        measurements = measurements.filter(measurement_method=measurement_method)
    
    if is_verified is not None:
        measurements = measurements.filter(is_verified=(is_verified.lower() == 'true'))
    
    if is_current is not None:
        measurements = measurements.filter(is_current=(is_current.lower() == 'true'))
    
    if start_date:
        measurements = measurements.filter(measurement_date__gte=start_date)
    
    if end_date:
        measurements = measurements.filter(measurement_date__lte=end_date)
    
    # Paginate
    measurements_page, paginator = paginate_queryset(request, measurements, per_page=20)
    
    # Calculate stats
    total = measurements.count()
    
    stats = {
        'total': total,
        'current': measurements.filter(is_current=True).count(),
        'verified': measurements.filter(is_verified=True).count(),
        'unverified': measurements.filter(is_verified=False).count(),
        'admission': measurements.filter(measurement_context='ADMISSION').count(),
        'annual': measurements.filter(measurement_context='ANNUAL').count(),
        'uniform_order': measurements.filter(measurement_context='UNIFORM_ORDER').count(),
        'unique_students': measurements.values('student').distinct().count(),
    }
    
    return render(request, 'uniforms/measurements/_measurement_results.html', {
        'measurements_page': measurements_page,
        'stats': stats,
    })


# =============================================================================
# UNIFORM SIZE SEARCH
# =============================================================================

def uniform_size_search(request):
    """HTMX-compatible uniform size search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'size_type', 'is_active', 'min_age', 'max_age'
    ])
    
    query = filters['q']
    size_type = filters['size_type']
    is_active = filters['is_active']
    min_age = filters['min_age']
    max_age = filters['max_age']
    
    # Build queryset
    sizes = UniformSize.objects.annotate(
        item_count=Count('uniform_items', distinct=True),
        stock_count=Count('stock_records', distinct=True),
        recommendation_count=Count('student_recommendations', distinct=True)
    ).order_by('display_order', 'name')
    
    # Apply text search
    if query:
        sizes = sizes.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply filters
    if size_type:
        sizes = sizes.filter(size_type=size_type)
    
    if is_active is not None:
        sizes = sizes.filter(is_active=(is_active.lower() == 'true'))
    
    if min_age:
        try:
            sizes = sizes.filter(min_age__gte=int(min_age))
        except:
            pass
    
    if max_age:
        try:
            sizes = sizes.filter(max_age__lte=int(max_age))
        except:
            pass
    
    # Paginate
    sizes_page, paginator = paginate_queryset(request, sizes, per_page=20)
    
    # Calculate stats
    total = sizes.count()
    
    stats = {
        'total': total,
        'active': sizes.filter(is_active=True).count(),
        'numeric': sizes.filter(size_type='NUMERIC').count(),
        'alpha': sizes.filter(size_type='ALPHA').count(),
        'age_based': sizes.filter(size_type='AGE_BASED').count(),
        'custom': sizes.filter(size_type='CUSTOM').count(),
        'total_items': sum(s.item_count for s in sizes),
    }
    
    return render(request, 'uniforms/sizes/_size_results.html', {
        'sizes_page': sizes_page,
        'stats': stats,
    })


# =============================================================================
# UNIFORM ITEM SEARCH
# =============================================================================

def uniform_item_search(request):
    """HTMX-compatible uniform item search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'item_type', 'gender', 'category', 'is_active',
        'is_mandatory', 'requires_sizing', 'is_taxable',
        'low_stock', 'min_price', 'max_price'
    ])
    
    query = filters['q']
    item_type = filters['item_type']
    gender = filters['gender']
    category = filters['category']
    is_active = filters['is_active']
    is_mandatory = filters['is_mandatory']
    requires_sizing = filters['requires_sizing']
    is_taxable = filters['is_taxable']
    low_stock = filters['low_stock']
    min_price = filters['min_price']
    max_price = filters['max_price']
    
    # Build queryset
    items = UniformItem.objects.select_related(
        'unit_of_measure',
        'inventory_account',
        'cogs_account',
        'revenue_account',
        'tax_rate'
    ).prefetch_related(
        'available_sizes'
    ).annotate(
        size_count=Count('available_sizes', distinct=True),
        stock_records_count=Count('stock_records', distinct=True),
        sale_count=Count('sale_items', distinct=True)
    ).order_by('item_type', 'name')
    
    # Apply text search
    if query:
        items = items.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(description__icontains=query) |
            Q(sku__icontains=query) |
            Q(barcode__icontains=query)
        )
    
    # Apply filters
    if item_type:
        items = items.filter(item_type=item_type)
    
    if gender:
        items = items.filter(gender=gender)
    
    if category:
        items = items.filter(category__icontains=category)
    
    if is_active is not None:
        items = items.filter(is_active=(is_active.lower() == 'true'))
    
    if is_mandatory is not None:
        items = items.filter(is_mandatory=(is_mandatory.lower() == 'true'))
    
    if requires_sizing is not None:
        items = items.filter(requires_sizing=(requires_sizing.lower() == 'true'))
    
    if is_taxable is not None:
        items = items.filter(is_taxable=(is_taxable.lower() == 'true'))
    
    if low_stock and low_stock.lower() == 'true':
        items = items.filter(current_stock__lte=F('reorder_level'))
    
    if min_price:
        try:
            items = items.filter(selling_price__gte=Decimal(min_price))
        except:
            pass
    
    if max_price:
        try:
            items = items.filter(selling_price__lte=Decimal(max_price))
        except:
            pass
    
    # Paginate
    items_page, paginator = paginate_queryset(request, items, per_page=20)
    
    # Calculate stats
    total = items.count()
    
    stats = {
        'total': total,
        'active': items.filter(is_active=True).count(),
        'mandatory': items.filter(is_mandatory=True).count(),
        'low_stock': items.filter(current_stock__lte=F('reorder_level')).count(),
        'out_of_stock': items.filter(current_stock=0).count(),
        'uniform': items.filter(item_type='UNIFORM').count(),
        'sports': items.filter(item_type='SPORTS').count(),
        'total_stock_value': items.aggregate(
            total=Sum(F('current_stock') * F('unit_cost'))
        )['total'] or 0,
        'total_selling_value': items.aggregate(
            total=Sum(F('current_stock') * F('selling_price'))
        )['total'] or 0,
    }
    
    return render(request, 'uniforms/items/_item_results.html', {
        'items_page': items_page,
        'stats': stats,
    })


# =============================================================================
# UNIFORM STOCK SEARCH
# =============================================================================

def uniform_stock_search(request):
    """HTMX-compatible uniform stock search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'uniform_item', 'size', 'location', 'low_stock'
    ])
    
    query = filters['q']
    uniform_item = filters['uniform_item']
    size = filters['size']
    location = filters['location']
    low_stock = filters['low_stock']
    
    # Build queryset
    stock = UniformStock.objects.select_related(
        'uniform_item__unit_of_measure',
        'size'
    ).order_by('uniform_item__name', 'size__display_order')
    
    # Apply text search
    if query:
        stock = stock.filter(
            Q(uniform_item__name__icontains=query) |
            Q(uniform_item__code__icontains=query) |
            Q(size__name__icontains=query) |
            Q(location__icontains=query)
        )
    
    # Apply filters
    if uniform_item:
        stock = stock.filter(uniform_item_id=uniform_item)
    
    if size:
        stock = stock.filter(size_id=size)
    
    if location:
        stock = stock.filter(location__icontains=location)
    
    if low_stock and low_stock.lower() == 'true':
        stock = stock.filter(
            quantity__lte=F('uniform_item__reorder_level')
        )
    
    # Paginate
    stock_page, paginator = paginate_queryset(request, stock, per_page=20)
    
    # Calculate stats
    total = stock.count()
    
    stats = {
        'total': total,
        'total_quantity': stock.aggregate(Sum('quantity'))['quantity__sum'] or 0,
        'total_reserved': stock.aggregate(Sum('reserved_quantity'))['reserved_quantity__sum'] or 0,
        'total_cost_value': stock.aggregate(Sum('total_cost_value'))['total_cost_value__sum'] or 0,
        'total_selling_value': stock.aggregate(Sum('total_selling_value'))['total_selling_value__sum'] or 0,
        'out_of_stock': stock.filter(quantity=0).count(),
        'low_stock': stock.filter(quantity__lte=F('uniform_item__reorder_level')).count(),
    }
    
    return render(request, 'uniforms/stock/_stock_results.html', {
        'stock_page': stock_page,
        'stats': stats,
    })


# =============================================================================
# PURCHASE ORDER SEARCH
# =============================================================================

def purchase_order_search(request):
    """HTMX-compatible purchase order search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'status', 'supplier_name', 'fiscal_period',
        'start_date', 'end_date', 'min_amount', 'max_amount'
    ])
    
    query = filters['q']
    status = filters['status']
    supplier_name = filters['supplier_name']
    fiscal_period = filters['fiscal_period']
    start_date = filters['start_date']
    end_date = filters['end_date']
    min_amount = filters['min_amount']
    max_amount = filters['max_amount']
    
    # Build queryset
    orders = UniformPurchaseOrder.objects.select_related(
        'fiscal_period',
        'payable_account',
        'journal_entry'
    ).prefetch_related(
        'items'
    ).annotate(
        item_count=Count('items', distinct=True),
        total_quantity_ordered=Sum('items__quantity_ordered'),
        total_quantity_received=Sum('items__quantity_received')
    ).order_by('-order_date')
    
    # Apply text search
    if query:
        orders = orders.filter(
            Q(po_number__icontains=query) |
            Q(supplier_name__icontains=query) |
            Q(supplier_contact__icontains=query) |
            Q(notes__icontains=query)
        )
    
    # Apply filters
    if status:
        orders = orders.filter(status=status)
    
    if supplier_name:
        orders = orders.filter(supplier_name__icontains=supplier_name)
    
    if fiscal_period:
        orders = orders.filter(fiscal_period_id=fiscal_period)
    
    if start_date:
        orders = orders.filter(order_date__gte=start_date)
    
    if end_date:
        orders = orders.filter(order_date__lte=end_date)
    
    if min_amount:
        try:
            orders = orders.filter(total_amount__gte=Decimal(min_amount))
        except:
            pass
    
    if max_amount:
        try:
            orders = orders.filter(total_amount__lte=Decimal(max_amount))
        except:
            pass
    
    # Paginate
    orders_page, paginator = paginate_queryset(request, orders, per_page=20)
    
    # Calculate stats
    total = orders.count()
    
    stats = {
        'total': total,
        'draft': orders.filter(status='DRAFT').count(),
        'submitted': orders.filter(status='SUBMITTED').count(),
        'approved': orders.filter(status='APPROVED').count(),
        'received': orders.filter(status='RECEIVED').count(),
        'partial': orders.filter(status='PARTIAL').count(),
        'total_amount': orders.aggregate(Sum('total_amount'))['total_amount__sum'] or 0,
        'total_paid': orders.aggregate(Sum('paid_amount'))['paid_amount__sum'] or 0,
        'total_balance': orders.aggregate(Sum('balance_due'))['balance_due__sum'] or 0,
    }
    
    return render(request, 'uniforms/purchase_orders/_order_results.html', {
        'orders_page': orders_page,
        'stats': stats,
    })


# =============================================================================
# UNIFORM SALE SEARCH
# =============================================================================

def uniform_sale_search(request):
    """HTMX-compatible uniform sale search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'status', 'sale_type', 'student', 'academic_session',
        'fiscal_period', 'start_date', 'end_date', 'payment_method',
        'min_amount', 'max_amount'
    ])
    
    query = filters['q']
    status = filters['status']
    sale_type = filters['sale_type']
    student = filters['student']
    academic_session = filters['academic_session']
    fiscal_period = filters['fiscal_period']
    start_date = filters['start_date']
    end_date = filters['end_date']
    payment_method = filters['payment_method']
    min_amount = filters['min_amount']
    max_amount = filters['max_amount']
    
    # Build queryset
    sales = UniformSale.objects.select_related(
        'student__current_academic_level',
        'academic_session',
        'fiscal_period',
        'fee_invoice',
        'payment_method',
        'journal_entry'
    ).prefetch_related(
        'items'
    ).annotate(
        item_count=Count('items', distinct=True),
        total_quantity=Sum('items__quantity')
    ).order_by('-sale_date')
    
    # Apply text search
    if query:
        sales = sales.filter(
            Q(sale_number__icontains=query) |
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__admission_number__icontains=query) |
            Q(payment_reference__icontains=query)
        )
    
    # Apply filters
    if status:
        sales = sales.filter(status=status)
    
    if sale_type:
        sales = sales.filter(sale_type=sale_type)
    
    if student:
        sales = sales.filter(student_id=student)
    
    if academic_session:
        sales = sales.filter(academic_session_id=academic_session)
    
    if fiscal_period:
        sales = sales.filter(fiscal_period_id=fiscal_period)
    
    if payment_method:
        sales = sales.filter(payment_method_id=payment_method)
    
    if start_date:
        sales = sales.filter(sale_date__gte=start_date)
    
    if end_date:
        sales = sales.filter(sale_date__lte=end_date)
    
    if min_amount:
        try:
            sales = sales.filter(total_amount__gte=Decimal(min_amount))
        except:
            pass
    
    if max_amount:
        try:
            sales = sales.filter(total_amount__lte=Decimal(max_amount))
        except:
            pass
    
    # Paginate
    sales_page, paginator = paginate_queryset(request, sales, per_page=20)
    
    # Calculate stats
    total = sales.count()
    
    stats = {
        'total': total,
        'draft': sales.filter(status='DRAFT').count(),
        'pending': sales.filter(status='PENDING').count(),
        'paid': sales.filter(status='PAID').count(),
        'issued': sales.filter(status='ISSUED').count(),
        'total_sales': sales.filter(sale_type='SALE').aggregate(
            Sum('total_amount'))['total_amount__sum'] or 0,
        'total_cost': sales.aggregate(Sum('total_cost'))['total_cost__sum'] or 0,
        'total_profit': sales.aggregate(Sum('gross_profit'))['gross_profit__sum'] or 0,
        'total_paid': sales.aggregate(Sum('paid_amount'))['paid_amount__sum'] or 0,
        'total_balance': sales.aggregate(Sum('balance'))['balance__sum'] or 0,
    }
    
    return render(request, 'uniforms/sales/_sale_results.html', {
        'sales_page': sales_page,
        'stats': stats,
    })


# =============================================================================
# STUDENT UNIFORM SIZE SEARCH
# =============================================================================

def student_uniform_size_search(request):
    """HTMX-compatible student uniform size search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'student', 'uniform_item', 'recommended_size',
        'academic_session', 'sizing_method', 'confidence_level',
        'is_current', 'growth_allowance'
    ])
    
    query = filters['q']
    student = filters['student']
    uniform_item = filters['uniform_item']
    recommended_size = filters['recommended_size']
    academic_session = filters['academic_session']
    sizing_method = filters['sizing_method']
    confidence_level = filters['confidence_level']
    is_current = filters['is_current']
    growth_allowance = filters['growth_allowance']
    
    # Build queryset
    size_recommendations = StudentUniformSize.objects.select_related(
        'student__current_academic_level',
        'uniform_item',
        'recommended_size',
        'academic_session'
    ).order_by('-recommendation_date', 'student__first_name')
    
    # Apply text search
    if query:
        size_recommendations = size_recommendations.filter(
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__admission_number__icontains=query) |
            Q(uniform_item__name__icontains=query)
        )
    
    # Apply filters
    if student:
        size_recommendations = size_recommendations.filter(student_id=student)
    
    if uniform_item:
        size_recommendations = size_recommendations.filter(uniform_item_id=uniform_item)
    
    if recommended_size:
        size_recommendations = size_recommendations.filter(recommended_size_id=recommended_size)
    
    if academic_session:
        size_recommendations = size_recommendations.filter(academic_session_id=academic_session)
    
    if sizing_method:
        size_recommendations = size_recommendations.filter(sizing_method=sizing_method)
    
    if confidence_level:
        size_recommendations = size_recommendations.filter(confidence_level=confidence_level)
    
    if is_current is not None:
        size_recommendations = size_recommendations.filter(is_current=(is_current.lower() == 'true'))
    
    if growth_allowance is not None:
        size_recommendations = size_recommendations.filter(growth_allowance=(growth_allowance.lower() == 'true'))
    
    # Paginate
    size_recommendations_page, paginator = paginate_queryset(request, size_recommendations, per_page=20)
    
    # Calculate stats
    total = size_recommendations.count()
    
    stats = {
        'total': total,
        'current': size_recommendations.filter(is_current=True).count(),
        'measured': size_recommendations.filter(sizing_method='MEASURED').count(),
        'fitted': size_recommendations.filter(sizing_method='FITTED').count(),
        'high_confidence': size_recommendations.filter(confidence_level='HIGH').count(),
        'medium_confidence': size_recommendations.filter(confidence_level='MEDIUM').count(),
        'low_confidence': size_recommendations.filter(confidence_level='LOW').count(),
        'with_growth_allowance': size_recommendations.filter(growth_allowance=True).count(),
        'unique_students': size_recommendations.values('student').distinct().count(),
    }
    
    return render(request, 'uniforms/student_sizes/_size_recommendation_results.html', {
        'size_recommendations_page': size_recommendations_page,
        'stats': stats,
    })


# =============================================================================
# MEASUREMENT SESSION SEARCH
# =============================================================================

def measurement_session_search(request):
    """HTMX-compatible measurement session search with pagination and stats"""
    
    # Parse filters
    filters = parse_filters(request, [
        'q', 'session_type', 'status', 'academic_session',
        'start_date', 'end_date'
    ])
    
    query = filters['q']
    session_type = filters['session_type']
    status = filters['status']
    academic_session = filters['academic_session']
    start_date = filters['start_date']
    end_date = filters['end_date']
    
    # Build queryset
    sessions = MeasurementSession.objects.select_related(
        'academic_session'
    ).prefetch_related(
        'target_classes',
        'target_students'
    ).annotate(
        class_count=Count('target_classes', distinct=True),
        student_count=Count('target_students', distinct=True)
    ).order_by('-session_date')
    
    # Apply text search
    if query:
        sessions = sessions.filter(
            Q(session_name__icontains=query) |
            Q(notes__icontains=query)
        )
    
    # Apply filters
    if session_type:
        sessions = sessions.filter(session_type=session_type)
    
    if status:
        sessions = sessions.filter(status=status)
    
    if academic_session:
        sessions = sessions.filter(academic_session_id=academic_session)
    
    if start_date:
        sessions = sessions.filter(session_date__gte=start_date)
    
    if end_date:
        sessions = sessions.filter(session_date__lte=end_date)
    
    # Paginate
    sessions_page, paginator = paginate_queryset(request, sessions, per_page=20)
    
    # Calculate stats
    total = sessions.count()
    
    stats = {
        'total': total,
        'planned': sessions.filter(status='PLANNED').count(),
        'in_progress': sessions.filter(status='IN_PROGRESS').count(),
        'completed': sessions.filter(status='COMPLETED').count(),
        'cancelled': sessions.filter(status='CANCELLED').count(),
        'total_students_measured': sessions.aggregate(
            Sum('total_students_measured'))['total_students_measured__sum'] or 0,
        'total_measurements': sessions.aggregate(
            Sum('total_measurements_taken'))['total_measurements_taken__sum'] or 0,
    }
    
    return render(request, 'uniforms/measurement_sessions/_session_results.html', {
        'sessions_page': sessions_page,
        'stats': stats,
    })


# =============================================================================
# QUICK STATS ENDPOINTS (for dashboard widgets)
# =============================================================================

@require_http_methods(["GET"])
def inventory_quick_stats(request):
    """Get quick statistics for uniform inventory"""
    
    stats = {
        'total_items': UniformItem.objects.filter(is_active=True).count(),
        'low_stock': UniformItem.objects.filter(
            is_active=True,
            current_stock__lte=F('reorder_level')
        ).count(),
        'out_of_stock': UniformItem.objects.filter(
            is_active=True,
            current_stock=0
        ).count(),
        'total_stock_value': UniformItem.objects.filter(
            is_active=True
        ).aggregate(
            total=Sum(F('current_stock') * F('unit_cost'))
        )['total'] or 0,
        'total_selling_value': UniformItem.objects.filter(
            is_active=True
        ).aggregate(
            total=Sum(F('current_stock') * F('selling_price'))
        )['total'] or 0,
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def sales_quick_stats(request):
    """Get quick statistics for uniform sales"""
    
    today = timezone.now().date()
    this_month = today.replace(day=1)
    
    stats = {
        'total_sales': UniformSale.objects.count(),
        'pending_payment': UniformSale.objects.filter(status='PENDING').count(),
        'today_sales': UniformSale.objects.filter(sale_date=today).count(),
        'this_month_sales': UniformSale.objects.filter(
            sale_date__gte=this_month
        ).count(),
        'this_month_revenue': UniformSale.objects.filter(
            sale_date__gte=this_month,
            status__in=['PAID', 'ISSUED']
        ).aggregate(Sum('total_amount'))['total_amount__sum'] or 0,
        'this_month_profit': UniformSale.objects.filter(
            sale_date__gte=this_month,
            status__in=['PAID', 'ISSUED']
        ).aggregate(Sum('gross_profit'))['gross_profit__sum'] or 0,
        'outstanding_balance': UniformSale.objects.filter(
            status__in=['PENDING', 'PARTIAL']
        ).aggregate(Sum('balance'))['balance__sum'] or 0,
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def purchase_order_quick_stats(request):
    """Get quick statistics for purchase orders"""
    
    stats = {
        'total': UniformPurchaseOrder.objects.count(),
        'draft': UniformPurchaseOrder.objects.filter(status='DRAFT').count(),
        'pending': UniformPurchaseOrder.objects.filter(status='SUBMITTED').count(),
        'awaiting_delivery': UniformPurchaseOrder.objects.filter(
            status='ORDERED'
        ).count(),
        'total_outstanding': UniformPurchaseOrder.objects.filter(
            status__in=['SUBMITTED', 'APPROVED', 'ORDERED', 'PARTIAL']
        ).aggregate(Sum('balance_due'))['balance_due__sum'] or 0,
    }
    
    return JsonResponse(stats)


@require_http_methods(["GET"])
def measurement_quick_stats(request):
    """Get quick statistics for measurements"""
    
    today = timezone.now().date()
    this_month = today.replace(day=1)
    
    stats = {
        'total_measurements': StudentMeasurement.objects.count(),
        'current_measurements': StudentMeasurement.objects.filter(is_current=True).count(),
        'verified': StudentMeasurement.objects.filter(is_verified=True).count(),
        'unverified': StudentMeasurement.objects.filter(is_verified=False).count(),
        'this_month': StudentMeasurement.objects.filter(
            measurement_date__gte=this_month
        ).count(),
        'students_measured': StudentMeasurement.objects.filter(
            is_current=True
        ).values('student').distinct().count(),
    }
    
    return JsonResponse(stats)