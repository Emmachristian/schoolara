# uniforms/utils.py

"""
Uniform Management Utility Functions

Provides helper functions for:
- Reference number generation (sale numbers, PO numbers)
- Size recommendation algorithms
- Stock availability checks
- Pricing calculations
- Measurement conversions
"""

from django.db import transaction
from django.db.models import Max, Q, Count, F
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
        # Get the highest number for current year
        queryset = UniformSale.objects.filter(
            sale_number__startswith=prefix
        ).select_for_update()
        
        result = queryset.aggregate(max_number=Max('sale_number'))
        
        if result['max_number']:
            try:
                # Extract numeric part (last segment)
                last_number = int(result['max_number'].split('-')[-1])
                new_number = last_number + 1
            except (ValueError, IndexError):
                # Fallback: count and increment
                new_number = queryset.count() + 1
        else:
            new_number = 1
        
        # Format with leading zeros
        formatted_number = f"{new_number:05d}"
        
        return f"{prefix}{formatted_number}"


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
        
        formatted_number = f"{new_number:05d}"
        
        return f"{prefix}{formatted_number}"


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
        
        formatted_number = f"{new_number:03d}"
        
        return f"{prefix}{formatted_number}"


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
                    # Within 5cm tolerance
                    score += 70
                elif size.min_height - 10 <= height <= size.max_height + 10:
                    # Within 10cm tolerance
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
        
        # Calculate average score
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
    
    # Sort by score
    size_scores.sort(key=lambda x: (x['score'], x['matches']), reverse=True)
    
    # Get recommended size
    best_match = size_scores[0]
    recommended_size = best_match['size']
    
    # Determine confidence
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
    
    # Get alternative sizes (top 3, excluding recommended)
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
    
    # Calculate age
    age = (timezone.now().date() - student.date_of_birth).days // 365
    
    # Growth allowance only for younger students
    if age > 15:
        return recommended_size  # Minimal growth expected
    
    # Get next larger size
    available_sizes = uniform_item.available_sizes.all().order_by('display_order')
    
    try:
        current_index = list(available_sizes).index(recommended_size)
        if current_index < len(available_sizes) - 1:
            # Return next size up
            return available_sizes[current_index + 1]
    except (ValueError, IndexError):
        pass
    
    return recommended_size


# =============================================================================
# STOCK AVAILABILITY CHECKS
# =============================================================================

def check_stock_availability(uniform_item, size=None, quantity=1):
    """
    Check if sufficient stock is available.
    
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
        # Check size-specific stock
        try:
            stock = UniformStock.objects.get(
                uniform_item=uniform_item,
                size=size
            )
            available_qty = stock.available_quantity
        except UniformStock.DoesNotExist:
            available_qty = 0
    else:
        # Check total stock
        available_qty = uniform_item.current_stock
    
    is_available = available_qty >= quantity
    
    if is_available:
        message = f"{available_qty} units available"
    else:
        shortage = quantity - available_qty
        message = f"Insufficient stock: {available_qty} available, {quantity} requested (short by {shortage})"
    
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
        # Use each item's reorder level
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
        
        # Calculate line total
        line_total = uniform_item.selling_price * quantity
        subtotal += line_total
        
        # Calculate tax for this line
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
    
    total_amount = subtotal + tax_amount
    
    return {
        'subtotal': subtotal,
        'tax_amount': tax_amount,
        'total_amount': total_amount,
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
    # If same unit, no conversion needed
    if from_unit == to_unit:
        return Decimal(str(value))
    
    # Must be same type
    if from_unit.uom_type != to_unit.uom_type:
        raise ValueError(f"Cannot convert between different measurement types")
    
    # Convert to base unit first
    value_decimal = Decimal(str(value))
    base_value = value_decimal * from_unit.conversion_factor
    
    # Convert from base to target unit
    converted_value = base_value / to_unit.conversion_factor
    
    return converted_value


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
    
    # Check minimum
    if measurement_type.min_value and value_decimal < measurement_type.min_value:
        return {
            'valid': False,
            'message': f'Value {value} is below minimum {measurement_type.min_value}',
            'warnings': []
        }
    
    # Check maximum
    if measurement_type.max_value and value_decimal > measurement_type.max_value:
        return {
            'valid': False,
            'message': f'Value {value} is above maximum {measurement_type.max_value}',
            'warnings': []
        }
    
    # Check if close to limits (within 10%)
    if measurement_type.min_value:
        limit_10_percent = measurement_type.min_value * Decimal('1.1')
        if value_decimal < limit_10_percent:
            warnings.append(f'Value is close to minimum limit ({measurement_type.min_value})')
    
    if measurement_type.max_value:
        limit_10_percent = measurement_type.max_value * Decimal('0.9')
        if value_decimal > limit_10_percent:
            warnings.append(f'Value is close to maximum limit ({measurement_type.max_value})')
    
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
    
    logger.info(f"Bulk updated prices for {updated_count} uniform items by {price_increase_percentage}%")
    
    return {
        'updated_count': updated_count,
        'items_updated': items_updated
    }


def bulk_adjust_stock(adjustments):
    """
    Bulk adjust stock levels.
    
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
                # Adjust size-specific stock
                stock, created = UniformStock.objects.get_or_create(
                    uniform_item=uniform_item,
                    size=size
                )
                
                old_quantity = stock.quantity
                stock.quantity += adjustment
                
                # Prevent negative stock
                if stock.quantity < 0:
                    stock.quantity = 0
                
                stock.save()
                
                adjustments_made.append({
                    'item': uniform_item,
                    'size': size,
                    'old_quantity': old_quantity,
                    'new_quantity': stock.quantity,
                    'adjustment': adjustment
                })
            else:
                # Adjust total stock
                old_quantity = uniform_item.current_stock
                uniform_item.current_stock += adjustment
                
                # Prevent negative stock
                if uniform_item.current_stock < 0:
                    uniform_item.current_stock = 0
                
                uniform_item.save()
                
                adjustments_made.append({
                    'item': uniform_item,
                    'size': None,
                    'old_quantity': old_quantity,
                    'new_quantity': uniform_item.current_stock,
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
    from django.db.models import Sum, Count, Avg
    from .models import UniformSale
    
    sales = UniformSale.objects.filter(
        sale_date__range=[start_date, end_date],
        status__in=['PAID', 'PARTIAL', 'ISSUED']
    )
    
    summary = sales.aggregate(
        total_sales=Sum('total_amount'),
        total_cost=Sum('total_cost'),
        total_profit=Sum('gross_profit'),
        count=Count('id'),
        avg_sale=Avg('total_amount')
    )
    
    # Calculate overall margin
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
    from django.db.models import Sum, Count
    from .models import UniformSaleItem, UniformSale
    
    items = UniformSaleItem.objects.filter(
        sale__sale_date__range=[start_date, end_date],
        sale__status__in=['PAID', 'PARTIAL', 'ISSUED']
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
    from django.db.models import Sum, F
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
    from .models import UniformItem, UniformStock
    import csv
    from io import StringIO
    
    output = StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        'Item Code',
        'Item Name',
        'Category',
        'Size',
        'Quantity',
        'Reserved',
        'Available',
        'Unit Cost',
        'Selling Price',
        'Stock Value (Cost)',
        'Stock Value (Selling)',
        'Status'
    ])
    
    # Data
    items = UniformItem.objects.filter(is_active=True).prefetch_related('stock_records')
    
    for item in items:
        if item.requires_sizing:
            # Export by size
            for stock in item.stock_records.all():
                writer.writerow([
                    item.code,
                    item.name,
                    item.category,
                    stock.size.name,
                    stock.quantity,
                    stock.reserved_quantity,
                    stock.available_quantity,
                    item.unit_cost,
                    item.selling_price,
                    stock.quantity * item.unit_cost,
                    stock.quantity * item.selling_price,
                    'Low Stock' if item.is_low_stock else 'OK'
                ])
        else:
            # Export total stock
            writer.writerow([
                item.code,
                item.name,
                item.category,
                'N/A',
                item.current_stock,
                0,
                item.current_stock,
                item.unit_cost,
                item.selling_price,
                item.stock_value,
                item.stock_value_selling,
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
    
    # Check required fields
    if 'student' not in sale_data:
        errors.append("Student is required")
    
    if 'items' not in sale_data or not sale_data['items']:
        errors.append("At least one item is required")
    
    # Validate items
    if 'items' in sale_data:
        for idx, item in enumerate(sale_data['items']):
            # Check required item fields
            if 'uniform_item' not in item:
                errors.append(f"Item {idx + 1}: uniform_item is required")
                continue
            
            uniform_item = item['uniform_item']
            
            # Check sizing requirement
            if uniform_item.requires_sizing and 'size' not in item:
                errors.append(f"Item {idx + 1}: {uniform_item.name} requires a size")
            
            # Check quantity
            quantity = item.get('quantity', 1)
            if quantity <= 0:
                errors.append(f"Item {idx + 1}: quantity must be positive")
            
            # Check stock availability
            size = item.get('size')
            availability = check_stock_availability(uniform_item, size, quantity)
            if not availability['available']:
                errors.append(f"Item {idx + 1}: {availability['message']}")
    
    # Check discount
    if 'discount_amount' in sale_data:
        discount = sale_data['discount_amount']
        if discount < 0:
            errors.append("Discount amount cannot be negative")
    
    valid = len(errors) == 0
    
    return {
        'valid': valid,
        'errors': errors,
        'warnings': warnings
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_size_display(size):
    """
    Format size for display.
    
    Args:
        size: UniformSize instance
        
    Returns:
        str: Formatted size string
    """
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
    ).order_by('-sale_date').prefetch_related('items__uniform_item', 'items__size')


def calculate_reorder_quantity(uniform_item, target_days=90):
    """
    Calculate recommended reorder quantity based on sales velocity.
    
    Args:
        uniform_item: UniformItem instance
        target_days: Number of days to stock for
        
    Returns:
        int: Recommended reorder quantity
    """
    from django.db.models import Sum
    from .models import UniformSaleItem
    from datetime import timedelta
    
    # Get sales from last 90 days
    lookback_date = timezone.now().date() - timedelta(days=90)
    
    sales_data = UniformSaleItem.objects.filter(
        uniform_item=uniform_item,
        sale__sale_date__gte=lookback_date,
        sale__status__in=['PAID', 'PARTIAL', 'ISSUED']
    ).aggregate(
        total_sold=Sum('quantity')
    )
    
    total_sold = sales_data['total_sold'] or 0
    
    if total_sold == 0:
        # No recent sales, use reorder level as fallback
        return uniform_item.reorder_level
    
    # Calculate daily velocity
    daily_velocity = total_sold / 90.0
    
    # Calculate target quantity
    target_quantity = int(daily_velocity * target_days)
    
    # Add current stock to see how much to order
    current_stock = uniform_item.current_stock
    reorder_quantity = max(0, target_quantity - current_stock)
    
    return reorder_quantity