# fees/invoice_generators.py

"""
Centralized invoice generation for all enrollment types.
PERMISSIVE - Uses what's available, skips what's not found.
"""

from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
import logging

from fees.models import FeeInvoice, FeeInvoiceItem, FeesCategory, FeesStructure
from fees.utils import generate_invoice_number
from core.models import FinancialSettings, FiscalPeriod

logger = logging.getLogger(__name__)


# =============================================================================
# CUSTOM EXCEPTIONS
# =============================================================================

class FeeStructureNotFoundError(ValueError):
    """Raised when required fee structure is not found"""
    pass


# =============================================================================
# CLASS ENROLLMENT INVOICE GENERATOR
# =============================================================================

class ClassEnrollmentInvoiceGenerator:
    """Generate invoices for class enrollment (academic fees)"""
    
    @staticmethod
    def generate(class_enrollment, **kwargs):
        """
        Generate invoice for class enrollment.
        
        Args:
            class_enrollment: StudentClassEnrollment instance
            **kwargs: Additional options
                - custom_due_date: Override due date
                - include_optional: Include optional fees
                - discount_amount: Apply discount
                
        Returns:
            FeeInvoice instance
            
        Raises:
            FeeStructureNotFoundError: If no fee structure exists
        """
        student = class_enrollment.student
        session = class_enrollment.academic_session
        class_instance = class_enrollment.class_instance
        
        # Get fee structure - MUST exist for academic fees
        fee_structures = FeesStructure.objects.filter(
            applicable_sessions=session,
            academic_levels=class_instance.academic_level,
            is_active=True
        )
        
        if not fee_structures.exists():
            raise FeeStructureNotFoundError(
                f"No active fee structure found for {class_instance.academic_level} "
                f"in {session.name}. Please create a fee structure in Admin → Fees → Fee Structures."
            )
        
        # Get settings
        settings = FinancialSettings.get_instance()
        
        # Calculate due date
        due_date = kwargs.get('custom_due_date') or (
            timezone.now().date() + timedelta(days=settings.default_payment_terms_days)
        )
        
        # Get fiscal period
        fiscal_period = FiscalPeriod.get_current_fiscal_period()
        if not fiscal_period:
            raise ValueError(
                "No active fiscal period found. "
                "Please create a fiscal period in Admin → Core → Fiscal Periods."
            )
        
        # Generate invoice number
        invoice_number = generate_invoice_number()
        
        # Create invoice
        invoice = FeeInvoice.objects.create(
            invoice_number=invoice_number,
            student=student,
            academic_session=session,
            fiscal_period=fiscal_period,
            issue_date=timezone.now().date(),
            due_date=due_date,
            status='PENDING',
            notes=f"Academic fees for {class_instance.get_display_name()}",
            revenue_account=settings.default_service_revenue_account,
            receivable_account=settings.default_receivables_account,
        )
        
        # Add items from fee structures
        include_optional = kwargs.get('include_optional', False)
        items_added = 0
        
        for fee_structure in fee_structures:
            for fee_item in fee_structure.items.filter(is_active=True):
                # Skip optional fees if not requested
                if not include_optional and not fee_item.fee_category.is_mandatory:
                    continue
                
                FeeInvoiceItem.objects.create(
                    invoice=invoice,
                    fee_category=fee_item.fee_category,
                    description=fee_item.description or fee_item.fee_category.name,
                    quantity=Decimal('1.00'),
                    unit_amount=fee_item.amount,
                    amount=fee_item.amount,
                    tax_percentage=(
                        fee_item.fee_category.default_tax_rate 
                        if fee_item.fee_category.is_taxable 
                        else Decimal('0.00')
                    ),
                )
                items_added += 1
        
        if items_added == 0:
            # Delete the empty invoice
            invoice.delete()
            raise FeeStructureNotFoundError(
                f"Fee structure exists but contains no items for {class_instance.academic_level} "
                f"in {session.name}. Please add fee items to the structure."
            )
        
        # Recalculate invoice totals
        invoice.calculate_totals()
        
        # Apply discount if provided
        discount_amount = kwargs.get('discount_amount')
        if discount_amount:
            invoice.discount_amount = Decimal(str(discount_amount))
            invoice.save()
        
        logger.info(
            f"Generated class enrollment invoice {invoice.invoice_number} "
            f"for {student.get_full_name()} with {items_added} items"
        )
        
        return invoice


# =============================================================================
# BOARDING ENROLLMENT INVOICE GENERATOR (PERMISSIVE)
# =============================================================================

class BoardingEnrollmentInvoiceGenerator:
    """Generate invoices for boarding enrollment - PERMISSIVE MODE"""
    
    @staticmethod
    def generate(boarding_enrollment, **kwargs):
        """
        Generate invoice for boarding enrollment.
        
        Uses whatever fee items are found in the applicable fee structure.
        If no boarding-specific items found, creates invoice with whatever is there.
        If no fee structure at all, raises error.
        
        Args:
            boarding_enrollment: BoardingEnrollment instance
            **kwargs: Additional options
                - custom_due_date: Override due date
                - include_meals: Include meal fees (default: True)
                - include_laundry: Include laundry fees (default: False)
                
        Returns:
            FeeInvoice instance
            
        Raises:
            FeeStructureNotFoundError: If no fee structure exists at all
        """
        student = boarding_enrollment.student
        session = boarding_enrollment.academic_session
        settings = FinancialSettings.get_instance()
        
        # =================================================================
        # STEP 1: FIND APPLICABLE FEE STRUCTURE
        # =================================================================
        fee_structures = FeesStructure.objects.filter(
            applicable_sessions=session,
            boarding_type_filter__in=[
                boarding_enrollment.boarding_type,
                'BOARDER_ONLY',
                'ALL'
            ],
            is_active=True
        ).order_by('priority')
        
        if not fee_structures.exists():
            raise FeeStructureNotFoundError(
                f"No boarding fee structure found for {boarding_enrollment.get_boarding_type_display()} "
                f"in {session.name}.\n\n"
                f"Please create a fee structure in Admin → Fees → Fee Structures with:\n"
                f"- Applicable Sessions: {session.name}\n"
                f"- Boarding Type Filter: {boarding_enrollment.boarding_type} or BOARDER_ONLY or ALL\n"
                f"- Add fee items (boarding, meals, laundry, etc.)"
            )
        
        # =================================================================
        # STEP 2: CREATE INVOICE
        # =================================================================
        due_date = kwargs.get('custom_due_date') or (
            timezone.now().date() + timedelta(days=settings.default_payment_terms_days)
        )
        
        fiscal_period = FiscalPeriod.get_current_fiscal_period()
        if not fiscal_period:
            raise ValueError(
                "No active fiscal period found. "
                "Please create a fiscal period in Admin → Core → Fiscal Periods."
            )
        
        invoice_number = generate_invoice_number()
        
        invoice = FeeInvoice.objects.create(
            invoice_number=invoice_number,
            student=student,
            academic_session=session,
            fiscal_period=fiscal_period,
            issue_date=timezone.now().date(),
            due_date=due_date,
            status='PENDING',
            notes=f"Boarding fees for {boarding_enrollment.get_boarding_type_display()}",
            revenue_account=settings.boarding_revenue_account or settings.default_service_revenue_account,
            receivable_account=settings.default_receivables_account,
        )
        
        # =================================================================
        # STEP 3: ADD ALL ITEMS FROM FEE STRUCTURES
        # =================================================================
        items_added = 0
        include_optional = kwargs.get('include_optional', True)  # Default True for boarding
        
        for fee_structure in fee_structures:
            for fee_item in fee_structure.items.filter(is_active=True):
                
                # Skip optional fees if not requested
                if not include_optional and not fee_item.fee_category.is_mandatory:
                    continue
                
                # ✅ Simple filtering logic (optional - you can remove this)
                # Skip meals if not requested
                if not kwargs.get('include_meals', True):
                    if any(word in fee_item.fee_category.name.lower() 
                           for word in ['meal', 'food', 'catering', 'lunch', 'breakfast', 'dinner']):
                        logger.info(f"Skipping meals item: {fee_item.fee_category.name}")
                        continue
                
                # Skip laundry if not requested
                if not kwargs.get('include_laundry', False):
                    if any(word in fee_item.fee_category.name.lower() 
                           for word in ['laundry', 'washing', 'cleaning']):
                        logger.info(f"Skipping laundry item: {fee_item.fee_category.name}")
                        continue
                
                # Add the item
                FeeInvoiceItem.objects.create(
                    invoice=invoice,
                    fee_category=fee_item.fee_category,
                    description=fee_item.description or fee_item.fee_category.name,
                    quantity=Decimal('1.00'),
                    unit_amount=fee_item.amount,
                    amount=fee_item.amount,
                    tax_percentage=(
                        fee_item.fee_category.default_tax_rate 
                        if fee_item.fee_category.is_taxable 
                        else Decimal('0.00')
                    ),
                )
                items_added += 1
                logger.info(f"Added boarding item: {fee_item.fee_category.name} - {fee_item.amount}")
        
        # =================================================================
        # STEP 4: VALIDATE AT LEAST ONE ITEM WAS ADDED
        # =================================================================
        if items_added == 0:
            # Delete the empty invoice
            invoice.delete()
            raise FeeStructureNotFoundError(
                f"Boarding fee structure exists but contains no items.\n\n"
                f"Please add fee items to the structure for {session.name}:\n"
                f"- Boarding accommodation fees\n"
                f"- Meals fees (optional)\n"
                f"- Laundry fees (optional)\n"
                f"- Any other boarding-related fees"
            )
        
        # Recalculate invoice totals
        invoice.calculate_totals()
        
        logger.info(
            f"Generated boarding invoice {invoice.invoice_number} "
            f"for {student.get_full_name()} with {items_added} items"
        )
        
        return invoice


# =============================================================================
# UNIFORM SALE INVOICE GENERATOR
# =============================================================================

class UniformSaleInvoiceGenerator:
    """
    Generate invoices for uniform sales.
    
    Note: This delegates to uniforms.services.UniformInvoiceService
    since uniform sales have complex inventory/COGS logic.
    """
    
    @staticmethod
    def generate(uniform_sale, **kwargs):
        """
        Generate invoice for uniform sale.
        
        Args:
            uniform_sale: UniformSale instance
            **kwargs: Additional options
            
        Returns:
            FeeInvoice instance
        """
        # Delegate to uniform-specific service
        from uniforms.services import UniformInvoiceService
        
        invoice = UniformInvoiceService.create_invoice_from_sale(uniform_sale)
        
        logger.info(
            f"Generated uniform invoice {invoice.invoice_number} "
            f"for sale {uniform_sale.sale_number}"
        )
        
        return invoice


# =============================================================================
# CONVENIENCE FUNCTION - SINGLE ENTRY POINT
# =============================================================================

def generate_enrollment_invoice(enrollment, enrollment_type, **kwargs):
    """
    Unified function to generate invoice for any enrollment type.
    
    Args:
        enrollment: Enrollment instance (any type)
        enrollment_type: One of ['CLASS', 'BOARDING', 'UNIFORM']
        **kwargs: Additional options passed to specific generator
        
    Returns:
        FeeInvoice instance
        
    Raises:
        ValueError: If enrollment_type is invalid
        
    Example:
        invoice = generate_enrollment_invoice(
            class_enrollment, 
            'CLASS', 
            include_optional=True
        )
    """
    generators = {
        'CLASS': ClassEnrollmentInvoiceGenerator,
        'BOARDING': BoardingEnrollmentInvoiceGenerator,
        'UNIFORM': UniformSaleInvoiceGenerator,
    }
    
    generator = generators.get(enrollment_type)
    if not generator:
        raise ValueError(
            f"Invalid enrollment_type: {enrollment_type}. "
            f"Must be one of {list(generators.keys())}"
        )
    
    return generator.generate(enrollment, **kwargs)