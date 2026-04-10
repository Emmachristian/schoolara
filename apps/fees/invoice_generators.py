# fees/invoice_generators.py

"""
Centralized invoice generation for all enrollment types.

ARCHITECTURE:
    UnifiedStudentInvoiceGenerator      — academic + boarding combined (PRIMARY)
    UniformSaleInvoiceGenerator         — uniform sales (always separate)
    ClassEnrollmentInvoiceGenerator     — academic only (internal)
    BoardingEnrollmentInvoiceGenerator  — boarding only (internal)

PUBLIC API:
    generate_student_enrollment_invoice()
    generate_uniform_sale_invoice()

INVOICE LIFECYCLE:
    DRAFT   → admin reviews → PENDING (journal entry posted)
    VOID    → zero-amount invoices (full scholarship/waiver)
"""

from decimal import Decimal
from django.db import transaction
from django.db.models import Q, Sum
from datetime import timedelta
import logging

from fees.models import (
    FeeInvoice, FeeInvoiceItem, FeesStructure,
    StudentScholarship, StudentAccount, AccountTransaction,
)
from fees.utils import generate_invoice_number
from core.models import FinancialSettings, FiscalPeriod
from core.utils import get_school_today, get_school_current_time

logger = logging.getLogger(__name__)


# =============================================================================
# EXCEPTIONS
# =============================================================================

class FeeStructureNotFoundError(ValueError):
    """Raised when no applicable fee structure exists for the enrollment."""
    pass


# =============================================================================
# MODULE-LEVEL HELPERS
# =============================================================================


def _estimate_scholarship_value(ss, invoice):
    """
    Rough estimate of what a scholarship would save on an invoice.
    Used only for BEST_OF / STANDALONE comparison.
    """
    program = ss.scholarship_program
    total   = invoice.total_amount or Decimal('0.00')

    if program.discount_type == 'PERCENTAGE':
        return total * (program.discount_percentage or Decimal('0')) / Decimal('100')
    if program.discount_type == 'FIXED_AMOUNT':
        return program.fixed_discount_amount or Decimal('0')
    if program.discount_type == 'FULL_WAIVER':
        return total
    if program.discount_type == 'CATEGORY_SPECIFIC':
        est = Decimal('0')
        for item in invoice.items.all():
            config = ss.category_discounts.get(item.fee_category.category_type, {})
            t, v = config.get('type'), Decimal(str(config.get('value', 0)))
            if t == 'full_waiver':      est += item.amount
            elif t == 'percentage':     est += (item.amount * v / Decimal('100')).quantize(Decimal('0.01'))
            elif t == 'fixed_amount':   est += min(v, item.amount)
        return est
    return Decimal('0.00')


# =============================================================================
# UNIFIED STUDENT INVOICE GENERATOR
# =============================================================================

class UnifiedStudentInvoiceGenerator:
    """
    Generates a single invoice combining academic + boarding fees.
    Primary generator — use this for all student enrollment invoices.
    """

    @staticmethod
    @transaction.atomic
    def generate(class_enrollment, **kwargs):
        """
        Generate unified invoice for a student enrollment.

        Args:
            class_enrollment: StudentClassEnrollment
            **kwargs:
                issue_date              — default: today (school tz)
                due_date                — default: issue_date + payment_terms_days
                fiscal_period           — default: period covering issue_date
                include_optional        — bool, default False
                include_boarding        — bool|None, None = auto-detect
                include_meals           — bool, default True
                include_laundry         — bool, default True
                auto_apply_scholarships — bool, default True
                auto_apply_discounts    — bool, default True
                payment_terms           — str
                discount_amount         — Decimal, manual discount applied last
                force                   — bool, regenerate even if invoice exists

        Returns:
            FeeInvoice (status DRAFT or VOID)
        """
        if class_enrollment.academic_invoice and not kwargs.get('force', False):
            raise ValueError(
                f"Enrollment already has invoice: "
                f"{class_enrollment.academic_invoice.invoice_number}"
            )

        student        = class_enrollment.student
        session        = class_enrollment.academic_session
        class_instance = class_enrollment.class_instance
        settings       = FinancialSettings.get_instance()

        issue_date    = kwargs.get('issue_date') or get_school_today()
        due_date      = kwargs.get('due_date') or (
            issue_date + timedelta(days=settings.default_payment_terms_days)
        )

        # FIX 3: use get_period_for_date(issue_date) so backdated invoices
        # get the correct period, not whatever period happens to be active today.
        fiscal_period = kwargs.get('fiscal_period') or FiscalPeriod.get_period_for_date(issue_date)

        if not fiscal_period:
            raise ValueError(
                "No fiscal period covers the invoice issue date. "
                "Create one in Admin → Core → Fiscal Periods."
            )

        # --- Fee structures ---
        academic_fee_structure = UnifiedStudentInvoiceGenerator._find_applicable_fee_structure(
            class_enrollment
        )
        if not academic_fee_structure:
            raise FeeStructureNotFoundError(
                f"No active fee structure for {class_instance.academic_level} "
                f"in {session.name}."
            )

        include_boarding       = kwargs.get('include_boarding', None)
        boarding_enrollment    = None
        boarding_fee_structure = None

        if include_boarding is None:
            boarding_enrollment  = student.boarding_enrollments.filter(
                academic_session=session, status='ACTIVE'
            ).first()
            include_boarding = boarding_enrollment is not None
        elif include_boarding:
            boarding_enrollment = student.boarding_enrollments.filter(
                academic_session=session, status='ACTIVE'
            ).first()
            if not boarding_enrollment:
                raise ValueError(
                    f"{student.get_full_name()} has no active boarding "
                    f"enrollment for {session.name}"
                )

        if include_boarding and boarding_enrollment:
            boarding_fee_structure = FeesStructure.objects.filter(
                applicable_sessions=session,
                boarding_type_filter__in=[boarding_enrollment.boarding_type, 'BOARDER_ONLY'],
                is_active=True,
            ).exclude(id=academic_fee_structure.id).order_by('priority').first()

        # --- Create invoice shell ---
        notes_parts = [f"Academic fees for {class_instance.get_display_name()}"]
        if include_boarding and boarding_enrollment:
            notes_parts.append(
                f"Boarding fees ({boarding_enrollment.get_boarding_type_display()})"
            )

        invoice = FeeInvoice.objects.create(
            invoice_number=generate_invoice_number(),
            student=student,
            academic_session=session,
            fiscal_period=fiscal_period,
            fee_structure=academic_fee_structure,
            issue_date=issue_date,
            due_date=due_date,
            status='DRAFT',
            payment_terms=kwargs.get('payment_terms', ''),
            notes="\n".join(notes_parts),
            subtotal_amount=Decimal('0.00'),
            total_amount=Decimal('0.00'),
            balance=Decimal('0.00'),
        )

        # --- Add line items ---
        include_optional = kwargs.get('include_optional', False)
        subtotal         = Decimal('0.00')
        tax_total        = Decimal('0.00')
        items_added      = 0

        def _add_items(fee_structure, skip_keywords=None):
            """Add line items from a fee structure to the invoice.

            skip_keywords: optional list of lowercase strings — items whose
            fee_category.name contains any of these words are skipped.
            Used to suppress meals/laundry on boarding structures when the
            caller opts out via include_meals / include_laundry kwargs.
            """
            nonlocal subtotal, tax_total, items_added
            for si in fee_structure.items.all().order_by('display_order'):
                # FIX 1: renamed from is_applicable_to_student() to
                # is_condition_met_for_student() per fees/models.py refactor.
                if not si.is_condition_met_for_student(student):
                    continue
                if not include_optional and not si.is_mandatory:
                    continue
                if skip_keywords:
                    cat = si.fee_category.name.lower()
                    if any(w in cat for w in skip_keywords):
                        continue

                # Pass session so variable amounts resolve boarding type correctly
                amount = si.get_amount_for_student(student, session)

                # Calculate tax inline — FeesStructureItem has no calculate_tax_amount()
                if si.is_taxable and si.tax_percentage:
                    tax_amount = (
                        amount * si.tax_percentage / Decimal('100')
                    ).quantize(Decimal('0.01'))
                else:
                    tax_amount = Decimal('0.00')

                final_amount = amount + tax_amount

                # FIX 2: set amount_in_school_currency on creation so that
                # FeeInvoice.total_in_school_currency (which sums this field)
                # returns a correct value from the first save.
                # For multi-currency invoices the exchange rate is applied
                # later when the invoice currency is resolved; for the common
                # school-currency case this is already the correct value.
                FeeInvoiceItem.objects.create(
                    invoice=invoice,
                    fee_category=si.fee_category,
                    description=si.get_description(),
                    quantity=Decimal('1.00'),
                    unit_amount=amount,
                    amount=amount,
                    tax_percentage=si.tax_percentage,
                    tax_amount=tax_amount,
                    discount_amount=Decimal('0.00'),
                    discount_percentage=Decimal('0.00'),
                    scholarship_discount_amount=Decimal('0.00'),
                    total_discount_amount=Decimal('0.00'),
                    final_amount=final_amount,
                    original_amount=amount,
                    amount_in_school_currency=final_amount,
                )
                subtotal    += amount
                tax_total   += tax_amount
                items_added += 1

        _add_items(academic_fee_structure)

        if include_boarding and boarding_fee_structure:
            include_meals   = kwargs.get('include_meals', True)
            include_laundry = kwargs.get('include_laundry', True)
            skip = []
            if not include_meals:
                skip += ['meal', 'food', 'catering', 'lunch', 'breakfast', 'dinner']
            if not include_laundry:
                skip += ['laundry', 'washing', 'cleaning']
            _add_items(boarding_fee_structure, skip_keywords=skip or None)

        if items_added == 0:
            invoice.delete()
            raise FeeStructureNotFoundError(
                f"Fee structures exist but contain no applicable items "
                f"for {student.get_full_name()}"
            )

        invoice.subtotal_amount = subtotal
        invoice.tax_amount      = tax_total
        invoice.total_amount    = subtotal + tax_total
        invoice.balance         = invoice.total_amount
        invoice.save()

        # --- Scholarships ---
        if kwargs.get('auto_apply_scholarships', True):
            invoice.auto_scholarships_applied = True
            invoice.save(update_fields=['auto_scholarships_applied'])
            UnifiedStudentInvoiceGenerator._auto_apply_scholarships(invoice)

        # --- Discounts ---
        # Do NOT set auto_discounts_applied=True here — DiscountEngine.apply_all()
        # guards against double-application by checking that flag at the top of
        # its own method and sets it itself at the end.  Pre-setting it here
        # caused apply_all() to exit immediately every time (no discounts applied).
        if kwargs.get('auto_apply_discounts', True):
            UnifiedStudentInvoiceGenerator._auto_apply_discounts(invoice)

        # --- Manual discount ---
        if kwargs.get('discount_amount'):
            manual = Decimal(str(kwargs['discount_amount']))
            invoice.discount_amount += manual
            invoice.total_amount    -= manual
            invoice.balance          = invoice.total_amount
            invoice.save()

        # --- Void if zero total ---
        if invoice.total_amount <= Decimal('0.00'):
            invoice.status  = 'VOID'
            invoice.balance = Decimal('0.00')
            invoice.notes   = (invoice.notes or '') + (
                "\n\nVOID — full amount covered by scholarships/discounts. "
                "No payment required."
            )
            invoice.save()
            class_enrollment.academic_invoice = invoice
            class_enrollment.save(update_fields=['academic_invoice'])
            if boarding_enrollment:
                boarding_enrollment.boarding_invoice = invoice
                boarding_enrollment.save(update_fields=['boarding_invoice'])
            return invoice

        # --- Account transaction ---
        try:
            student_account, _ = StudentAccount.objects.get_or_create(student=student)
            tx_amount = -invoice.total_amount
            AccountTransaction.objects.create(
                student_account=student_account,
                transaction_type='INVOICE',
                amount=tx_amount,
                description=f"Invoice {invoice.invoice_number} — {session.name}",
                balance_after=student_account.get_current_balance() + tx_amount,
                invoice=invoice,
                academic_session=session,
                fiscal_period=fiscal_period,
                reference_number=invoice.invoice_number,
            )
            student_account.last_transaction_date = get_school_current_time()
            student_account.save(update_fields=['last_transaction_date'])
        except Exception:
            logger.exception(
                f"Failed to create AccountTransaction for invoice {invoice.invoice_number}"
            )

        # --- Journal entry ---
        UnifiedStudentInvoiceGenerator._create_journal_entry(invoice)

        # --- Link enrollment ---
        class_enrollment.academic_invoice = invoice
        class_enrollment.save(update_fields=['academic_invoice'])
        if boarding_enrollment:
            boarding_enrollment.boarding_invoice = invoice
            boarding_enrollment.save(update_fields=['boarding_invoice'])

        return invoice

    # =========================================================================
    # FEE STRUCTURE FINDER
    # =========================================================================

    @staticmethod
    def _find_applicable_fee_structure(class_enrollment, target_session=None):
        student        = class_enrollment.student
        class_instance = class_enrollment.class_instance
        session        = target_session or class_enrollment.academic_session

        structures = FeesStructure.objects.filter(
            is_active=True,
            applicable_sessions=session,
            academic_levels=class_instance.academic_level,
            boarding_type_filter__in=['ALL', 'DAY_ONLY'],
        ).order_by('priority')

        if structures.filter(applicable_classes__isnull=False).exists():
            structures = structures.filter(applicable_classes=class_instance)

        for structure in structures:
            if structure.is_applicable_to_student(student, session):
                return structure

        return None

    # =========================================================================
    # SCHOLARSHIP COMBINATION RESOLVER
    # =========================================================================

    @staticmethod
    def _resolve_scholarship_combination(candidates, invoice):
        """
        Return the subset of scholarships to apply based on combination_mode.

        STANDALONE: only the highest-value standalone scholarship applies
        BEST_OF:    only the single highest-value scholarship applies
        ADDITIVE:   all additive scholarships apply, plus the best BEST_OF if any
        """
        if not candidates:
            return []

        modes = {ss.scholarship_program.combination_mode for ss in candidates}

        if 'STANDALONE' in modes:
            standalone = [
                ss for ss in candidates
                if ss.scholarship_program.combination_mode == 'STANDALONE'
            ]
            return [max(standalone, key=lambda ss: _estimate_scholarship_value(ss, invoice))]

        if modes == {'BEST_OF'}:
            return [max(candidates, key=lambda ss: _estimate_scholarship_value(ss, invoice))]

        additive = [ss for ss in candidates if ss.scholarship_program.combination_mode == 'ADDITIVE']
        best_of  = [ss for ss in candidates if ss.scholarship_program.combination_mode == 'BEST_OF']

        result = list(additive)
        if best_of:
            result.append(max(best_of, key=lambda ss: _estimate_scholarship_value(ss, invoice)))
        return result

    # =========================================================================
    # AUTO-APPLY SCHOLARSHIPS
    # =========================================================================

    @staticmethod
    def _auto_apply_scholarships(invoice):
        """
        Apply resolved scholarships to every invoice line item.
 
        Supports three modes per scholarship:
        A. Category-specific (use_category_specific_discounts = True)
        B. Global percentage / waiver / budget-based
        C. Legacy CATEGORY_SPECIFIC program discount_type
 
        FIX (original): After all scholarships are applied, call
        recalculate_totals() on each item then on the invoice.
 
        FIX (new): Added CATEGORY_SPECIFIC fallback in MODE B/C.
        When a student has use_category_specific_discounts=False but the
        program discount_type is CATEGORY_SPECIFIC, the real generator was
        silently applying zero discount because the if/elif chain never
        matched. The fix applies program.discount_percentage or
        program.fixed_discount_amount as a global fallback in this case,
        which is the correct intended behaviour for students who haven't had
        per-category rules configured yet.
        """
        scholarships = StudentScholarship.objects.filter(
            student=invoice.student,
            status='ACTIVE',
            start_date__lte=invoice.issue_date,
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=invoice.issue_date)
        ).select_related('scholarship_program').order_by(
            'scholarship_program__program_type', 'id'
        )
 
        if not scholarships.exists():
            return
 
        resolved = UnifiedStudentInvoiceGenerator._resolve_scholarship_combination(
            list(scholarships), invoice
        )
        if not resolved:
            return
 
        invoice_items              = list(invoice.items.all())
        total_scholarship_discount = Decimal('0.00')
 
        for scholarship in resolved:
            try:
                program           = scholarship.scholarship_program
                scholarship_total = Decimal('0.00')
 
                # ----- MODE A: Category-specific (StudentScholarship level) -----
                if scholarship.use_category_specific_discounts:
                    if not scholarship.category_discounts:
                        logger.error(
                            f"Scholarship {scholarship.id} ({program.name}): "
                            f"use_category_specific_discounts=True but "
                            f"category_discounts is empty."
                        )
                        continue
 
                    for item in invoice_items:
                        discount = scholarship.calculate_discount_for_amount(
                            item.amount, item.fee_category.category_type
                        )
                        if discount <= 0:
                            continue
                        item.scholarship_discount_amount = (
                            item.scholarship_discount_amount or Decimal('0.00')
                        ) + discount
                        item.has_scholarship_discount = True
                        item.save(update_fields=[
                            'scholarship_discount_amount',
                            'has_scholarship_discount',
                        ])
                        scholarship_total += discount
 
                    if scholarship.is_budget_based() and scholarship_total > 0:
                        scholarship.total_amount_used += scholarship_total
                        scholarship.save(update_fields=['total_amount_used'])
 
                # ----- MODE B / C: Global or legacy CATEGORY_SPECIFIC -----
                else:
                    if program.discount_type == 'CATEGORY_SPECIFIC':
                        applicable_cats = program.applicable_fee_categories.all()
                        eligible_items  = (
                            [i for i in invoice_items if i.fee_category in applicable_cats]
                            if applicable_cats.exists() else invoice_items
                        )
                    else:
                        eligible_items = invoice_items
 
                    eligible_total = sum(i.amount for i in eligible_items)
                    if eligible_total <= 0:
                        continue
 
                    # ----- FIX: CATEGORY_SPECIFIC fallback -----
                    # When use_category_specific_discounts=False and the program
                    # discount_type is CATEGORY_SPECIFIC, apply program-level
                    # discount_percentage or fixed_discount_amount as a global
                    # fallback. Previously this fell through to the final else
                    # branch and logged a warning with zero discount applied.
                    if program.discount_type == 'CATEGORY_SPECIFIC' and not scholarship.use_category_specific_discounts:
                        if program.discount_percentage:
                            discount_amount = (
                                eligible_total * program.discount_percentage / Decimal('100')
                            ).quantize(Decimal('0.01'))
                            if program.maximum_award_amount:
                                discount_amount = min(discount_amount, program.maximum_award_amount)
                        elif program.fixed_discount_amount:
                            discount_amount = min(program.fixed_discount_amount, eligible_total)
                        else:
                            logger.warning(
                                f"Scholarship {scholarship.id} ({program.name}): "
                                f"CATEGORY_SPECIFIC with no per-student rules and "
                                f"no global fallback (discount_percentage and "
                                f"fixed_discount_amount are both unset). "
                                f"Zero discount applied."
                            )
                            continue
 
                    elif program.discount_type == 'PERCENTAGE' and program.discount_percentage:
                        discount_amount = (
                            eligible_total * program.discount_percentage / Decimal('100')
                        ).quantize(Decimal('0.01'))
                        if program.maximum_award_amount:
                            discount_amount = min(discount_amount, program.maximum_award_amount)
 
                    elif program.discount_type == 'FULL_WAIVER':
                        discount_amount = eligible_total
 
                    elif program.discount_type == 'FIXED_AMOUNT' and scholarship.amount_awarded > 0:
                        remaining = scholarship.get_remaining_balance()
                        if not remaining or remaining <= 0:
                            continue
                        discount_amount = min(remaining, eligible_total).quantize(Decimal('0.01'))
 
                    else:
                        logger.warning(
                            f"Scholarship {scholarship.id} ({program.name}): "
                            f"no valid discount configuration — skipping."
                        )
                        continue
 
                    if discount_amount <= 0:
                        continue
 
                    # Distribute proportionally across eligible items
                    for item in eligible_items:
                        proportion    = item.amount / eligible_total
                        item_discount = (discount_amount * proportion).quantize(Decimal('0.01'))
                        if item_discount <= 0:
                            continue
                        item.scholarship_discount_amount = (
                            item.scholarship_discount_amount or Decimal('0.00')
                        ) + item_discount
                        item.has_scholarship_discount = True
                        item.save(update_fields=[
                            'scholarship_discount_amount',
                            'has_scholarship_discount',
                        ])
                        scholarship_total += item_discount
 
                    if scholarship.is_budget_based() and scholarship_total > 0:
                        scholarship.total_amount_used += scholarship_total
                        scholarship.save(update_fields=['total_amount_used'])
 
                total_scholarship_discount += scholarship_total
 
            except Exception:
                logger.exception(
                    f"Error applying scholarship {scholarship.id} "
                    f"({scholarship.scholarship_program.name}) "
                    f"to invoice {invoice.invoice_number}"
                )
 
        if total_scholarship_discount > 0:
            for item in invoice_items:
                item.recalculate_totals()
                item.save()
            invoice.recalculate_totals()

    # =========================================================================
    # AUTO-APPLY DISCOUNTS  (via DiscountEngine)
    # =========================================================================

    @staticmethod
    def _auto_apply_discounts(invoice):
        """
        Delegate discount application to DiscountEngine.
        Handles tiered, category-matrix, flat, and combination-mode logic.

        DiscountEngine.apply_all() guards against double-application by
        checking invoice.auto_discounts_applied at the top of the method
        and sets that flag itself before returning.  The caller must NOT
        pre-set it — doing so causes apply_all() to exit immediately with
        no discounts applied.

        Discounts are calculated on item.final_amount (the post-scholarship
        net amount) so stacking is correct: scholarship reduces first, then
        the discount percentage is taken off whatever remains.
        """
        try:
            from fees.models import DiscountEngine
            engine = DiscountEngine(
                student=invoice.student,
                invoice=invoice,
                academic_session=invoice.academic_session,
            )
            engine.apply_all()
        except Exception:
            logger.exception(
                f"DiscountEngine failed for invoice {invoice.invoice_number}"
            )

    # =========================================================================
    # JOURNAL ENTRY
    # =========================================================================

    @staticmethod
    def _create_journal_entry(invoice):
        """
        Create a DRAFT journal entry for the invoice.

        FIX 5: The old code had a dead-code guard (`if not settings`) because
        FinancialSettings.get_instance() never returns None — it always returns
        the singleton or raises. Both get_instance() and get_account_mappings()
        (which raises ValueError when required GL accounts are missing) are now
        inside a single try/except so any configuration error is caught and
        logged rather than crashing the whole invoice generation.
        """
        try:
            if invoice.total_amount <= Decimal('0.00'):
                return None

            from finance.models import Journal, JournalEntry, JournalTransaction
            from finance.utils import generate_journal_entry_number

            settings           = FinancialSettings.get_instance()
            mappings           = settings.get_account_mappings()
            receivable_account = invoice.get_receivable_account()

            if not receivable_account:
                logger.error(
                    f"No receivable account configured — cannot create journal "
                    f"entry for invoice {invoice.invoice_number}"
                )
                return None

            fees_journal, _ = Journal.objects.get_or_create(
                journal_type='FEES',
                defaults={
                    'name': 'Fee Collection Journal',
                    'description': 'Student fee invoices and collections',
                    'is_active': True,
                },
            )

            journal_entry = JournalEntry.objects.create(
                journal=fees_journal,
                entry_number=generate_journal_entry_number(fees_journal),
                entry_date=invoice.issue_date,
                fiscal_period=invoice.fiscal_period,
                academic_session=invoice.academic_session,
                reference_number=invoice.invoice_number,
                description=f"Student Fee Invoice — {invoice.student.get_full_name()}",
                status='DRAFT',
            )

            # Debit: receivables
            JournalTransaction.objects.create(
                journal_entry=journal_entry,
                account=receivable_account,
                amount=invoice.total_amount,
                is_debit=True,
                description=f"Student fees — {invoice.student.get_full_name()}",
            )

            # Credit: revenue (broken down by category type)
            revenue_breakdown = invoice.items.values(
                'fee_category__category_type',
                'fee_category__code',
            ).annotate(total=Sum('final_amount')).order_by('fee_category__category_type')

            if not revenue_breakdown.exists():
                JournalTransaction.objects.create(
                    journal_entry=journal_entry,
                    account=mappings.default_revenue_account,
                    amount=invoice.total_amount,
                    is_debit=False,
                    description=f"Fee revenue — {invoice.academic_session.name}",
                )
            else:
                BOARDING_TYPES = {'BOARDING', 'LAUNDRY'}
                for row in revenue_breakdown:
                    cat_type = row['fee_category__category_type'] or ''
                    cat_code = row['fee_category__code'] or ''
                    amount   = row['total']

                    if cat_type in BOARDING_TYPES:
                        account = mappings.boarding_revenue_account or mappings.default_revenue_account
                        desc    = "Boarding services revenue"
                    elif cat_type == 'UNIFORM':
                        account = mappings.uniform_and_book_sales_account or mappings.default_revenue_account
                        desc    = "Uniform sales revenue"
                    else:
                        account = mappings.default_revenue_account
                        label   = cat_type or cat_code or 'Other'
                        desc    = f"{label.replace('_', ' ').title()} revenue"

                    JournalTransaction.objects.create(
                        journal_entry=journal_entry,
                        account=account,
                        amount=amount,
                        is_debit=False,
                        description=desc,
                    )

            invoice.journal_entry = journal_entry
            invoice.save(update_fields=['journal_entry'])
            return journal_entry

        except Exception:
            logger.exception(
                f"Failed to create journal entry for invoice {invoice.invoice_number}"
            )
            return None

    # =========================================================================
    # BULK GENERATE
    # =========================================================================

    @staticmethod
    @transaction.atomic
    def bulk_generate(enrollments, **kwargs):
        """
        Generate invoices for multiple class enrollments.

        Returns:
            dict with keys: created_count, voided_count, skipped, errors, invoices
        """
        results = {
            'created_count': 0,
            'voided_count':  0,
            'skipped':       0,
            'errors':        [],
            'invoices':      [],
        }

        for enrollment in enrollments:
            try:
                if enrollment.academic_invoice and not kwargs.get('force', False):
                    results['skipped'] += 1
                    continue
                invoice = UnifiedStudentInvoiceGenerator.generate(enrollment, **kwargs)
                if invoice.status == 'VOID':
                    results['voided_count'] += 1
                else:
                    results['created_count'] += 1
                results['invoices'].append(invoice)
            except Exception as e:
                results['errors'].append(
                    f"{enrollment.student.get_full_name()} "
                    f"({enrollment.class_instance}): {e}"
                )
                logger.exception(
                    f"Bulk invoice generation failed for enrollment {enrollment.id}"
                )

        return results


# =============================================================================
# UNIFORM SALE INVOICE GENERATOR
# =============================================================================

class UniformSaleInvoiceGenerator:
    """
    Generate invoices for uniform sales.
    Always separate from enrollment invoices.
    Delegates complex inventory/COGS logic to uniforms.services.
    """

    @staticmethod
    def generate(uniform_sale, **kwargs):
        if uniform_sale.fee_invoice_id and not kwargs.get('force', False):
            raise ValueError(
                f"Uniform sale already has invoice: "
                f"{uniform_sale.fee_invoice.invoice_number}"
            )
        from uniforms.services import UniformInvoiceService
        return UniformInvoiceService.create_invoice_from_sale(uniform_sale, **kwargs)

    @staticmethod
    @transaction.atomic
    def bulk_generate(uniform_sales, **kwargs):
        results = {'created_count': 0, 'skipped': 0, 'errors': [], 'invoices': []}
        for sale in uniform_sales:
            try:
                if sale.fee_invoice_id and not kwargs.get('force', False):
                    results['skipped'] += 1
                    continue
                invoice = UniformSaleInvoiceGenerator.generate(sale, **kwargs)
                results['created_count'] += 1
                results['invoices'].append(invoice)
            except Exception as e:
                results['errors'].append(f"Sale {sale.sale_number}: {e}")
                logger.exception(f"Uniform invoice generation failed for sale {sale.sale_number}")
        return results


# =============================================================================
# INTERNAL GENERATORS  (academic-only / boarding-only)
# =============================================================================

class ClassEnrollmentInvoiceGenerator:
    """Academic-only invoices. Internal use — prefer UnifiedStudentInvoiceGenerator."""

    @staticmethod
    @transaction.atomic
    def generate(class_enrollment, **kwargs):
        kwargs['include_boarding'] = False
        return UnifiedStudentInvoiceGenerator.generate(class_enrollment, **kwargs)

    @staticmethod
    def _find_applicable_fee_structure(class_enrollment):
        return UnifiedStudentInvoiceGenerator._find_applicable_fee_structure(class_enrollment)

    @staticmethod
    @transaction.atomic
    def bulk_generate(enrollments, **kwargs):
        kwargs['include_boarding'] = False
        return UnifiedStudentInvoiceGenerator.bulk_generate(enrollments, **kwargs)


class BoardingEnrollmentInvoiceGenerator:
    """Boarding-only invoices. Internal use — prefer UnifiedStudentInvoiceGenerator."""

    @staticmethod
    @transaction.atomic
    def generate(boarding_enrollment, **kwargs):
        student = boarding_enrollment.student
        session = boarding_enrollment.academic_session

        class_enrollment = student.class_enrollments.filter(
            academic_session=session,
            is_active=True,
            completion_status='ONGOING',
        ).first()

        if not class_enrollment:
            raise ValueError(
                f"{student.get_full_name()} has no active class enrollment "
                f"for {session.name}"
            )

        kwargs['include_boarding'] = True
        return UnifiedStudentInvoiceGenerator.generate(class_enrollment, **kwargs)


# =============================================================================
# PUBLIC API
# =============================================================================

def generate_student_enrollment_invoice(class_enrollment, **kwargs):
    """Primary function — generate invoice for a student enrollment (academic + boarding)."""
    return UnifiedStudentInvoiceGenerator.generate(class_enrollment, **kwargs)


def generate_uniform_sale_invoice(uniform_sale, **kwargs):
    """Generate invoice for a uniform sale. Always separate from enrollment invoices."""
    return UniformSaleInvoiceGenerator.generate(uniform_sale, **kwargs)


def generate_invoice_preview(class_enrollment):
    """
    Pure in-memory invoice preview — zero DB writes.

    FIXED:
    - Removed proportional redistribution of discounts.
    - DiscountEngine is now the single source of truth for BOTH:
        • per-item discount_amount
        • final_amount
    - Prevents CATEGORY_MATRIX corruption (e.g. Meals getting discount).
    """

    import types
    from decimal import Decimal
    from django.db.models import Q
    from core.utils import get_school_today
    import logging

    logger = logging.getLogger(__name__)

    student    = class_enrollment.student
    session    = class_enrollment.academic_session
    issue_date = get_school_today()

    # ── 1. Academic fee structure ────────────────────────────────────────────
    structure = UnifiedStudentInvoiceGenerator._find_applicable_fee_structure(class_enrollment)
    if not structure:
        raise FeeStructureNotFoundError(
            f"No active fee structure for "
            f"{class_enrollment.class_instance.academic_level} in {session.name}."
        )

    # ── 2. Build academic preview items ──────────────────────────────────────
    preview_items = []
    subtotal  = Decimal('0.00')
    tax_total = Decimal('0.00')

    def _add_structure_items(struct):
        nonlocal subtotal, tax_total

        for si in struct.items.select_related(
            'fee_category', 'fee_category__display_group'
        ).order_by('display_order'):

            if not si.is_condition_met_for_student(student):
                continue

            if not si.is_mandatory:
                continue

            amount = si.get_amount_for_student(student, session)

            tax_amount = (
                (amount * si.tax_percentage / Decimal('100')).quantize(Decimal('0.01'))
                if (si.is_taxable and si.tax_percentage)
                else Decimal('0.00')
            )

            item = types.SimpleNamespace(
                fee_category                = si.fee_category,
                description                 = si.get_description(),
                amount                      = amount,
                tax_amount                  = tax_amount,
                scholarship_discount_amount = Decimal('0.00'),
                discount_amount             = Decimal('0.00'),
                final_amount                = amount + tax_amount,
            )

            preview_items.append(item)

            subtotal  += amount
            tax_total += tax_amount

    _add_structure_items(structure)

    if not preview_items:
        raise FeeStructureNotFoundError(
            f"Fee structure exists but has no applicable items "
            f"for {student.get_full_name()}"
        )

    # ── 2b. Boarding ─────────────────────────────────────────────────────────
    boarding_enrollment = student.boarding_enrollments.filter(
        academic_session=session,
        status='ACTIVE',
    ).first()

    boarding_fee_structure = None

    if boarding_enrollment:
        boarding_fee_structure = FeesStructure.objects.filter(
            applicable_sessions=session,
            boarding_type_filter__in=[
                boarding_enrollment.boarding_type,
                'BOARDER_ONLY',
            ],
            is_active=True,
        ).exclude(id=structure.id).order_by('priority').first()

        if boarding_fee_structure:
            _add_structure_items(boarding_fee_structure)

    # ── 3. Scholarships ──────────────────────────────────────────────────────
    total_scholarship = Decimal('0.00')

    scholarships = StudentScholarship.objects.filter(
        student=student,
        status='ACTIVE',
        start_date__lte=issue_date,
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=issue_date)
    ).select_related('scholarship_program')

    for scholarship in scholarships:
        program     = scholarship.scholarship_program
        schol_total = Decimal('0.00')

        # ── CATEGORY-SPECIFIC (student-level)
        if scholarship.use_category_specific_discounts and scholarship.category_discounts:
            for item in preview_items:
                disc = scholarship.calculate_discount_for_amount(
                    item.amount, item.fee_category.category_type
                )
                if disc > 0:
                    item.scholarship_discount_amount += disc
                    item.final_amount = max(
                        item.final_amount - disc, Decimal('0.00')
                    )
                    schol_total += disc

        else:
            eligible_total = sum(i.amount for i in preview_items)
            if eligible_total <= 0:
                continue

            if program.discount_type == 'CATEGORY_SPECIFIC':
                if program.discount_percentage:
                    disc = (
                        eligible_total * program.discount_percentage / Decimal('100')
                    ).quantize(Decimal('0.01'))
                elif getattr(program, 'fixed_discount_amount', None):
                    disc = min(program.fixed_discount_amount, eligible_total)
                else:
                    logger.warning(
                        f"Scholarship {scholarship.id} misconfigured — no fallback"
                    )
                    continue

            elif program.discount_type == 'PERCENTAGE':
                disc = (
                    eligible_total * program.discount_percentage / Decimal('100')
                ).quantize(Decimal('0.01'))

            elif program.discount_type == 'FULL_WAIVER':
                disc = eligible_total

            elif program.discount_type == 'FIXED_AMOUNT':
                remaining = scholarship.get_remaining_balance()
                disc = min(remaining or Decimal('0'), eligible_total)

            else:
                disc = Decimal('0.00')

            if disc > 0:
                for item in preview_items:
                    proportion = item.amount / eligible_total
                    item_disc  = (disc * proportion).quantize(Decimal('0.01'))

                    item.scholarship_discount_amount += item_disc
                    item.final_amount = max(
                        item.final_amount - item_disc, Decimal('0.00')
                    )
                    schol_total += item_disc

        total_scholarship += schol_total

    net_after_scholarships = max(
        subtotal + tax_total - total_scholarship,
        Decimal('0.00')
    )

    # ── 4. Discounts (FIXED) ─────────────────────────────────────────────────
    total_discount   = Decimal('0.00')
    discount_summary = []

    try:
        from fees.models import DiscountEngine

        engine = DiscountEngine(
            student          = student,
            invoice          = None,
            academic_session = session,
        )

        discount_lines = engine.get_preview_discounts(
            base_amount   = net_after_scholarships,
            preview_items = preview_items,  # engine mutates items
        )

        for d in discount_lines:
            discount_summary.append(d)
            total_discount += d['total']

    except Exception:
        logger.exception("Preview discount calculation failed")

    # ❌ REMOVED proportional redistribution

    net_total = max(
        net_after_scholarships - total_discount,
        Decimal('0.00')
    )

    any_scholarship = any(i.scholarship_discount_amount > 0 for i in preview_items)
    any_discount    = any(i.discount_amount > 0 for i in preview_items)

    return {
        'structure':          structure,
        'boarding_structure': boarding_fee_structure,
        'items':              preview_items,
        'subtotal_amount':    subtotal,
        'scholarship_amount': total_scholarship,
        'has_scholarships':   total_scholarship > 0,
        'discount_summary':   discount_summary,
        'discount_amount':    total_discount,
        'has_discounts':      total_discount > 0,
        'tax_amount':         tax_total,
        'net_total':          net_total,
        'will_be_void':       net_total <= Decimal('0.00'),
        'any_scholarship':    any_scholarship,
        'any_discount':       any_discount,
        'has_boarding':       boarding_enrollment is not None,
        'boarding_type':      (
            boarding_enrollment.get_boarding_type_display()
            if boarding_enrollment else None
        ),
        'error': None,
    }
 

# =============================================================================
# DEPRECATED
# =============================================================================

def generate_enrollment_invoice(enrollment, enrollment_type='UNIFIED', **kwargs):
    """Deprecated. Use generate_student_enrollment_invoice() instead."""
    import warnings
    warnings.warn(
        "generate_enrollment_invoice() is deprecated. "
        "Use generate_student_enrollment_invoice() or generate_uniform_sale_invoice().",
        DeprecationWarning,
        stacklevel=2,
    )
    generators = {
        'UNIFIED':  UnifiedStudentInvoiceGenerator,
        'CLASS':    ClassEnrollmentInvoiceGenerator,
        'BOARDING': BoardingEnrollmentInvoiceGenerator,
    }
    generator = generators.get(enrollment_type)
    if not generator:
        raise ValueError(f"Invalid enrollment_type: {enrollment_type}")
    return generator.generate(enrollment, **kwargs)