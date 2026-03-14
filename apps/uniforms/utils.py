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

CHANGES FROM PREVIOUS VERSION:
- Fixed: return_uniform_sale unsized item branch now goes through UniformStock
  (get_or_create with size=None + stock.save()) instead of writing
  current_stock directly on UniformItem. The signal syncs current_stock
  after stock.save(); writing it directly bypassed the signal entirely.
- Fixed: bulk_adjust_stock unsized item branch has the same fix applied —
  now creates/updates the UniformStock record instead of touching
  current_stock directly.
- Fixed: check_stock_availability now reads available_quantity from
  UniformStock for unsized items instead of falling back to
  current_stock, so the check reflects the same source of truth as
  the rest of the stock system.
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
    Generate unique uniform sale number.
    Format: US-YYYY-NNNNN (e.g., US-2024-00001)

    Returns:
        str: Unique sale number
    """
    from .models import UniformSale

    current_year = timezone.now().year
    prefix = f"US-{current_year}-"

    with transaction.atomic():
        queryset = UniformSale.objects.filter(
            sale_number__startswith=prefix
        ).select_for_update()

        result = queryset.aggregate(max_number=Max('sale_number'))

        if result['max_number']:
            try:
                last_number = int(result['max_number'].split('-')[-1])
                new_number = last_number + 1
            except (ValueError, IndexError):
                new_number = queryset.count() + 1
        else:
            new_number = 1

        return f"{prefix}{new_number:05d}"


def generate_purchase_order_number():
    """
    Generate unique purchase order number.
    Format: PO-YYYY-NNNNN (e.g., PO-2024-00001)

    Returns:
        str: Unique PO number
    """
    from .models import UniformPurchaseOrder

    current_year = timezone.now().year
    prefix = f"PO-{current_year}-"

    with transaction.atomic():
        queryset = UniformPurchaseOrder.objects.filter(
            po_number__startswith=prefix
        ).select_for_update()

        result = queryset.aggregate(max_number=Max('po_number'))

        if result['max_number']:
            try:
                last_number = int(result['max_number'].split('-')[-1])
                new_number = last_number + 1
            except (ValueError, IndexError):
                new_number = queryset.count() + 1
        else:
            new_number = 1

        return f"{prefix}{new_number:05d}"


def generate_measurement_session_code():
    """
    Generate unique measurement session code.
    Format: MS-YYYY-MM-NNN (e.g., MS-2024-09-001)

    Returns:
        str: Unique session code
    """
    from .models import MeasurementSession

    current_date = timezone.now()
    prefix = f"MS-{current_date.year}-{current_date.month:02d}-"

    with transaction.atomic():
        queryset = MeasurementSession.objects.filter(
            session_name__startswith=prefix
        ).select_for_update()

        count = queryset.count()
        new_number = count + 1

        return f"{prefix}{new_number:03d}"


def generate_cash_receipt_number():
    """
    Generate unique cash receipt number for cash payments.
    Called automatically by signals when payment_method is CASH.
    Format: RCP-YYYY-NNNNN (e.g., RCP-2025-00001)

    Returns:
        str: Unique receipt number
    """
    from .models import UniformSale

    current_year = timezone.now().year
    prefix = f"RCP-{current_year}-"

    with transaction.atomic():
        queryset = UniformSale.objects.filter(
            payment_reference__startswith=prefix
        ).select_for_update()

        result = queryset.aggregate(max_ref=Max('payment_reference'))

        if result['max_ref']:
            try:
                last_number = int(result['max_ref'].split('-')[-1])
                new_number = last_number + 1
            except (ValueError, IndexError):
                new_number = queryset.count() + 1
        else:
            new_number = 1

        return f"{prefix}{new_number:05d}"


# =============================================================================
# SIZE RECOMMENDATION ALGORITHMS
# =============================================================================

def recommend_size_from_measurements(student, uniform_item):
    """
    Recommend uniform size based on student measurements.

    Args:
        student: Student instance
        uniform_item: UniformItem instance

    Returns:
        dict: {
            'recommended_size': UniformSize instance or None,
            'confidence': 'HIGH', 'MEDIUM', or 'LOW',
            'alternative_sizes': List of UniformSize instances,
            'reason': str explanation
        }
    """
    from .models import StudentMeasurement, UniformSize

    # Get current measurements
    measurements = StudentMeasurement.objects.filter(
        student=student,
        is_current=True
    ).select_related('measurement_type')

    if not measurements.exists():
        return {
            'recommended_size': None,
            'confidence': 'LOW',
            'alternative_sizes': [],
            'reason': 'No measurements available for student'
        }

    # Build measurement dict
    measurement_dict = {}
    for m in measurements:
        code = m.measurement_type.code.upper()
        measurement_dict[code] = float(m.value)

    # Get available sizes for this item
    available_sizes = uniform_item.available_sizes.all()

    if not available_sizes.exists():
        return {
            'recommended_size': None,
            'confidence': 'LOW',
            'alternative_sizes': [],
            'reason': 'No sizes configured for this item'
        }

    # Score each size
    size_scores = []

    for size in available_sizes:
        score = 0
        matches = 0
        total_checks = 0

        # Check height
        if 'HEIGHT' in measurement_dict:
            height = measurement_dict['HEIGHT']
            total_checks += 1

            if size.min_height and size.max_height:
                if size.min_height <= height <= size.max_height:
                    score += 100
                    matches += 1
                elif size.min_height - 5 <= height <= size.max_height + 5:
                    score += 70
                elif size.min_height - 10 <= height <= size.max_height + 10:
                    score += 40

        # Check chest
        if 'CHEST' in measurement_dict:
            chest = measurement_dict['CHEST']
            total_checks += 1

            if size.min_chest and size.max_chest:
                if size.min_chest <= chest <= size.max_chest:
                    score += 100
                    matches += 1
                elif size.min_chest - 3 <= chest <= size.max_chest + 3:
                    score += 70
                elif size.min_chest - 6 <= chest <= size.max_chest + 6:
                    score += 40

        # Check waist
        if 'WAIST' in measurement_dict:
            waist = measurement_dict['WAIST']
            total_checks += 1

            if size.min_waist and size.max_waist:
                if size.min_waist <= waist <= size.max_waist:
                    score += 100
                    matches += 1
                elif size.min_waist - 3 <= waist <= size.max_waist + 3:
                    score += 70
                elif size.min_waist - 6 <= waist <= size.max_waist + 6:
                    score += 40

        # Check age if available
        if hasattr(student, 'date_of_birth') and student.date_of_birth:
            age = (timezone.now().date() - student.date_of_birth).days // 365

            if size.min_age and size.max_age:
                total_checks += 1
                if size.min_age <= age <= size.max_age:
                    score += 50
                    matches += 1

        if total_checks > 0:
            avg_score = score / total_checks
            size_scores.append({
                'size': size,
                'score': avg_score,
                'matches': matches,
                'total_checks': total_checks
            })

    if not size_scores:
        return {
            'recommended_size': None,
            'confidence': 'LOW',
            'alternative_sizes': [],
            'reason': 'Could not match measurements to available sizes'
        }

    # Sort by score descending
    size_scores.sort(key=lambda x: (x['score'], x['matches']), reverse=True)

    best_match = size_scores[0]
    recommended_size = best_match['size']

    # Determine confidence level
    if best_match['matches'] == best_match['total_checks']:
        confidence = 'HIGH'
        reason = f"All {best_match['matches']} measurements match perfectly"
    elif best_match['score'] >= 80:
        confidence = 'HIGH'
        reason = f"Strong match: {best_match['matches']}/{best_match['total_checks']} measurements in range"
    elif best_match['score'] >= 60:
        confidence = 'MEDIUM'
        reason = f"Good match: {best_match['matches']}/{best_match['total_checks']} measurements in range"
    else:
        confidence = 'LOW'
        reason = f"Weak match: Only {best_match['matches']}/{best_match['total_checks']} measurements in range"

    # Top 3 alternatives (excluding the recommended)
    alternative_sizes = [s['size'] for s in size_scores[1:4]]

    return {
        'recommended_size': recommended_size,
        'confidence': confidence,
        'alternative_sizes': alternative_sizes,
        'reason': reason
    }


def apply_growth_allowance(recommended_size, student, uniform_item, months=6):
    """
    Apply growth allowance to recommended size.
    For young students, recommend a larger size to account for growth.

    Args:
        recommended_size: Currently recommended UniformSize
        student: Student instance
        uniform_item: UniformItem instance
        months: Number of months to plan for (default: 6)

    Returns:
        UniformSize: Size with growth allowance applied (may be same as input)
    """
    if not hasattr(student, 'date_of_birth') or not student.date_of_birth:
        return recommended_size

    age = (timezone.now().date() - student.date_of_birth).days // 365

    # Minimal growth expected above age 15
    if age > 15:
        return recommended_size

    available_sizes = uniform_item.available_sizes.all().order_by('display_order')

    try:
        size_list = list(available_sizes)
        current_index = size_list.index(recommended_size)
        if current_index < len(size_list) - 1:
            return size_list[current_index + 1]
    except (ValueError, IndexError):
        pass

    return recommended_size


# =============================================================================
# STOCK AVAILABILITY CHECKS
# =============================================================================

def check_stock_availability(uniform_item, size=None, quantity=1):
    """
    Check if sufficient stock is available.

    CHANGED: unsized items now read available_quantity from UniformStock
    (size=None) instead of current_stock on the item. This keeps the check
    consistent with the rest of the stock system — current_stock is a derived
    cache value and may not reflect reserved quantities.

    Args:
        uniform_item: UniformItem instance
        size: UniformSize instance (optional)
        quantity: Quantity required

    Returns:
        dict: {
            'available': bool,
            'quantity_available': int,
            'quantity_requested': int,
            'message': str
        }
    """
    from .models import UniformStock

    if uniform_item.requires_sizing and size:
        try:
            stock = UniformStock.objects.get(
                uniform_item=uniform_item,
                size=size
            )
            available_qty = stock.available_quantity
        except UniformStock.DoesNotExist:
            available_qty = 0
    else:
        # CHANGED: read from the stock record, not current_stock on the item
        try:
            stock = UniformStock.objects.get(
                uniform_item=uniform_item,
                size__isnull=True
            )
            available_qty = stock.available_quantity
        except UniformStock.DoesNotExist:
            available_qty = 0

    is_available = available_qty >= quantity

    if is_available:
        message = f"{available_qty} units available"
    else:
        shortage = quantity - available_qty
        message = (
            f"Insufficient stock: {available_qty} available, "
            f"{quantity} requested (short by {shortage})"
        )

    return {
        'available': is_available,
        'quantity_available': available_qty,
        'quantity_requested': quantity,
        'message': message
    }


def get_low_stock_items(threshold=None):
    """
    Get list of uniform items with low stock.

    Args:
        threshold: Custom threshold (uses item's reorder_level if None)

    Returns:
        QuerySet: UniformItem instances with low stock
    """
    from .models import UniformItem

    if threshold is not None:
        return UniformItem.objects.filter(
            is_active=True,
            current_stock__lte=threshold
        ).order_by('current_stock')
    else:
        return UniformItem.objects.filter(
            is_active=True,
            current_stock__lte=F('reorder_level')
        ).order_by('current_stock')


def get_out_of_stock_items():
    """
    Get list of uniform items that are out of stock.

    Returns:
        QuerySet: UniformItem instances with zero stock
    """
    from .models import UniformItem

    return UniformItem.objects.filter(
        is_active=True,
        current_stock=0
    ).order_by('name')


# =============================================================================
# PRICING CALCULATIONS
# =============================================================================

def calculate_uniform_bundle_price(items_with_quantities):
    """
    Calculate total price for a bundle of uniform items.

    Args:
        items_with_quantities: List of dicts [
            {'uniform_item': UniformItem, 'quantity': int},
            ...
        ]

    Returns:
        dict: {
            'subtotal': Decimal,
            'tax_amount': Decimal,
            'total_amount': Decimal,
            'items_breakdown': list
        }
    """
    from core.models import FinancialSettings

    settings = FinancialSettings.get_instance()
    default_tax_rate = settings.default_tax_rate if settings else Decimal('18.00')

    subtotal = Decimal('0.00')
    tax_amount = Decimal('0.00')
    items_breakdown = []

    for item_data in items_with_quantities:
        uniform_item = item_data['uniform_item']
        quantity = item_data['quantity']

        line_total = uniform_item.selling_price * quantity
        subtotal += line_total

        if uniform_item.is_taxable:
            if uniform_item.tax_rate:
                tax_rate = uniform_item.tax_rate.rate
            else:
                tax_rate = default_tax_rate

            line_tax = (line_total * tax_rate) / 100
            tax_amount += line_tax
        else:
            line_tax = Decimal('0.00')

        items_breakdown.append({
            'item': uniform_item,
            'quantity': quantity,
            'unit_price': uniform_item.selling_price,
            'line_total': line_total,
            'tax_amount': line_tax
        })

    return {
        'subtotal': subtotal,
        'tax_amount': tax_amount,
        'total_amount': subtotal + tax_amount,
        'items_breakdown': items_breakdown
    }


def apply_discount_to_amount(amount, discount_percentage=None, discount_amount=None):
    """
    Apply discount to an amount.

    Args:
        amount: Original amount
        discount_percentage: Percentage discount (0-100)
        discount_amount: Fixed discount amount

    Returns:
        dict: {
            'original_amount': Decimal,
            'discount_amount': Decimal,
            'final_amount': Decimal
        }
    """
    original_amount = Decimal(str(amount))

    if discount_percentage:
        discount_amt = (original_amount * Decimal(str(discount_percentage))) / 100
    elif discount_amount:
        discount_amt = Decimal(str(discount_amount))
    else:
        discount_amt = Decimal('0.00')

    final_amount = original_amount - discount_amt

    # Ensure final amount is not negative
    if final_amount < 0:
        final_amount = Decimal('0.00')
        discount_amt = original_amount

    return {
        'original_amount': original_amount,
        'discount_amount': discount_amt,
        'final_amount': final_amount
    }


# =============================================================================
# MEASUREMENT UTILITIES
# =============================================================================

def convert_measurement(value, from_unit, to_unit):
    """
    Convert measurement from one unit to another.

    Args:
        value: Measurement value
        from_unit: UnitOfMeasure instance (source)
        to_unit: UnitOfMeasure instance (target)

    Returns:
        Decimal: Converted value
    """
    if from_unit == to_unit:
        return Decimal(str(value))

    if from_unit.uom_type != to_unit.uom_type:
        raise ValueError("Cannot convert between different measurement types")

    value_decimal = Decimal(str(value))
    base_value = value_decimal * from_unit.conversion_factor
    return base_value / to_unit.conversion_factor


def validate_measurement_value(measurement_type, value):
    """
    Validate if a measurement value is within acceptable range.

    Args:
        measurement_type: MeasurementType instance
        value: Measurement value to validate

    Returns:
        dict: {
            'valid': bool,
            'message': str,
            'warnings': list of str
        }
    """
    warnings = []

    try:
        value_decimal = Decimal(str(value))
    except (ValueError, TypeError):
        return {
            'valid': False,
            'message': 'Invalid numeric value',
            'warnings': []
        }

    if measurement_type.min_value and value_decimal < measurement_type.min_value:
        return {
            'valid': False,
            'message': f'Value {value} is below minimum {measurement_type.min_value}',
            'warnings': []
        }

    if measurement_type.max_value and value_decimal > measurement_type.max_value:
        return {
            'valid': False,
            'message': f'Value {value} is above maximum {measurement_type.max_value}',
            'warnings': []
        }

    if measurement_type.min_value:
        limit_10_percent = measurement_type.min_value * Decimal('1.1')
        if value_decimal < limit_10_percent:
            warnings.append(
                f'Value is close to minimum limit ({measurement_type.min_value})'
            )

    if measurement_type.max_value:
        limit_10_percent = measurement_type.max_value * Decimal('0.9')
        if value_decimal > limit_10_percent:
            warnings.append(
                f'Value is close to maximum limit ({measurement_type.max_value})'
            )

    return {
        'valid': True,
        'message': 'Measurement value is valid',
        'warnings': warnings
    }


# =============================================================================
# BULK OPERATIONS
# =============================================================================

def bulk_update_uniform_prices(uniform_items, price_increase_percentage):
    """
    Bulk update uniform prices by a percentage.

    Args:
        uniform_items: QuerySet or list of UniformItem instances
        price_increase_percentage: Percentage to increase (can be negative)

    Returns:
        dict: {
            'updated_count': int,
            'items_updated': list of dicts with old/new prices
        }
    """
    percentage = Decimal(str(price_increase_percentage))
    multiplier = 1 + (percentage / 100)

    items_updated = []
    updated_count = 0

    with transaction.atomic():
        for item in uniform_items:
            old_price = item.selling_price
            new_price = (old_price * multiplier).quantize(Decimal('0.01'))

            item.selling_price = new_price
            item.save()

            items_updated.append({
                'item': item,
                'old_price': old_price,
                'new_price': new_price,
                'increase': new_price - old_price
            })

            updated_count += 1

    logger.info(
        f"Bulk updated prices for {updated_count} uniform items "
        f"by {price_increase_percentage}%"
    )

    return {
        'updated_count': updated_count,
        'items_updated': items_updated
    }


def bulk_adjust_stock(adjustments):
    """
    Bulk adjust stock levels.

    CHANGED: unsized item branch now goes through UniformStock (get_or_create
    with size=None) instead of writing current_stock directly on the item.
    The signal syncs current_stock automatically after stock.save().

    Args:
        adjustments: List of dicts [
            {
                'uniform_item': UniformItem,
                'size': UniformSize (optional),
                'adjustment': int (positive or negative)
            },
            ...
        ]

    Returns:
        dict: {
            'adjusted_count': int,
            'adjustments_made': list
        }
    """
    from .models import UniformStock

    adjustments_made = []
    adjusted_count = 0

    with transaction.atomic():
        for adj in adjustments:
            uniform_item = adj['uniform_item']
            size = adj.get('size')
            adjustment = adj['adjustment']

            if uniform_item.requires_sizing and size:
                stock, _ = UniformStock.objects.get_or_create(
                    uniform_item=uniform_item,
                    size=size
                )
                old_quantity = stock.quantity
                stock.quantity = max(0, stock.quantity + adjustment)
                stock.save()

                adjustments_made.append({
                    'item': uniform_item,
                    'size': size,
                    'old_quantity': old_quantity,
                    'new_quantity': stock.quantity,
                    'adjustment': adjustment
                })
            else:
                # CHANGED: route through UniformStock so the signal keeps
                # current_stock in sync instead of writing it directly.
                stock, _ = UniformStock.objects.get_or_create(
                    uniform_item=uniform_item,
                    size=None,
                    defaults={'quantity': uniform_item.current_stock},
                )
                old_quantity = stock.quantity
                stock.quantity = max(0, stock.quantity + adjustment)
                stock.save()
                # Signal syncs uniform_item.current_stock after save()

                adjustments_made.append({
                    'item': uniform_item,
                    'size': None,
                    'old_quantity': old_quantity,
                    'new_quantity': stock.quantity,
                    'adjustment': adjustment
                })

            adjusted_count += 1

    logger.info(f"Bulk adjusted stock for {adjusted_count} items")

    return {
        'adjusted_count': adjusted_count,
        'adjustments_made': adjustments_made
    }


# =============================================================================
# REPORTING UTILITIES
# =============================================================================

def get_uniform_sales_summary(start_date, end_date, by='day'):
    """
    Get summary of uniform sales for a date range.

    Args:
        start_date: Start date
        end_date: End date
        by: Grouping ('day', 'week', 'month')

    Returns:
        dict: Summary statistics
    """
    from django.db.models import Avg
    from .models import UniformSale

    sales = UniformSale.objects.filter(
        sale_date__range=[start_date, end_date],
        status__in=['PAID', 'PARTIAL', 'ISSUED'],
        cancelled=False,
        returned=False
    )

    summary = sales.aggregate(
        total_sales=Sum('total_amount'),
        total_cost=Sum('total_cost'),
        total_profit=Sum('gross_profit'),
        count=Count('id'),
        avg_sale=Avg('total_amount')
    )

    if summary['total_sales'] and summary['total_sales'] > 0:
        summary['margin_percentage'] = (
            (summary['total_profit'] or 0) / summary['total_sales']
        ) * 100
    else:
        summary['margin_percentage'] = 0

    return summary


def get_best_selling_items(start_date, end_date, limit=10):
    """
    Get best-selling uniform items for a date range.

    Args:
        start_date: Start date
        end_date: End date
        limit: Number of items to return

    Returns:
        list: List of dicts with item and sales data
    """
    from .models import UniformSaleItem

    items = UniformSaleItem.objects.filter(
        sale__sale_date__range=[start_date, end_date],
        sale__status__in=['PAID', 'PARTIAL', 'ISSUED'],
        sale__cancelled=False,
        sale__returned=False
    ).values(
        'uniform_item__id',
        'uniform_item__name',
        'uniform_item__code'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum('total_price'),
        sale_count=Count('sale__id', distinct=True)
    ).order_by('-total_quantity')[:limit]

    return list(items)


def get_inventory_valuation():
    """
    Calculate total inventory valuation.

    Returns:
        dict: {
            'cost_value': Decimal (at cost price),
            'selling_value': Decimal (at selling price),
            'potential_profit': Decimal,
            'items_count': int
        }
    """
    from .models import UniformItem

    items = UniformItem.objects.filter(is_active=True)

    valuation = items.aggregate(
        cost_value=Sum(F('current_stock') * F('unit_cost')),
        selling_value=Sum(F('current_stock') * F('selling_price')),
        items_count=Count('id')
    )

    cost_value = valuation['cost_value'] or Decimal('0.00')
    selling_value = valuation['selling_value'] or Decimal('0.00')

    return {
        'cost_value': cost_value,
        'selling_value': selling_value,
        'potential_profit': selling_value - cost_value,
        'items_count': valuation['items_count'] or 0
    }


# =============================================================================
# DATA IMPORT/EXPORT UTILITIES
# =============================================================================

def export_stock_levels_to_csv():
    """
    Export current stock levels to CSV format.

    Returns:
        str: CSV data as string
    """
    from .models import UniformItem
    import csv
    from io import StringIO

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        'Item Code', 'Item Name', 'Category', 'Size',
        'Quantity', 'Reserved', 'Available',
        'Unit Cost', 'Selling Price',
        'Stock Value (Cost)', 'Stock Value (Selling)', 'Status'
    ])

    items = UniformItem.objects.filter(
        is_active=True
    ).prefetch_related('stock_records__size')

    for item in items:
        if item.requires_sizing:
            for stock in item.stock_records.all():
                writer.writerow([
                    item.code, item.name, item.category,
                    stock.size.name if stock.size else 'No Size',
                    stock.quantity, stock.reserved_quantity, stock.available_quantity,
                    item.unit_cost, item.selling_price,
                    stock.quantity * item.unit_cost,
                    stock.quantity * item.selling_price,
                    'Low Stock' if item.is_low_stock else 'OK'
                ])
        else:
            for stock in item.stock_records.filter(size__isnull=True):
                writer.writerow([
                    item.code, item.name, item.category, 'N/A',
                    stock.quantity, stock.reserved_quantity, stock.available_quantity,
                    item.unit_cost, item.selling_price,
                    stock.quantity * item.unit_cost,
                    stock.quantity * item.selling_price,
                    'Low Stock' if item.is_low_stock else 'OK'
                ])

    return output.getvalue()


# =============================================================================
# VALIDATION UTILITIES
# =============================================================================

def validate_uniform_sale_data(sale_data):
    """
    Validate uniform sale data before creating sale.

    Args:
        sale_data: Dict with sale information

    Returns:
        dict: {
            'valid': bool,
            'errors': list of str,
            'warnings': list of str
        }
    """
    errors = []
    warnings = []

    if 'student' not in sale_data:
        errors.append("Student is required")

    if 'items' not in sale_data or not sale_data['items']:
        errors.append("At least one item is required")

    if 'items' in sale_data:
        for idx, item in enumerate(sale_data['items']):
            if 'uniform_item' not in item:
                errors.append(f"Item {idx + 1}: uniform_item is required")
                continue

            uniform_item = item['uniform_item']

            if uniform_item.requires_sizing and 'size' not in item:
                errors.append(f"Item {idx + 1}: {uniform_item.name} requires a size")

            quantity = item.get('quantity', 1)
            if quantity <= 0:
                errors.append(f"Item {idx + 1}: quantity must be positive")

            size = item.get('size')
            availability = check_stock_availability(uniform_item, size, quantity)
            if not availability['available']:
                errors.append(f"Item {idx + 1}: {availability['message']}")

    if 'discount_amount' in sale_data:
        if sale_data['discount_amount'] < 0:
            errors.append("Discount amount cannot be negative")

    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_size_display(size):
    """Format size for display."""
    if not size:
        return "One Size"
    return f"Size {size.name}"


def get_student_uniform_history(student):
    """
    Get complete uniform purchase history for a student.

    Args:
        student: Student instance

    Returns:
        QuerySet: UniformSale instances for student
    """
    from .models import UniformSale

    return UniformSale.objects.filter(
        student=student
    ).order_by('-sale_date').prefetch_related(
        'items__uniform_item', 'items__size'
    )


def calculate_reorder_quantity(uniform_item, target_days=90):
    """
    Calculate recommended reorder quantity based on sales velocity.

    Args:
        uniform_item: UniformItem instance
        target_days: Number of days to stock for

    Returns:
        int: Recommended reorder quantity
    """
    from .models import UniformSaleItem
    from datetime import timedelta

    lookback_date = timezone.now().date() - timedelta(days=90)

    sales_data = UniformSaleItem.objects.filter(
        uniform_item=uniform_item,
        sale__sale_date__gte=lookback_date,
        sale__status__in=['PAID', 'PARTIAL', 'ISSUED'],
        sale__cancelled=False,
        sale__returned=False
    ).aggregate(total_sold=Sum('quantity'))

    total_sold = sales_data['total_sold'] or 0

    if total_sold == 0:
        return uniform_item.reorder_level

    daily_velocity = total_sold / 90.0
    target_quantity = int(daily_velocity * target_days)
    reorder_quantity = max(0, target_quantity - uniform_item.current_stock)

    return reorder_quantity


# =============================================================================
# SALE CANCELLATION AND RETURN PROCESSING
# =============================================================================

@transaction.atomic
def cancel_uniform_sale(sale, user, reason):
    """
    Cancel a uniform sale (before items were issued).

    Actions:
    1. Mark sale as cancelled
    2. Cancel/void the fee invoice
    3. Log a warning if payment was already made (refund must be processed manually)
    4. No inventory adjustment needed — items never left the warehouse

    Args:
        sale: UniformSale instance
        user: User performing cancellation
        reason: Reason for cancellation

    Returns:
        tuple: (success: bool, message: str)
    """
    can_cancel, msg = sale.can_be_cancelled()
    if not can_cancel:
        return False, msg

    try:
        sale.cancelled = True
        sale.cancelled_on = timezone.now()
        sale.cancelled_by_id = str(user.id)
        sale.cancellation_reason = reason
        sale.status = 'CANCELLED'
        sale.save()

        # Cancel the linked invoice if present
        if sale.fee_invoice:
            invoice = sale.fee_invoice
            invoice.status = 'CANCELLED'
            invoice.save()
            logger.info(
                f"Cancelled invoice {invoice.invoice_number} "
                f"for sale {sale.sale_number}"
            )

        # Warn if payment already recorded — refund must be handled separately
        if sale.paid_amount > 0 and sale.fee_invoice:
            payments = sale.fee_invoice.payments.filter(
                status='COMPLETED',
                reversed=False,
                refunded=False
            )
            if payments.exists():
                payment_numbers = [p.payment_number for p in payments]
                logger.warning(
                    f"Uniform sale {sale.sale_number} cancelled but has outstanding "
                    f"payments: {payment_numbers}. Process refunds manually."
                )

        logger.info(f"Uniform sale {sale.sale_number} cancelled by {user}")
        return True, "Sale cancelled successfully"

    except Exception as e:
        logger.error(
            f"Error cancelling uniform sale {sale.sale_number}: {e}",
            exc_info=True
        )
        return False, f"Error: {str(e)}"


@transaction.atomic
def return_uniform_sale(sale, user, reason, condition):
    """
    Process return of issued uniforms (items come back to inventory).

    Actions:
    1. Mark sale as returned
    2. Return items to UniformStock — both sized and unsized go through the
       stock record so the signal keeps current_stock accurate
    3. Create reversal journal entries via finance module
    4. Cancel the linked invoice and warn about outstanding payments

    CHANGED: unsized item branch now goes through UniformStock (get_or_create
    with size=None + stock.save()) instead of writing current_stock directly
    on the item. Writing current_stock directly bypassed the post_save signal
    on UniformStock, meaning the next stock record save for that item could
    overwrite current_stock back to the stale value.

    Args:
        sale: UniformSale instance
        user: User processing return
        reason: Reason for return
        condition: Condition of returned items

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

        # 1. Mark sale as returned
        sale.returned = True
        sale.returned_on = timezone.now()
        sale.returned_by_id = str(user.id)
        sale.return_reason = reason
        sale.return_condition = condition
        sale.status = 'RETURNED'

        # 2. Return items to inventory via UniformStock
        for item in sale.items.all():
            if item.uniform_item.requires_sizing and item.size:
                # Sized item — update the per-size stock record
                stock, created = UniformStock.objects.get_or_create(
                    uniform_item=item.uniform_item,
                    size=item.size,
                    defaults={'quantity': 0},
                )
                stock.quantity += item.quantity
                stock.save()
                # Signal syncs uniform_item.current_stock after save()
                logger.info(
                    f"Returned {item.quantity}x {item.uniform_item.name} "
                    f"Size {item.size.name} to stock"
                )
            else:
                # CHANGED: unsized item — go through the UniformStock record
                # (size=None) so the signal keeps current_stock accurate.
                stock, created = UniformStock.objects.get_or_create(
                    uniform_item=item.uniform_item,
                    size=None,
                    defaults={'quantity': 0},
                )
                stock.quantity += item.quantity
                stock.save()
                # Signal syncs uniform_item.current_stock after save()
                logger.info(
                    f"Returned {item.quantity}x {item.uniform_item.name} "
                    f"(unsized) to stock"
                )

        # 3. Create reversal journal entry
        fiscal_period = FiscalPeriod.get_current_fiscal_period()

        general_journal = Journal.objects.filter(
            journal_type='GENERAL',
            is_active=True
        ).first()

        return_entry = None

        if general_journal and fiscal_period:
            return_entry = JournalEntry.objects.create(
                journal=general_journal,
                entry_date=timezone.now().date(),
                fiscal_period=fiscal_period,
                reference_number=sale.sale_number,
                description=(
                    f"RETURN: Uniform Sale {sale.sale_number} — "
                    f"{sale.student.get_full_name()} — {reason}"
                ),
                status='POSTED'
            )

            inventory_account = sale.get_inventory_account()
            cogs_account = sale.get_cogs_account()
            revenue_account = sale.get_revenue_account()
            receivable_account = sale.get_receivable_account()

            if not all([
                inventory_account, cogs_account,
                revenue_account, receivable_account
            ]):
                logger.error(
                    f"Missing accounts for return journal entry on sale "
                    f"{sale.sale_number}. Journal entry created without all "
                    f"lines — review manually."
                )

            # Reversal of original COGS entry:
            # Original: DR COGS / CR Inventory
            # Reversal: DR Inventory / CR COGS
            if inventory_account:
                JournalTransaction.objects.create(
                    journal_entry=return_entry,
                    account=inventory_account,
                    amount=sale.total_cost,
                    is_debit=True,
                    description=f"Inventory restored — return of sale {sale.sale_number}"
                )

            if cogs_account:
                JournalTransaction.objects.create(
                    journal_entry=return_entry,
                    account=cogs_account,
                    amount=sale.total_cost,
                    is_debit=False,
                    description=f"COGS reversed — return of sale {sale.sale_number}"
                )

            # Reversal of original revenue entry:
            # Original: DR Receivables / CR Revenue
            # Reversal: DR Revenue / CR Receivables
            if revenue_account:
                JournalTransaction.objects.create(
                    journal_entry=return_entry,
                    account=revenue_account,
                    amount=sale.total_amount,
                    is_debit=True,
                    description=f"Revenue reversed — return of sale {sale.sale_number}"
                )

            if receivable_account:
                JournalTransaction.objects.create(
                    journal_entry=return_entry,
                    account=receivable_account,
                    amount=sale.total_amount,
                    is_debit=False,
                    description=f"Receivables reversed — return of sale {sale.sale_number}"
                )

            sale.return_journal_entry = return_entry
            logger.info(
                f"Created return journal entry {return_entry.entry_number} "
                f"for sale {sale.sale_number}"
            )
        else:
            logger.warning(
                f"Could not create return journal entry for {sale.sale_number}: "
                f"no active journal or fiscal period found."
            )

        sale.save()

        # 4. Cancel the invoice and warn about outstanding payments
        if sale.fee_invoice:
            sale.fee_invoice.status = 'CANCELLED'
            sale.fee_invoice.save()

            if sale.paid_amount > 0:
                logger.warning(
                    f"Uniform sale {sale.sale_number} returned but was paid "
                    f"({sale.paid_amount}). Process payment refunds separately."
                )

        logger.info(f"Uniform sale {sale.sale_number} returned by {user}")
        return True, "Return processed successfully", return_entry

    except Exception as e:
        logger.error(
            f"Error processing return for uniform sale {sale.sale_number}: {e}",
            exc_info=True
        )
        return False, f"Error: {str(e)}", None