# uniforms/utils.py

"""
Uniform Management Utility Functions

Provides helper functions for:
- Reference number generation (sale numbers, PO numbers, receipt numbers)
- Size recommendation algorithms
- Stock availability checks
- Pricing calculations
- Measurement conversions
- Sale cancellation and return processing

CHANGES FROM ORIGINAL:
- Removed generate_measurement_session_code() — MeasurementSession model
  has been removed. Measurement sessions are no longer a concept in this app.
- Fixed export_stock_levels_to_csv() — removed reference to item.category
  which no longer exists on UniformItem. Now uses item.get_item_type_display().
- Fixed apply_growth_allowance() — uses get_school_today() from core.utils
  instead of timezone.now().date() for consistent timezone behaviour.
- Fixed check_stock_availability() — unsized items read available_quantity
  from UniformStock (size=None) not from item.current_stock, so the check
  reflects reserved quantities correctly.
- Fixed bulk_adjust_stock() — unsized item branch routes through UniformStock
  (get_or_create size=None + stock.save()) instead of writing current_stock
  directly on UniformItem. Writing current_stock directly bypassed the signal.
- Fixed return_uniform_sale() — unsized item branch routes through UniformStock
  so the uniform_stock_post_save signal keeps current_stock accurate. Also
  added entry_number to JournalEntry creation to match the pattern used in
  _create_purchase_order_journal_entry in signals.py.
- Stock only moves on issue/return — cancel_uniform_sale() does not restore
  stock because stock is only decremented when items are physically issued
  (status → ISSUED). A cancelled pre-issue sale has no stock to restore.
"""

from django.db import transaction
from django.db.models import Max, Q, Count, F, Sum
from django.utils import timezone
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# REFERENCE NUMBER GENERATION
# =============================================================================

def generate_uniform_sale_number():
    """
    Generate a unique uniform sale number.
    Format: US-YYYY-NNNNN (e.g. US-2024-00001)
    Thread-safe via select_for_update.
    """
    from .models import UniformSale

    current_year = timezone.now().year
    prefix = f"US-{current_year}-"

    with transaction.atomic():
        result = (
            UniformSale.objects
            .filter(sale_number__startswith=prefix)
            .select_for_update()
            .aggregate(max_number=Max('sale_number'))
        )

        if result['max_number']:
            try:
                last_number = int(result['max_number'].split('-')[-1])
                new_number  = last_number + 1
            except (ValueError, IndexError):
                new_number = (
                    UniformSale.objects
                    .filter(sale_number__startswith=prefix)
                    .count() + 1
                )
        else:
            new_number = 1

        return f"{prefix}{new_number:05d}"


def generate_purchase_order_number():
    """
    Generate a unique purchase order number.
    Format: PO-YYYY-NNNNN (e.g. PO-2024-00001)
    Thread-safe via select_for_update.
    """
    from .models import UniformPurchaseOrder

    current_year = timezone.now().year
    prefix = f"PO-{current_year}-"

    with transaction.atomic():
        result = (
            UniformPurchaseOrder.objects
            .filter(po_number__startswith=prefix)
            .select_for_update()
            .aggregate(max_number=Max('po_number'))
        )

        if result['max_number']:
            try:
                last_number = int(result['max_number'].split('-')[-1])
                new_number  = last_number + 1
            except (ValueError, IndexError):
                new_number = (
                    UniformPurchaseOrder.objects
                    .filter(po_number__startswith=prefix)
                    .count() + 1
                )
        else:
            new_number = 1

        return f"{prefix}{new_number:05d}"


def generate_cash_receipt_number():
    """
    Generate a unique cash receipt number for cash payments.
    Called automatically by the uniform_sale_pre_save signal when
    the payment method is CASH and no reference has been set.
    Format: RCP-YYYY-NNNNN (e.g. RCP-2025-00001)
    Thread-safe via select_for_update.
    """
    from .models import UniformSale

    current_year = timezone.now().year
    prefix = f"RCP-{current_year}-"

    with transaction.atomic():
        result = (
            UniformSale.objects
            .filter(payment_reference__startswith=prefix)
            .select_for_update()
            .aggregate(max_ref=Max('payment_reference'))
        )

        if result['max_ref']:
            try:
                last_number = int(result['max_ref'].split('-')[-1])
                new_number  = last_number + 1
            except (ValueError, IndexError):
                new_number = (
                    UniformSale.objects
                    .filter(payment_reference__startswith=prefix)
                    .count() + 1
                )
        else:
            new_number = 1

        return f"{prefix}{new_number:05d}"


# =============================================================================
# SIZE RECOMMENDATION
# =============================================================================

def recommend_size_from_measurements(student, uniform_item):
    """
    Recommend a uniform size for a student based on their current measurements.

    Scores every available size for the item against the student's current
    measurements. HEIGHT, CHEST, and WAIST are the primary signals. Each
    measurement is scored 0–100 depending on how well it falls within the
    size's configured range, with partial credit for values that are close
    but outside the range. The best-scoring size is recommended.

    The recommendation algorithm reads measurement_type.code to look up
    HEIGHT, CHEST, and WAIST — this is why MeasurementType.code values
    must follow those conventions.

    Args:
        student:      Student instance
        uniform_item: UniformItem instance

    Returns:
        dict: {
            'recommended_size':  UniformSize or None,
            'confidence':        'HIGH' | 'MEDIUM' | 'LOW',
            'alternative_sizes': list of UniformSize (up to 3),
            'reason':            str explanation,
        }
    """
    from .models import StudentMeasurement

    no_recommendation = {
        'recommended_size':  None,
        'confidence':        'LOW',
        'alternative_sizes': [],
        'reason':            '',
    }

    # Fetch the student's current measurements, keyed by measurement type code.
    measurements = StudentMeasurement.objects.filter(
        student=student,
        is_current=True,
    ).select_related('measurement_type')

    if not measurements.exists():
        no_recommendation['reason'] = 'No measurements recorded for this student'
        return no_recommendation

    measurement_dict = {
        m.measurement_type.code.upper(): float(m.value)
        for m in measurements
    }

    # Get all active sizes available for this item.
    available_sizes = uniform_item.available_sizes.filter(is_active=True).order_by(
        'display_order'
    )

    if not available_sizes.exists():
        no_recommendation['reason'] = 'No sizes configured for this item'
        return no_recommendation

    # ── Score each size ───────────────────────────────────────────────────────

    size_scores = []

    for size in available_sizes:
        score        = 0
        matches      = 0   # measurements that fall perfectly in range
        total_checks = 0   # measurements we had data + range for

        def _score_dimension(value, lo, hi):
            """
            Score a single measurement against a size range.
            Perfect fit = 100, just outside = 70, further out = 40, far = 0.
            """
            if lo is None or hi is None:
                return None  # no range defined for this dimension
            if lo <= value <= hi:
                return 100
            tolerance_1 = (hi - lo) * 0.1   # 10 % of range width
            tolerance_2 = (hi - lo) * 0.25  # 25 % of range width
            if (lo - tolerance_1) <= value <= (hi + tolerance_1):
                return 70
            if (lo - tolerance_2) <= value <= (hi + tolerance_2):
                return 40
            return 0

        # Height
        if 'HEIGHT' in measurement_dict:
            result = _score_dimension(
                measurement_dict['HEIGHT'],
                float(size.min_height) if size.min_height else None,
                float(size.max_height) if size.max_height else None,
            )
            if result is not None:
                total_checks += 1
                score += result
                if result == 100:
                    matches += 1

        # Chest
        if 'CHEST' in measurement_dict:
            result = _score_dimension(
                measurement_dict['CHEST'],
                float(size.min_chest) if size.min_chest else None,
                float(size.max_chest) if size.max_chest else None,
            )
            if result is not None:
                total_checks += 1
                score += result
                if result == 100:
                    matches += 1

        # Waist
        if 'WAIST' in measurement_dict:
            result = _score_dimension(
                measurement_dict['WAIST'],
                float(size.min_waist) if size.min_waist else None,
                float(size.max_waist) if size.max_waist else None,
            )
            if result is not None:
                total_checks += 1
                score += result
                if result == 100:
                    matches += 1

        if total_checks > 0:
            avg_score = score / total_checks
            size_scores.append({
                'size':         size,
                'avg_score':    avg_score,
                'matches':      matches,
                'total_checks': total_checks,
            })

    if not size_scores:
        no_recommendation['reason'] = (
            'No size ranges are configured — add height/chest/waist ranges '
            'to the available sizes for this item'
        )
        return no_recommendation

    # Sort: highest average score first, then most perfect matches.
    size_scores.sort(key=lambda x: (x['avg_score'], x['matches']), reverse=True)

    best          = size_scores[0]
    best_size     = best['size']
    avg_score     = best['avg_score']
    matches       = best['matches']
    total_checks  = best['total_checks']

    # ── Confidence level ──────────────────────────────────────────────────────

    if matches == total_checks and total_checks > 0:
        confidence = 'HIGH'
        reason = f"All {matches} measurement(s) fall perfectly within this size's ranges"
    elif avg_score >= 80:
        confidence = 'HIGH'
        reason = (
            f"Strong match — {matches}/{total_checks} measurement(s) in range, "
            f"others very close"
        )
    elif avg_score >= 50:
        confidence = 'MEDIUM'
        reason = (
            f"Good match — {matches}/{total_checks} measurement(s) in range"
        )
    else:
        confidence = 'LOW'
        reason = (
            f"Weak match — only {matches}/{total_checks} measurement(s) in range. "
            f"Consider fitting the student manually."
        )

    # Up to 3 alternatives (excluding the recommended size).
    alternative_sizes = [s['size'] for s in size_scores[1:4]]

    return {
        'recommended_size':  best_size,
        'confidence':        confidence,
        'alternative_sizes': alternative_sizes,
        'reason':            reason,
    }


def apply_growth_allowance(recommended_size, student, uniform_item):
    """
    Suggest one size up to account for expected growth.

    Applied automatically by the student_measurement_post_save signal for
    students below age 15. Uses get_school_today() for consistent timezone
    behaviour rather than timezone.now().date().

    Args:
        recommended_size: Currently recommended UniformSize
        student:          Student instance
        uniform_item:     UniformItem instance

    Returns:
        UniformSize: One size up if applicable, otherwise the input size.
    """
    from core.utils import get_school_today

    if not getattr(student, 'date_of_birth', None):
        return recommended_size

    today = get_school_today()
    age   = (today - student.date_of_birth).days // 365

    # Students 15 and older are unlikely to need a growth allowance.
    if age >= 15:
        return recommended_size

    sizes = list(
        uniform_item.available_sizes.filter(is_active=True).order_by('display_order')
    )

    try:
        idx = sizes.index(recommended_size)
        if idx < len(sizes) - 1:
            logger.debug(
                f"Growth allowance applied for {student.get_full_name()} "
                f"(age {age}): {recommended_size.name} → {sizes[idx + 1].name}"
            )
            return sizes[idx + 1]
    except (ValueError, IndexError):
        pass

    return recommended_size


# =============================================================================
# STOCK AVAILABILITY
# =============================================================================

def check_stock_availability(uniform_item, size=None, quantity=1):
    """
    Check whether sufficient stock is available for a sale line item.

    Reads available_quantity from the UniformStock record — not from
    item.current_stock — so that reserved quantities are correctly
    reflected for both sized and unsized items.

    Args:
        uniform_item: UniformItem instance
        size:         UniformSize instance (or None for unsized items)
        quantity:     Units required

    Returns:
        dict: {
            'available':          bool,
            'quantity_available': int,
            'quantity_requested': int,
            'message':            str,
        }
    """
    from .models import UniformStock

    try:
        if uniform_item.requires_sizing and size:
            stock = UniformStock.objects.get(uniform_item=uniform_item, size=size)
        else:
            stock = UniformStock.objects.get(uniform_item=uniform_item, size__isnull=True)
        available_qty = stock.available_quantity
    except UniformStock.DoesNotExist:
        available_qty = 0

    is_available = available_qty >= quantity

    if is_available:
        message = f"{available_qty} unit(s) available"
    else:
        shortage = quantity - available_qty
        message  = (
            f"Insufficient stock: {available_qty} available, "
            f"{quantity} requested (short by {shortage})"
        )

    return {
        'available':          is_available,
        'quantity_available': available_qty,
        'quantity_requested': quantity,
        'message':            message,
    }


def get_low_stock_items(threshold=None):
    """
    Return active UniformItems at or below the given stock threshold.
    If threshold is None, each item's own reorder_level is used.
    """
    from .models import UniformItem

    if threshold is not None:
        return UniformItem.objects.filter(
            is_active=True,
            current_stock__lte=threshold,
        ).order_by('current_stock')

    return UniformItem.objects.filter(
        is_active=True,
        current_stock__lte=F('reorder_level'),
    ).order_by('current_stock')


def get_out_of_stock_items():
    """Return active UniformItems with zero stock."""
    from .models import UniformItem

    return UniformItem.objects.filter(
        is_active=True,
        current_stock=0,
    ).order_by('name')


# =============================================================================
# PRICING CALCULATIONS
# =============================================================================

def calculate_uniform_bundle_price(items_with_quantities):
    """
    Calculate the total price for a bundle of uniform items.

    Args:
        items_with_quantities: list of dicts:
            [{'uniform_item': UniformItem, 'quantity': int}, ...]

    Returns:
        dict: {
            'subtotal':        Decimal,
            'tax_amount':      Decimal,
            'total_amount':    Decimal,
            'items_breakdown': list of dicts,
        }
    """
    from core.models import FinancialSettings

    settings          = FinancialSettings.get_instance()
    default_tax_rate  = settings.default_tax_rate if settings else Decimal('18.00')

    subtotal        = Decimal('0.00')
    tax_amount      = Decimal('0.00')
    items_breakdown = []

    for item_data in items_with_quantities:
        uniform_item = item_data['uniform_item']
        quantity     = item_data['quantity']
        line_total   = uniform_item.selling_price * quantity
        subtotal    += line_total

        if uniform_item.is_taxable:
            rate       = uniform_item.tax_rate.rate if uniform_item.tax_rate else default_tax_rate
            line_tax   = (line_total * rate) / 100
            tax_amount += line_tax
        else:
            line_tax = Decimal('0.00')

        items_breakdown.append({
            'item':       uniform_item,
            'quantity':   quantity,
            'unit_price': uniform_item.selling_price,
            'line_total': line_total,
            'tax_amount': line_tax,
        })

    return {
        'subtotal':        subtotal,
        'tax_amount':      tax_amount,
        'total_amount':    subtotal + tax_amount,
        'items_breakdown': items_breakdown,
    }


def apply_discount_to_amount(amount, discount_percentage=None, discount_amount=None):
    """
    Apply either a percentage or a fixed discount to an amount.

    Args:
        amount:              Original amount (numeric or Decimal)
        discount_percentage: Percentage discount (0–100), or None
        discount_amount:     Fixed discount amount, or None

    Returns:
        dict: {
            'original_amount': Decimal,
            'discount_amount': Decimal,
            'final_amount':    Decimal,  (floored at 0)
        }
    """
    original = Decimal(str(amount))

    if discount_percentage:
        discount = (original * Decimal(str(discount_percentage))) / 100
    elif discount_amount:
        discount = Decimal(str(discount_amount))
    else:
        discount = Decimal('0.00')

    final = original - discount
    if final < 0:
        discount = original
        final    = Decimal('0.00')

    return {
        'original_amount': original,
        'discount_amount': discount,
        'final_amount':    final,
    }


# =============================================================================
# MEASUREMENT UTILITIES
# =============================================================================

def convert_measurement(value, from_unit, to_unit):
    """
    Convert a measurement value between two UnitOfMeasure instances.

    Args:
        value:     Numeric measurement value
        from_unit: UnitOfMeasure instance (source)
        to_unit:   UnitOfMeasure instance (target)

    Returns:
        Decimal: Converted value

    Raises:
        ValueError: If the units belong to different measurement types.
    """
    if from_unit == to_unit:
        return Decimal(str(value))

    if from_unit.uom_type != to_unit.uom_type:
        raise ValueError(
            f"Cannot convert between '{from_unit.uom_type}' and "
            f"'{to_unit.uom_type}' — incompatible measurement types"
        )

    base_value = Decimal(str(value)) * from_unit.conversion_factor
    return base_value / to_unit.conversion_factor


def validate_measurement_value(measurement_type, value):
    """
    Check whether a value is within the acceptable range for a MeasurementType.

    Args:
        measurement_type: MeasurementType instance
        value:            Measurement value to check

    Returns:
        dict: {
            'valid':    bool,
            'message':  str,
            'warnings': list of str,
        }
    """
    warnings = []

    try:
        value_decimal = Decimal(str(value))
    except (ValueError, TypeError):
        return {'valid': False, 'message': 'Invalid numeric value', 'warnings': []}

    unit_abbr = measurement_type.unit.abbreviation

    if measurement_type.min_value is not None and value_decimal < measurement_type.min_value:
        return {
            'valid':    False,
            'message':  (
                f"{measurement_type.name} value {value_decimal} is below the "
                f"minimum of {measurement_type.min_value} {unit_abbr}"
            ),
            'warnings': [],
        }

    if measurement_type.max_value is not None and value_decimal > measurement_type.max_value:
        return {
            'valid':    False,
            'message':  (
                f"{measurement_type.name} value {value_decimal} is above the "
                f"maximum of {measurement_type.max_value} {unit_abbr}"
            ),
            'warnings': [],
        }

    # Soft warnings when within 10 % of a bound.
    if measurement_type.min_value is not None:
        if value_decimal < measurement_type.min_value * Decimal('1.1'):
            warnings.append(
                f"Value is close to the minimum ({measurement_type.min_value} {unit_abbr})"
            )

    if measurement_type.max_value is not None:
        if value_decimal > measurement_type.max_value * Decimal('0.9'):
            warnings.append(
                f"Value is close to the maximum ({measurement_type.max_value} {unit_abbr})"
            )

    return {'valid': True, 'message': 'Value is within acceptable range', 'warnings': warnings}


# =============================================================================
# BULK OPERATIONS
# =============================================================================

def bulk_update_uniform_prices(uniform_items, price_increase_percentage):
    """
    Increase (or decrease) selling prices for multiple items by a percentage.

    Args:
        uniform_items:            QuerySet or iterable of UniformItem instances
        price_increase_percentage: Percentage change (negative = price reduction)

    Returns:
        dict: {
            'updated_count': int,
            'items_updated': list of dicts with old/new prices,
        }
    """
    multiplier    = 1 + (Decimal(str(price_increase_percentage)) / 100)
    items_updated = []
    updated_count = 0

    with transaction.atomic():
        for item in uniform_items:
            old_price = item.selling_price
            new_price = (old_price * multiplier).quantize(Decimal('0.01'))

            item.selling_price = new_price
            item.save()

            items_updated.append({
                'item':      item,
                'old_price': old_price,
                'new_price': new_price,
                'change':    new_price - old_price,
            })
            updated_count += 1

    logger.info(
        f"Bulk price update: {updated_count} item(s) "
        f"by {price_increase_percentage}%"
    )
    return {'updated_count': updated_count, 'items_updated': items_updated}


def bulk_adjust_stock(adjustments):
    """
    Adjust stock levels for multiple items in a single transaction.

    All adjustments go through UniformStock.save() so the
    uniform_stock_post_save signal keeps UniformItem.current_stock accurate
    for both sized and unsized items. Never writes current_stock directly
    on UniformItem.

    Args:
        adjustments: list of dicts:
            [
                {
                    'uniform_item': UniformItem,
                    'size':         UniformSize or None,
                    'adjustment':   int (positive = add, negative = remove),
                },
                ...
            ]

    Returns:
        dict: {
            'adjusted_count':   int,
            'adjustments_made': list of dicts,
        }
    """
    from .models import UniformStock

    adjustments_made = []
    adjusted_count   = 0

    with transaction.atomic():
        for adj in adjustments:
            uniform_item = adj['uniform_item']
            size         = adj.get('size')
            adjustment   = adj['adjustment']

            stock, _ = UniformStock.objects.get_or_create(
                uniform_item=uniform_item,
                size=size,
                defaults={'quantity': 0},
            )

            old_quantity    = stock.quantity
            stock.quantity  = max(0, stock.quantity + adjustment)
            stock.save()
            # Signal syncs uniform_item.current_stock after save().

            adjustments_made.append({
                'item':         uniform_item,
                'size':         size,
                'old_quantity': old_quantity,
                'new_quantity': stock.quantity,
                'adjustment':   adjustment,
            })
            adjusted_count += 1

    logger.info(f"Bulk stock adjustment: {adjusted_count} record(s) updated")
    return {'adjusted_count': adjusted_count, 'adjustments_made': adjustments_made}


# =============================================================================
# REPORTING UTILITIES
# =============================================================================

def get_uniform_sales_summary(start_date, end_date):
    """
    Aggregate uniform sales statistics for a date range.

    Args:
        start_date: date
        end_date:   date

    Returns:
        dict: totals and margin percentage.
    """
    from .models import UniformSale
    from django.db.models import Avg

    sales = UniformSale.objects.filter(
        sale_date__range=[start_date, end_date],
        status__in=['PAID', 'PARTIAL', 'ISSUED'],
        cancelled=False,
        returned=False,
    )

    summary = sales.aggregate(
        total_sales=Sum('total_amount'),
        total_cost=Sum('total_cost'),
        total_profit=Sum('gross_profit'),
        count=Count('id'),
        avg_sale=Avg('total_amount'),
    )

    total_sales  = summary.get('total_sales') or Decimal('0.00')
    total_profit = summary.get('total_profit') or Decimal('0.00')

    summary['margin_percentage'] = (
        (total_profit / total_sales * 100) if total_sales else Decimal('0.00')
    )
    return summary


def get_best_selling_items(start_date, end_date, limit=10):
    """
    Return the top-selling uniform items for a date range.

    Args:
        start_date: date
        end_date:   date
        limit:      Maximum number of items to return

    Returns:
        list of dicts with item identifiers and sales totals.
    """
    from .models import UniformSaleItem

    return list(
        UniformSaleItem.objects.filter(
            sale__sale_date__range=[start_date, end_date],
            sale__status__in=['PAID', 'PARTIAL', 'ISSUED'],
            sale__cancelled=False,
            sale__returned=False,
        )
        .values('uniform_item__id', 'uniform_item__name', 'uniform_item__code')
        .annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum('total_price'),
            sale_count=Count('sale__id', distinct=True),
        )
        .order_by('-total_quantity')[:limit]
    )


def get_inventory_valuation():
    """
    Calculate total inventory value at cost and at selling price.

    Returns:
        dict: {
            'cost_value':      Decimal,
            'selling_value':   Decimal,
            'potential_profit':Decimal,
            'items_count':     int,
        }
    """
    from .models import UniformItem

    valuation = UniformItem.objects.filter(is_active=True).aggregate(
        cost_value=Sum(F('current_stock') * F('unit_cost')),
        selling_value=Sum(F('current_stock') * F('selling_price')),
        items_count=Count('id'),
    )

    cost_value    = valuation['cost_value']    or Decimal('0.00')
    selling_value = valuation['selling_value'] or Decimal('0.00')

    return {
        'cost_value':       cost_value,
        'selling_value':    selling_value,
        'potential_profit': selling_value - cost_value,
        'items_count':      valuation['items_count'] or 0,
    }


# =============================================================================
# EXPORT UTILITIES
# =============================================================================

def export_stock_levels_to_csv():
    """
    Export current stock levels to a CSV string.

    Uses item.get_item_type_display() instead of the removed item.category
    field. Groups sized items by their per-size stock records and unsized
    items by their single size=None stock record.

    Returns:
        str: CSV data
    """
    from .models import UniformItem
    import csv
    from io import StringIO

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        'Item Code', 'Item Name', 'Item Type', 'Size',
        'Quantity', 'Reserved', 'Available',
        'Unit Cost', 'Selling Price',
        'Stock Value (Cost)', 'Stock Value (Selling)', 'Status',
    ])

    items = UniformItem.objects.filter(
        is_active=True
    ).prefetch_related('stock_records__size').order_by('item_type', 'name')

    for item in items:
        item_type_display = item.get_item_type_display()
        status_label      = 'Low Stock' if item.is_low_stock else 'OK'

        stock_records = item.stock_records.all()

        if stock_records.exists():
            for stock in stock_records:
                size_label = stock.size.name if stock.size else 'N/A'
                writer.writerow([
                    item.code,
                    item.name,
                    item_type_display,
                    size_label,
                    stock.quantity,
                    stock.reserved_quantity,
                    stock.available_quantity,
                    item.unit_cost,
                    item.selling_price,
                    stock.quantity * item.unit_cost,
                    stock.quantity * item.selling_price,
                    status_label,
                ])
        else:
            # Item exists but has no stock records yet.
            writer.writerow([
                item.code, item.name, item_type_display, 'N/A',
                0, 0, 0,
                item.unit_cost, item.selling_price,
                0, 0, status_label,
            ])

    return output.getvalue()


# =============================================================================
# VALIDATION UTILITIES
# =============================================================================

def validate_uniform_sale_data(sale_data):
    """
    Validate a uniform sale data dict before creating the sale.

    Args:
        sale_data: dict with 'student', 'items' (list), and optionally
                   'discount_amount'

    Returns:
        dict: {
            'valid':    bool,
            'errors':   list of str,
            'warnings': list of str,
        }
    """
    errors   = []
    warnings = []

    if 'student' not in sale_data:
        errors.append("Student is required")

    items = sale_data.get('items', [])
    if not items:
        errors.append("At least one item is required")

    for idx, item_data in enumerate(items, start=1):
        prefix       = f"Item {idx}"
        uniform_item = item_data.get('uniform_item')

        if not uniform_item:
            errors.append(f"{prefix}: uniform_item is required")
            continue

        if uniform_item.requires_sizing and 'size' not in item_data:
            errors.append(f"{prefix}: {uniform_item.name} requires a size")

        quantity = item_data.get('quantity', 1)
        if quantity <= 0:
            errors.append(f"{prefix}: quantity must be greater than zero")

        size         = item_data.get('size')
        availability = check_stock_availability(uniform_item, size, quantity)
        if not availability['available']:
            errors.append(f"{prefix}: {availability['message']}")

    discount = sale_data.get('discount_amount', 0)
    if discount < 0:
        errors.append("Discount amount cannot be negative")

    return {
        'valid':    len(errors) == 0,
        'errors':   errors,
        'warnings': warnings,
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_size_display(size):
    """Return a human-readable size label, or 'One Size' if size is None."""
    return f"Size {size.name}" if size else "One Size"


def get_student_uniform_history(student):
    """
    Return all uniform sales for a student, most recent first.

    Args:
        student: Student instance

    Returns:
        QuerySet: UniformSale instances with items pre-fetched.
    """
    from .models import UniformSale

    return (
        UniformSale.objects
        .filter(student=student)
        .order_by('-sale_date')
        .prefetch_related('items__uniform_item', 'items__size')
    )


def calculate_reorder_quantity(uniform_item, target_days=90):
    """
    Suggest a reorder quantity based on 90-day sales velocity.

    Looks back 90 days to calculate average daily sales, then projects
    forward to cover target_days of demand. Returns the item's own
    reorder_level if no recent sales data is available.

    Args:
        uniform_item: UniformItem instance
        target_days:  Days of stock to target (default 90)

    Returns:
        int: Recommended quantity to order.
    """
    from .models import UniformSaleItem
    from datetime import timedelta
    from core.utils import get_school_today

    lookback_date = get_school_today() - timedelta(days=90)

    total_sold = (
        UniformSaleItem.objects
        .filter(
            uniform_item=uniform_item,
            sale__sale_date__gte=lookback_date,
            sale__status__in=['PAID', 'PARTIAL', 'ISSUED'],
            sale__cancelled=False,
            sale__returned=False,
        )
        .aggregate(total=Sum('quantity'))['total'] or 0
    )

    if total_sold == 0:
        return uniform_item.reorder_level

    daily_velocity   = total_sold / 90.0
    target_quantity  = int(daily_velocity * target_days)
    reorder_quantity = max(0, target_quantity - uniform_item.current_stock)

    return reorder_quantity


# =============================================================================
# SALE CANCELLATION AND RETURN PROCESSING
# =============================================================================

@transaction.atomic
def cancel_uniform_sale(sale, user, reason):
    """
    Cancel a uniform sale that has NOT yet been issued.

    Stock is NOT restored here. Stock is only decremented when items are
    physically issued (status → ISSUED). A sale cancelled before issue
    has never touched stock, so there is nothing to restore.

    Actions:
    1. Mark the sale as CANCELLED.
    2. Cancel the linked fee invoice if one exists.
    3. Warn if payments were already recorded (manual refund required).

    Args:
        sale:   UniformSale instance
        user:   User performing the cancellation
        reason: str reason for cancellation

    Returns:
        tuple: (success: bool, message: str)
    """
    can_cancel, msg = sale.can_be_cancelled()
    if not can_cancel:
        return False, msg

    try:
        sale.cancelled           = True
        sale.cancelled_on        = timezone.now()
        sale.cancelled_by_id     = str(user.id)
        sale.cancellation_reason = reason
        sale.status              = 'CANCELLED'
        sale.save()

        if sale.fee_invoice:
            sale.fee_invoice.status = 'CANCELLED'
            sale.fee_invoice.save()
            logger.info(
                f"Cancelled invoice {sale.fee_invoice.invoice_number} "
                f"for sale {sale.sale_number}"
            )

        # Warn if payment was already made — a manual refund is needed.
        if sale.paid_amount > 0 and sale.fee_invoice:
            outstanding = sale.fee_invoice.payments.filter(
                status='COMPLETED',
                reversed=False,
                refunded=False,
            )
            if outstanding.exists():
                payment_numbers = [p.payment_number for p in outstanding]
                logger.warning(
                    f"Sale {sale.sale_number} cancelled but has outstanding "
                    f"payment(s) {payment_numbers} — process refund manually"
                )

        logger.info(f"Sale {sale.sale_number} cancelled by {user}")
        return True, "Sale cancelled successfully"

    except Exception as e:
        logger.error(
            f"Error cancelling sale {sale.sale_number}: {e}", exc_info=True
        )
        return False, f"Error: {str(e)}"


@transaction.atomic
def return_uniform_sale(sale, user, reason, condition):
    """
    Process a return of issued uniforms (items come back to the warehouse).

    Stock IS restored here because the sale was already issued and stock
    was decremented at that point. Restoration goes through UniformStock.save()
    so the uniform_stock_post_save signal keeps UniformItem.current_stock
    accurate for both sized and unsized items.

    Actions:
    1. Mark the sale as RETURNED.
    2. Restore stock for every line item via UniformStock.
    3. Create a reversal journal entry (revenue + COGS reversed).
    4. Cancel the linked invoice and warn about outstanding payments.

    Args:
        sale:      UniformSale instance (must be in ISSUED status)
        user:      User processing the return
        reason:    str reason for return
        condition: str return condition code (GOOD, FAIR, WORN, DAMAGED, UNUSABLE)

    Returns:
        tuple: (success: bool, message: str, journal_entry: JournalEntry or None)
    """
    can_return, msg = sale.can_be_returned()
    if not can_return:
        return False, msg, None

    try:
        from finance.models import JournalEntry, JournalTransaction, Journal
        from core.models import FiscalPeriod
        from .models import UniformStock

        # 1. Mark as returned.
        sale.returned        = True
        sale.returned_on     = timezone.now()
        sale.returned_by_id  = str(user.id)
        sale.return_reason   = reason
        sale.return_condition= condition
        sale.status          = 'RETURNED'

        # 2. Restore stock for every line item.
        for item in sale.items.select_related('uniform_item', 'size').all():
            stock, _ = UniformStock.objects.get_or_create(
                uniform_item=item.uniform_item,
                size=item.size,             # None for unsized items
                defaults={'quantity': 0},
            )
            stock.quantity += item.quantity
            stock.save()
            # uniform_stock_post_save signal syncs item.current_stock.

            size_label = f" Size {item.size.name}" if item.size else " (unsized)"
            logger.info(
                f"Stock restored: {item.uniform_item.name}{size_label} "
                f"+{item.quantity} (now {stock.quantity})"
            )

        # 3. Create reversal journal entry.
        fiscal_period    = FiscalPeriod.get_current_fiscal_period()
        general_journal  = Journal.objects.filter(
            journal_type='GENERAL', is_active=True
        ).first()
        return_entry = None

        if general_journal and fiscal_period:
            return_entry = JournalEntry.objects.create(
                journal=general_journal,
                entry_number=f"JE-RET-{sale.sale_number}",
                entry_date=timezone.now().date(),
                fiscal_period=fiscal_period,
                reference_number=sale.sale_number,
                description=(
                    f"RETURN: Uniform Sale {sale.sale_number} — "
                    f"{sale.student.get_full_name()} — {reason}"
                ),
                status='POSTED',
            )

            inventory_account  = sale.get_inventory_account()
            cogs_account       = sale.get_cogs_account()
            revenue_account    = sale.get_revenue_account()
            receivable_account = sale.get_receivable_account()

            if not all([inventory_account, cogs_account, revenue_account, receivable_account]):
                logger.error(
                    f"One or more GL accounts missing for return of sale "
                    f"{sale.sale_number} — journal entry created but may be "
                    f"incomplete. Review manually."
                )

            # Reversal of COGS entry (original: DR COGS / CR Inventory)
            # Reversal:                          DR Inventory / CR COGS
            if inventory_account:
                JournalTransaction.objects.create(
                    journal_entry=return_entry,
                    account=inventory_account,
                    amount=sale.total_cost,
                    is_debit=True,
                    description=f"Inventory restored — return of sale {sale.sale_number}",
                )
            if cogs_account:
                JournalTransaction.objects.create(
                    journal_entry=return_entry,
                    account=cogs_account,
                    amount=sale.total_cost,
                    is_debit=False,
                    description=f"COGS reversed — return of sale {sale.sale_number}",
                )

            # Reversal of revenue entry (original: DR Receivables / CR Revenue)
            # Reversal:                           DR Revenue / CR Receivables
            if revenue_account:
                JournalTransaction.objects.create(
                    journal_entry=return_entry,
                    account=revenue_account,
                    amount=sale.total_amount,
                    is_debit=True,
                    description=f"Revenue reversed — return of sale {sale.sale_number}",
                )
            if receivable_account:
                JournalTransaction.objects.create(
                    journal_entry=return_entry,
                    account=receivable_account,
                    amount=sale.total_amount,
                    is_debit=False,
                    description=f"Receivables reversed — return of sale {sale.sale_number}",
                )

            sale.return_journal_entry = return_entry
            logger.info(
                f"Return journal entry {return_entry.entry_number} created "
                f"for sale {sale.sale_number}"
            )
        else:
            logger.warning(
                f"No active General Journal or fiscal period found — "
                f"return journal entry not created for sale {sale.sale_number}"
            )

        sale.save()

        # 4. Cancel the invoice and warn about outstanding payments.
        if sale.fee_invoice:
            sale.fee_invoice.status = 'CANCELLED'
            sale.fee_invoice.save()

            if sale.paid_amount > 0:
                logger.warning(
                    f"Sale {sale.sale_number} returned but was paid "
                    f"({sale.paid_amount}) — process payment refund separately"
                )

        logger.info(f"Sale {sale.sale_number} returned by {user}")
        return True, "Return processed successfully", return_entry

    except Exception as e:
        logger.error(
            f"Error processing return for sale {sale.sale_number}: {e}",
            exc_info=True,
        )
        return False, f"Error: {str(e)}", None