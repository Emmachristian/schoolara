# fees/invoice_generators.py - COMPLETE UNIFIED ARCHITECTURE WITH DRAFT INVOICES

"""
Centralized invoice generation for all enrollment types.

ARCHITECTURE:
1. UnifiedStudentInvoiceGenerator - Combines academic + boarding (PRIMARY)
2. UniformSaleInvoiceGenerator - Uniform sales (always separate)
3. ClassEnrollmentInvoiceGenerator - Academic only (internal use)
4. BoardingEnrollmentInvoiceGenerator - Boarding only (internal use)

PUBLIC API:
- generate_student_enrollment_invoice() - Use this for student invoices
- generate_uniform_sale_invoice() - Use this for uniform sales

WORKFLOW:
- Invoices created as DRAFT (can be modified/deleted)
- Admin reviews and changes to PENDING (finalized)
- Zero-amount invoices (full scholarship) auto-set to VOID
- Journal entries posted automatically when status → PENDING
- AccountTransaction created immediately for balance tracking
"""

from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from datetime import timedelta
import logging

from fees.models import (
    FeeInvoice, FeeInvoiceItem, FeesCategory, FeesStructure, 
    StudentScholarship, FeesDiscount, StudentAccount, AccountTransaction
)
from fees.utils import generate_invoice_number
from core.models import FinancialSettings, FiscalPeriod
from core.utils import get_school_today, get_school_current_time

logger = logging.getLogger(__name__)


# =============================================================================
# CUSTOM EXCEPTIONS
# =============================================================================

class FeeStructureNotFoundError(ValueError):
    """Raised when required fee structure is not found"""
    pass


# =============================================================================
# HELPER FUNCTIONS (Module-level)
# =============================================================================

def _calculate_category_discount(amount, config, scholarship=None):
    """
    Calculate discount based on category-specific configuration.
    
    Args:
        amount: Decimal - Item amount to calculate discount for
        config: dict - Category discount configuration
        scholarship: StudentScholarship - For budget checking (optional)
    
    Returns:
        Decimal: Discount amount
    """
    discount_type = config.get('type')
    discount_value = Decimal(str(config.get('value', 0)))
    
    # Calculate base discount
    if discount_type == 'percentage':
        discount = (amount * discount_value / Decimal('100.00')).quantize(Decimal('0.01'))
        
    elif discount_type == 'full_waiver':
        # Full waiver is 100%
        discount = amount
        
    elif discount_type == 'fixed_amount':
        # Fixed amount per invoice item (capped at item amount)
        discount = min(discount_value, amount)
        
    elif discount_type == 'none':
        discount = Decimal('0.00')
        
    else:
        logger.warning(f"Unknown discount type: {discount_type}")
        discount = Decimal('0.00')
    
    # Check budget constraints for budget-based scholarships
    if scholarship and scholarship.is_budget_based():
        remaining_balance = scholarship.get_remaining_balance()
        
        if remaining_balance is not None and remaining_balance > 0:
            # Cap discount at remaining balance
            discount = min(discount, remaining_balance)
        elif remaining_balance is not None and remaining_balance <= 0:
            # Budget exhausted
            discount = Decimal('0.00')
    
    return discount.quantize(Decimal('0.01'))


# =============================================================================
# UNIFIED STUDENT INVOICE GENERATOR (PRIMARY - USE THIS)
# =============================================================================

class UnifiedStudentInvoiceGenerator:
    """
    Generate a SINGLE invoice combining academic + boarding fees.
    
    🎯 PRIMARY GENERATOR - Use this for all student enrollment invoices.
    """
    
    @staticmethod
    @transaction.atomic
    def generate(class_enrollment, **kwargs):
        """
        Generate unified invoice for student (academic + boarding if applicable).
        
        Args:
            class_enrollment: StudentClassEnrollment instance (required)
            **kwargs: Additional options
                - issue_date: Date (default: today)
                - due_date: Date (default: issue_date + payment_terms_days)
                - fiscal_period: FiscalPeriod instance (default: current)
                - include_optional: Include optional fees (default: False)
                - include_boarding: Force include/exclude boarding (default: auto-detect)
                - include_meals: Include meal fees for boarders (default: True)
                - include_laundry: Include laundry fees (default: True)
                - auto_apply_scholarships: Auto-apply scholarships (default: True)
                - auto_apply_discounts: Auto-apply discounts (default: True)
                - payment_terms: Payment terms text
                - force: Generate even if enrollment already has invoice
                
        Returns:
            FeeInvoice instance (status = DRAFT or VOID)
        """
        # Check if enrollment already has invoice
        if class_enrollment.academic_invoice and not kwargs.get('force', False):
            raise ValueError(
                f"Enrollment already has invoice: {class_enrollment.academic_invoice.invoice_number}"
            )
        
        student = class_enrollment.student
        session = class_enrollment.academic_session
        class_instance = class_enrollment.class_instance
        
        # Get settings
        settings = FinancialSettings.get_instance()
        
        # Get dates using school timezone
        issue_date = kwargs.get('issue_date') or get_school_today()
        due_date = kwargs.get('due_date') or (
            issue_date + timedelta(days=settings.default_payment_terms_days)
        )
        
        # Get fiscal period
        fiscal_period = kwargs.get('fiscal_period') or FiscalPeriod.get_current_fiscal_period()
        if not fiscal_period:
            raise ValueError(
                "No active fiscal period found. "
                "Please create a fiscal period in Admin → Core → Fiscal Periods."
            )
        
        # =====================================================================
        # FIND ACADEMIC FEE STRUCTURE
        # =====================================================================
        academic_fee_structure = UnifiedStudentInvoiceGenerator._find_applicable_fee_structure(
            class_enrollment
        )
        
        if not academic_fee_structure:
            raise FeeStructureNotFoundError(
                f"No active academic fee structure found for {class_instance.academic_level} "
                f"in {session.name}. Please create a fee structure."
            )
        
        logger.info(f"Using academic fee structure: {academic_fee_structure.name}")
        
        # =====================================================================
        # CHECK FOR BOARDING ENROLLMENT
        # =====================================================================
        include_boarding = kwargs.get('include_boarding', None)
        boarding_enrollment = None
        boarding_fee_structure = None
        
        # Auto-detect boarding enrollment if not explicitly specified
        if include_boarding is None:
            boarding_enrollment = student.boarding_enrollments.filter(
                academic_session=session,
                status='ACTIVE'
            ).first()
            include_boarding = boarding_enrollment is not None
        elif include_boarding:
            # Forced to include boarding - must find it
            boarding_enrollment = student.boarding_enrollments.filter(
                academic_session=session,
                status='ACTIVE'
            ).first()
            
            if not boarding_enrollment:
                raise ValueError(
                    f"Student {student.get_full_name()} does not have an active "
                    f"boarding enrollment for {session.name}"
                )
        
        # Find boarding fee structure if needed
        if include_boarding and boarding_enrollment:
            logger.info(f"Student has boarding: {boarding_enrollment.boarding_type}")
            
            boarding_fee_structures = FeesStructure.objects.filter(
                applicable_sessions=session,
                boarding_type_filter__in=[
                    boarding_enrollment.boarding_type,
                    'BOARDER_ONLY',
                ],
                is_active=True
            ).exclude(
                id=academic_fee_structure.id
            ).order_by('priority')
            
            if boarding_fee_structures.exists():
                boarding_fee_structure = boarding_fee_structures.first()
                logger.info(f"Using boarding fee structure: {boarding_fee_structure.name}")
            else:
                logger.warning(
                    f"No boarding fee structure found for {boarding_enrollment.get_boarding_type_display()}"
                )
        
        # =====================================================================
        # CREATE INVOICE (AS DRAFT)
        # =====================================================================
        invoice_number = generate_invoice_number()
        
        # Determine primary fee structure (academic takes precedence)
        primary_fee_structure = academic_fee_structure
        
        # Build notes
        notes_parts = [f"Academic fees for {class_instance.get_display_name()}"]
        if include_boarding and boarding_enrollment:
            notes_parts.append(f"Boarding fees ({boarding_enrollment.get_boarding_type_display()})")
        
        invoice = FeeInvoice.objects.create(
            invoice_number=invoice_number,
            student=student,
            academic_session=session,
            fiscal_period=fiscal_period,
            fee_structure=primary_fee_structure,
            issue_date=issue_date,
            due_date=due_date,
            status='DRAFT',
            payment_terms=kwargs.get('payment_terms', ''),
            notes="\n".join(notes_parts),
            subtotal_amount=Decimal('0.00'),
            total_amount=Decimal('0.00'),
            balance=Decimal('0.00'),
        )
        
        logger.info(f"Created DRAFT invoice {invoice_number}")
        
        # =====================================================================
        # ADD ACADEMIC ITEMS
        # =====================================================================
        include_optional = kwargs.get('include_optional', False)
        items_added = 0
        subtotal = Decimal('0.00')
        tax_total = Decimal('0.00')
        
        logger.info(f"Adding academic items from structure: {academic_fee_structure.name}")
        
        for structure_item in academic_fee_structure.items.all().order_by('display_order'):
            if not structure_item.is_applicable_to_student(student):
                logger.debug(f"Skipping non-applicable item: {structure_item.fee_category.name}")
                continue
            
            if not include_optional and not structure_item.is_mandatory:
                logger.debug(f"Skipping optional item: {structure_item.fee_category.name}")
                continue
            
            amount = structure_item.get_amount_for_student(student)
            tax_amount = structure_item.calculate_tax_amount(amount)
            
            FeeInvoiceItem.objects.create(
                invoice=invoice,
                fee_category=structure_item.fee_category,
                description=structure_item.get_description(),
                quantity=Decimal('1.00'),
                unit_amount=amount,
                amount=amount,
                tax_percentage=structure_item.tax_percentage,
                tax_amount=tax_amount,
                discount_amount=Decimal('0.00'),
                discount_percentage=Decimal('0.00'),
                scholarship_discount_amount=Decimal('0.00'),
                total_discount_amount=Decimal('0.00'),
                final_amount=amount + tax_amount,
                original_amount=amount,
            )
            
            items_added += 1
            subtotal += amount
            tax_total += tax_amount
            
            logger.debug(f"Added academic item: {structure_item.fee_category.name} - {amount}")
        
        # =====================================================================
        # ADD BOARDING ITEMS (if applicable)
        # =====================================================================
        if include_boarding and boarding_fee_structure:
            logger.info(f"Adding boarding items from structure: {boarding_fee_structure.name}")
            
            for structure_item in boarding_fee_structure.items.all().order_by('display_order'):
                if not structure_item.is_applicable_to_student(student):
                    logger.debug(f"Skipping non-applicable boarding item: {structure_item.fee_category.name}")
                    continue
                
                if not include_optional and not structure_item.is_mandatory:
                    logger.debug(f"Skipping optional boarding item: {structure_item.fee_category.name}")
                    continue
                
                if not kwargs.get('include_meals', True):
                    if any(word in structure_item.fee_category.name.lower() 
                           for word in ['meal', 'food', 'catering', 'lunch', 'breakfast', 'dinner']):
                        continue
                
                if not kwargs.get('include_laundry', True):
                    if any(word in structure_item.fee_category.name.lower() 
                           for word in ['laundry', 'washing', 'cleaning']):
                        continue
                
                amount = structure_item.get_amount_for_student(student)
                tax_amount = structure_item.calculate_tax_amount(amount)
                
                FeeInvoiceItem.objects.create(
                    invoice=invoice,
                    fee_category=structure_item.fee_category,
                    description=structure_item.get_description(),
                    quantity=Decimal('1.00'),
                    unit_amount=amount,
                    amount=amount,
                    tax_percentage=structure_item.tax_percentage,
                    tax_amount=tax_amount,
                    discount_amount=Decimal('0.00'),
                    discount_percentage=Decimal('0.00'),
                    scholarship_discount_amount=Decimal('0.00'),
                    total_discount_amount=Decimal('0.00'),
                    final_amount=amount + tax_amount,
                    original_amount=amount,
                )
                
                items_added += 1
                subtotal += amount
                tax_total += tax_amount
                
                logger.debug(f"Added boarding item: {structure_item.fee_category.name} - {amount}")
        
        # =====================================================================
        # UPDATE INVOICE TOTALS BEFORE DISCOUNTS
        # =====================================================================
        if items_added == 0:
            invoice.delete()
            raise FeeStructureNotFoundError(
                f"Fee structures exist but contain no applicable items for {student.get_full_name()}"
            )
        
        invoice.subtotal_amount = subtotal
        invoice.tax_amount = tax_total
        invoice.total_amount = subtotal + tax_total
        invoice.balance = invoice.total_amount
        invoice.save()
        
        logger.info(f"Invoice subtotal before discounts: {invoice.total_amount}")
        
        # =====================================================================
        # ✅ AUTO-APPLY SCHOLARSHIPS & DISCOUNTS
        # =====================================================================
        if kwargs.get('auto_apply_scholarships', True):
            invoice.auto_scholarships_applied = True
            invoice.save()
            UnifiedStudentInvoiceGenerator._auto_apply_scholarships(invoice)
        
        if kwargs.get('auto_apply_discounts', True):
            invoice.auto_discounts_applied = True
            invoice.save()
            UnifiedStudentInvoiceGenerator._auto_apply_discounts(invoice)
        
        # Apply manual discount if provided
        discount_amount = kwargs.get('discount_amount')
        if discount_amount:
            invoice.discount_amount += Decimal(str(discount_amount))
            invoice.total_amount -= Decimal(str(discount_amount))
            invoice.balance = invoice.total_amount
            invoice.save()
        
        # =====================================================================
        # ✅ HANDLE ZERO-AMOUNT INVOICES (FULL SCHOLARSHIP/WAIVER)
        # =====================================================================
        if invoice.total_amount <= Decimal('0.00'):
            logger.info(
                f"Invoice {invoice.invoice_number} has zero total amount - "
                f"marking as VOID (full scholarship/waiver)"
            )
            
            invoice.status = 'VOID'
            invoice.balance = Decimal('0.00')
            
            void_note = (
                "\n\n" + "="*70 + "\n"
                "STATUS: VOID - No Payment Required\n"
                "="*70 + "\n"
                f"Original Subtotal:        {invoice.subtotal_amount:>15,.2f}\n"
                f"Scholarship Discount:     {invoice.scholarship_discount_amount:>15,.2f}\n"
                f"Regular Discount:         {invoice.discount_amount:>15,.2f}\n"
                f"Tax:                      {invoice.tax_amount:>15,.2f}\n"
                f"Final Total:              {invoice.total_amount:>15,.2f}\n\n"
                "This invoice has been voided because the full amount is covered by\n"
                "scholarships and/or discounts. No payment is required from the student.\n"
                "="*70
            )
            invoice.notes = (invoice.notes or '') + void_note
            invoice.save()
            
            logger.info(f"✅ Invoice {invoice.invoice_number} marked as VOID")
            
            class_enrollment.academic_invoice = invoice
            class_enrollment.save(update_fields=['academic_invoice'])
            
            if boarding_enrollment:
                boarding_enrollment.boarding_invoice = invoice
                boarding_enrollment.save(update_fields=['boarding_invoice'])
            
            return invoice
        
        # =====================================================================
        # CREATE ACCOUNT TRANSACTION
        # =====================================================================
        logger.info(f"Invoice {invoice.invoice_number} remains DRAFT - ready for review")
        
        try:
            student_account, account_created = StudentAccount.objects.get_or_create(
                student=student
            )
            
            if account_created:
                logger.info(f"Created new student account for {student.get_full_name()}")
            
            transaction_amount = -invoice.total_amount
            current_balance = student_account.get_current_balance()
            balance_after = current_balance + transaction_amount
            
            AccountTransaction.objects.create(
                student_account=student_account,
                transaction_type='INVOICE',
                amount=transaction_amount,
                description=f"Invoice {invoice.invoice_number} - {session.name}",
                balance_after=balance_after,
                invoice=invoice,
                academic_session=session,
                fiscal_period=fiscal_period,
                reference_number=invoice.invoice_number
            )
            
            student_account.last_transaction_date = timezone.now()
            student_account.save(update_fields=['last_transaction_date'])
            
            logger.info(f"[OK] Created AccountTransaction: Amount={transaction_amount}")
            
        except Exception as e:
            logger.error(f"Error creating account transaction: {e}", exc_info=True)

        # ✅ CREATE DRAFT JOURNAL ENTRY
        UnifiedStudentInvoiceGenerator._create_journal_entry(invoice)

        class_enrollment.academic_invoice = invoice
        class_enrollment.save(update_fields=['academic_invoice'])
        
        if boarding_enrollment:
            boarding_enrollment.boarding_invoice = invoice
            boarding_enrollment.save(update_fields=['boarding_invoice'])
        
        logger.info(
            f"✅ Generated DRAFT invoice {invoice.invoice_number} "
            f"for {student.get_full_name()} with {items_added} items "
            f"(Total: {invoice.total_amount}, Balance: {invoice.balance})"
        )
        
        return invoice
    
    @staticmethod
    def _find_applicable_fee_structure(class_enrollment, target_session=None):
        """Find the most appropriate fee structure for a class enrollment."""
        student = class_enrollment.student
        class_instance = class_enrollment.class_instance
        session = target_session or class_enrollment.academic_session
        
        structures = FeesStructure.objects.filter(
            is_active=True,
            applicable_sessions=session,
            academic_levels=class_instance.academic_level,
            boarding_type_filter__in=['ALL', 'DAY_ONLY']
        ).order_by('priority')
        
        structures_with_classes = structures.filter(
            applicable_classes__isnull=False
        ).distinct()
        
        if structures_with_classes.exists():
            structures = structures.filter(
                applicable_classes=class_instance
            )
        
        matching_structures = []
        
        for structure in structures:
            if structure.is_applicable_to_student(student, session):
                matching_structures.append(structure)
        
        if not matching_structures:
            logger.warning(
                f"No fee structure found for {student.get_full_name()} "
                f"in {class_instance} for {session}"
            )
            return None
        
        return matching_structures[0]

    @staticmethod
    def _auto_apply_scholarships(invoice):
        """
        Automatically apply active scholarships to invoice with category-specific discount support.
        
        Handles three discount modes:
        1. Global discount (PERCENTAGE, FIXED_AMOUNT, FULL_WAIVER)
        2. Category-specific discounts (per StudentScholarship.category_discounts)
        3. Legacy CATEGORY_SPECIFIC (program.applicable_fee_categories)
        """
        
        logger.info(f"Auto-applying scholarships to invoice {invoice.invoice_number}")
        
        # Get active scholarships for student
        scholarships = StudentScholarship.objects.filter(
            student=invoice.student,
            status='ACTIVE',
            start_date__lte=invoice.issue_date,
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=invoice.issue_date)
        ).select_related('scholarship_program').order_by('scholarship_program__program_type', 'id')
        
        logger.info(f"Checking scholarships for {invoice.student.get_full_name()}")
        logger.info(f"  Invoice issue date: {invoice.issue_date}")
        logger.info(f"  Found {scholarships.count()} potentially active scholarship(s)")
        
        if not scholarships.exists():
            logger.info("No active scholarships found for student")
            return
        
        # Log scholarship details
        for scholarship in scholarships:
            logger.info(f"  → Scholarship: {scholarship.scholarship_program.name}")
            logger.info(f"    Start: {scholarship.start_date}, End: {scholarship.end_date or 'No end date'}")
            logger.info(f"    Type: {'Policy-based' if scholarship.is_policy_based() else 'Budget-based'}")
            logger.info(f"    Category-specific: {scholarship.use_category_specific_discounts}")
            if scholarship.is_budget_based():
                logger.info(f"    Balance: {scholarship.get_remaining_balance():,.2f}")
        
        # Get all invoice items
        invoice_items = invoice.items.all()
        
        if not invoice_items.exists():
            logger.info("No invoice items to apply scholarships to")
            return
        
        total_scholarship_discount = Decimal('0.00')
        
        # =========================================================================
        # PROCESS EACH SCHOLARSHIP
        # =========================================================================
        
        for scholarship in scholarships:
            try:
                program = scholarship.scholarship_program
                scholarship_total_discount = Decimal('0.00')
                
                logger.info(f"\n  Processing scholarship: {program.name}")
                logger.info(f"    Program type: {program.program_type}")
                logger.info(f"    Discount type: {program.discount_type}")
                logger.info(f"    Category-specific mode: {scholarship.use_category_specific_discounts}")
                
                # =====================================================================
                # MODE 1: CATEGORY-SPECIFIC DISCOUNTS (StudentScholarship level) ⭐ NEW
                # =====================================================================
                
                if scholarship.use_category_specific_discounts:
                    logger.info(f"    Using category-specific discount rules")
                    
                    # ✅ VALIDATE: Check if category_discounts is actually configured
                    if not scholarship.category_discounts:
                        logger.error(
                            f"    ❌ CRITICAL ERROR: Scholarship {scholarship.id} ({program.name}) "
                            f"has use_category_specific_discounts=True but category_discounts is EMPTY! "
                            f"This scholarship will be SKIPPED. Please edit the scholarship to configure discounts."
                        )
                        logger.error(
                            f"       This usually means the scholarship form was saved incorrectly. "
                            f"       Admin should: (1) Edit scholarship, (2) Configure category discounts, (3) Save again."
                        )
                        continue
                    
                    # ✅ Log configuration summary
                    categories_with_discounts = sum(
                        1 for config in scholarship.category_discounts.values() 
                        if config.get('type') != 'none'
                    )
                    
                    logger.info(
                        f"    Category discount configuration: {len(scholarship.category_discounts)} categories total, "
                        f"{categories_with_discounts} with active discounts"
                    )
                    
                    # Process each invoice item
                    for item in invoice_items:
                        # Get category code
                        category_code = item.fee_category.category_type or item.fee_category.code
                        
                        # Get discount config for this category
                        discount_config = scholarship.category_discounts.get(category_code)
                        
                        # ✅ Better validation with clearer logging
                        if not discount_config:
                            logger.debug(
                                f"      • {item.fee_category.name} ({category_code}): "
                                f"Not in scholarship configuration - no discount"
                            )
                            continue
                            
                        if discount_config.get('type') == 'none':
                            logger.debug(
                                f"      • {item.fee_category.name} ({category_code}): "
                                f"Explicitly excluded from scholarship (type='none')"
                            )
                            continue
                        
                        # Calculate discount for this item
                        item_discount = _calculate_category_discount(
                            item.amount,
                            discount_config,
                            scholarship  # Pass scholarship for budget checking
                        )
                        
                        if item_discount > 0:
                            # Apply discount to item
                            item.scholarship_discount_amount = (
                                item.scholarship_discount_amount or Decimal('0.00')
                            ) + item_discount
                            item.has_scholarship_discount = True
                            item.save(update_fields=['scholarship_discount_amount', 'has_scholarship_discount'])
                            
                            scholarship_total_discount += item_discount
                            
                            discount_type_display = discount_config.get('type', 'unknown')
                            discount_value = discount_config.get('value', 0)
                            
                            logger.info(
                                f"      ✅ {item.fee_category.name} ({category_code}): "
                                f"{discount_type_display} ({discount_value}) = {item_discount:,.2f}"
                            )
                            
                            # Track budget usage for budget-based scholarships
                            if scholarship.is_budget_based():
                                scholarship.total_amount_used += item_discount
                        else:
                            # Log why no discount was applied
                            logger.debug(
                                f"      • {item.fee_category.name} ({category_code}): "
                                f"Config present but calculated discount = 0 "
                                f"(type={discount_config.get('type')}, value={discount_config.get('value')})"
                            )
                
                # =====================================================================
                # MODE 2: GLOBAL DISCOUNT (Program level)
                # =====================================================================
                
                else:
                    logger.info(f"    Using program's global discount")
                    
                    # Check if this is legacy CATEGORY_SPECIFIC with applicable_fee_categories
                    if program.discount_type == 'CATEGORY_SPECIFIC':
                        # Legacy mode: Filter by applicable_fee_categories
                        applicable_categories = program.applicable_fee_categories.all()
                        
                        if not applicable_categories.exists():
                            # No categories specified = apply to all
                            eligible_items = invoice_items
                            logger.info(f"    Legacy CATEGORY_SPECIFIC: No categories specified, applying to all items")
                        else:
                            eligible_items = [
                                item for item in invoice_items
                                if item.fee_category in applicable_categories
                            ]
                            logger.info(
                                f"    Legacy CATEGORY_SPECIFIC: {len(eligible_items)} eligible items "
                                f"(out of {invoice_items.count()} total)"
                            )
                    else:
                        # Global discount applies to all items
                        eligible_items = invoice_items
                        logger.info(f"    Global discount: Applying to all {invoice_items.count()} items")
                    
                    # Calculate total eligible amount
                    eligible_total = sum(item.amount for item in eligible_items)
                    
                    if eligible_total <= 0:
                        logger.info(f"    No eligible amount for scholarship (eligible_total = {eligible_total})")
                        continue
                    
                    logger.info(f"    Eligible subtotal: {eligible_total:,.2f}")
                    
                    # =====================================================================
                    # Calculate discount based on program discount type
                    # =====================================================================
                    
                    if program.discount_type == 'PERCENTAGE' and program.discount_percentage is not None:
                        # Percentage discount
                        discount_amount = (
                            eligible_total * program.discount_percentage / Decimal('100.00')
                        ).quantize(Decimal('0.01'))
                        
                        # Apply program maximum if set
                        if program.maximum_award_amount and discount_amount > program.maximum_award_amount:
                            logger.info(f"    Capping discount at maximum: {program.maximum_award_amount:,.2f}")
                            discount_amount = program.maximum_award_amount
                        
                        logger.info(
                            f"    Percentage discount: {program.discount_percentage}% of "
                            f"{eligible_total:,.2f} = {discount_amount:,.2f}"
                        )
                        
                    elif program.discount_type == 'FULL_WAIVER':
                        # Full waiver (100%)
                        discount_amount = eligible_total
                        logger.info(f"    Full waiver: {discount_amount:,.2f}")
                        
                    elif program.discount_type == 'FIXED_AMOUNT' and scholarship.amount_awarded > 0:
                        # Fixed amount (budget-based)
                        remaining_balance = scholarship.get_remaining_balance()
                        
                        if remaining_balance <= 0:
                            logger.info(
                                f"    Budget exhausted (balance: {remaining_balance:,.2f}) - "
                                f"skipping this scholarship"
                            )
                            continue
                        
                        discount_amount = min(remaining_balance, eligible_total).quantize(Decimal('0.01'))
                        logger.info(
                            f"    Fixed amount: min(balance: {remaining_balance:,.2f}, "
                            f"eligible: {eligible_total:,.2f}) = {discount_amount:,.2f}"
                        )
                        
                    elif program.discount_type == 'CATEGORY_SPECIFIC':
                        # Legacy CATEGORY_SPECIFIC mode
                        if program.discount_percentage:
                            discount_amount = (
                                eligible_total * program.discount_percentage / Decimal('100.00')
                            ).quantize(Decimal('0.01'))
                            logger.info(
                                f"    Legacy category-specific (percentage): "
                                f"{program.discount_percentage}% of {eligible_total:,.2f} = {discount_amount:,.2f}"
                            )
                        elif program.fixed_discount_amount:
                            discount_amount = min(program.fixed_discount_amount, eligible_total)
                            logger.info(
                                f"    Legacy category-specific (fixed): "
                                f"min({program.fixed_discount_amount:,.2f}, {eligible_total:,.2f}) = {discount_amount:,.2f}"
                            )
                        else:
                            discount_amount = Decimal('0.00')
                            logger.warning(
                                f"    Legacy CATEGORY_SPECIFIC mode but no percentage or fixed amount set!"
                            )
                        
                    else:
                        logger.warning(f"    ❌ No valid discount configuration")
                        logger.warning(f"       - discount_type: {program.discount_type}")
                        logger.warning(f"       - discount_percentage: {program.discount_percentage}")
                        logger.warning(f"       - fixed_discount_amount: {program.fixed_discount_amount}")
                        logger.warning(f"       - amount_awarded: {scholarship.amount_awarded}")
                        logger.warning(f"       This scholarship will be skipped. Please review program configuration.")
                        continue
                    
                    # =====================================================================
                    # Distribute discount across eligible items proportionally
                    # =====================================================================
                    
                    if discount_amount > 0:
                        logger.info(f"    Distributing {discount_amount:,.2f} across {len(eligible_items)} items")
                        
                        # Distribute proportionally
                        for item in eligible_items:
                            if eligible_total > 0:
                                proportion = item.amount / eligible_total
                                item_discount = (discount_amount * proportion).quantize(Decimal('0.01'))
                                
                                if item_discount > 0:
                                    item.scholarship_discount_amount = (
                                        item.scholarship_discount_amount or Decimal('0.00')
                                    ) + item_discount
                                    item.has_scholarship_discount = True
                                    item.save(update_fields=['scholarship_discount_amount', 'has_scholarship_discount'])
                                    
                                    scholarship_total_discount += item_discount
                                    
                                    logger.debug(
                                        f"      • {item.fee_category.name}: "
                                        f"{proportion * 100:.1f}% × {discount_amount:,.2f} = {item_discount:,.2f}"
                                    )
                        
                        # Track budget usage for budget-based scholarships
                        if scholarship.is_budget_based():
                            scholarship.total_amount_used += discount_amount
                        
                        logger.info(f"    ✅ Total discount distributed: {scholarship_total_discount:,.2f}")
                    else:
                        logger.warning(f"    ⚠️ No discount applied (discount_amount = {discount_amount})")
                
                # =====================================================================
                # Save scholarship if budget tracking updated
                # =====================================================================
                
                if scholarship_total_discount > 0:
                    total_scholarship_discount += scholarship_total_discount
                    
                    if scholarship.is_budget_based():
                        scholarship.save(update_fields=['total_amount_used'])
                        new_balance = scholarship.get_remaining_balance()
                        logger.info(
                            f"    Updated scholarship balance: {new_balance:,.2f} "
                            f"(used: {scholarship.total_amount_used:,.2f} of {scholarship.amount_awarded:,.2f})"
                        )
                    
                    logger.info(f"    Scholarship total discount: {scholarship_total_discount:,.2f}")
                else:
                    logger.warning(
                        f"    ⚠️ No discount applied from scholarship '{program.name}' "
                        f"(scholarship_total_discount = 0)"
                    )
                    
                    # Provide helpful diagnostic info
                    if scholarship.use_category_specific_discounts:
                        if not scholarship.category_discounts:
                            logger.warning(f"       → category_discounts is empty!")
                        else:
                            active_count = sum(
                                1 for c in scholarship.category_discounts.values() 
                                if c.get('type') != 'none'
                            )
                            logger.warning(
                                f"       → {active_count} categories with discounts configured, "
                                f"but no matching items on invoice"
                            )
                
            except Exception as e:
                logger.error(
                    f"❌ EXCEPTION: Error auto-applying scholarship {scholarship.id} "
                    f"({scholarship.scholarship_program.name}) to invoice {invoice.invoice_number}: {e}",
                    exc_info=True
                )
                logger.error(
                    f"   This scholarship will be SKIPPED. Please review logs and scholarship configuration."
                )
        
        # =========================================================================
        # UPDATE INVOICE TOTALS
        # =========================================================================
        
        if total_scholarship_discount > 0:
            invoice.scholarship_discount_amount = total_scholarship_discount
            invoice.has_scholarships_applied = True
            
            # Recalculate invoice totals
            invoice.total_amount = invoice.subtotal_amount - total_scholarship_discount
            invoice.balance = invoice.total_amount - invoice.paid_amount
            invoice.save(update_fields=[
                'scholarship_discount_amount',
                'has_scholarships_applied',
                'total_amount',
                'balance'
            ])
            
            logger.info(f"\n" + "="*80)
            logger.info(f"✅ TOTAL SCHOLARSHIP DISCOUNT APPLIED: {total_scholarship_discount:,.2f}")
            logger.info(f"   Invoice subtotal: {invoice.subtotal_amount:,.2f}")
            logger.info(f"   Scholarship discount: -{total_scholarship_discount:,.2f}")
            logger.info(f"   New invoice total: {invoice.total_amount:,.2f}")
            logger.info(f"   Invoice balance: {invoice.balance:,.2f}")
            logger.info("="*80)
        else:
            logger.info("\n" + "="*80)
            logger.warning("⚠️ NO SCHOLARSHIP DISCOUNTS APPLIED")
            
            if scholarships.exists():
                logger.warning(
                    f"   {scholarships.count()} scholarship(s) found but none resulted in discounts!"
                )
                logger.warning("   Possible reasons:")
                logger.warning("   1. Category-specific mode enabled but category_discounts is empty")
                logger.warning("   2. No invoice items match scholarship's category configuration")
                logger.warning("   3. Budget-based scholarship has zero remaining balance")
                logger.warning("   4. Scholarship program has invalid discount configuration")
                logger.warning("   Please review scholarship configurations and logs above.")
            
            logger.info("="*80)
    
    @staticmethod
    def _auto_apply_discounts(invoice):
        """Automatically apply eligible discounts to invoice."""
        from fees.models import FeesDiscount
        
        logger.info(f"Auto-applying discounts to invoice {invoice.invoice_number}")
        
        discounts = FeesDiscount.objects.filter(
            academic_session=invoice.academic_session,
            is_active=True,
            auto_apply=True,
            start_date__lte=invoice.issue_date,
            end_date__gte=invoice.issue_date,
        )
        
        if not discounts.exists():
            logger.info("No auto-apply discounts found")
            return
        
        logger.info(f"Found {discounts.count()} auto-apply discounts")
        
        total_discount = Decimal('0.00')
        
        for discount in discounts:
            try:
                if discount.applicable_structures.exists():
                    if not discount.applicable_structures.filter(
                        id=invoice.fee_structure.id
                    ).exists():
                        logger.info(f"  Discount {discount.code}: Not applicable to this structure")
                        continue
                
                discount_base = invoice.subtotal_amount - invoice.scholarship_discount_amount
                
                if discount_base <= 0:
                    logger.info(f"  Discount {discount.code}: No remaining amount to discount")
                    continue
                
                if discount.discount_type == 'PERCENTAGE':
                    discount_amount = (discount_base * discount.discount_value / 100).quantize(Decimal('0.01'))
                else:
                    discount_amount = discount.discount_value
                
                discount_amount = min(discount_amount, discount_base)
                
                if discount_amount > 0:
                    total_discount += discount_amount
                    logger.info(f"  ✅ Applied discount {discount.code}: {discount_amount}")
                
            except Exception as e:
                logger.error(f"Error auto-applying discount {discount.code} to invoice {invoice.invoice_number}: {e}", exc_info=True)
        
        if total_discount > 0:
            invoice.discount_amount += total_discount
            invoice.has_discounts_applied = True
            invoice.total_amount -= total_discount
            invoice.balance = invoice.total_amount - invoice.paid_amount
            invoice.save()
            
            logger.info(f"✅ Total regular discount applied: {total_discount}")
            logger.info(f"   New invoice total: {invoice.total_amount}")
        else:
            logger.info("No regular discounts applied")

    @staticmethod
    def _create_journal_entry(invoice):
        """Create DRAFT journal entry for the invoice."""
        try:
            if invoice.total_amount <= Decimal('0.00'):
                logger.info(
                    f"[SKIPPED] Journal entry not created for {invoice.invoice_number} - "
                    f"zero amount invoice (full scholarship/waiver applied)"
                )
                return None
            
            from finance.models import Journal, JournalEntry, JournalTransaction
            from django.db.models import Sum
            
            receivable_account = invoice.get_receivable_account()
            
            if not receivable_account:
                logger.error("[ERROR] Cannot create journal entry: No receivable account configured")
                return None
            
            from core.models import FinancialSettings
            settings = FinancialSettings.get_instance()
            if not settings:
                logger.error("[ERROR] FinancialSettings not configured")
                return None
            
            mappings = settings.get_account_mappings()
            
            logger.info(f"Creating DRAFT journal entry for invoice {invoice.invoice_number}")
            
            fees_journal, _ = Journal.objects.get_or_create(
                journal_type='FEES',
                defaults={
                    'name': 'Fee Collection Journal',
                    'description': 'Student fee invoices and collections',
                    'is_active': True
                }
            )

            from finance.utils import generate_journal_entry_number
            entry_number = generate_journal_entry_number(fees_journal)

            journal_entry = JournalEntry.objects.create(
                journal=fees_journal,
                entry_number=entry_number,
                entry_date=invoice.issue_date,
                fiscal_period=invoice.fiscal_period,
                academic_session=invoice.academic_session,
                reference_number=invoice.invoice_number,
                description=f"Student Fee Invoice - {invoice.student.get_full_name()}",
                status='DRAFT',
            )
            
            JournalTransaction.objects.create(
                journal_entry=journal_entry,
                account=receivable_account,
                amount=invoice.total_amount,
                is_debit=True,
                description=f"Student fees - {invoice.student.get_full_name()}",
            )
            
            revenue_breakdown = invoice.items.values(
                'fee_category__category_type',
                'fee_category__code'
            ).annotate(
                total_amount=Sum('final_amount')
            ).order_by('fee_category__category_type')
            
            if not revenue_breakdown.exists():
                logger.warning(f"Invoice {invoice.invoice_number} has no items")
                
                JournalTransaction.objects.create(
                    journal_entry=journal_entry,
                    account=mappings.default_revenue_account,
                    amount=invoice.total_amount,
                    is_debit=False,
                    description=f"Fee revenue - {invoice.academic_session.name}",
                )
            else:
                for item in revenue_breakdown:
                    category_type = item['fee_category__category_type'] or ''
                    category_code = item['fee_category__code'] or ''
                    amount = item['total_amount']
                    
                    if category_type in [
                        'TUITION', 'EXAM', 'DEVELOPMENT', 'MEDICAL', 'SPORT',
                        'MEALS', 'TECHNOLOGY', 'LABORATORY', 'LIBRARY', 'TRANSPORT',
                        'ADMISSION', 'REGISTRATION', 'CLUB', 'LATE_PAYMENT',
                        'FIELD_TRIP', 'GRADUATION', 'INSURANCE', 'BOOKS', 'OTHER'
                    ]:
                        revenue_account = mappings.default_revenue_account
                        description = f"{category_type.replace('_', ' ').title()} revenue"
                    
                    elif category_type in ['BOARDING', 'LAUNDRY']:
                        revenue_account = mappings.boarding_revenue_account or mappings.default_revenue_account
                        description = "Boarding services revenue"
                    
                    elif category_type == 'UNIFORM':
                        revenue_account = mappings.uniform_and_book_sales_account or mappings.default_revenue_account
                        description = "Uniform sales revenue"
                    
                    elif not category_type:
                        code_mapping = {
                            'TUITION': (mappings.default_revenue_account, "Tuition revenue"),
                            'EXAM': (mappings.default_revenue_account, "Examination revenue"),
                            'BOARD': (mappings.boarding_revenue_account or mappings.default_revenue_account, "Boarding revenue"),
                            'MEALS': (mappings.default_revenue_account, "Meals revenue"),
                        }
                        
                        if category_code in code_mapping:
                            revenue_account, description = code_mapping[category_code]
                        else:
                            revenue_account = mappings.default_revenue_account
                            description = f"{category_code} revenue" if category_code else "Other revenue"
                    
                    else:
                        revenue_account = mappings.default_revenue_account
                        description = f"{category_type.replace('_', ' ').title()} revenue"
                    
                    JournalTransaction.objects.create(
                        journal_entry=journal_entry,
                        account=revenue_account,
                        amount=amount,
                        is_debit=False,
                        description=description,
                    )
            
            invoice.journal_entry = journal_entry
            invoice.save(update_fields=['journal_entry'])
            
            logger.info(f"[OK] Created DRAFT journal entry {journal_entry.entry_number}")
            logger.info(f"     Journal entry will be POSTED when invoice is finalized to PENDING")
            
            return journal_entry
        
        except Exception as e:
            logger.error(f"[ERROR] Error creating journal entry: {e}", exc_info=True)
            return None
    
    @staticmethod
    @transaction.atomic
    def bulk_generate(enrollments, **kwargs):
        """Generate unified invoices for multiple class enrollments."""
        results = {
            'created_count': 0,
            'voided_count': 0,
            'skipped': 0,
            'errors': [],
            'invoices': []
        }
        
        logger.info(f"Starting bulk invoice generation for {len(enrollments)} enrollments")
        
        for enrollment in enrollments:
            try:
                if enrollment.academic_invoice and not kwargs.get('force', False):
                    results['skipped'] += 1
                    logger.debug(f"Skipped enrollment {enrollment.id}: already has invoice")
                    continue
                
                invoice = UnifiedStudentInvoiceGenerator.generate(enrollment, **kwargs)
                
                if invoice.status == 'VOID':
                    results['voided_count'] += 1
                else:
                    results['created_count'] += 1
                
                results['invoices'].append(invoice)
                
            except Exception as e:
                error_msg = (
                    f"{enrollment.student.get_full_name()} "
                    f"({enrollment.class_instance}): {str(e)}"
                )
                results['errors'].append(error_msg)
                logger.error(
                    f"Error generating unified invoice for enrollment {enrollment.id}: {e}",
                    exc_info=True
                )
        
        logger.info(
            f"✅ Bulk unified invoice generation complete: "
            f"{results['created_count']} created (DRAFT), "
            f"{results['voided_count']} voided (full scholarship), "
            f"{results['skipped']} skipped, "
            f"{len(results['errors'])} errors"
        )
        
        return results


# =============================================================================
# UNIFORM SALE INVOICE GENERATOR (ALWAYS SEPARATE)
# =============================================================================

class UniformSaleInvoiceGenerator:
    """
    Generate invoices for uniform sales.
    
    🎯 IMPORTANT: Uniform invoices are ALWAYS SEPARATE from enrollment invoices.
    Students can have multiple uniform invoices throughout the year.
    
    This delegates to uniforms.services.UniformInvoiceService since uniform 
    sales have complex inventory/COGS logic.
    """
    
    @staticmethod
    def generate(uniform_sale, **kwargs):
        """
        Generate invoice for uniform sale.
        
        Args:
            uniform_sale: UniformSale instance
            **kwargs: Additional options
                - issue_date: Date (default: sale date)
                - due_date: Date (default: issue_date + payment_terms)
                - payment_terms: Payment terms text
                - force: Regenerate even if invoice exists
            
        Returns:
            FeeInvoice instance
            
        Raises:
            ValueError: If uniform sale already has invoice
        """
        # Check if sale already has invoice
        if hasattr(uniform_sale, 'invoice') and uniform_sale.invoice and not kwargs.get('force', False):
            raise ValueError(
                f"Uniform sale already has invoice: {uniform_sale.invoice.invoice_number}"
            )
        
        # Delegate to uniform-specific service
        from uniforms.services import UniformInvoiceService
        
        invoice = UniformInvoiceService.create_invoice_from_sale(
            uniform_sale,
            **kwargs
        )
        
        logger.info(
            f"Generated uniform invoice {invoice.invoice_number} "
            f"for sale {uniform_sale.sale_number} "
            f"({invoice.items.count()} items, {invoice.total_amount})"
        )
        
        return invoice
    
    @staticmethod
    @transaction.atomic
    def bulk_generate(uniform_sales, **kwargs):
        """
        Generate invoices for multiple uniform sales.
        
        Args:
            uniform_sales: QuerySet or list of UniformSale instances
            **kwargs: Options passed to generate() for each sale
            
        Returns:
            dict: Results
        """
        results = {
            'created_count': 0,
            'skipped': 0,
            'errors': [],
            'invoices': []
        }
        
        for sale in uniform_sales:
            try:
                # Skip if already has invoice (unless force=True)
                if hasattr(sale, 'invoice') and sale.invoice and not kwargs.get('force', False):
                    results['skipped'] += 1
                    logger.debug(f"Skipped sale {sale.sale_number}: already has invoice")
                    continue
                
                # Generate invoice
                invoice = UniformSaleInvoiceGenerator.generate(sale, **kwargs)
                
                results['created_count'] += 1
                results['invoices'].append(invoice)
                
            except Exception as e:
                error_msg = f"Sale {sale.sale_number}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(
                    f"Error generating uniform invoice for sale {sale.sale_number}: {e}",
                    exc_info=True
                )
        
        logger.info(
            f"Bulk uniform invoice generation complete: "
            f"{results['created_count']} created, "
            f"{results['skipped']} skipped, "
            f"{len(results['errors'])} errors"
        )
        
        return results


# =============================================================================
# CLASS ENROLLMENT INVOICE GENERATOR (INTERNAL USE ONLY)
# =============================================================================

class ClassEnrollmentInvoiceGenerator:
    """
    Generate invoices for class enrollment (academic fees ONLY).
    
    ⚠️ INTERNAL USE ONLY - For testing and special cases.
    ⚠️ For normal invoice generation, use UnifiedStudentInvoiceGenerator instead.
    
    This generator creates academic-only invoices and does NOT include boarding fees.
    Use this only when you specifically need to separate academic and boarding invoices.
    """
    
    @staticmethod
    @transaction.atomic
    def generate(class_enrollment, **kwargs):
        """Generate academic-only invoice (internal use)"""
        # Delegate to unified generator with boarding disabled
        return UnifiedStudentInvoiceGenerator.generate(
            class_enrollment,
            include_boarding=False,
            **kwargs
        )
    
    @staticmethod
    def _find_applicable_fee_structure(class_enrollment):
        """Find applicable fee structure (delegates to unified generator)"""
        return UnifiedStudentInvoiceGenerator._find_applicable_fee_structure(class_enrollment)
    
    @staticmethod
    @transaction.atomic
    def bulk_generate(enrollments, **kwargs):
        """Bulk generate academic-only invoices (internal use)"""
        kwargs['include_boarding'] = False
        return UnifiedStudentInvoiceGenerator.bulk_generate(enrollments, **kwargs)


# =============================================================================
# BOARDING ENROLLMENT INVOICE GENERATOR (INTERNAL USE ONLY)
# =============================================================================

class BoardingEnrollmentInvoiceGenerator:
    """
    Generate invoices for boarding enrollment (boarding fees ONLY).
    
    ⚠️ INTERNAL USE ONLY - For testing and special cases.
    ⚠️ For normal invoice generation, use UnifiedStudentInvoiceGenerator instead.
    
    This generator creates boarding-only invoices. Use this only when you need to:
    - Generate a separate boarding invoice (e.g., mid-term boarding enrollment)
    - Test boarding fee structures in isolation
    - Handle special cases where boarding fees must be invoiced separately
    """
    
    @staticmethod
    @transaction.atomic
    def generate(boarding_enrollment, **kwargs):
        """
        Generate boarding-only invoice (internal use).
        
        NOTE: This requires the student to also have a class enrollment
        for the same session, since we delegate to the unified generator.
        """
        student = boarding_enrollment.student
        session = boarding_enrollment.academic_session
        
        # Find class enrollment for this session
        class_enrollment = student.class_enrollments.filter(
            academic_session=session,
            is_active=True,
            completion_status='ONGOING'
        ).first()
        
        if not class_enrollment:
            raise ValueError(
                f"Cannot generate boarding-only invoice: Student {student.get_full_name()} "
                f"does not have an active class enrollment for {session.name}"
            )
        
        # Generate invoice with academic disabled, boarding forced
        return UnifiedStudentInvoiceGenerator.generate(
            class_enrollment,
            include_boarding=True,
            # Note: This still includes academic fees
            # For truly boarding-only, you'd need custom logic
            **kwargs
        )


# =============================================================================
# PUBLIC API - USE THESE FUNCTIONS
# =============================================================================

def generate_student_enrollment_invoice(class_enrollment, **kwargs):
    """
    🎯 PRIMARY FUNCTION: Generate invoice for student enrollment (academic + boarding combined).
    
    Invoices are created as DRAFT and must be manually finalized to PENDING.
    """
    return UnifiedStudentInvoiceGenerator.generate(class_enrollment, **kwargs)


def generate_uniform_sale_invoice(uniform_sale, **kwargs):
    """
    🎯 Generate invoice for uniform sale.
    
    Uniform invoices are ALWAYS SEPARATE from enrollment invoices.
    This delegates to uniforms.services.UniformInvoiceService.
    
    Args:
        uniform_sale: UniformSale instance
        **kwargs: Additional options
        
    Returns:
        FeeInvoice instance
        
    Example:
        invoice = generate_uniform_sale_invoice(uniform_sale)
    """
    return UniformSaleInvoiceGenerator.generate(uniform_sale, **kwargs)


# =============================================================================
# LEGACY FUNCTION (DEPRECATED - for backward compatibility)
# =============================================================================

def generate_enrollment_invoice(enrollment, enrollment_type='UNIFIED', **kwargs):
    """
    DEPRECATED: Use generate_student_enrollment_invoice() or 
    generate_uniform_sale_invoice() instead.
    
    This function is kept for backward compatibility only.
    """
    import warnings
    warnings.warn(
        "generate_enrollment_invoice() is deprecated. "
        "Use generate_student_enrollment_invoice() or generate_uniform_sale_invoice() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    generators = {
        'UNIFIED': UnifiedStudentInvoiceGenerator,
        'CLASS': ClassEnrollmentInvoiceGenerator,
        'BOARDING': BoardingEnrollmentInvoiceGenerator,
    }
    
    generator = generators.get(enrollment_type)
    if not generator:
        raise ValueError(
            f"Invalid enrollment_type: {enrollment_type}. "
            f"Must be one of {list(generators.keys())}. "
            f"For uniform sales, use generate_uniform_sale_invoice() instead."
        )
    
    return generator.generate(enrollment, **kwargs)