# uniforms/views.py

"""
Uniform Management Views

Comprehensive view functions for:
- Measurement Types Management (CRUD + Print)
- Student Measurements (CRUD + Print + Bulk)
- Uniform Sizes (CRUD + Print)
- Uniform Items/Inventory (CRUD + Print + Stock)
- Purchase Orders (CRUD + Print + Receiving)
- Uniform Sales (CRUD + Print + Returns/Cancellations)
- Student Uniform Sizes (CRUD + Print)
- Measurement Sessions (CRUD + Print)
- Reports and Analytics

All views delegate business logic to services.py
Uses SweetAlert2 for all notifications via Django messages
Uses core.utils for timezone-aware operations
Audit trail automatically handled by BaseModel

Pattern follows academics/views.py
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib import messages
from django.db.models import Q, Count, Sum, Avg, Prefetch, F, DecimalField
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.core.exceptions import ValidationError
from datetime import timedelta, date, datetime
from decimal import Decimal
import logging

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ⭐ Import timezone utilities from core
from core.utils import (
    get_school_today,
    get_school_current_time,
    get_school_timezone,
    localize_datetime,
    get_active_academic_session,
    format_money,
    calculate_percentage,
    validate_date_range,
)

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
    MeasurementSession,
)

from .forms import (
    MeasurementTypeForm,
    MeasurementTypeFilterForm,
    StudentMeasurementForm,
    StudentMeasurementFilterForm,
    BulkMeasurementForm,
    UniformSizeForm,
    UniformSizeFilterForm,
    UniformItemForm,
    UniformItemFilterForm,
    UniformStockForm,
    StockAdjustmentForm,
    UniformPurchaseOrderForm,
    UniformPurchaseOrderItemForm,
    UniformPurchaseOrderFilterForm,
    UniformSaleForm,
    UniformSaleItemForm,
    UniformSaleFilterForm,
    StudentUniformSizeForm,
    MeasurementSessionForm,
    MeasurementSessionFilterForm,
)

from students.models import Student
from academics.models import AcademicSession, Class

logger = logging.getLogger(__name__)


# =============================================================================
# DASHBOARD
# =============================================================================

@login_required
def uniforms_dashboard(request):
    """Main uniforms dashboard with overview statistics"""
    
    try:
        today = get_school_today()
        current_session = get_active_academic_session()
        
        # Inventory statistics
        inventory_stats = {
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
            )['total'] or Decimal('0.00'),
        }
        
        # Sales statistics
        this_month = today.replace(day=1)
        sales_stats = {
            'total_sales': UniformSale.objects.filter(
                cancelled=False,
                returned=False
            ).count(),
            'pending_payment': UniformSale.objects.filter(
                status='PENDING',
                cancelled=False,
                returned=False
            ).count(),
            'this_month_sales': UniformSale.objects.filter(
                sale_date__gte=this_month,
                cancelled=False,
                returned=False
            ).count(),
            'this_month_revenue': UniformSale.objects.filter(
                sale_date__gte=this_month,
                status__in=['PAID', 'ISSUED'],
                cancelled=False,
                returned=False
            ).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00'),
        }
        
        # Measurement statistics
        measurement_stats = {
            'total_measurements': StudentMeasurement.objects.count(),
            'current_measurements': StudentMeasurement.objects.filter(is_current=True).count(),
            'verified': StudentMeasurement.objects.filter(is_verified=True).count(),
            'this_month': StudentMeasurement.objects.filter(
                measurement_date__gte=this_month
            ).count(),
        }
        
        # Purchase order statistics
        po_stats = {
            'total': UniformPurchaseOrder.objects.count(),
            'pending': UniformPurchaseOrder.objects.filter(
                status__in=['DRAFT', 'SUBMITTED', 'APPROVED']
            ).count(),
            'awaiting_delivery': UniformPurchaseOrder.objects.filter(
                status='ORDERED'
            ).count(),
        }
        
    except Exception as e:
        logger.error(f"Error getting dashboard statistics: {e}")
        inventory_stats = {}
        sales_stats = {}
        measurement_stats = {}
        po_stats = {}
    
    # Get recent activities
    recent_sales = UniformSale.objects.select_related(
        'student', 'academic_session'
    ).filter(
        cancelled=False,
        returned=False
    ).order_by('-created_at')[:10]
    
    recent_measurements = StudentMeasurement.objects.select_related(
        'student', 'measurement_type'
    ).order_by('-created_at')[:10]
    
    low_stock_items = UniformItem.objects.filter(
        is_active=True,
        current_stock__lte=F('reorder_level')
    ).order_by('current_stock')[:10]
    
    pending_pos = UniformPurchaseOrder.objects.filter(
        status__in=['SUBMITTED', 'APPROVED', 'ORDERED']
    ).order_by('-order_date')[:10]
    
    context = {
        'inventory_stats': inventory_stats,
        'sales_stats': sales_stats,
        'measurement_stats': measurement_stats,
        'po_stats': po_stats,
        'recent_sales': recent_sales,
        'recent_measurements': recent_measurements,
        'low_stock_items': low_stock_items,
        'pending_pos': pending_pos,
    }
    
    return render(request, 'uniforms/dashboard.html', context)


# =============================================================================
# HELPER FUNCTIONS FOR FILTERING
# =============================================================================

def get_filtered_measurement_types(request):
    """Helper function to get filtered measurement types queryset"""
    measurement_types = MeasurementType.objects.select_related('unit').order_by(
        'category', 'display_order', 'name'
    )
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '')
    is_active = request.GET.get('is_active', '')
    is_required = request.GET.get('is_required', '')
    unit = request.GET.get('unit', '')
    
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
    if is_active:
        measurement_types = measurement_types.filter(is_active=(is_active.lower() == 'true'))
    if is_required:
        measurement_types = measurement_types.filter(is_required=(is_required.lower() == 'true'))
    
    return measurement_types


def get_filtered_student_measurements(request):
    """Helper function to get filtered student measurements queryset"""
    measurements = StudentMeasurement.objects.select_related(
        'student__current_academic_level',
        'measurement_type__unit',
        'academic_session'
    ).order_by('-measurement_date', 'student__first_name')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    student = request.GET.get('student', '')
    measurement_type = request.GET.get('measurement_type', '')
    academic_session = request.GET.get('academic_session', '')
    measurement_context = request.GET.get('measurement_context', '')
    is_verified = request.GET.get('is_verified', '')
    is_current = request.GET.get('is_current', '')
    measurement_date_from = request.GET.get('measurement_date_from', '')
    measurement_date_to = request.GET.get('measurement_date_to', '')
    
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
    if is_verified:
        measurements = measurements.filter(is_verified=(is_verified.lower() == 'true'))
    if is_current:
        measurements = measurements.filter(is_current=(is_current.lower() == 'true'))
    if measurement_date_from:
        measurements = measurements.filter(measurement_date__gte=measurement_date_from)
    if measurement_date_to:
        measurements = measurements.filter(measurement_date__lte=measurement_date_to)
    
    return measurements


def get_filtered_uniform_sizes(request):
    """Helper function to get filtered uniform sizes queryset"""
    sizes = UniformSize.objects.annotate(
        item_count=Count('uniform_items', distinct=True)
    ).order_by('display_order', 'name')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    size_type = request.GET.get('size_type', '')
    is_active = request.GET.get('is_active', '')
    
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
    if is_active:
        sizes = sizes.filter(is_active=(is_active.lower() == 'true'))
    
    return sizes


def get_filtered_uniform_items(request):
    """Helper function to get filtered uniform items queryset"""
    items = UniformItem.objects.select_related(
        'unit_of_measure', 'tax_rate'
    ).prefetch_related('available_sizes').annotate(
        size_count=Count('available_sizes', distinct=True)
    ).order_by('item_type', 'name')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    item_type = request.GET.get('item_type', '')
    gender = request.GET.get('gender', '')
    category = request.GET.get('category', '')
    is_active = request.GET.get('is_active', '')
    is_mandatory = request.GET.get('is_mandatory', '')
    stock_status = request.GET.get('stock_status', '')
    
    # Apply text search
    if query:
        items = items.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(sku__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply filters
    if item_type:
        items = items.filter(item_type=item_type)
    if gender:
        items = items.filter(gender=gender)
    if category:
        items = items.filter(category__icontains=category)
    if is_active:
        items = items.filter(is_active=(is_active.lower() == 'true'))
    if is_mandatory:
        items = items.filter(is_mandatory=(is_mandatory.lower() == 'true'))
    if stock_status:
        if stock_status == 'low_stock':
            items = items.filter(current_stock__lte=F('reorder_level'))
        elif stock_status == 'out_of_stock':
            items = items.filter(current_stock=0)
        elif stock_status == 'in_stock':
            items = items.filter(current_stock__gt=F('reorder_level'))
    
    return items


def get_filtered_purchase_orders(request):
    """Helper function to get filtered purchase orders queryset"""
    orders = UniformPurchaseOrder.objects.select_related(
        'fiscal_period', 'journal_entry'
    ).prefetch_related('items').order_by('-order_date')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    fiscal_period = request.GET.get('fiscal_period', '')
    order_date_from = request.GET.get('order_date_from', '')
    order_date_to = request.GET.get('order_date_to', '')
    
    # Apply text search
    if query:
        orders = orders.filter(
            Q(po_number__icontains=query) |
            Q(supplier_name__icontains=query) |
            Q(notes__icontains=query)
        )
    
    # Apply filters
    if status:
        orders = orders.filter(status=status)
    if fiscal_period:
        orders = orders.filter(fiscal_period_id=fiscal_period)
    if order_date_from:
        orders = orders.filter(order_date__gte=order_date_from)
    if order_date_to:
        orders = orders.filter(order_date__lte=order_date_to)
    
    return orders


def get_filtered_uniform_sales(request):
    """Helper function to get filtered uniform sales queryset"""
    sales = UniformSale.objects.select_related(
        'student__current_academic_level',
        'academic_session',
        'fiscal_period',
        'fee_invoice',
        'payment_method'
    ).prefetch_related('items').order_by('-sale_date')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    sale_type = request.GET.get('sale_type', '')
    student = request.GET.get('student', '')
    academic_session = request.GET.get('academic_session', '')
    sale_date_from = request.GET.get('sale_date_from', '')
    sale_date_to = request.GET.get('sale_date_to', '')
    
    # Apply text search
    if query:
        sales = sales.filter(
            Q(sale_number__icontains=query) |
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__admission_number__icontains=query)
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
    if sale_date_from:
        sales = sales.filter(sale_date__gte=sale_date_from)
    if sale_date_to:
        sales = sales.filter(sale_date__lte=sale_date_to)
    
    return sales


def get_filtered_measurement_sessions(request):
    """Helper function to get filtered measurement sessions queryset"""
    sessions = MeasurementSession.objects.select_related(
        'academic_session'
    ).prefetch_related('target_classes').order_by('-session_date')
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    session_type = request.GET.get('session_type', '')
    status = request.GET.get('status', '')
    academic_session = request.GET.get('academic_session', '')
    
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
    
    return sessions


# =============================================================================
# MEASUREMENT TYPE VIEWS
# =============================================================================

@login_required
def measurement_type_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = MeasurementTypeFilterForm(request.GET or None)
    measurement_types = get_filtered_measurement_types(request)
    
    # Calculate statistics
    stats = {
        'total': measurement_types.count(),
        'active': measurement_types.filter(is_active=True).count(),
        'required': measurement_types.filter(is_required=True).count(),
        'uniform': measurement_types.filter(category='UNIFORM').count(),
        'sports': measurement_types.filter(category='SPORTS').count(),
        'health': measurement_types.filter(category='HEALTH').count(),
    }
    
    # Pagination
    paginator = Paginator(measurement_types, 20)
    page_number = request.GET.get('page', 1)
    measurement_types_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'measurement_types_page': measurement_types_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'uniforms/measurement_types/_type_results.html', context)
    else:
        return render(request, 'uniforms/measurement_types/list.html', context)


@login_required
def measurement_type_detail(request, pk):
    """View measurement type details"""
    measurement_type = get_object_or_404(MeasurementType, pk=pk)
    
    # Get related measurements
    recent_measurements = measurement_type.student_measurements.select_related(
        'student', 'academic_session'
    ).order_by('-measurement_date')[:20]
    
    # Statistics
    measurement_count = measurement_type.student_measurements.count()
    verified_count = measurement_type.student_measurements.filter(is_verified=True).count()
    
    # Average value
    avg_value = measurement_type.student_measurements.filter(
        is_current=True
    ).aggregate(Avg('value'))['value__avg']
    
    context = {
        'measurement_type': measurement_type,
        'recent_measurements': recent_measurements,
        'measurement_count': measurement_count,
        'verified_count': verified_count,
        'avg_value': avg_value,
    }
    
    return render(request, 'uniforms/measurement_types/detail.html', context)


@login_required
def measurement_type_create(request):
    """Create new measurement type"""
    if request.method == 'POST':
        form = MeasurementTypeForm(request.POST)
        if form.is_valid():
            try:
                measurement_type = form.save()
                messages.success(
                    request,
                    f'Measurement type "{measurement_type.name}" created successfully'
                )
                return redirect('uniforms:measurement_type_detail', pk=measurement_type.pk)
            except Exception as e:
                logger.error(f"Error creating measurement type: {e}")
                messages.error(request, f'Error creating measurement type: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = MeasurementTypeForm()
    
    context = {
        'form': form,
        'title': 'Create Measurement Type',
        'submit_text': 'Create',
    }
    
    return render(request, 'uniforms/measurement_types/form.html', context)


@login_required
def measurement_type_edit(request, pk):
    """Edit measurement type"""
    measurement_type = get_object_or_404(MeasurementType, pk=pk)
    
    if request.method == 'POST':
        form = MeasurementTypeForm(request.POST, instance=measurement_type)
        if form.is_valid():
            try:
                measurement_type = form.save()
                messages.success(
                    request,
                    f'Measurement type "{measurement_type.name}" updated successfully'
                )
                return redirect('uniforms:measurement_type_detail', pk=measurement_type.pk)
            except Exception as e:
                logger.error(f"Error updating measurement type: {e}")
                messages.error(request, f'Error updating measurement type: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = MeasurementTypeForm(instance=measurement_type)
    
    context = {
        'form': form,
        'measurement_type': measurement_type,
        'title': f'Edit {measurement_type.name}',
        'submit_text': 'Update',
    }
    
    return render(request, 'uniforms/measurement_types/form.html', context)


@login_required
def measurement_type_delete(request, pk):
    """Delete measurement type with HTMX support"""
    measurement_type = get_object_or_404(MeasurementType, pk=pk)
    
    if request.method == 'POST':
        # Check if has measurements
        if measurement_type.student_measurements.exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Cannot delete measurement type with existing measurements'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, 'Cannot delete measurement type with existing measurements')
                return redirect('uniforms:measurement_type_detail', pk=pk)
        
        try:
            type_name = measurement_type.name
            measurement_type.delete()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Measurement type "{type_name}" deleted successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('uniforms:measurement_type_list')
                return response
            else:
                messages.success(request, f'Measurement type "{type_name}" deleted successfully')
                return redirect('uniforms:measurement_type_list')
                
        except Exception as e:
            logger.error(f"Error deleting measurement type: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error deleting measurement type: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error deleting measurement type: {str(e)}')
                return redirect('uniforms:measurement_type_detail', pk=pk)


# =============================================================================
# STUDENT MEASUREMENT VIEWS
# =============================================================================

@login_required
def student_measurement_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = StudentMeasurementFilterForm(request.GET or None)
    measurements = get_filtered_student_measurements(request)
    
    # Calculate statistics
    stats = {
        'total': measurements.count(),
        'current': measurements.filter(is_current=True).count(),
        'verified': measurements.filter(is_verified=True).count(),
        'unverified': measurements.filter(is_verified=False).count(),
    }
    
    # Pagination
    paginator = Paginator(measurements, 20)
    page_number = request.GET.get('page', 1)
    measurements_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'measurements_page': measurements_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'uniforms/measurements/_measurement_results.html', context)
    else:
        return render(request, 'uniforms/measurements/list.html', context)


@login_required
def student_measurement_create(request):
    """Create new student measurement"""
    student_id = request.GET.get('student')
    student = None
    if student_id:
        student = get_object_or_404(Student, pk=student_id)
    
    if request.method == 'POST':
        form = StudentMeasurementForm(request.POST, student=student)
        if form.is_valid():
            try:
                measurement = form.save()
                messages.success(
                    request,
                    f'Measurement recorded for {measurement.student.get_full_name()}'
                )
                return redirect('uniforms:student_measurement_list')
            except Exception as e:
                logger.error(f"Error creating measurement: {e}")
                messages.error(request, f'Error creating measurement: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = StudentMeasurementForm(student=student)
    
    context = {
        'form': form,
        'title': 'Record Student Measurement',
        'submit_text': 'Record',
    }
    
    return render(request, 'uniforms/measurements/form.html', context)

@login_required
def student_measurement_detail(request, pk):
    """View student measurement details"""
    measurement = get_object_or_404(
        StudentMeasurement.objects.select_related(
            'student__current_academic_level',
            'measurement_type__unit',
            'academic_session'
        ),
        pk=pk
    )
    
    # Get other measurements for this student and type
    other_measurements = StudentMeasurement.objects.filter(
        student=measurement.student,
        measurement_type=measurement.measurement_type
    ).exclude(pk=pk).order_by('-measurement_date')[:5]
    
    # Get verified by user
    verified_by = measurement.get_verified_by_user()
    
    context = {
        'measurement': measurement,
        'other_measurements': other_measurements,
        'verified_by': verified_by,
    }
    
    return render(request, 'uniforms/measurements/detail.html', context)


@login_required
def student_measurement_edit(request, pk):
    """Edit student measurement"""
    measurement = get_object_or_404(StudentMeasurement, pk=pk)
    
    if request.method == 'POST':
        form = StudentMeasurementForm(request.POST, instance=measurement)
        if form.is_valid():
            try:
                measurement = form.save()
                messages.success(
                    request,
                    f'Measurement updated for {measurement.student.get_full_name()}'
                )
                return redirect('uniforms:student_measurement_detail', pk=measurement.pk)
            except Exception as e:
                logger.error(f"Error updating measurement: {e}")
                messages.error(request, f'Error updating measurement: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = StudentMeasurementForm(instance=measurement)
    
    context = {
        'form': form,
        'measurement': measurement,
        'title': f'Edit Measurement',
        'submit_text': 'Update',
    }
    
    return render(request, 'uniforms/measurements/form.html', context)


@login_required
def student_measurement_delete(request, pk):
    """Delete student measurement with HTMX support"""
    measurement = get_object_or_404(StudentMeasurement, pk=pk)
    
    if request.method == 'POST':
        try:
            student_name = measurement.student.get_full_name()
            measurement_type = measurement.measurement_type.name
            measurement.delete()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Measurement deleted for {student_name}'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('uniforms:student_measurement_list')
                return response
            else:
                messages.success(request, f'Measurement deleted for {student_name}')
                return redirect('uniforms:student_measurement_list')
                
        except Exception as e:
            logger.error(f"Error deleting measurement: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error deleting measurement: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error deleting measurement: {str(e)}')
                return redirect('uniforms:student_measurement_detail', pk=pk)


@login_required
def student_measurement_verify(request, pk):
    """Verify student measurement"""
    measurement = get_object_or_404(StudentMeasurement, pk=pk)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                measurement.is_verified = True
                measurement.verified_by_id = str(request.user.id)
                measurement.verification_date = get_school_current_time()
                measurement.save()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Measurement verified successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('uniforms:student_measurement_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(request, 'Measurement verified successfully')
                return redirect('uniforms:student_measurement_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error verifying measurement: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error verifying measurement: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error verifying measurement: {str(e)}')
                return redirect('uniforms:student_measurement_detail', pk=pk)


@login_required
def student_measurement_bulk_create(request):
    """Bulk create measurements for multiple students"""
    if request.method == 'POST':
        form = BulkMeasurementForm(request.POST)
        if form.is_valid():
            try:
                # Get form data
                academic_session = form.cleaned_data['academic_session']
                measurement_date = form.cleaned_data['measurement_date']
                measurement_context = form.cleaned_data['measurement_context']
                measurement_method = form.cleaned_data['measurement_method']
                target_class = form.cleaned_data.get('target_class')
                measurement_session = form.cleaned_data.get('measurement_session')
                
                # Get students
                if target_class:
                    students = target_class.students.filter(enrollment_status='ACTIVE')
                else:
                    students = Student.objects.filter(enrollment_status='ACTIVE')
                
                # Redirect to bulk measurement entry page
                return redirect('uniforms:student_measurement_bulk_entry')
                
            except Exception as e:
                logger.error(f"Error setting up bulk measurements: {e}")
                messages.error(request, f'Error: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = BulkMeasurementForm()
    
    context = {
        'form': form,
        'title': 'Bulk Measurement Setup',
        'submit_text': 'Continue',
    }
    
    return render(request, 'uniforms/measurements/bulk_form.html', context)

# =============================================================================
# UNIFORM STOCK VIEWS (MISSING)
# =============================================================================

@login_required
def uniform_stock_list(request):
    """List all stock records with filtering"""
    stock_records = UniformStock.objects.select_related(
        'uniform_item', 'size'
    ).order_by('uniform_item__name', 'size__display_order')
    
    # Apply filters
    query = request.GET.get('q', '').strip()
    if query:
        stock_records = stock_records.filter(
            Q(uniform_item__name__icontains=query) |
            Q(uniform_item__code__icontains=query) |
            Q(size__name__icontains=query)
        )
    
    item_id = request.GET.get('item')
    if item_id:
        stock_records = stock_records.filter(uniform_item_id=item_id)
    
    # Statistics
    stats = {
        'total_records': stock_records.count(),
        'total_quantity': stock_records.aggregate(Sum('quantity'))['quantity__sum'] or 0,
        'total_value': stock_records.aggregate(Sum('total_cost_value'))['total_cost_value__sum'] or Decimal('0.00'),
        'low_stock': stock_records.filter(quantity__lte=F('uniform_item__reorder_level')).count(),
    }
    
    # Pagination
    paginator = Paginator(stock_records, 20)
    page_number = request.GET.get('page', 1)
    stock_page = paginator.get_page(page_number)
    
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'stock_page': stock_page,
        'paginator': paginator,
        'stats': stats,
        'is_htmx': is_htmx,
    }
    
    if is_htmx:
        return render(request, 'uniforms/stock/_stock_results.html', context)
    else:
        return render(request, 'uniforms/stock/list.html', context)


@login_required
def uniform_stock_detail(request, pk):
    """View stock record details"""
    stock = get_object_or_404(
        UniformStock.objects.select_related('uniform_item', 'size'),
        pk=pk
    )
    
    # Get recent transactions (you might have a StockTransaction model)
    # recent_transactions = stock.transactions.order_by('-created_at')[:10]
    
    context = {
        'stock': stock,
        # 'recent_transactions': recent_transactions,
    }
    
    return render(request, 'uniforms/stock/detail.html', context)


@login_required
def uniform_stock_create(request):
    """Create new stock record"""
    if request.method == 'POST':
        form = UniformStockForm(request.POST)
        if form.is_valid():
            try:
                stock = form.save()
                messages.success(
                    request,
                    f'Stock record created for {stock.uniform_item.name} - Size {stock.size.name}'
                )
                return redirect('uniforms:uniform_stock_detail', pk=stock.pk)
            except Exception as e:
                logger.error(f"Error creating stock record: {e}")
                messages.error(request, f'Error creating stock record: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        # Pre-fill item if provided
        item_id = request.GET.get('item')
        initial = {}
        if item_id:
            initial['uniform_item'] = item_id
        form = UniformStockForm(initial=initial)
    
    context = {
        'form': form,
        'title': 'Create Stock Record',
        'submit_text': 'Create',
    }
    
    return render(request, 'uniforms/stock/form.html', context)


@login_required
def uniform_stock_edit(request, pk):
    """Edit stock record"""
    stock = get_object_or_404(UniformStock, pk=pk)
    
    if request.method == 'POST':
        form = UniformStockForm(request.POST, instance=stock)
        if form.is_valid():
            try:
                stock = form.save()
                messages.success(request, 'Stock record updated successfully')
                return redirect('uniforms:uniform_stock_detail', pk=stock.pk)
            except Exception as e:
                logger.error(f"Error updating stock record: {e}")
                messages.error(request, f'Error updating stock record: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = UniformStockForm(instance=stock)
    
    context = {
        'form': form,
        'stock': stock,
        'title': 'Edit Stock Record',
        'submit_text': 'Update',
    }
    
    return render(request, 'uniforms/stock/form.html', context)


@login_required
def uniform_stock_delete(request, pk):
    """Delete stock record with HTMX support"""
    stock = get_object_or_404(UniformStock, pk=pk)
    
    if request.method == 'POST':
        if stock.quantity > 0:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Cannot delete stock record with quantity > 0'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, 'Cannot delete stock record with quantity > 0')
                return redirect('uniforms:uniform_stock_detail', pk=pk)
        
        try:
            item_name = f"{stock.uniform_item.name} - Size {stock.size.name}"
            stock.delete()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Stock record for {item_name} deleted'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('uniforms:uniform_stock_list')
                return response
            else:
                messages.success(request, f'Stock record for {item_name} deleted')
                return redirect('uniforms:uniform_stock_list')
                
        except Exception as e:
            logger.error(f"Error deleting stock record: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error deleting stock record: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error deleting stock record: {str(e)}')
                return redirect('uniforms:uniform_stock_detail', pk=pk)

# =============================================================================
# UNIFORM SIZE VIEWS
# =============================================================================

@login_required
def uniform_size_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = UniformSizeFilterForm(request.GET or None)
    sizes = get_filtered_uniform_sizes(request)
    
    # Calculate statistics
    stats = {
        'total': sizes.count(),
        'active': sizes.filter(is_active=True).count(),
        'numeric': sizes.filter(size_type='NUMERIC').count(),
        'alpha': sizes.filter(size_type='ALPHA').count(),
    }
    
    # Pagination
    paginator = Paginator(sizes, 20)
    page_number = request.GET.get('page', 1)
    sizes_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'sizes_page': sizes_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'uniforms/sizes/_size_results.html', context)
    else:
        return render(request, 'uniforms/sizes/list.html', context)


@login_required
def uniform_size_create(request):
    """Create new uniform size"""
    if request.method == 'POST':
        form = UniformSizeForm(request.POST)
        if form.is_valid():
            try:
                size = form.save()
                messages.success(request, f'Uniform size "{size.name}" created successfully')
                return redirect('uniforms:uniform_size_list')
            except Exception as e:
                logger.error(f"Error creating uniform size: {e}")
                messages.error(request, f'Error creating uniform size: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = UniformSizeForm()
    
    context = {
        'form': form,
        'title': 'Create Uniform Size',
        'submit_text': 'Create',
    }
    
    return render(request, 'uniforms/sizes/form.html', context)

@login_required
def uniform_size_detail(request, pk):
    """View uniform size details"""
    size = get_object_or_404(UniformSize, pk=pk)
    
    # Get items using this size
    items = size.uniform_items.filter(is_active=True).order_by('name')
    
    # Get stock records
    stock_records = size.stock_records.select_related('uniform_item').order_by('uniform_item__name')
    
    # Statistics
    total_stock = stock_records.aggregate(Sum('quantity'))['quantity__sum'] or 0
    total_value = sum(sr.total_cost_value for sr in stock_records)
    
    context = {
        'size': size,
        'items': items,
        'stock_records': stock_records,
        'total_stock': total_stock,
        'total_value': total_value,
    }
    
    return render(request, 'uniforms/sizes/detail.html', context)


@login_required
def uniform_size_edit(request, pk):
    """Edit uniform size"""
    size = get_object_or_404(UniformSize, pk=pk)
    
    if request.method == 'POST':
        form = UniformSizeForm(request.POST, instance=size)
        if form.is_valid():
            try:
                size = form.save()
                messages.success(request, f'Uniform size "{size.name}" updated successfully')
                return redirect('uniforms:uniform_size_detail', pk=size.pk)
            except Exception as e:
                logger.error(f"Error updating uniform size: {e}")
                messages.error(request, f'Error updating uniform size: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = UniformSizeForm(instance=size)
    
    context = {
        'form': form,
        'size': size,
        'title': f'Edit {size.name}',
        'submit_text': 'Update',
    }
    
    return render(request, 'uniforms/sizes/form.html', context)


@login_required
def uniform_size_delete(request, pk):
    """Delete uniform size with HTMX support"""
    size = get_object_or_404(UniformSize, pk=pk)
    
    if request.method == 'POST':
        # Check if used by items
        if size.uniform_items.exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Cannot delete size that is used by uniform items'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, 'Cannot delete size that is used by uniform items')
                return redirect('uniforms:uniform_size_detail', pk=pk)
        
        try:
            size_name = size.name
            size.delete()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Size "{size_name}" deleted successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('uniforms:uniform_size_list')
                return response
            else:
                messages.success(request, f'Size "{size_name}" deleted successfully')
                return redirect('uniforms:uniform_size_list')
                
        except Exception as e:
            logger.error(f"Error deleting size: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error deleting size: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error deleting size: {str(e)}')
                return redirect('uniforms:uniform_size_detail', pk=pk)


# =============================================================================
# UNIFORM ITEM VIEWS
# =============================================================================

@login_required
def uniform_item_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = UniformItemFilterForm(request.GET or None)
    items = get_filtered_uniform_items(request)
    
    # Calculate statistics
    stats = {
        'total': items.count(),
        'active': items.filter(is_active=True).count(),
        'low_stock': items.filter(current_stock__lte=F('reorder_level')).count(),
        'out_of_stock': items.filter(current_stock=0).count(),
        'total_value': items.aggregate(
            total=Sum(F('current_stock') * F('unit_cost'))
        )['total'] or Decimal('0.00'),
    }
    
    # Pagination
    paginator = Paginator(items, 20)
    page_number = request.GET.get('page', 1)
    items_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'items_page': items_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'uniforms/items/partials/_item_results.html', context)
    else:
        return render(request, 'uniforms/items/list.html', context)


@login_required
def uniform_item_detail(request, pk):
    """View uniform item details"""
    item = get_object_or_404(
        UniformItem.objects.select_related('unit_of_measure', 'tax_rate'),
        pk=pk
    )
    
    # Get stock records by size
    stock_records = item.stock_records.select_related('size').order_by('size__display_order')
    
    # Get recent sales
    recent_sales = item.sale_items.select_related(
        'sale__student', 'size'
    ).order_by('-sale__sale_date')[:10]
    
    # Statistics
    total_quantity_sold = item.sale_items.aggregate(Sum('quantity'))['quantity__sum'] or 0
    total_revenue = item.sale_items.aggregate(Sum('total_price'))['total_price__sum'] or Decimal('0.00')
    
    context = {
        'item': item,
        'stock_records': stock_records,
        'recent_sales': recent_sales,
        'total_quantity_sold': total_quantity_sold,
        'total_revenue': total_revenue,
    }
    
    return render(request, 'uniforms/items/detail.html', context)


@login_required
def uniform_item_create(request):
    """Create new uniform item"""
    if request.method == 'POST':
        form = UniformItemForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                item = form.save()
                messages.success(request, f'Uniform item "{item.name}" created successfully')
                return redirect('uniforms:uniform_item_detail', pk=item.pk)
            except Exception as e:
                logger.error(f"Error creating uniform item: {e}")
                messages.error(request, f'Error creating uniform item: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = UniformItemForm()
    
    context = {
        'form': form,
        'title': 'Create Uniform Item',
        'submit_text': 'Create',
    }
    
    return render(request, 'uniforms/items/form.html', context)


@login_required
def uniform_item_edit(request, pk):
    """Edit uniform item"""
    item = get_object_or_404(UniformItem, pk=pk)
    
    if request.method == 'POST':
        form = UniformItemForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            try:
                item = form.save()
                messages.success(request, f'Uniform item "{item.name}" updated successfully')
                return redirect('uniforms:uniform_item_detail', pk=item.pk)
            except Exception as e:
                logger.error(f"Error updating uniform item: {e}")
                messages.error(request, f'Error updating uniform item: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = UniformItemForm(instance=item)
    
    context = {
        'form': form,
        'item': item,
        'title': f'Edit {item.name}',
        'submit_text': 'Update',
    }
    
    return render(request, 'uniforms/items/form.html', context)


@login_required
def uniform_item_delete(request, pk):
    """Delete uniform item with HTMX support"""
    item = get_object_or_404(UniformItem, pk=pk)
    
    if request.method == 'POST':
        # Check if has stock
        if item.current_stock > 0:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Cannot delete item with {item.current_stock} units in stock'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, 'Cannot delete item with stock')
                return redirect('uniforms:uniform_item_detail', pk=pk)
        
        # Check if has sales
        if item.sale_items.exists():
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Cannot delete item with existing sales records'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, 'Cannot delete item with existing sales records')
                return redirect('uniforms:uniform_item_detail', pk=pk)
        
        try:
            item_name = item.name
            item.delete()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Uniform item "{item_name}" deleted successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('uniforms:uniform_item_list')
                return response
            else:
                messages.success(request, f'Uniform item "{item_name}" deleted successfully')
                return redirect('uniforms:uniform_item_list')
                
        except Exception as e:
            logger.error(f"Error deleting uniform item: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error deleting uniform item: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error deleting uniform item: {str(e)}')
                return redirect('uniforms:uniform_item_detail', pk=pk)


@login_required
def uniform_item_toggle_active(request, pk):
    """Toggle uniform item active status with HTMX support"""
    item = get_object_or_404(UniformItem, pk=pk)
    
    if request.method == 'POST':
        try:
            item.is_active = not item.is_active
            item.save()
            
            status_text = 'activated' if item.is_active else 'deactivated'
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Uniform item "{item.name}" {status_text} successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('uniforms:uniform_item_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(request, f'Uniform item "{item.name}" {status_text} successfully')
                return redirect('uniforms:uniform_item_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error toggling uniform item active status: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error updating uniform item: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error updating uniform item: {str(e)}')
                return redirect('uniforms:uniform_item_detail', pk=pk)


@login_required
def uniform_item_adjust_stock(request, pk):
    """Adjust uniform item stock with HTMX support"""
    item = get_object_or_404(UniformItem, pk=pk)
    
    if request.method == 'POST':
        try:
            adjustment_type = request.POST.get('adjustment_type')
            quantity = int(request.POST.get('quantity', 0))
            reason = request.POST.get('reason', '').strip()
            
            if not reason:
                raise ValidationError('Adjustment reason is required')
            
            if quantity < 0:
                raise ValidationError('Quantity must be positive')
            
            old_stock = item.current_stock
            
            with transaction.atomic():
                if adjustment_type == 'ADD':
                    item.current_stock += quantity
                elif adjustment_type == 'REMOVE':
                    if quantity > item.current_stock:
                        raise ValidationError('Cannot remove more than current stock')
                    item.current_stock -= quantity
                elif adjustment_type == 'SET':
                    item.current_stock = quantity
                else:
                    raise ValidationError('Invalid adjustment type')
                
                item.save()
                
                # Log the adjustment (you could create a StockAdjustment model for audit trail)
                logger.info(
                    f"Stock adjusted for {item.name}: {old_stock} -> {item.current_stock} "
                    f"({adjustment_type}, {quantity} units) - Reason: {reason}"
                )
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Stock adjusted successfully. New stock: {item.current_stock}'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('uniforms:uniform_item_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(request, f'Stock adjusted successfully. New stock: {item.current_stock}')
                return redirect('uniforms:uniform_item_detail', pk=pk)
                
        except ValidationError as e:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = str(e)
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, str(e))
                return redirect('uniforms:uniform_item_detail', pk=pk)
        except Exception as e:
            logger.error(f"Error adjusting stock: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error adjusting stock: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error adjusting stock: {str(e)}')
                return redirect('uniforms:uniform_item_detail', pk=pk)
            
# =============================================================================
# PURCHASE ORDER VIEWS
# =============================================================================

@login_required
def purchase_order_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = UniformPurchaseOrderFilterForm(request.GET or None)
    orders = get_filtered_purchase_orders(request)
    
    # Calculate statistics
    stats = {
        'total': orders.count(),
        'draft': orders.filter(status='DRAFT').count(),
        'pending': orders.filter(status__in=['SUBMITTED', 'APPROVED']).count(),
        'received': orders.filter(status='RECEIVED').count(),
        'total_amount': orders.aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00'),
    }
    
    # Pagination
    paginator = Paginator(orders, 20)
    page_number = request.GET.get('page', 1)
    orders_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'orders_page': orders_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'uniforms/purchase_orders/partials/_order_results.html', context)
    else:
        return render(request, 'uniforms/purchase_orders/list.html', context)


@login_required
def purchase_order_create(request):
    """Create new purchase order"""
    if request.method == 'POST':
        form = UniformPurchaseOrderForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    po = form.save(commit=False)
                    # Generate PO number
                    today = get_school_today()
                    year_month = today.strftime('%Y%m')
                    last_po = UniformPurchaseOrder.objects.filter(
                        po_number__startswith=f'UPO-{year_month}'
                    ).order_by('-po_number').first()
                    
                    if last_po:
                        try:
                            last_num = int(last_po.po_number.split('-')[-1])
                            new_num = last_num + 1
                        except:
                            new_num = 1
                    else:
                        new_num = 1
                    
                    po.po_number = f'UPO-{year_month}-{new_num:04d}'
                    po.save()
                    form.save_m2m()
                
                messages.success(request, f'Purchase order {po.po_number} created successfully')
                return redirect('uniforms:purchase_order_detail', pk=po.pk)
            except Exception as e:
                logger.error(f"Error creating purchase order: {e}")
                messages.error(request, f'Error creating purchase order: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = UniformPurchaseOrderForm()
    
    context = {
        'form': form,
        'title': 'Create Purchase Order',
        'submit_text': 'Create',
    }
    
    return render(request, 'uniforms/purchase_orders/form.html', context)

@login_required
def purchase_order_detail(request, pk):
    """View purchase order details"""
    po = get_object_or_404(
        UniformPurchaseOrder.objects.select_related(
            'fiscal_period', 'journal_entry'
        ).prefetch_related('items__uniform_item', 'items__size'),
        pk=pk
    )
    
    # Get approval user
    approved_by = po.get_approved_by_user() if po.approved_by_id else None
    
    context = {
        'po': po,
        'approved_by': approved_by,
    }
    
    return render(request, 'uniforms/purchase_orders/detail.html', context)


@login_required
def purchase_order_edit(request, pk):
    """Edit purchase order (only if DRAFT)"""
    po = get_object_or_404(UniformPurchaseOrder, pk=pk)
    
    if po.status not in ['DRAFT']:
        messages.error(request, 'Only draft purchase orders can be edited')
        return redirect('uniforms:purchase_order_detail', pk=pk)
    
    if request.method == 'POST':
        form = UniformPurchaseOrderForm(request.POST, instance=po)
        if form.is_valid():
            try:
                po = form.save()
                messages.success(request, f'Purchase order {po.po_number} updated successfully')
                return redirect('uniforms:purchase_order_detail', pk=po.pk)
            except Exception as e:
                logger.error(f"Error updating purchase order: {e}")
                messages.error(request, f'Error updating purchase order: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = UniformPurchaseOrderForm(instance=po)
    
    context = {
        'form': form,
        'po': po,
        'title': f'Edit {po.po_number}',
        'submit_text': 'Update',
    }
    
    return render(request, 'uniforms/purchase_orders/form.html', context)


@login_required
def purchase_order_delete(request, pk):
    """Delete purchase order (only if DRAFT)"""
    po = get_object_or_404(UniformPurchaseOrder, pk=pk)
    
    if request.method == 'POST':
        if po.status != 'DRAFT':
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Only draft purchase orders can be deleted'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, 'Only draft purchase orders can be deleted')
                return redirect('uniforms:purchase_order_detail', pk=pk)
        
        try:
            po_number = po.po_number
            po.delete()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Purchase order {po_number} deleted'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('uniforms:purchase_order_list')
                return response
            else:
                messages.success(request, f'Purchase order {po_number} deleted')
                return redirect('uniforms:purchase_order_list')
                
        except Exception as e:
            logger.error(f"Error deleting purchase order: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error deleting purchase order: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error deleting purchase order: {str(e)}')
                return redirect('uniforms:purchase_order_detail', pk=pk)


@login_required
def purchase_order_submit(request, pk):
    """Submit purchase order for approval"""
    po = get_object_or_404(UniformPurchaseOrder, pk=pk)
    
    if request.method == 'POST':
        if po.status != 'DRAFT':
            messages.error(request, 'Only draft purchase orders can be submitted')
            return redirect('uniforms:purchase_order_detail', pk=pk)
        
        if not po.items.exists():
            messages.error(request, 'Cannot submit purchase order without items')
            return redirect('uniforms:purchase_order_detail', pk=pk)
        
        try:
            with transaction.atomic():
                po.status = 'SUBMITTED'
                po.save()
            
            messages.success(request, f'Purchase order {po.po_number} submitted for approval')
            return redirect('uniforms:purchase_order_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error submitting purchase order: {e}")
            messages.error(request, f'Error submitting purchase order: {str(e)}')
            return redirect('uniforms:purchase_order_detail', pk=pk)


@login_required
def purchase_order_approve(request, pk):
    """Approve purchase order"""
    po = get_object_or_404(UniformPurchaseOrder, pk=pk)
    
    if request.method == 'POST':
        if po.status != 'SUBMITTED':
            messages.error(request, 'Only submitted purchase orders can be approved')
            return redirect('uniforms:purchase_order_detail', pk=pk)
        
        try:
            with transaction.atomic():
                po.status = 'APPROVED'
                po.approved_by_id = str(request.user.id)
                po.approved_at = get_school_current_time()
                po.save()
            
            messages.success(request, f'Purchase order {po.po_number} approved')
            return redirect('uniforms:purchase_order_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error approving purchase order: {e}")
            messages.error(request, f'Error approving purchase order: {str(e)}')
            return redirect('uniforms:purchase_order_detail', pk=pk)


@login_required
def purchase_order_receive(request, pk):
    """Receive purchase order items and update inventory"""
    po = get_object_or_404(UniformPurchaseOrder, pk=pk)
    
    if request.method == 'POST':
        if po.status not in ['APPROVED', 'ORDERED', 'PARTIAL']:
            messages.error(request, 'Purchase order must be approved/ordered to receive items')
            return redirect('uniforms:purchase_order_detail', pk=pk)
        
        try:
            with transaction.atomic():
                # Update quantities received for each item
                all_received = True
                for item in po.items.all():
                    received_qty = int(request.POST.get(f'qty_{item.pk}', 0))
                    item.quantity_received = received_qty
                    item.save()
                    
                    if received_qty < item.quantity_ordered:
                        all_received = False
                    
                    # Update stock
                    if item.size:
                        stock, created = UniformStock.objects.get_or_create(
                            uniform_item=item.uniform_item,
                            size=item.size
                        )
                        stock.quantity += received_qty
                        stock.save()
                    
                    # Update item total stock
                    item.uniform_item.current_stock += received_qty
                    item.uniform_item.save()
                
                # Update PO status
                if all_received:
                    po.status = 'RECEIVED'
                    po.actual_delivery_date = get_school_today()
                else:
                    po.status = 'PARTIAL'
                po.save()
            
            messages.success(request, f'Purchase order {po.po_number} received successfully')
            return redirect('uniforms:purchase_order_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error receiving purchase order: {e}")
            messages.error(request, f'Error receiving purchase order: {str(e)}')
            return redirect('uniforms:purchase_order_detail', pk=pk)

# =============================================================================
# UNIFORM SALE VIEWS
# =============================================================================

@login_required
def uniform_sale_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = UniformSaleFilterForm(request.GET or None)
    sales = get_filtered_uniform_sales(request)
    
    # Calculate statistics
    stats = {
        'total': sales.count(),
        'pending': sales.filter(status='PENDING', cancelled=False, returned=False).count(),
        'paid': sales.filter(status='PAID', cancelled=False, returned=False).count(),
        'cancelled': sales.filter(cancelled=True).count(),
        'returned': sales.filter(returned=True).count(),
        'total_revenue': sales.filter(
            cancelled=False, returned=False
        ).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00'),
    }
    
    # Pagination
    paginator = Paginator(sales, 20)
    page_number = request.GET.get('page', 1)
    sales_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'sales_page': sales_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'uniforms/sales/_sale_results.html', context)
    else:
        return render(request, 'uniforms/sales/list.html', context)


@login_required
def uniform_sale_detail(request, pk):
    """View uniform sale details"""
    sale = get_object_or_404(
        UniformSale.objects.select_related(
            'student', 'academic_session', 'fee_invoice', 'journal_entry'
        ).prefetch_related('items__uniform_item', 'items__size'),
        pk=pk
    )
    
    # Get audit trail
    audit_trail = sale.get_audit_trail()
    
    context = {
        'sale': sale,
        'audit_trail': audit_trail,
    }
    
    return render(request, 'uniforms/sales/detail.html', context)


@login_required
def uniform_sale_create(request):
    """Create new uniform sale"""
    student_id = request.GET.get('student')
    student = None
    if student_id:
        student = get_object_or_404(Student, pk=student_id)
    
    if request.method == 'POST':
        form = UniformSaleForm(request.POST, student=student)
        if form.is_valid():
            try:
                with transaction.atomic():
                    sale = form.save(commit=False)
                    # Generate sale number
                    today = get_school_today()
                    year_month = today.strftime('%Y%m')
                    last_sale = UniformSale.objects.filter(
                        sale_number__startswith=f'US-{year_month}'
                    ).order_by('-sale_number').first()
                    
                    if last_sale:
                        try:
                            last_num = int(last_sale.sale_number.split('-')[-1])
                            new_num = last_num + 1
                        except:
                            new_num = 1
                    else:
                        new_num = 1
                    
                    sale.sale_number = f'US-{year_month}-{new_num:05d}'
                    sale.save()
                    form.save_m2m()
                
                messages.success(request, f'Uniform sale {sale.sale_number} created successfully')
                return redirect('uniforms:uniform_sale_detail', pk=sale.pk)
            except Exception as e:
                logger.error(f"Error creating uniform sale: {e}")
                messages.error(request, f'Error creating uniform sale: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = UniformSaleForm(student=student)
    
    context = {
        'form': form,
        'title': 'Create Uniform Sale',
        'submit_text': 'Create',
    }
    
    return render(request, 'uniforms/sales/form.html', context)

@login_required
def uniform_sale_edit(request, pk):
    sale = get_object_or_404(UniformSale, pk=pk)

    if sale.status != 'DRAFT' or sale.cancelled or sale.returned:
        messages.error(request, 'Only draft, active sales can be edited')
        return redirect('uniforms:uniform_sale_detail', pk=pk)

    student = None
    student_id = request.GET.get('student')
    if student_id:
        student = get_object_or_404(Student, pk=student_id)

    if request.method == 'POST':
        form = UniformSaleForm(request.POST, instance=sale, student=student)
        if form.is_valid():
            try:
                form.save()
                messages.success(
                    request,
                    f'Uniform sale {sale.sale_number} updated successfully'
                )
                return redirect('uniforms:uniform_sale_detail', pk=sale.pk)
            except Exception:
                logger.exception("Error updating uniform sale")
                messages.error(request, 'An unexpected error occurred')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = UniformSaleForm(instance=sale, student=student)

    return render(request, 'uniforms/sales/form.html', {
        'form': form,
        'title': 'Update Uniform Sale',
        'submit_text': 'Edit',
    })

@login_required
def uniform_sale_cancel(request, pk):
    """Cancel uniform sale with HTMX support"""
    sale = get_object_or_404(UniformSale, pk=pk)
    
    if request.method == 'POST':
        can_cancel, reason = sale.can_be_cancelled()
        if not can_cancel:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Cannot cancel sale: {reason}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Cannot cancel sale: {reason}')
                return redirect('uniforms:uniform_sale_detail', pk=pk)
        
        try:
            cancellation_reason = request.POST.get('cancellation_reason', '')
            if not cancellation_reason:
                raise ValidationError('Cancellation reason is required')
            
            with transaction.atomic():
                sale.cancelled = True
                sale.cancelled_on = get_school_current_time()
                sale.cancelled_by_id = str(request.user.id)
                sale.cancellation_reason = cancellation_reason
                sale.status = 'CANCELLED'
                sale.save()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Sale {sale.sale_number} cancelled successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('uniforms:uniform_sale_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(request, f'Sale {sale.sale_number} cancelled successfully')
                return redirect('uniforms:uniform_sale_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error cancelling sale: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error cancelling sale: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error cancelling sale: {str(e)}')
                return redirect('uniforms:uniform_sale_detail', pk=pk)


@login_required
def uniform_sale_return(request, pk):
    """Return uniform sale items with HTMX support"""
    sale = get_object_or_404(UniformSale, pk=pk)
    
    if request.method == 'POST':
        can_return, reason = sale.can_be_returned()
        if not can_return:
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Cannot return items: {reason}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Cannot return items: {reason}')
                return redirect('uniforms:uniform_sale_detail', pk=pk)
        
        try:
            return_reason = request.POST.get('return_reason', '')
            return_condition = request.POST.get('return_condition', '')
            
            if not return_reason or not return_condition:
                raise ValidationError('Return reason and condition are required')
            
            with transaction.atomic():
                sale.returned = True
                sale.returned_on = get_school_current_time()
                sale.returned_by_id = str(request.user.id)
                sale.return_reason = return_reason
                sale.return_condition = return_condition
                sale.status = 'RETURNED'
                sale.save()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Sale {sale.sale_number} returned successfully'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('uniforms:uniform_sale_detail', kwargs={'pk': pk})
                return response
            else:
                messages.success(request, f'Sale {sale.sale_number} returned successfully')
                return redirect('uniforms:uniform_sale_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error processing return: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error processing return: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error processing return: {str(e)}')
                return redirect('uniforms:uniform_sale_detail', pk=pk)
            
@login_required
def uniform_sale_delete(request, pk):
    """Delete uniform sale (only if DRAFT)"""
    sale = get_object_or_404(UniformSale, pk=pk)
    
    if request.method == 'POST':
        if sale.status != 'DRAFT':
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = 'Only draft sales can be deleted'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, 'Only draft sales can be deleted')
                return redirect('uniforms:uniform_sale_detail', pk=pk)
        
        try:
            sale_number = sale.sale_number
            sale.delete()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Uniform sale {sale_number} deleted'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('uniforms:uniform_sale_list')
                return response
            else:
                messages.success(request, f'Uniform sale {sale_number} deleted')
                return redirect('uniforms:uniform_sale_list')
                
        except Exception as e:
            logger.error(f"Error deleting uniform sale: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error deleting uniform sale: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error deleting uniform sale: {str(e)}')
                return redirect('uniforms:uniform_sale_detail', pk=pk)


@login_required
def uniform_sale_finalize(request, pk):
    """Finalize draft uniform sale"""
    sale = get_object_or_404(UniformSale, pk=pk)
    
    if request.method == 'POST':
        if sale.status != 'DRAFT':
            messages.error(request, 'Only draft sales can be finalized')
            return redirect('uniforms:uniform_sale_detail', pk=pk)
        
        if not sale.items.exists():
            messages.error(request, 'Cannot finalize sale without items')
            return redirect('uniforms:uniform_sale_detail', pk=pk)
        
        try:
            with transaction.atomic():
                # Calculate totals
                sale.calculate_totals()
                
                # Update status
                if sale.total_amount == 0:
                    sale.status = 'PAID'
                else:
                    sale.status = 'PENDING'
                
                sale.save()
            
            messages.success(request, f'Uniform sale {sale.sale_number} finalized')
            return redirect('uniforms:uniform_sale_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error finalizing uniform sale: {e}")
            messages.error(request, f'Error finalizing uniform sale: {str(e)}')
            return redirect('uniforms:uniform_sale_detail', pk=pk)


@login_required
def uniform_sale_issue(request, pk):
    """Mark uniforms as issued to student"""
    sale = get_object_or_404(UniformSale, pk=pk)
    
    if request.method == 'POST':
        if sale.status not in ['PAID', 'PARTIAL']:
            messages.error(request, 'Sale must be paid/partially paid before issuing items')
            return redirect('uniforms:uniform_sale_detail', pk=pk)
        
        if sale.cancelled or sale.returned:
            messages.error(request, 'Cannot issue cancelled or returned sales')
            return redirect('uniforms:uniform_sale_detail', pk=pk)
        
        try:
            with transaction.atomic():
                # Deduct from stock
                for item in sale.items.all():
                    if item.size:
                        stock = UniformStock.objects.get(
                            uniform_item=item.uniform_item,
                            size=item.size
                        )
                        if stock.available_quantity < item.quantity:
                            raise ValidationError(
                                f'Insufficient stock for {item.uniform_item.name} - Size {item.size.name}'
                            )
                        stock.quantity -= item.quantity
                        stock.save()
                    
                    # Update item stock
                    item.uniform_item.current_stock -= item.quantity
                    item.uniform_item.save()
                
                # Update sale
                sale.status = 'ISSUED'
                sale.issued_by_id = str(request.user.id)
                sale.issued_at = get_school_current_time()
                sale.save()
            
            messages.success(request, f'Uniforms issued to {sale.student.get_full_name()}')
            return redirect('uniforms:uniform_sale_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error issuing uniforms: {e}")
            messages.error(request, f'Error issuing uniforms: {str(e)}')
            return redirect('uniforms:uniform_sale_detail', pk=pk)
            
# =============================================================================
# MEASUREMENT SESSION VIEWS
# =============================================================================

@login_required
def measurement_session_list(request):
    """Handle BOTH full page loads AND HTMX search/filter requests"""
    filter_form = MeasurementSessionFilterForm(request.GET or None)
    sessions = get_filtered_measurement_sessions(request)
    
    # Calculate statistics
    stats = {
        'total': sessions.count(),
        'planned': sessions.filter(status='PLANNED').count(),
        'in_progress': sessions.filter(status='IN_PROGRESS').count(),
        'completed': sessions.filter(status='COMPLETED').count(),
    }
    
    # Pagination
    paginator = Paginator(sessions, 20)
    page_number = request.GET.get('page', 1)
    sessions_page = paginator.get_page(page_number)
    
    # Detect HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'sessions_page': sessions_page,
        'paginator': paginator,
        'stats': stats,
        'filter_form': filter_form,
        'is_htmx': is_htmx,
    }
    
    # Return appropriate template
    if is_htmx:
        return render(request, 'uniforms/measurement_sessions/_session_results.html', context)
    else:
        return render(request, 'uniforms/measurement_sessions/list.html', context)


@login_required
def measurement_session_create(request):
    """Create new measurement session"""
    if request.method == 'POST':
        form = MeasurementSessionForm(request.POST)
        if form.is_valid():
            try:
                session = form.save()
                messages.success(request, f'Measurement session "{session.session_name}" created successfully')
                return redirect('uniforms:measurement_session_list')
            except Exception as e:
                logger.error(f"Error creating measurement session: {e}")
                messages.error(request, f'Error creating measurement session: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = MeasurementSessionForm()
    
    context = {
        'form': form,
        'title': 'Create Measurement Session',
        'submit_text': 'Create',
    }
    
    return render(request, 'uniforms/measurement_sessions/form.html', context)

@login_required
def measurement_session_detail(request, pk):
    """View measurement session details"""
    session = get_object_or_404(
        MeasurementSession.objects.select_related('academic_session'),
        pk=pk
    )
    
    # Get measurements from this session
    measurements = StudentMeasurement.objects.filter(
        measurement_context='UNIFORM_ORDER',
        measurement_date=session.session_date
    ).select_related('student', 'measurement_type')[:50]
    
    coordinator = session.get_coordinator()
    
    context = {
        'session': session,
        'measurements': measurements,
        'coordinator': coordinator,
    }
    
    return render(request, 'uniforms/measurement_sessions/detail.html', context)


@login_required
def measurement_session_edit(request, pk):
    """Edit measurement session (only if PLANNED)"""
    session = get_object_or_404(MeasurementSession, pk=pk)
    
    if session.status not in ['PLANNED']:
        messages.error(request, 'Only planned sessions can be edited')
        return redirect('uniforms:measurement_session_detail', pk=pk)
    
    if request.method == 'POST':
        form = MeasurementSessionForm(request.POST, instance=session)
        if form.is_valid():
            try:
                session = form.save()
                messages.success(request, f'Session "{session.session_name}" updated')
                return redirect('uniforms:measurement_session_detail', pk=session.pk)
            except Exception as e:
                logger.error(f"Error updating session: {e}")
                messages.error(request, f'Error updating session: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = MeasurementSessionForm(instance=session)
    
    context = {
        'form': form,
        'session': session,
        'title': f'Edit {session.session_name}',
        'submit_text': 'Update',
    }
    
    return render(request, 'uniforms/measurement_sessions/form.html', context)


@login_required
def measurement_session_start(request, pk):
    """Start measurement session"""
    session = get_object_or_404(MeasurementSession, pk=pk)
    
    if request.method == 'POST':
        if session.status != 'PLANNED':
            messages.error(request, 'Only planned sessions can be started')
            return redirect('uniforms:measurement_session_detail', pk=pk)
        
        try:
            with transaction.atomic():
                session.status = 'IN_PROGRESS'
                session.coordinator_id = str(request.user.id)
                session.save()
            
            messages.success(request, f'Session "{session.session_name}" started')
            return redirect('uniforms:measurement_session_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error starting session: {e}")
            messages.error(request, f'Error starting session: {str(e)}')
            return redirect('uniforms:measurement_session_detail', pk=pk)


@login_required
def measurement_session_complete(request, pk):
    """Complete measurement session"""
    session = get_object_or_404(MeasurementSession, pk=pk)
    
    if request.method == 'POST':
        if session.status != 'IN_PROGRESS':
            messages.error(request, 'Only in-progress sessions can be completed')
            return redirect('uniforms:measurement_session_detail', pk=pk)
        
        try:
            with transaction.atomic():
                session.status = 'COMPLETED'
                session.save()
            
            messages.success(request, f'Session "{session.session_name}" completed')
            return redirect('uniforms:measurement_session_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error completing session: {e}")
            messages.error(request, f'Error completing session: {str(e)}')
            return redirect('uniforms:measurement_session_detail', pk=pk)
        

# =============================================================================
# STUDENT UNIFORM SIZE VIEWS (MISSING)
# =============================================================================

@login_required
def student_uniform_size_list(request):
    """List student uniform size recommendations"""
    recommendations = StudentUniformSize.objects.select_related(
        'student', 'uniform_item', 'recommended_size', 'academic_session'
    ).order_by('-recommendation_date')
    
    # Apply filters
    query = request.GET.get('q', '').strip()
    if query:
        recommendations = recommendations.filter(
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(uniform_item__name__icontains=query)
        )
    
    student_id = request.GET.get('student')
    if student_id:
        recommendations = recommendations.filter(student_id=student_id)
    
    # Pagination
    paginator = Paginator(recommendations, 20)
    page_number = request.GET.get('page', 1)
    recommendations_page = paginator.get_page(page_number)
    
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    context = {
        'recommendations_page': recommendations_page,
        'paginator': paginator,
        'is_htmx': is_htmx,
    }
    
    if is_htmx:
        return render(request, 'uniforms/student_sizes/_size_results.html', context)
    else:
        return render(request, 'uniforms/student_sizes/list.html', context)


@login_required
def student_uniform_size_create(request):
    """Create student uniform size recommendation"""
    student_id = request.GET.get('student')
    student = None
    if student_id:
        student = get_object_or_404(Student, pk=student_id)
    
    if request.method == 'POST':
        form = StudentUniformSizeForm(request.POST, student=student)
        if form.is_valid():
            try:
                recommendation = form.save()
                messages.success(
                    request,
                    f'Size recommendation created for {recommendation.student.get_full_name()}'
                )
                return redirect('uniforms:student_uniform_size_list')
            except Exception as e:
                logger.error(f"Error creating size recommendation: {e}")
                messages.error(request, f'Error creating size recommendation: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        form = StudentUniformSizeForm(student=student)
    
    context = {
        'form': form,
        'title': 'Create Size Recommendation',
        'submit_text': 'Create',
    }
    
    return render(request, 'uniforms/student_sizes/form.html', context)

# =============================================================================
# REPORT VIEWS (MISSING)
# =============================================================================

@login_required
def inventory_report(request):
    """Inventory status report"""
    items = UniformItem.objects.filter(is_active=True).select_related(
        'unit_of_measure'
    ).order_by('item_type', 'name')
    
    # Calculate statistics
    stats = {
        'total_items': items.count(),
        'total_value': items.aggregate(
            total=Sum(F('current_stock') * F('unit_cost'))
        )['total'] or Decimal('0.00'),
        'low_stock_items': items.filter(current_stock__lte=F('reorder_level')).count(),
        'out_of_stock_items': items.filter(current_stock=0).count(),
    }
    
    context = {
        'items': items,
        'stats': stats,
        'title': 'Inventory Report',
    }
    
    return render(request, 'uniforms/reports/inventory.html', context)


@login_required
def sales_report(request):
    """Uniform sales report"""
    # Date range from filters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    sales = UniformSale.objects.filter(
        cancelled=False,
        returned=False
    ).select_related('student', 'academic_session')
    
    if date_from:
        sales = sales.filter(sale_date__gte=date_from)
    if date_to:
        sales = sales.filter(sale_date__lte=date_to)
    
    # Statistics
    stats = {
        'total_sales': sales.count(),
        'total_revenue': sales.aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00'),
        'total_cost': sales.aggregate(Sum('total_cost'))['total_cost__sum'] or Decimal('0.00'),
        'gross_profit': Decimal('0.00'),
    }
    stats['gross_profit'] = stats['total_revenue'] - stats['total_cost']
    
    context = {
        'sales': sales[:100],  # Limit for display
        'stats': stats,
        'date_from': date_from,
        'date_to': date_to,
        'title': 'Sales Report',
    }
    
    return render(request, 'uniforms/reports/sales.html', context)


@login_required
def low_stock_report(request):
    """Low stock items report"""
    low_stock_items = UniformItem.objects.filter(
        is_active=True,
        current_stock__lte=F('reorder_level')
    ).select_related('unit_of_measure').order_by('current_stock')
    
    context = {
        'items': low_stock_items,
        'title': 'Low Stock Report',
    }
    
    return render(request, 'uniforms/reports/low_stock.html', context)

# =============================================================================
# EXPORT VIEWS
# =============================================================================

@login_required
def export_uniform_items_excel(request):
    """Export uniform items to Excel with filters applied"""
    items = get_filtered_uniform_items(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Uniform Items"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Code', 'Name', 'Type', 'Gender', 'Unit Cost', 'Selling Price',
        'Current Stock', 'Reorder Level', 'Status'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, item in enumerate(items, start=1):
        ws.append([
            idx,
            item.code,
            item.name,
            item.get_item_type_display(),
            item.get_gender_display(),
            float(item.unit_cost),
            float(item.selling_price),
            item.current_stock,
            item.reorder_level,
            'Active' if item.is_active else 'Inactive',
        ])
    
    # Auto-adjust column widths
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width
    
    # Create response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"uniform_items_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
def export_uniform_sales_excel(request):
    """Export uniform sales to Excel with filters applied"""
    sales = get_filtered_uniform_sales(request)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Uniform Sales"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Headers
    headers = [
        '#', 'Sale Number', 'Student', 'Sale Date', 'Total Amount',
        'Paid Amount', 'Balance', 'Status'
    ]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Data rows
    for idx, sale in enumerate(sales, start=1):
        ws.append([
            idx,
            sale.sale_number,
            sale.student.get_full_name(),
            sale.sale_date.strftime('%Y-%m-%d'),
            float(sale.total_amount),
            float(sale.paid_amount),
            float(sale.balance),
            sale.get_status_display(),
        ])
    
    # Auto-adjust column widths
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width
    
    # Create response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"uniform_sales_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response

@login_required
def export_measurements_excel(request):
    """Export measurements to Excel"""
    measurements = get_filtered_student_measurements(request)
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Student Measurements"
    
    # Headers
    headers = [
        '#', 'Student', 'Admission No', 'Measurement Type', 'Value',
        'Unit', 'Date', 'Context', 'Verified'
    ]
    ws.append(headers)
    
    # Data
    for idx, m in enumerate(measurements, start=1):
        ws.append([
            idx,
            m.student.get_full_name(),
            m.student.admission_number,
            m.measurement_type.name,
            float(m.value),
            m.measurement_type.unit.abbreviation,
            m.measurement_date.strftime('%Y-%m-%d'),
            m.get_measurement_context_display(),
            'Yes' if m.is_verified else 'No',
        ])
    
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"measurements_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


# =============================================================================
# MISSING PRINT VIEW FUNCTIONS
# =============================================================================

@login_required
def measurement_type_print_detail(request, pk):
    """Print single measurement type details"""
    measurement_type = get_object_or_404(MeasurementType, pk=pk)
    
    # Get statistics
    measurement_count = measurement_type.student_measurements.count()
    verified_count = measurement_type.student_measurements.filter(is_verified=True).count()
    avg_value = measurement_type.student_measurements.filter(
        is_current=True
    ).aggregate(Avg('value'))['value__avg']
    
    context = {
        'measurement_type': measurement_type,
        'measurement_count': measurement_count,
        'verified_count': verified_count,
        'avg_value': avg_value,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'uniforms/measurement_types/print_detail.html', context)


@login_required
def measurement_type_print_view(request):
    """Print list of measurement types"""
    measurement_types = get_filtered_measurement_types(request)
    
    context = {
        'measurement_types': measurement_types,
        'print_date': get_school_current_time(),
        'filters_applied': bool(request.GET),
    }
    
    return render(request, 'uniforms/measurement_types/print_list.html', context)


@login_required
def export_measurement_types_excel(request):
    """Export measurement types to Excel"""
    measurement_types = get_filtered_measurement_types(request)
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Measurement Types"
    
    # Headers
    headers = [
        '#', 'Code', 'Name', 'Category', 'Unit', 'Min Value', 'Max Value',
        'Required', 'Active', 'Display Order'
    ]
    ws.append(headers)
    
    # Style header
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # Data
    for idx, mt in enumerate(measurement_types, start=1):
        ws.append([
            idx,
            mt.code,
            mt.name,
            mt.get_category_display(),
            mt.unit.abbreviation,
            float(mt.min_value) if mt.min_value else '',
            float(mt.max_value) if mt.max_value else '',
            'Yes' if mt.is_required else 'No',
            'Yes' if mt.is_active else 'No',
            mt.display_order,
        ])
    
    # Auto-adjust columns
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        ws.column_dimensions[column_letter].width = min(max_length + 2, 50)
    
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"measurement_types_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
def student_measurement_print_detail(request, pk):
    """Print single student measurement details"""
    measurement = get_object_or_404(
        StudentMeasurement.objects.select_related(
            'student', 'measurement_type', 'academic_session'
        ),
        pk=pk
    )
    
    # Get other measurements for this student and type
    other_measurements = StudentMeasurement.objects.filter(
        student=measurement.student,
        measurement_type=measurement.measurement_type
    ).exclude(pk=pk).order_by('-measurement_date')[:10]
    
    context = {
        'measurement': measurement,
        'other_measurements': other_measurements,
        'verified_by': measurement.get_verified_by_user(),
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'uniforms/measurements/print_detail.html', context)


@login_required
def student_measurements_print_view(request):
    """Print list of student measurements"""
    measurements = get_filtered_student_measurements(request)[:100]  # Limit for printing
    
    context = {
        'measurements': measurements,
        'print_date': get_school_current_time(),
        'filters_applied': bool(request.GET),
    }
    
    return render(request, 'uniforms/measurements/print_list.html', context)


@login_required
def uniform_size_print_detail(request, pk):
    """Print single uniform size details"""
    size = get_object_or_404(UniformSize, pk=pk)
    
    # Get items using this size
    items = size.uniform_items.filter(is_active=True).order_by('name')
    
    # Get stock records
    stock_records = size.stock_records.select_related('uniform_item').order_by('uniform_item__name')
    
    context = {
        'size': size,
        'items': items,
        'stock_records': stock_records,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'uniforms/sizes/print_detail.html', context)


@login_required
def uniform_sizes_print_view(request):
    """Print list of uniform sizes"""
    sizes = get_filtered_uniform_sizes(request)
    
    context = {
        'sizes': sizes,
        'print_date': get_school_current_time(),
        'filters_applied': bool(request.GET),
    }
    
    return render(request, 'uniforms/sizes/print_list.html', context)


@login_required
def export_uniform_sizes_excel(request):
    """Export uniform sizes to Excel"""
    sizes = get_filtered_uniform_sizes(request)
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Uniform Sizes"
    
    headers = [
        '#', 'Code', 'Name', 'Type', 'Min Height', 'Max Height',
        'Min Chest', 'Max Chest', 'Min Age', 'Max Age', 'Active'
    ]
    ws.append(headers)
    
    # Style header
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # Data
    for idx, size in enumerate(sizes, start=1):
        ws.append([
            idx,
            size.code,
            size.name,
            size.get_size_type_display(),
            float(size.min_height) if size.min_height else '',
            float(size.max_height) if size.max_height else '',
            float(size.min_chest) if size.min_chest else '',
            float(size.max_chest) if size.max_chest else '',
            size.min_age or '',
            size.max_age or '',
            'Yes' if size.is_active else 'No',
        ])
    
    # Auto-adjust columns
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        ws.column_dimensions[column_letter].width = min(max_length + 2, 50)
    
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"uniform_sizes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
def uniform_item_print_detail(request, pk):
    """Print single uniform item details"""
    item = get_object_or_404(UniformItem, pk=pk)
    
    # Get stock records
    stock_records = item.stock_records.select_related('size').order_by('size__display_order')
    
    # Get recent sales
    recent_sales = item.sale_items.select_related(
        'sale__student', 'size'
    ).order_by('-sale__sale_date')[:10]
    
    context = {
        'item': item,
        'stock_records': stock_records,
        'recent_sales': recent_sales,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'uniforms/items/print_detail.html', context)


@login_required
def uniform_items_print_view(request):
    """Print list of uniform items"""
    items = get_filtered_uniform_items(request)[:100]  # Limit for printing
    
    context = {
        'items': items,
        'print_date': get_school_current_time(),
        'filters_applied': bool(request.GET),
    }
    
    return render(request, 'uniforms/items/print_list.html', context)


@login_required
def uniform_stock_print_detail(request, pk):
    """Print single stock record details"""
    stock = get_object_or_404(
        UniformStock.objects.select_related('uniform_item', 'size'),
        pk=pk
    )
    
    context = {
        'stock': stock,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'uniforms/stock/print_detail.html', context)


@login_required
def uniform_stock_print_view(request):
    """Print list of stock records"""
    stock_records = UniformStock.objects.select_related(
        'uniform_item', 'size'
    ).order_by('uniform_item__name', 'size__display_order')[:100]
    
    context = {
        'stock_records': stock_records,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'uniforms/stock/print_list.html', context)


@login_required
def export_uniform_stock_excel(request):
    """Export stock records to Excel"""
    stock_records = UniformStock.objects.select_related(
        'uniform_item', 'size'
    ).order_by('uniform_item__name', 'size__display_order')
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Uniform Stock"
    
    headers = [
        '#', 'Item Code', 'Item Name', 'Size', 'Quantity', 'Reserved',
        'Available', 'Location', 'Cost Value', 'Selling Value'
    ]
    ws.append(headers)
    
    # Style header
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # Data
    for idx, stock in enumerate(stock_records, start=1):
        ws.append([
            idx,
            stock.uniform_item.code,
            stock.uniform_item.name,
            stock.size.name,
            stock.quantity,
            stock.reserved_quantity,
            stock.available_quantity,
            stock.location or '',
            float(stock.total_cost_value),
            float(stock.total_selling_value),
        ])
    
    # Auto-adjust columns
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        ws.column_dimensions[column_letter].width = min(max_length + 2, 50)
    
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"uniform_stock_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
def purchase_order_print_detail(request, pk):
    """Print purchase order details"""
    po = get_object_or_404(
        UniformPurchaseOrder.objects.select_related('fiscal_period'),
        pk=pk
    )
    
    items = po.items.select_related('uniform_item', 'size')
    
    context = {
        'po': po,
        'items': items,
        'approved_by': po.get_approved_by_user(),
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'uniforms/purchase_orders/print_detail.html', context)


@login_required
def purchase_orders_print_view(request):
    """Print list of purchase orders"""
    orders = get_filtered_purchase_orders(request)[:50]  # Limit for printing
    
    context = {
        'orders': orders,
        'print_date': get_school_current_time(),
        'filters_applied': bool(request.GET),
    }
    
    return render(request, 'uniforms/purchase_orders/print_list.html', context)


@login_required
def export_purchase_orders_excel(request):
    """Export purchase orders to Excel"""
    orders = get_filtered_purchase_orders(request)
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Purchase Orders"
    
    headers = [
        '#', 'PO Number', 'Supplier', 'Order Date', 'Expected Delivery',
        'Status', 'Subtotal', 'Tax', 'Total', 'Paid', 'Balance'
    ]
    ws.append(headers)
    
    # Style header
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # Data
    for idx, po in enumerate(orders, start=1):
        ws.append([
            idx,
            po.po_number,
            po.supplier_name,
            po.order_date.strftime('%Y-%m-%d'),
            po.expected_delivery_date.strftime('%Y-%m-%d') if po.expected_delivery_date else '',
            po.get_status_display(),
            float(po.subtotal),
            float(po.tax_amount),
            float(po.total_amount),
            float(po.paid_amount),
            float(po.balance_due),
        ])
    
    # Auto-adjust columns
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        ws.column_dimensions[column_letter].width = min(max_length + 2, 50)
    
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"purchase_orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
def purchase_order_cancel(request, pk):
    """Cancel purchase order"""
    po = get_object_or_404(UniformPurchaseOrder, pk=pk)
    
    if request.method == 'POST':
        if po.status in ['RECEIVED', 'CANCELLED']:
            messages.error(request, f'Cannot cancel purchase order in {po.get_status_display()} status')
            return redirect('uniforms:purchase_order_detail', pk=pk)
        
        try:
            with transaction.atomic():
                po.status = 'CANCELLED'
                po.save()
            
            messages.success(request, f'Purchase order {po.po_number} cancelled')
            return redirect('uniforms:purchase_order_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error cancelling purchase order: {e}")
            messages.error(request, f'Error cancelling purchase order: {str(e)}')
            return redirect('uniforms:purchase_order_detail', pk=pk)


@login_required
def uniform_sale_print_detail(request, pk):
    """Print uniform sale details"""
    sale = get_object_or_404(
        UniformSale.objects.select_related('student', 'academic_session'),
        pk=pk
    )
    
    items = sale.items.select_related('uniform_item', 'size')
    
    context = {
        'sale': sale,
        'items': items,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'uniforms/sales/print_detail.html', context)


@login_required
def uniform_sale_print_invoice(request, pk):
    """Print uniform sale invoice"""
    sale = get_object_or_404(
        UniformSale.objects.select_related('student', 'academic_session'),
        pk=pk
    )
    
    items = sale.items.select_related('uniform_item', 'size')
    
    context = {
        'sale': sale,
        'items': items,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'uniforms/sales/print_invoice.html', context)


@login_required
def uniform_sales_print_view(request):
    """Print list of uniform sales"""
    sales = get_filtered_uniform_sales(request)[:50]  # Limit for printing
    
    context = {
        'sales': sales,
        'print_date': get_school_current_time(),
        'filters_applied': bool(request.GET),
    }
    
    return render(request, 'uniforms/sales/print_list.html', context)


@login_required
def student_uniform_size_detail(request, pk):
    """View student uniform size recommendation details"""
    size_rec = get_object_or_404(
        StudentUniformSize.objects.select_related(
            'student', 'uniform_item', 'recommended_size', 'academic_session'
        ),
        pk=pk
    )
    
    # Get other recommendations for this student
    other_recommendations = StudentUniformSize.objects.filter(
        student=size_rec.student
    ).exclude(pk=pk).select_related('uniform_item', 'recommended_size').order_by('-recommendation_date')[:10]
    
    context = {
        'size_rec': size_rec,
        'other_recommendations': other_recommendations,
    }
    
    return render(request, 'uniforms/student_sizes/detail.html', context)


@login_required
def student_uniform_size_edit(request, pk):
    """Edit student uniform size recommendation"""
    size_rec = get_object_or_404(StudentUniformSize, pk=pk)
    
    if request.method == 'POST':
        from .forms import StudentUniformSizeForm
        form = StudentUniformSizeForm(request.POST, instance=size_rec)
        if form.is_valid():
            try:
                size_rec = form.save()
                messages.success(request, 'Size recommendation updated successfully')
                return redirect('uniforms:student_uniform_size_detail', pk=size_rec.pk)
            except Exception as e:
                logger.error(f"Error updating size recommendation: {e}")
                messages.error(request, f'Error updating size recommendation: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below')
    else:
        from .forms import StudentUniformSizeForm
        form = StudentUniformSizeForm(instance=size_rec)
    
    context = {
        'form': form,
        'size_rec': size_rec,
        'title': 'Edit Size Recommendation',
        'submit_text': 'Update',
    }
    
    return render(request, 'uniforms/student_sizes/form.html', context)


@login_required
def student_uniform_size_delete(request, pk):
    """Delete student uniform size recommendation"""
    size_rec = get_object_or_404(StudentUniformSize, pk=pk)
    
    if request.method == 'POST':
        try:
            student_name = size_rec.student.get_full_name()
            item_name = size_rec.uniform_item.name
            size_rec.delete()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Size recommendation deleted for {student_name}'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('uniforms:student_uniform_size_list')
                return response
            else:
                messages.success(request, f'Size recommendation deleted for {student_name}')
                return redirect('uniforms:student_uniform_size_list')
                
        except Exception as e:
            logger.error(f"Error deleting size recommendation: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error deleting size recommendation: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error deleting size recommendation: {str(e)}')
                return redirect('uniforms:student_uniform_size_detail', pk=pk)


@login_required
def bulk_size_recommendation(request):
    """Bulk size recommendation for students"""
    # This would be implemented based on your specific requirements
    messages.info(request, 'Bulk size recommendation feature coming soon')
    return redirect('uniforms:student_uniform_size_list')


@login_required
def student_uniform_size_print_detail(request, pk):
    """Print student uniform size recommendation"""
    size_rec = get_object_or_404(
        StudentUniformSize.objects.select_related(
            'student', 'uniform_item', 'recommended_size'
        ),
        pk=pk
    )
    
    context = {
        'size_rec': size_rec,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'uniforms/student_sizes/print_detail.html', context)


@login_required
def student_uniform_sizes_print_view(request):
    """Print list of student uniform size recommendations"""
    recommendations = StudentUniformSize.objects.select_related(
        'student', 'uniform_item', 'recommended_size'
    ).order_by('-recommendation_date')[:100]
    
    context = {
        'recommendations': recommendations,
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'uniforms/student_sizes/print_list.html', context)


@login_required
def export_student_uniform_sizes_excel(request):
    """Export student uniform sizes to Excel"""
    recommendations = StudentUniformSize.objects.select_related(
        'student', 'uniform_item', 'recommended_size', 'academic_session'
    ).order_by('-recommendation_date')
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Student Uniform Sizes"
    
    headers = [
        '#', 'Student', 'Admission No', 'Item', 'Recommended Size',
        'Sizing Method', 'Confidence', 'Date', 'Session', 'Current'
    ]
    ws.append(headers)
    
    # Style header
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # Data
    for idx, rec in enumerate(recommendations, start=1):
        ws.append([
            idx,
            rec.student.get_full_name(),
            rec.student.admission_number,
            rec.uniform_item.name,
            rec.recommended_size.name,
            rec.get_sizing_method_display(),
            rec.get_confidence_level_display(),
            rec.recommendation_date.strftime('%Y-%m-%d'),
            rec.academic_session.session_name,
            'Yes' if rec.is_current else 'No',
        ])
    
    # Auto-adjust columns
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        ws.column_dimensions[column_letter].width = min(max_length + 2, 50)
    
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"student_uniform_sizes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
def measurement_session_delete(request, pk):
    """Delete measurement session"""
    session = get_object_or_404(MeasurementSession, pk=pk)
    
    if request.method == 'POST':
        try:
            session_name = session.session_name
            session.delete()
            
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Measurement session "{session_name}" deleted'
                response['HX-Alert-Type'] = 'success'
                response['HX-Close-Modal'] = 'true'
                response['HX-Redirect'] = reverse('uniforms:measurement_session_list')
                return response
            else:
                messages.success(request, f'Measurement session "{session_name}" deleted')
                return redirect('uniforms:measurement_session_list')
                
        except Exception as e:
            logger.error(f"Error deleting measurement session: {e}")
            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx:
                response = HttpResponse()
                response['HX-Alert-Message'] = f'Error deleting measurement session: {str(e)}'
                response['HX-Alert-Type'] = 'error'
                response['HX-Close-Modal'] = 'true'
                return response
            else:
                messages.error(request, f'Error deleting measurement session: {str(e)}')
                return redirect('uniforms:measurement_session_detail', pk=pk)


@login_required
def measurement_session_cancel(request, pk):
    """Cancel measurement session"""
    session = get_object_or_404(MeasurementSession, pk=pk)
    
    if request.method == 'POST':
        if session.status == 'COMPLETED':
            messages.error(request, 'Cannot cancel completed session')
            return redirect('uniforms:measurement_session_detail', pk=pk)
        
        try:
            with transaction.atomic():
                session.status = 'CANCELLED'
                session.save()
            
            messages.success(request, f'Session "{session.session_name}" cancelled')
            return redirect('uniforms:measurement_session_detail', pk=pk)
                
        except Exception as e:
            logger.error(f"Error cancelling session: {e}")
            messages.error(request, f'Error cancelling session: {str(e)}')
            return redirect('uniforms:measurement_session_detail', pk=pk)


@login_required
def measurement_session_print_detail(request, pk):
    """Print measurement session details"""
    session = get_object_or_404(
        MeasurementSession.objects.select_related('academic_session'),
        pk=pk
    )
    
    # Get measurements from this session
    measurements = StudentMeasurement.objects.filter(
        measurement_context='UNIFORM_ORDER',
        measurement_date=session.session_date
    ).select_related('student', 'measurement_type')[:100]
    
    context = {
        'session': session,
        'measurements': measurements,
        'coordinator': session.get_coordinator(),
        'print_date': get_school_current_time(),
    }
    
    return render(request, 'uniforms/measurement_sessions/print_detail.html', context)


@login_required
def measurement_sessions_print_view(request):
    """Print list of measurement sessions"""
    sessions = get_filtered_measurement_sessions(request)[:50]
    
    context = {
        'sessions': sessions,
        'print_date': get_school_current_time(),
        'filters_applied': bool(request.GET),
    }
    
    return render(request, 'uniforms/measurement_sessions/print_list.html', context)


@login_required
def export_measurement_sessions_excel(request):
    """Export measurement sessions to Excel"""
    sessions = get_filtered_measurement_sessions(request)
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Measurement Sessions"
    
    headers = [
        '#', 'Session Name', 'Type', 'Date', 'Status', 'Academic Session',
        'Students Measured', 'Total Measurements'
    ]
    ws.append(headers)
    
    # Style header
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # Data
    for idx, session in enumerate(sessions, start=1):
        ws.append([
            idx,
            session.session_name,
            session.get_session_type_display(),
            session.session_date.strftime('%Y-%m-%d'),
            session.get_status_display(),
            session.academic_session.session_name,
            session.total_students_measured,
            session.total_measurements_taken,
        ])
    
    # Auto-adjust columns
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        ws.column_dimensions[column_letter].width = min(max_length + 2, 50)
    
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"measurement_sessions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
def measurement_summary_report(request):
    """Measurement summary report"""
    # Get filters
    academic_session_id = request.GET.get('academic_session')
    class_id = request.GET.get('class')
    
    measurements = StudentMeasurement.objects.select_related(
        'student', 'measurement_type', 'academic_session'
    ).filter(is_current=True)
    
    if academic_session_id:
        measurements = measurements.filter(academic_session_id=academic_session_id)
    if class_id:
        measurements = measurements.filter(student__current_class_id=class_id)
    
    # Group by measurement type
    from collections import defaultdict
    by_type = defaultdict(list)
    
    for m in measurements:
        by_type[m.measurement_type].append(m)
    
    # Calculate statistics
    stats = []
    for mt, measures in by_type.items():
        values = [float(m.value) for m in measures]
        stats.append({
            'type': mt,
            'count': len(values),
            'average': sum(values) / len(values) if values else 0,
            'min': min(values) if values else 0,
            'max': max(values) if values else 0,
        })
    
    context = {
        'stats': stats,
        'total_students': measurements.values('student').distinct().count(),
        'filters_applied': bool(request.GET),
    }
    
    return render(request, 'uniforms/reports/measurement_summary.html', context)


@login_required
def student_orders_report(request):
    """Student orders report"""
    # Get filters
    academic_session_id = request.GET.get('academic_session')
    class_id = request.GET.get('class')
    
    sales = UniformSale.objects.select_related(
        'student', 'academic_session'
    ).filter(cancelled=False, returned=False)
    
    if academic_session_id:
        sales = sales.filter(academic_session_id=academic_session_id)
    if class_id:
        sales = sales.filter(student__current_class_id=class_id)
    
    # Group by student
    from collections import defaultdict
    by_student = defaultdict(list)
    
    for sale in sales:
        by_student[sale.student].append(sale)
    
    # Calculate totals
    student_totals = []
    for student, student_sales in by_student.items():
        total = sum(s.total_amount for s in student_sales)
        paid = sum(s.paid_amount for s in student_sales)
        student_totals.append({
            'student': student,
            'total_sales': len(student_sales),
            'total_amount': total,
            'paid_amount': paid,
            'balance': total - paid,
        })
    
    # Sort by total amount
    student_totals.sort(key=lambda x: x['total_amount'], reverse=True)
    
    context = {
        'student_totals': student_totals[:100],  # Limit for display
        'filters_applied': bool(request.GET),
    }
    
    return render(request, 'uniforms/reports/student_orders.html', context)


# =============================================================================
# BULK OPERATION PLACEHOLDER
# =============================================================================

@login_required
def student_measurement_bulk_entry(request):
    """Bulk measurement entry interface"""
    messages.info(request, 'Bulk measurement entry feature coming soon')
    return redirect('uniforms:student_measurement_list')


# =============================================================================
# AJAX ENDPOINTS
# =============================================================================

@login_required
def ajax_get_item_sizes(request, item_pk):
    """Get available sizes for an item"""
    try:
        item = UniformItem.objects.get(pk=item_pk)
        sizes = item.available_sizes.filter(is_active=True).order_by('display_order')
        
        data = [
            {'id': size.id, 'name': size.name, 'code': size.code}
            for size in sizes
        ]
        
        return JsonResponse({'success': True, 'sizes': data})
    except UniformItem.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Item not found'}, status=404)
    except Exception as e:
        logger.error(f"Error getting item sizes: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def ajax_get_item_price(request, item_pk):
    """Get item pricing"""
    try:
        item = UniformItem.objects.get(pk=item_pk)
        
        data = {
            'unit_cost': float(item.unit_cost),
            'selling_price': float(item.selling_price),
            'is_taxable': item.is_taxable,
            'tax_rate_id': item.tax_rate_id if item.tax_rate else None,
        }
        
        return JsonResponse({'success': True, 'data': data})
    except UniformItem.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Item not found'}, status=404)
    except Exception as e:
        logger.error(f"Error getting item price: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def ajax_get_stock_quantity(request, item_pk, size_pk):
    """Get stock quantity for item and size"""
    try:
        stock = UniformStock.objects.get(uniform_item_id=item_pk, size_id=size_pk)
        
        data = {
            'quantity': stock.quantity,
            'reserved': stock.reserved_quantity,
            'available': stock.available_quantity,
        }
        
        return JsonResponse({'success': True, 'data': data})
    except UniformStock.DoesNotExist:
        return JsonResponse({'success': True, 'data': {'quantity': 0, 'reserved': 0, 'available': 0}})
    except Exception as e:
        logger.error(f"Error getting stock quantity: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def ajax_get_student_measurements(request, student_pk):
    """Get student measurements"""
    try:
        measurements = StudentMeasurement.objects.filter(
            student_id=student_pk,
            is_current=True
        ).select_related('measurement_type')
        
        data = [
            {
                'type_id': m.measurement_type_id,
                'type_name': m.measurement_type.name,
                'value': float(m.value),
                'unit': m.measurement_type.unit.abbreviation,
            }
            for m in measurements
        ]
        
        return JsonResponse({'success': True, 'measurements': data})
    except Exception as e:
        logger.error(f"Error getting student measurements: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def ajax_get_size_recommendation(request, student_pk, item_pk):
    """Get size recommendation for student and item"""
    try:
        recommendation = StudentUniformSize.objects.filter(
            student_id=student_pk,
            uniform_item_id=item_pk,
            is_current=True
        ).select_related('recommended_size').first()
        
        if recommendation:
            data = {
                'size_id': recommendation.recommended_size_id,
                'size_name': recommendation.recommended_size.name,
                'confidence': recommendation.confidence_level,
            }
            return JsonResponse({'success': True, 'data': data})
        else:
            return JsonResponse({'success': False, 'error': 'No recommendation found'})
    except Exception as e:
        logger.error(f"Error getting size recommendation: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def ajax_check_po_number(request):
    """Check if PO number exists"""
    po_number = request.GET.get('po_number', '').strip()
    exclude_id = request.GET.get('exclude_id')
    
    if not po_number:
        return JsonResponse({'exists': False})
    
    qs = UniformPurchaseOrder.objects.filter(po_number=po_number)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    
    return JsonResponse({'exists': qs.exists()})


@login_required
def ajax_calculate_sale_total(request):
    """Calculate sale total from items"""
    try:
        items = request.POST.getlist('items[]')  # List of item data as JSON
        # This would parse the items and calculate totals
        # Implementation depends on how you structure your sale item forms
        
        return JsonResponse({'success': True, 'total': 0})  # Placeholder
    except Exception as e:
        logger.error(f"Error calculating sale total: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
        

