# uniforms/stats.py

"""
Uniform Management Statistics and Analytics

Centralised functions for all statistical calculations in the uniforms module.
Views, reports, and the dashboard all delegate here so the logic lives in
one place and is independently testable.

Each function returns a plain dict so callers can merge, cache, or serialise
the result without any ORM coupling.

Function index:
    get_inventory_stats()               — stock levels, values, alert counts
    get_sales_stats()                   — revenue, COGS, margin for a period
    get_sales_by_item_type()            — revenue broken down by item type
    get_sales_trend()                   — daily/monthly revenue series
    get_purchase_order_stats()          — PO counts and outstanding value by status
    get_measurement_stats()             — measurement coverage and verification rates
    get_measurement_coverage_by_type()  — count and avg per measurement type
    get_student_uniform_coverage()      — students with sizes / sales this session
    get_measurement_coverage_by_class() — measurement completeness per class
    get_top_selling_items()             — best-selling items by quantity
    get_low_stock_summary()             — items at or below reorder level
    get_stock_valuation()               — total cost/selling value of all stock
    get_cogs_and_margin_stats()         — gross profit and margin for a period
    get_dashboard_stats()               — aggregated snapshot for the dashboard
"""

from django.db.models import (
    Sum, Count, Avg, F, Q, Max, Min, FloatField, ExpressionWrapper,
)
from django.utils import timezone
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# INVENTORY STATISTICS
# =============================================================================

def get_inventory_stats():
    """
    High-level snapshot of the current inventory.

    Returns:
        dict: {
            total_items:        int   — active items
            sized_items:        int   — items that require sizing
            unsized_items:      int   — items that do not require sizing
            low_stock_count:    int   — items at or below reorder level
            out_of_stock_count: int   — items with zero stock
            total_stock_units:  int   — sum of all current_stock values
            total_cost_value:   Decimal
            total_selling_value:Decimal
            potential_profit:   Decimal
            mandatory_items:    int   — items marked is_mandatory
        }
    """
    from .models import UniformItem

    try:
        items = UniformItem.objects.filter(is_active=True)
        agg   = items.aggregate(
            total_units   = Sum('current_stock'),
            cost_value    = Sum(F('current_stock') * F('unit_cost')),
            selling_value = Sum(F('current_stock') * F('selling_price')),
        )

        cost_value    = agg['cost_value']    or Decimal('0.00')
        selling_value = agg['selling_value'] or Decimal('0.00')

        return {
            'total_items':         items.count(),
            'sized_items':         items.filter(requires_sizing=True).count(),
            'unsized_items':       items.filter(requires_sizing=False).count(),
            'low_stock_count':     items.filter(current_stock__lte=F('reorder_level')).count(),
            'out_of_stock_count':  items.filter(current_stock=0).count(),
            'total_stock_units':   agg['total_units'] or 0,
            'total_cost_value':    cost_value,
            'total_selling_value': selling_value,
            'potential_profit':    selling_value - cost_value,
            'mandatory_items':     items.filter(is_mandatory=True).count(),
        }
    except Exception as e:
        logger.error(f"Error in get_inventory_stats: {e}", exc_info=True)
        return {}


# =============================================================================
# SALES STATISTICS
# =============================================================================

def get_sales_stats(date_from=None, date_to=None, academic_session_id=None,
                    fiscal_period_id=None):
    """
    Revenue, cost, and margin aggregates for a date range or session.

    Args:
        date_from:           date | None  — inclusive start
        date_to:             date | None  — inclusive end
        academic_session_id: UUID | None  — filter via fiscal_period
        fiscal_period_id:    UUID | None  — direct fiscal period filter

    Returns:
        dict: {
            total_sales:     int
            draft_count:     int
            pending_count:   int
            paid_count:      int
            issued_count:    int
            cancelled_count: int
            returned_count:  int
            total_revenue:   Decimal  (active sales only)
            total_cost:      Decimal
            gross_profit:    Decimal
            gross_margin_pct:Decimal  (0-100)
            avg_sale_value:  Decimal
            total_discount:  Decimal
            total_tax:       Decimal
        }
    """
    from .models import UniformSale

    try:
        qs = UniformSale.objects.all()

        if date_from:
            qs = qs.filter(sale_date__gte=date_from)
        if date_to:
            qs = qs.filter(sale_date__lte=date_to)
        if academic_session_id:
            qs = qs.filter(
                fiscal_period__related_academic_session_id=academic_session_id
            )
        if fiscal_period_id:
            qs = qs.filter(fiscal_period_id=fiscal_period_id)

        active = qs.filter(cancelled=False, returned=False)
        agg    = active.aggregate(
            revenue  = Sum('total_amount'),
            cost     = Sum('total_cost'),
            profit   = Sum('gross_profit'),
            discount = Sum('discount_amount'),
            tax      = Sum('tax_amount'),
            avg_val  = Avg('total_amount'),
        )

        revenue = agg['revenue'] or Decimal('0.00')
        cost    = agg['cost']    or Decimal('0.00')
        profit  = agg['profit']  or Decimal('0.00')
        margin  = (profit / revenue * 100) if revenue else Decimal('0.00')

        return {
            'total_sales':      qs.count(),
            'draft_count':      qs.filter(status='DRAFT').count(),
            'pending_count':    qs.filter(status='PENDING',   cancelled=False, returned=False).count(),
            'paid_count':       qs.filter(status='PAID',      cancelled=False, returned=False).count(),
            'issued_count':     qs.filter(status='ISSUED',    cancelled=False, returned=False).count(),
            'cancelled_count':  qs.filter(cancelled=True).count(),
            'returned_count':   qs.filter(returned=True).count(),
            'total_revenue':    revenue,
            'total_cost':       cost,
            'gross_profit':     profit,
            'gross_margin_pct': round(margin, 2),
            'avg_sale_value':   agg['avg_val'] or Decimal('0.00'),
            'total_discount':   agg['discount'] or Decimal('0.00'),
            'total_tax':        agg['tax']      or Decimal('0.00'),
        }
    except Exception as e:
        logger.error(f"Error in get_sales_stats: {e}", exc_info=True)
        return {}


def get_sales_by_item_type(date_from=None, date_to=None):
    """
    Break revenue and quantity down by UniformItem.item_type.

    Returns:
        list of dicts: [{
            item_type:         str  (e.g. 'UNIFORM')
            item_type_display: str  (e.g. 'School Uniform')
            quantity_sold:     int
            total_revenue:     Decimal
            total_cost:        Decimal
            gross_profit:      Decimal
        }, ...]
        Ordered by total_revenue descending.
    """
    from .models import UniformSaleItem, UniformItem

    try:
        qs = UniformSaleItem.objects.filter(
            sale__cancelled=False,
            sale__returned=False,
        )
        if date_from:
            qs = qs.filter(sale__sale_date__gte=date_from)
        if date_to:
            qs = qs.filter(sale__sale_date__lte=date_to)

        rows = (
            qs
            .values('uniform_item__item_type')
            .annotate(
                quantity_sold = Sum('quantity'),
                total_revenue = Sum('total_price'),
                total_cost    = Sum('total_cost'),
            )
            .order_by('-total_revenue')
        )

        type_map = dict(UniformItem.ITEM_TYPE_CHOICES)

        return [
            {
                'item_type':         r['uniform_item__item_type'],
                'item_type_display': type_map.get(r['uniform_item__item_type'], r['uniform_item__item_type']),
                'quantity_sold':     r['quantity_sold'] or 0,
                'total_revenue':     r['total_revenue'] or Decimal('0.00'),
                'total_cost':        r['total_cost']    or Decimal('0.00'),
                'gross_profit':      (r['total_revenue'] or Decimal('0.00')) - (r['total_cost'] or Decimal('0.00')),
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Error in get_sales_by_item_type: {e}", exc_info=True)
        return []


def get_sales_trend(date_from, date_to, group_by='day'):
    """
    Time-series of sale count and revenue for charting.

    Args:
        date_from: date — start of range
        date_to:   date — end of range
        group_by:  'day' | 'month'

    Returns:
        list of dicts: [{
            period:      str   (YYYY-MM-DD for day, YYYY-MM for month)
            sale_count:  int
            revenue:     Decimal
        }, ...]
        Ordered chronologically.
    """
    from .models import UniformSale
    from django.db.models.functions import TruncDay, TruncMonth

    try:
        qs = UniformSale.objects.filter(
            sale_date__gte=date_from,
            sale_date__lte=date_to,
            cancelled=False,
            returned=False,
        )

        trunc_fn = TruncDay if group_by == 'day' else TruncMonth

        rows = (
            qs
            .annotate(period=trunc_fn('sale_date'))
            .values('period')
            .annotate(
                sale_count = Count('id'),
                revenue    = Sum('total_amount'),
            )
            .order_by('period')
        )

        fmt = '%Y-%m-%d' if group_by == 'day' else '%Y-%m'

        return [
            {
                'period':     r['period'].strftime(fmt),
                'sale_count': r['sale_count'],
                'revenue':    r['revenue'] or Decimal('0.00'),
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Error in get_sales_trend: {e}", exc_info=True)
        return []


# =============================================================================
# PURCHASE ORDER STATISTICS
# =============================================================================

def get_purchase_order_stats():
    """
    PO counts and outstanding value grouped by status.

    Returns:
        dict: {
            total:             int
            draft:             int
            submitted:         int
            approved:          int
            ordered:           int
            received:          int
            partial:           int
            cancelled:         int
            outstanding_value: Decimal  (DRAFT + SUBMITTED + APPROVED + ORDERED)
            total_value:       Decimal  (all non-cancelled)
        }
    """
    from .models import UniformPurchaseOrder

    try:
        qs  = UniformPurchaseOrder.objects.all()
        agg = qs.aggregate(
            outstanding = Sum(
                'total_amount',
                filter=Q(status__in=['DRAFT', 'SUBMITTED', 'APPROVED', 'ORDERED'])
            ),
            non_cancelled = Sum(
                'total_amount',
                filter=~Q(status='CANCELLED')
            ),
        )

        by_status = {
            row['status']: row['count']
            for row in qs.values('status').annotate(count=Count('id'))
        }

        return {
            'total':             qs.count(),
            'draft':             by_status.get('DRAFT',     0),
            'submitted':         by_status.get('SUBMITTED', 0),
            'approved':          by_status.get('APPROVED',  0),
            'ordered':           by_status.get('ORDERED',   0),
            'received':          by_status.get('RECEIVED',  0),
            'partial':           by_status.get('PARTIAL',   0),
            'cancelled':         by_status.get('CANCELLED', 0),
            'outstanding_value': agg['outstanding']    or Decimal('0.00'),
            'total_value':       agg['non_cancelled']  or Decimal('0.00'),
        }
    except Exception as e:
        logger.error(f"Error in get_purchase_order_stats: {e}", exc_info=True)
        return {}


# =============================================================================
# MEASUREMENT STATISTICS
# =============================================================================

def get_measurement_stats(academic_session_id=None):
    """
    Measurement coverage and verification for a session (or all time).

    Returns:
        dict: {
            total_measurements:   int
            current_measurements: int
            verified:             int
            unverified:           int
            verification_rate_pct:float  (0-100)
            students_measured:    int   (distinct students with ≥1 current measurement)
            measurement_types_in_use: int
            context_breakdown:    list of {context, display, count}
        }
    """
    from .models import StudentMeasurement

    try:
        qs = StudentMeasurement.objects.all()
        if academic_session_id:
            qs = qs.filter(academic_session_id=academic_session_id)

        total    = qs.count()
        verified = qs.filter(is_verified=True).count()
        ver_rate = round((verified / total * 100), 1) if total else 0.0

        context_rows = (
            qs
            .values('measurement_context')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        context_map  = dict(StudentMeasurement.MEASUREMENT_CONTEXT_CHOICES)

        return {
            'total_measurements':      total,
            'current_measurements':    qs.filter(is_current=True).count(),
            'verified':                verified,
            'unverified':              total - verified,
            'verification_rate_pct':   ver_rate,
            'students_measured':       qs.filter(is_current=True).values('student').distinct().count(),
            'measurement_types_in_use':qs.values('measurement_type').distinct().count(),
            'context_breakdown': [
                {
                    'context': r['measurement_context'],
                    'display': context_map.get(r['measurement_context'], r['measurement_context']),
                    'count':   r['count'],
                }
                for r in context_rows
            ],
        }
    except Exception as e:
        logger.error(f"Error in get_measurement_stats: {e}", exc_info=True)
        return {}


def get_measurement_coverage_by_type(academic_session_id=None):
    """
    Per-measurement-type stats: count of current measurements and average value.

    Returns:
        list of dicts: [{
            type_id:       UUID
            type_name:     str
            type_code:     str
            unit:          str   (abbreviation)
            count:         int
            avg_value:     Decimal | None
            min_value:     Decimal | None
            max_value:     Decimal | None
        }, ...]
        Ordered by MeasurementType.display_order.
    """
    from .models import StudentMeasurement, MeasurementType

    try:
        qs = StudentMeasurement.objects.filter(is_current=True)
        if academic_session_id:
            qs = qs.filter(academic_session_id=academic_session_id)

        rows = (
            qs
            .values(
                'measurement_type__id',
                'measurement_type__name',
                'measurement_type__code',
                'measurement_type__unit__abbreviation',
                'measurement_type__display_order',
            )
            .annotate(
                count     = Count('id'),
                avg_value = Avg('value'),
                min_value = Min('value'),
                max_value = Max('value'),
            )
            .order_by('measurement_type__display_order')
        )

        return [
            {
                'type_id':   r['measurement_type__id'],
                'type_name': r['measurement_type__name'],
                'type_code': r['measurement_type__code'],
                'unit':      r['measurement_type__unit__abbreviation'],
                'count':     r['count'],
                'avg_value': r['avg_value'],
                'min_value': r['min_value'],
                'max_value': r['max_value'],
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Error in get_measurement_coverage_by_type: {e}", exc_info=True)
        return []


# =============================================================================
# STUDENT COVERAGE STATISTICS
# =============================================================================

def get_student_uniform_coverage(academic_session_id):
    """
    How many active students have measurements, size recommendations,
    and uniform sales in the given academic session.

    Args:
        academic_session_id: UUID — required

    Returns:
        dict: {
            total_active_students:      int
            students_with_measurements: int
            students_with_sizes:        int
            students_with_sales:        int
            measurement_coverage_pct:   float
            size_coverage_pct:          float
            sales_coverage_pct:         float
        }
    """
    from .models import StudentMeasurement, StudentUniformSize, UniformSale
    from students.models import Student

    try:
        total = Student.objects.filter(enrollment_status='ACTIVE').count()
        if not total:
            return {
                'total_active_students':      0,
                'students_with_measurements': 0,
                'students_with_sizes':        0,
                'students_with_sales':        0,
                'measurement_coverage_pct':   0.0,
                'size_coverage_pct':          0.0,
                'sales_coverage_pct':         0.0,
            }

        measured = (
            StudentMeasurement.objects
            .filter(academic_session_id=academic_session_id, is_current=True)
            .values('student')
            .distinct()
            .count()
        )
        sized = (
            StudentUniformSize.objects
            .filter(academic_session_id=academic_session_id, is_current=True)
            .values('student')
            .distinct()
            .count()
        )
        with_sales = (
            UniformSale.objects
            .filter(
                fiscal_period__related_academic_session_id=academic_session_id,
                cancelled=False,
                returned=False,
            )
            .values('student')
            .distinct()
            .count()
        )

        def pct(n):
            return round(n / total * 100, 1)

        return {
            'total_active_students':      total,
            'students_with_measurements': measured,
            'students_with_sizes':        sized,
            'students_with_sales':        with_sales,
            'measurement_coverage_pct':   pct(measured),
            'size_coverage_pct':          pct(sized),
            'sales_coverage_pct':         pct(with_sales),
        }
    except Exception as e:
        logger.error(f"Error in get_student_uniform_coverage: {e}", exc_info=True)
        return {}


def get_measurement_coverage_by_class(academic_session_id):
    """
    Measurement completeness broken down by class for a given session.

    Returns:
        list of dicts: [{
            class_id:           UUID
            class_name:         str
            enrolled_students:  int
            students_measured:  int
            coverage_pct:       float
        }, ...]
        Ordered by coverage_pct ascending (least covered first).
    """
    from .models import StudentMeasurement
    from academics.models import StudentClassEnrollment

    try:
        # Students enrolled in each class this session.
        enrollments = (
            StudentClassEnrollment.objects
            .filter(
                academic_session_id=academic_session_id,
                is_active=True,
                completion_status='ONGOING',
            )
            .values('class_instance__id', 'class_instance__academic_level__name',
                    'class_instance__section')
            .annotate(enrolled=Count('student', distinct=True))
        )

        # Students who have at least one current measurement this session.
        measured_ids = set(
            StudentMeasurement.objects
            .filter(academic_session_id=academic_session_id, is_current=True)
            .values_list('student_id', flat=True)
            .distinct()
        )

        result = []
        for row in enrollments:
            class_id   = row['class_instance__id']
            level_name = row['class_instance__academic_level__name'] or ''
            section    = row['class_instance__section'] or ''
            name       = f"{level_name} {section}".strip()
            enrolled   = row['enrolled']

            # Count how many of this class's students have measurements.
            class_students = set(
                StudentClassEnrollment.objects
                .filter(
                    class_instance_id=class_id,
                    academic_session_id=academic_session_id,
                    is_active=True,
                    completion_status='ONGOING',
                )
                .values_list('student_id', flat=True)
            )
            measured = len(class_students & measured_ids)

            result.append({
                'class_id':          class_id,
                'class_name':        name,
                'enrolled_students': enrolled,
                'students_measured': measured,
                'coverage_pct':      round(measured / enrolled * 100, 1) if enrolled else 0.0,
            })

        return sorted(result, key=lambda x: x['coverage_pct'])

    except Exception as e:
        logger.error(f"Error in get_measurement_coverage_by_class: {e}", exc_info=True)
        return []


# =============================================================================
# TOP SELLERS & LOW STOCK
# =============================================================================

def get_top_selling_items(limit=10, date_from=None, date_to=None):
    """
    Best-selling uniform items by quantity sold.

    Returns:
        list of dicts: [{
            item_id:       UUID
            item_name:     str
            item_code:     str
            item_type:     str
            quantity_sold: int
            total_revenue: Decimal
            total_cost:    Decimal
            gross_profit:  Decimal
        }, ...]
    """
    from .models import UniformSaleItem

    try:
        qs = UniformSaleItem.objects.filter(
            sale__cancelled=False,
            sale__returned=False,
        )
        if date_from:
            qs = qs.filter(sale__sale_date__gte=date_from)
        if date_to:
            qs = qs.filter(sale__sale_date__lte=date_to)

        rows = (
            qs
            .values(
                'uniform_item__id',
                'uniform_item__name',
                'uniform_item__code',
                'uniform_item__item_type',
            )
            .annotate(
                quantity_sold = Sum('quantity'),
                total_revenue = Sum('total_price'),
                total_cost    = Sum('total_cost'),
            )
            .order_by('-quantity_sold')[:limit]
        )

        return [
            {
                'item_id':       r['uniform_item__id'],
                'item_name':     r['uniform_item__name'],
                'item_code':     r['uniform_item__code'],
                'item_type':     r['uniform_item__item_type'],
                'quantity_sold': r['quantity_sold'] or 0,
                'total_revenue': r['total_revenue'] or Decimal('0.00'),
                'total_cost':    r['total_cost']    or Decimal('0.00'),
                'gross_profit': (r['total_revenue'] or Decimal('0.00'))
                              - (r['total_cost']    or Decimal('0.00')),
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Error in get_top_selling_items: {e}", exc_info=True)
        return []


def get_low_stock_summary(include_out_of_stock=True):
    """
    Items at or below their reorder level, optionally split by severity.

    Returns:
        dict: {
            out_of_stock:   list of UniformItem  (current_stock == 0)
            critical:       list of UniformItem  (0 < current_stock <= reorder_level / 2)
            low:            list of UniformItem  (reorder_level/2 < current_stock <= reorder_level)
            total_count:    int
            reorder_value:  Decimal  — estimated cost to restock to reorder_level
        }
    """
    from .models import UniformItem

    try:
        low_qs = UniformItem.objects.filter(
            is_active=True,
            current_stock__lte=F('reorder_level'),
        ).order_by('current_stock')

        out_of_stock = []
        critical     = []
        low          = []
        reorder_value= Decimal('0.00')

        for item in low_qs:
            shortfall      = max(item.reorder_level - item.current_stock, 0)
            reorder_value += shortfall * item.unit_cost

            if item.current_stock == 0:
                out_of_stock.append(item)
            elif item.current_stock <= item.reorder_level // 2:
                critical.append(item)
            else:
                low.append(item)

        return {
            'out_of_stock':  out_of_stock,
            'critical':      critical,
            'low':           low,
            'total_count':   len(out_of_stock) + len(critical) + len(low),
            'reorder_value': reorder_value,
        }
    except Exception as e:
        logger.error(f"Error in get_low_stock_summary: {e}", exc_info=True)
        return {'out_of_stock': [], 'critical': [], 'low': [], 'total_count': 0, 'reorder_value': Decimal('0.00')}


# =============================================================================
# FINANCIAL STATISTICS
# =============================================================================

def get_stock_valuation():
    """
    Detailed stock valuation across all active items and their stock records.

    Returns:
        dict: {
            total_cost_value:    Decimal  (Sum of UniformStock.total_cost_value)
            total_selling_value: Decimal
            potential_profit:    Decimal
            items_count:         int
            stock_records_count: int
            by_item_type:        list of {item_type, display, cost_value, selling_value}
        }
    """
    from .models import UniformStock, UniformItem

    try:
        agg = UniformStock.objects.aggregate(
            cost_value    = Sum('total_cost_value'),
            selling_value = Sum('total_selling_value'),
            records       = Count('id'),
        )

        cost_value    = agg['cost_value']    or Decimal('0.00')
        selling_value = agg['selling_value'] or Decimal('0.00')

        # Breakdown by item type via UniformItem.
        type_rows = (
            UniformItem.objects
            .filter(is_active=True)
            .values('item_type')
            .annotate(
                cost_value    = Sum(F('current_stock') * F('unit_cost')),
                selling_value = Sum(F('current_stock') * F('selling_price')),
            )
            .order_by('-cost_value')
        )
        type_map = dict(UniformItem.ITEM_TYPE_CHOICES)

        return {
            'total_cost_value':    cost_value,
            'total_selling_value': selling_value,
            'potential_profit':    selling_value - cost_value,
            'items_count':         UniformItem.objects.filter(is_active=True).count(),
            'stock_records_count': agg['records'] or 0,
            'by_item_type': [
                {
                    'item_type':     r['item_type'],
                    'display':       type_map.get(r['item_type'], r['item_type']),
                    'cost_value':    r['cost_value']    or Decimal('0.00'),
                    'selling_value': r['selling_value'] or Decimal('0.00'),
                }
                for r in type_rows
            ],
        }
    except Exception as e:
        logger.error(f"Error in get_stock_valuation: {e}", exc_info=True)
        return {}


def get_cogs_and_margin_stats(date_from=None, date_to=None,
                              academic_session_id=None):
    """
    Gross profit and margin breakdown per uniform item for a period.

    Useful for the sales report profitability section.

    Returns:
        dict: {
            total_revenue:   Decimal
            total_cogs:      Decimal
            gross_profit:    Decimal
            gross_margin_pct:Decimal
            by_item: list of {
                item_id, item_name, item_code,
                quantity_sold, revenue, cogs, profit, margin_pct
            }
        }
    """
    from .models import UniformSaleItem

    try:
        qs = UniformSaleItem.objects.filter(
            sale__cancelled=False,
            sale__returned=False,
        )
        if date_from:
            qs = qs.filter(sale__sale_date__gte=date_from)
        if date_to:
            qs = qs.filter(sale__sale_date__lte=date_to)
        if academic_session_id:
            qs = qs.filter(
                sale__fiscal_period__related_academic_session_id=academic_session_id
            )

        totals = qs.aggregate(
            revenue = Sum('total_price'),
            cogs    = Sum('total_cost'),
        )
        total_rev  = totals['revenue'] or Decimal('0.00')
        total_cogs = totals['cogs']    or Decimal('0.00')
        total_prof = total_rev - total_cogs
        total_marg = (total_prof / total_rev * 100) if total_rev else Decimal('0.00')

        rows = (
            qs
            .values('uniform_item__id', 'uniform_item__name', 'uniform_item__code')
            .annotate(
                qty     = Sum('quantity'),
                revenue = Sum('total_price'),
                cogs    = Sum('total_cost'),
            )
            .order_by('-revenue')
        )

        by_item = []
        for r in rows:
            rev  = r['revenue'] or Decimal('0.00')
            cost = r['cogs']    or Decimal('0.00')
            prof = rev - cost
            marg = round(prof / rev * 100, 2) if rev else Decimal('0.00')
            by_item.append({
                'item_id':      r['uniform_item__id'],
                'item_name':    r['uniform_item__name'],
                'item_code':    r['uniform_item__code'],
                'quantity_sold':r['qty'] or 0,
                'revenue':      rev,
                'cogs':         cost,
                'profit':       prof,
                'margin_pct':   marg,
            })

        return {
            'total_revenue':    total_rev,
            'total_cogs':       total_cogs,
            'gross_profit':     total_prof,
            'gross_margin_pct': round(total_marg, 2),
            'by_item':          by_item,
        }
    except Exception as e:
        logger.error(f"Error in get_cogs_and_margin_stats: {e}", exc_info=True)
        return {}


# =============================================================================
# DASHBOARD AGGREGATED SNAPSHOT
# =============================================================================

def get_dashboard_stats():
    """
    Single call that returns everything needed for the uniforms dashboard.

    Runs each sub-function independently so a failure in one does not
    prevent the rest from rendering.

    Returns:
        dict: {
            inventory:         dict  from get_inventory_stats()
            sales:             dict  from get_sales_stats() for this month
            sales_this_month:  dict  from get_sales_stats() for this month
            purchase_orders:   dict  from get_purchase_order_stats()
            measurements:      dict  from get_measurement_stats()
            low_stock:         dict  from get_low_stock_summary()
            top_sellers:       list  from get_top_selling_items(5)
            stock_valuation:   dict  from get_stock_valuation()
        }
    """
    from core.utils import get_school_today

    today      = get_school_today()
    month_start= today.replace(day=1)

    results = {}

    for key, fn, kwargs in [
        ('inventory',        get_inventory_stats,       {}),
        ('sales',            get_sales_stats,           {}),
        ('sales_this_month', get_sales_stats,           {'date_from': month_start, 'date_to': today}),
        ('purchase_orders',  get_purchase_order_stats,  {}),
        ('measurements',     get_measurement_stats,     {}),
        ('low_stock',        get_low_stock_summary,     {}),
        ('stock_valuation',  get_stock_valuation,       {}),
    ]:
        try:
            results[key] = fn(**kwargs)
        except Exception as e:
            logger.error(f"Dashboard stats error for '{key}': {e}", exc_info=True)
            results[key] = {}

    try:
        results['top_sellers'] = get_top_selling_items(
            limit=5, date_from=month_start, date_to=today
        )
    except Exception as e:
        logger.error(f"Dashboard stats error for 'top_sellers': {e}", exc_info=True)
        results['top_sellers'] = []

    return results