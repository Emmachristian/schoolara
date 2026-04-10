# uniforms/models.py

"""
Uniform and Measurement Management Models

Comprehensive uniform management system with FULL FINANCIAL INTEGRATION:
- Measurement tracking for students
- Uniform sizing and recommendations
- Inventory management with accounting
- Sales and transactions integrated with fee system
- Automatic invoice and journal entry creation
- Cost of Goods Sold (COGS) tracking

All user tracking handled automatically by BaseModel

CHANGES FROM ORIGINAL:
- Removed MeasurementSession model — measuring a student only requires a
  StudentMeasurement record. measurement_context=UNIFORM_ORDER captures
  why it was taken. academic_session on the measurement provides the
  session context already.
- Removed UniformSize.min_age / max_age — school uniforms are sized by
  body measurements, not age. These fields were always empty.
- Removed UniformItem.category/subcategory (redundant with item_type),
  barcode (redundant with sku), maximum_stock (no enforcement logic),
  supplier_* fields (belong on UniformPurchaseOrder), material and
  care_instructions (retail catalogue fields, unused in business logic).
- FIX: Removed self._sync_parent_stock() from UniformStock.save().
  current_stock sync is handled exclusively by the uniform_stock_post_save
  and uniform_stock_post_delete signals via _sync_item_stock_from_records()
  so the logic lives in one place and correctly respects signal toggling
  during bulk imports.

KEPT:
- MeasurementType as a separate model — allows adding new measurement types
  without code changes, controls active/inactive per type, stores per-type
  validation ranges and units in the database, and sets display order.
- StudentMeasurement.academic_session FK — needed for term-based reporting
  and for the student_measurement_post_save signal to correctly scope
  StudentUniformSize recommendations to the right session.
- StudentUniformSize — stores the recommended size per student/item/session
  for reference and override by staff.
"""

from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
import logging

from utils.models import BaseModel

logger = logging.getLogger(__name__)


# =============================================================================
# MEASUREMENT TYPE
# =============================================================================

class MeasurementType(BaseModel):
    """
    A type of body measurement used for uniform sizing.

    Keeping this as a separate model (rather than a CharField choices list)
    means:
    - New measurement types (e.g. HEAD for caps, INSEAM for trousers) can be
      added by an admin without a code change or migration.
    - Per-type validation ranges (min_value, max_value) are stored in the
      database and configurable without a deploy.
    - Types can be deactivated without deleting historical records.
    - Display order and unit can be managed independently per type.

    The code field is used by recommend_size_from_measurements() in utils.py
    to look up measurements by type (HEIGHT, CHEST, WAIST). Standard codes
    to create on setup: HEIGHT, CHEST, WAIST, HIPS, INSEAM, SHOULDER,
    SLEEVE, NECK, HEAD, SHOE_SIZE, WEIGHT.
    """

    CATEGORY_CHOICES = [
        ('UNIFORM', 'Uniform Measurements'),
        ('SPORTS',  'Sports Equipment'),
        ('HEALTH',  'Health Measurements'),
        ('OTHER',   'Other'),
    ]

    name     = models.CharField("Name",        max_length=50)
    code     = models.CharField(
        "Code",
        max_length=20,
        unique=True,
        db_index=True,
        help_text=(
            "Short uppercase identifier used in code (e.g. HEIGHT, CHEST, WAIST). "
            "Used by the size recommendation algorithm — do not change after setup."
        ),
    )
    category = models.CharField(
        "Category",
        max_length=15,
        choices=CATEGORY_CHOICES,
        default='UNIFORM',
        db_index=True,
    )
    description = models.TextField("Description", blank=True)

    unit = models.ForeignKey(
        'core.UnitOfMeasure',
        on_delete=models.PROTECT,
        related_name='measurement_types',
        verbose_name="Unit of Measure",
        help_text="Unit this measurement is recorded in (cm, kg, etc.)",
    )

    # Validation bounds — used in StudentMeasurement.clean() to catch
    # obvious data-entry errors. These are advisory, not hard limits.
    min_value = models.DecimalField(
        "Minimum Value",
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum reasonable value for this measurement type",
    )
    max_value = models.DecimalField(
        "Maximum Value",
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum reasonable value for this measurement type",
    )

    display_order = models.PositiveIntegerField(
        "Display Order",
        default=100,
        db_index=True,
        help_text="Controls the order measurements appear in forms and reports",
    )
    is_required = models.BooleanField(
        "Is Required",
        default=False,
        help_text="Whether this measurement must be recorded for every student",
    )
    is_active = models.BooleanField("Is Active", default=True, db_index=True)

    class Meta:
        verbose_name        = "Measurement Type"
        verbose_name_plural = "Measurement Types"
        ordering            = ['category', 'display_order', 'name']
        indexes = [
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['code']),
        ]

    def __str__(self):
        return f"{self.name} ({self.unit.abbreviation})"

    def clean(self):
        super().clean()
        if self.min_value is not None and self.max_value is not None:
            if self.min_value >= self.max_value:
                raise ValidationError({
                    'min_value': "Minimum value must be less than maximum value"
                })


# =============================================================================
# STUDENT MEASUREMENT
# =============================================================================

class StudentMeasurement(BaseModel):
    """
    A single body measurement recorded for a student.

    Used for uniform sizing — when a student needs a uniform, staff measure
    them, record the values here, and the system recommends sizes via
    recommend_size_from_measurements() in utils.py.

    academic_session is kept so measurements can be reported and filtered
    by term, and so the student_measurement_post_save signal can scope
    StudentUniformSize recommendations to the correct session.

    is_current=True marks the latest measurement per student + measurement_type.
    save() automatically retires the previous current record so there is
    always exactly one current measurement per student per type.
    """

    MEASUREMENT_CONTEXT_CHOICES = [
        ('ADMISSION',     'Admission'),
        ('ANNUAL',        'Annual Check'),
        ('UNIFORM_ORDER', 'Uniform Order'),
        ('HEALTH_CHECK',  'Health Check'),
        ('UPDATE',        'Update / Correction'),
        ('OTHER',         'Other'),
    ]

    MEASUREMENT_METHOD_CHOICES = [
        ('MANUAL',          'Manual (Tape Measure)'),
        ('DIGITAL',         'Digital Tool'),
        ('ESTIMATED',       'Estimated'),
        ('SELF_REPORTED',   'Self Reported'),
        ('PARENT_REPORTED', 'Parent Reported'),
    ]

    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='measurements',
        verbose_name="Student",
    )
    measurement_type = models.ForeignKey(
        MeasurementType,
        on_delete=models.PROTECT,
        related_name='student_measurements',
        verbose_name="Measurement Type",
        help_text="What is being measured (Height, Chest, Waist, etc.)",
    )
    value = models.DecimalField(
        "Value",
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    measurement_date = models.DateField(
        "Measurement Date",
        default=timezone.now,
        db_index=True,
    )
    academic_session = models.ForeignKey(
        'academics.AcademicSession',
        on_delete=models.CASCADE,
        related_name='student_measurements',
        verbose_name="Academic Session",
        help_text=(
            "Term this measurement was recorded in. Used for session-based "
            "reporting and scoping size recommendations."
        ),
    )

    measurement_context = models.CharField(
        "Context",
        max_length=20,
        choices=MEASUREMENT_CONTEXT_CHOICES,
        default='UNIFORM_ORDER',
    )
    measurement_method = models.CharField(
        "Method",
        max_length=20,
        choices=MEASUREMENT_METHOD_CHOICES,
        default='MANUAL',
    )

    is_verified       = models.BooleanField("Is Verified", default=False, db_index=True)
    verified_by_id    = models.CharField(
        "Verified By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="ID of the user who verified this measurement",
    )
    verification_date = models.DateTimeField("Verification Date", null=True, blank=True)

    is_current = models.BooleanField(
        "Is Current",
        default=True,
        db_index=True,
        help_text="True for the most recent measurement of this type for this student",
    )
    notes = models.TextField("Notes", blank=True)

    class Meta:
        verbose_name        = "Student Measurement"
        verbose_name_plural = "Student Measurements"
        ordering            = ['-measurement_date', 'measurement_type__display_order']
        indexes = [
            models.Index(fields=['student', 'measurement_type']),
            models.Index(fields=['student', 'is_current']),
            models.Index(fields=['measurement_date']),
            models.Index(fields=['academic_session']),
            models.Index(fields=['is_verified']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'measurement_type'],
                condition=models.Q(is_current=True),
                name='unique_current_measurement_per_student_type',
            )
        ]

    def __str__(self):
        return (
            f"{self.student.get_full_name()} — "
            f"{self.measurement_type.name}: "
            f"{self.value} {self.measurement_type.unit.abbreviation}"
        )

    # ── Save ─────────────────────────────────────────────────────────────────

    def save(self, *args, **kwargs):
        """
        When saving a current measurement, retire all previous current
        measurements for the same student + type so only one is ever
        marked is_current=True at a time.
        """
        if self.is_current:
            StudentMeasurement.objects.filter(
                student=self.student,
                measurement_type=self.measurement_type,
                is_current=True,
            ).exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)

    # ── Validation ────────────────────────────────────────────────────────────

    def clean(self):
        super().clean()
        if self.value is None or self.measurement_type_id is None:
            return
        mt = self.measurement_type
        if mt.min_value is not None and self.value < mt.min_value:
            raise ValidationError({
                'value': (
                    f"{mt.name} value {self.value} is below the "
                    f"expected minimum of {mt.min_value} {mt.unit.abbreviation}"
                )
            })
        if mt.max_value is not None and self.value > mt.max_value:
            raise ValidationError({
                'value': (
                    f"{mt.name} value {self.value} is above the "
                    f"expected maximum of {mt.max_value} {mt.unit.abbreviation}"
                )
            })

    # ── Helpers ───────────────────────────────────────────────────────────────

    def get_verified_by_user(self):
        if not self.verified_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            return get_user_model().objects.using('default').get(id=self.verified_by_id)
        except Exception as e:
            logger.error(f"Error fetching verified_by user: {e}")
            return None


# =============================================================================
# UNIFORM SIZE
# =============================================================================

class UniformSize(BaseModel):
    """
    A standard size option for uniform items.

    The min/max measurement ranges (height, chest, waist in cm) are used by
    recommend_size_from_measurements() in utils.py to score each size against
    a student's current measurements and suggest the best fit.

    Age-based size ranges (min_age/max_age) have been removed — school
    uniforms are sized by body measurements, not age.
    """

    SIZE_TYPE_CHOICES = [
        ('NUMERIC',   'Numeric (e.g., 32, 34, 36)'),
        ('ALPHA',     'Alphabetic (e.g., S, M, L, XL)'),
        ('AGE_BASED', 'Age-Based (e.g., 6-7 years)'),
        ('CUSTOM',    'Custom'),
    ]

    name      = models.CharField("Size Name", max_length=20)
    code      = models.CharField("Size Code", max_length=10, unique=True, db_index=True)
    size_type = models.CharField(
        "Size Type", max_length=15, choices=SIZE_TYPE_CHOICES, default='ALPHA'
    )

    # Body measurement ranges (cm) matched against StudentMeasurement values
    # by recommend_size_from_measurements(). Leave blank if not applicable.
    min_height = models.DecimalField(
        "Min Height (cm)", max_digits=5, decimal_places=1, null=True, blank=True
    )
    max_height = models.DecimalField(
        "Max Height (cm)", max_digits=5, decimal_places=1, null=True, blank=True
    )
    min_chest = models.DecimalField(
        "Min Chest (cm)", max_digits=5, decimal_places=1, null=True, blank=True
    )
    max_chest = models.DecimalField(
        "Max Chest (cm)", max_digits=5, decimal_places=1, null=True, blank=True
    )
    min_waist = models.DecimalField(
        "Min Waist (cm)", max_digits=5, decimal_places=1, null=True, blank=True
    )
    max_waist = models.DecimalField(
        "Max Waist (cm)", max_digits=5, decimal_places=1, null=True, blank=True
    )

    description   = models.TextField("Description", blank=True)
    display_order = models.PositiveIntegerField("Display Order", default=100, db_index=True)
    is_active     = models.BooleanField("Is Active", default=True, db_index=True)

    class Meta:
        verbose_name        = "Uniform Size"
        verbose_name_plural = "Uniform Sizes"
        ordering            = ['display_order', 'name']
        indexes = [
            models.Index(fields=['size_type', 'is_active']),
            models.Index(fields=['code']),
        ]

    def __str__(self):
        return self.name


# =============================================================================
# UNIFORM ITEM (INVENTORY)
# =============================================================================

class UniformItem(BaseModel):
    """
    A uniform item held in inventory, with full accounting integration.

    REMOVED FIELDS:
    - barcode            → redundant with sku
    - category           → redundant with item_type; use item_type for filtering
    - subcategory        → redundant with item_type
    - maximum_stock      → no enforcement logic exists anywhere
    - supplier_name/contact/item_code → belong on UniformPurchaseOrder;
                           the same item can come from different suppliers
    - material           → retail catalogue field, unused in business logic
    - care_instructions  → retail catalogue field, unused in business logic

    Do NOT add a 'category' field back. Filter and group by item_type.
    """

    ITEM_TYPE_CHOICES = [
        ('UNIFORM',   'School Uniform'),
        ('SPORTS',    'Sports Uniform'),
        ('PE',        'PE Kit'),
        ('ACCESSORY', 'Accessory'),
        ('SHOES',     'Shoes'),
        ('BAG',       'School Bag'),
        ('OTHER',     'Other'),
    ]

    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('U', 'Unisex'),
    ]

    # ── Basic information ─────────────────────────────────────────────────────

    name        = models.CharField("Item Name",   max_length=100)
    code        = models.CharField("Item Code",   max_length=50, unique=True, db_index=True)
    description = models.TextField("Description", blank=True)
    item_type   = models.CharField(
        "Item Type",
        max_length=20,
        choices=ITEM_TYPE_CHOICES,
        default='UNIFORM',
        db_index=True,
    )
    gender = models.CharField(
        "Gender", max_length=1, choices=GENDER_CHOICES, default='U'
    )

    # ── Sizing ────────────────────────────────────────────────────────────────

    requires_sizing = models.BooleanField("Requires Sizing", default=True)
    available_sizes = models.ManyToManyField(
        UniformSize,
        blank=True,
        related_name='uniform_items',
        verbose_name="Available Sizes",
    )

    # ── Unit of measure ───────────────────────────────────────────────────────

    unit_of_measure = models.ForeignKey(
        'core.UnitOfMeasure',
        on_delete=models.PROTECT,
        related_name='uniform_items',
        verbose_name="Unit of Measure",
        help_text="Unit for inventory tracking (pcs, dozen, etc.)",
    )

    # ── Pricing ───────────────────────────────────────────────────────────────

    unit_cost = models.DecimalField(
        "Unit Cost",
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Cost price per unit (for COGS calculation)",
    )
    selling_price = models.DecimalField(
        "Selling Price",
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
    )
    markup_percentage = models.DecimalField(
        "Markup %",
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Auto-calculated: (selling_price - unit_cost) / unit_cost × 100",
    )

    # ── Inventory ─────────────────────────────────────────────────────────────

    sku = models.CharField(
        "SKU",
        max_length=50,
        blank=True,
        null=True,
        unique=True,
        help_text="Stock Keeping Unit — primary external identifier",
    )

    # Denormalised cache maintained exclusively by the uniform_stock_post_save
    # and uniform_stock_post_delete signals. Never write to this field directly.
    # Always save through UniformStock so the signal fires and keeps this in sync.
    current_stock = models.IntegerField("Current Stock", default=0)
    reorder_level = models.IntegerField(
        "Reorder Level",
        default=10,
        help_text="Low-stock warning triggers when stock falls to or below this",
    )

    # ── Additional details ────────────────────────────────────────────────────

    image = models.ImageField(
        "Item Image", upload_to='uniforms/items/', blank=True, null=True
    )
    color = models.CharField("Color", max_length=50, blank=True)

    # ── Tax configuration ─────────────────────────────────────────────────────

    is_taxable = models.BooleanField("Is Taxable", default=True)
    tax_rate   = models.ForeignKey(
        'core.TaxRate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uniform_items',
        help_text="Tax rate to apply (uses system default if blank)",
    )

    # GL account overrides — leave blank to use FinancialSettings defaults.
    inventory_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='uniform_inventory_items',
        verbose_name="Inventory Account Override",
    )
    cogs_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='uniform_cogs_items',
        verbose_name="COGS Account Override",
    )
    revenue_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='uniform_revenue_items',
        verbose_name="Revenue Account Override",
    )

    # ── Status ────────────────────────────────────────────────────────────────

    is_active    = models.BooleanField("Is Active",    default=True,  db_index=True)
    is_mandatory = models.BooleanField("Is Mandatory", default=False)
    notes        = models.TextField("Notes", blank=True)

    class Meta:
        verbose_name        = "Uniform Item"
        verbose_name_plural = "Uniform Items"
        ordering            = ['item_type', 'name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['item_type', 'is_active']),
            models.Index(fields=['sku']),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def is_low_stock(self):
        return self.current_stock <= self.reorder_level

    @property
    def stock_value(self):
        """Total inventory value at cost price."""
        return self.current_stock * self.unit_cost

    @property
    def stock_value_selling(self):
        """Total inventory value at selling price."""
        return self.current_stock * self.selling_price

    @property
    def potential_profit(self):
        return self.stock_value_selling - self.stock_value

    # ── Save ─────────────────────────────────────────────────────────────────

    def save(self, *args, **kwargs):
        if self.unit_cost > 0:
            self.markup_percentage = round(
                ((self.selling_price - self.unit_cost) / self.unit_cost) * 100, 2
            )
        else:
            self.markup_percentage = Decimal('0.00')
        super().save(*args, **kwargs)

    # ── GL account helpers ────────────────────────────────────────────────────

    def get_inventory_account(self):
        if self.inventory_account:
            return self.inventory_account
        from core.models import FinancialSettings
        settings = FinancialSettings.get_instance()
        if settings:
            return settings.get_expense_mappings().default_inventory_account
        return None

    def get_cogs_account(self):
        if self.cogs_account:
            return self.cogs_account
        from core.models import FinancialSettings
        settings = FinancialSettings.get_instance()
        if settings:
            return settings.get_expense_mappings().default_cogs_account
        return None

    def get_revenue_account(self):
        if self.revenue_account:
            return self.revenue_account
        from core.models import FinancialSettings
        return FinancialSettings.get_uniform_revenue_account()


# =============================================================================
# UNIFORM STOCK (SIZE-SPECIFIC INVENTORY)
# =============================================================================

class UniformStock(BaseModel):
    """
    Stock level for a uniform item, optionally scoped to a size.

    For sized items (shirts, trousers, shoes) each size gets its own record.
    For unsized items (belts, ties, bags) a single record with size=None
    tracks the total stock.

    IMPORTANT — current_stock synchronisation:
    UniformItem.current_stock is a denormalised cache. It is kept in sync
    exclusively by the uniform_stock_post_save and uniform_stock_post_delete
    signals via _sync_item_stock_from_records(). This save() method
    intentionally does NOT call any sync helper directly — doing so would
    run the same Sum()+update() twice and would silently skip the sync
    whenever signals are disabled for bulk imports.

    Rule: never write to UniformItem.current_stock directly. Always save
    through UniformStock and let the signal handle the sync.
    """

    uniform_item = models.ForeignKey(
        UniformItem,
        on_delete=models.CASCADE,
        related_name='stock_records',
    )
    size = models.ForeignKey(
        UniformSize,
        on_delete=models.CASCADE,
        related_name='stock_records',
        null=True,
        blank=True,
        help_text="Leave blank for items that do not require sizing",
    )

    quantity          = models.IntegerField("Quantity in Stock", default=0)
    reserved_quantity = models.IntegerField(
        "Reserved Quantity",
        default=0,
        help_text="Quantity reserved in pending sales",
    )

    location   = models.CharField("Storage Location", max_length=100, blank=True)
    bin_number = models.CharField("Bin Number",        max_length=50,  blank=True)

    total_cost_value = models.DecimalField(
        "Total Cost Value",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Cached: quantity × unit_cost",
    )
    total_selling_value = models.DecimalField(
        "Total Selling Value",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Cached: quantity × selling_price",
    )

    class Meta:
        verbose_name        = "Uniform Stock"
        verbose_name_plural = "Uniform Stock"
        ordering            = ['uniform_item', 'size']
        indexes = [
            models.Index(fields=['uniform_item', 'size']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['uniform_item', 'size'],
                condition=models.Q(size__isnull=False),
                name='unique_stock_per_item_and_size',
            ),
            models.UniqueConstraint(
                fields=['uniform_item'],
                condition=models.Q(size__isnull=True),
                name='unique_stock_per_unsized_item',
            ),
        ]

    def __str__(self):
        size_info = f" - Size {self.size.name}" if self.size else " (No Size)"
        return f"{self.uniform_item.name}{size_info}: {self.quantity} units"

    @property
    def available_quantity(self):
        return self.quantity - self.reserved_quantity

    def save(self, *args, **kwargs):
        """
        Recalculate cached value fields then save.

        current_stock on the parent UniformItem is synced by the
        uniform_stock_post_save signal after this call — not here,
        so the sync logic lives in exactly one place.
        """
        self.total_cost_value    = self.quantity * self.uniform_item.unit_cost
        self.total_selling_value = self.quantity * self.uniform_item.selling_price
        super().save(*args, **kwargs)


# =============================================================================
# UNIFORM PURCHASE ORDER
# =============================================================================

class UniformPurchaseOrder(BaseModel):
    """
    Purchase order raised when restocking uniform inventory.

    Supplier information lives here — not on UniformItem — because the same
    item can come from different suppliers over time, and storing it here
    preserves the full procurement history.
    """

    STATUS_CHOICES = [
        ('DRAFT',     'Draft'),
        ('SUBMITTED', 'Submitted'),
        ('APPROVED',  'Approved'),
        ('ORDERED',   'Ordered'),
        ('RECEIVED',  'Received'),
        ('PARTIAL',   'Partially Received'),
        ('CANCELLED', 'Cancelled'),
    ]

    po_number = models.CharField("PO Number", max_length=50, unique=True, db_index=True)

    supplier_name    = models.CharField("Supplier Name",    max_length=100)
    supplier_contact = models.CharField("Supplier Contact", max_length=100, blank=True)
    supplier_email   = models.EmailField("Supplier Email",  blank=True)
    supplier_phone   = models.CharField("Supplier Phone",   max_length=20,  blank=True)

    order_date             = models.DateField("Order Date",             default=timezone.now, db_index=True)
    expected_delivery_date = models.DateField("Expected Delivery Date", null=True, blank=True)
    actual_delivery_date   = models.DateField("Actual Delivery Date",   null=True, blank=True)

    subtotal      = models.DecimalField("Subtotal",      max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax_amount    = models.DecimalField("Tax Amount",    max_digits=12, decimal_places=2, default=Decimal('0.00'))
    shipping_cost = models.DecimalField("Shipping Cost", max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount  = models.DecimalField("Total Amount",  max_digits=12, decimal_places=2, default=Decimal('0.00'))
    payment_terms = models.CharField(   "Payment Terms", max_length=100,                  blank=True)
    paid_amount   = models.DecimalField("Paid Amount",   max_digits=12, decimal_places=2, default=Decimal('0.00'))
    balance_due   = models.DecimalField("Balance Due",   max_digits=12, decimal_places=2, default=Decimal('0.00'))

    journal_entry = models.ForeignKey(
        'finance.JournalEntry',
        verbose_name="Journal Entry",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='uniform_purchase_orders',
        help_text="Goods-receipt journal entry created when PO status → RECEIVED",
    )
    auto_create_journal_entry = models.BooleanField(
        "Auto-Create Journal Entry", default=True
    )

    fiscal_period = models.ForeignKey(
        'core.FiscalPeriod',
        verbose_name="Fiscal Period",
        on_delete=models.PROTECT,
        related_name='uniform_purchase_orders',
        null=True, blank=True,
    )

    status = models.CharField(
        "Status", max_length=15, choices=STATUS_CHOICES, default='DRAFT', db_index=True
    )
    approved_by_id = models.CharField("Approved By ID", max_length=50, null=True, blank=True)
    approved_at    = models.DateTimeField("Approved At", null=True, blank=True)
    notes          = models.TextField("Notes", blank=True)

    class Meta:
        verbose_name        = "Uniform Purchase Order"
        verbose_name_plural = "Uniform Purchase Orders"
        ordering            = ['-order_date']
        indexes = [
            models.Index(fields=['po_number']),
            models.Index(fields=['order_date']),
            models.Index(fields=['status']),
            models.Index(fields=['fiscal_period']),
        ]

    def __str__(self):
        return f"PO {self.po_number} - {self.supplier_name}"

    def get_payable_account(self):
        from core.models import FinancialSettings
        settings = FinancialSettings.get_instance()
        return settings.get_account_mappings().default_payable_account if settings else None

    def get_approved_by_user(self):
        if not self.approved_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            return get_user_model().objects.using('default').get(id=self.approved_by_id)
        except Exception as e:
            logger.error(f"Error fetching approved_by user: {e}")
            return None


class UniformPurchaseOrderItem(BaseModel):
    """Line item on a uniform purchase order."""

    purchase_order = models.ForeignKey(
        UniformPurchaseOrder, on_delete=models.CASCADE, related_name='items'
    )
    uniform_item = models.ForeignKey(
        UniformItem, on_delete=models.CASCADE, related_name='purchase_order_items'
    )
    size = models.ForeignKey(
        UniformSize,
        on_delete=models.CASCADE,
        related_name='purchase_order_items',
        null=True, blank=True,
    )

    quantity_ordered  = models.PositiveIntegerField("Quantity Ordered")
    quantity_received = models.PositiveIntegerField("Quantity Received", default=0)
    unit_price        = models.DecimalField("Unit Price",  max_digits=10, decimal_places=2)
    total_price       = models.DecimalField("Total Price", max_digits=12, decimal_places=2)

    # Currency may differ from school currency (e.g. South Sudan school buying
    # uniforms priced in UGX). Leave blank to inherit from the parent PO.
    currency = models.CharField("Currency", max_length=3, blank=True)
    notes    = models.TextField("Notes", blank=True)

    class Meta:
        verbose_name        = "Purchase Order Item"
        verbose_name_plural = "Purchase Order Items"
        ordering            = ['purchase_order', 'uniform_item']

    def __str__(self):
        size_info = f" - Size {self.size.name}" if self.size else ""
        return f"{self.uniform_item.name}{size_info}: {self.quantity_ordered} units"

    def save(self, *args, **kwargs):
        self.total_price = self.quantity_ordered * self.unit_price
        super().save(*args, **kwargs)


# =============================================================================
# UNIFORM SALE / ISSUANCE
# =============================================================================

class UniformSale(BaseModel):
    """
    Sale or issuance of uniforms to a student, with full financial integration.

    CURRENCY
    --------
    currency      — ISO code the sale is denominated in (blank = school currency).
    exchange_rate — rate between sale currency and school currency at time of
                    sale. Stored permanently and never recalculated.

    ACADEMIC SESSION
    ----------------
    Not stored directly. Use the `academic_session` property which derives it
    from fiscal_period.related_academic_session. Use
    select_related('fiscal_period__related_academic_session') on querysets
    to avoid N+1 queries.

    STOCK MOVEMENT
    --------------
    Stock is decremented only when the sale is issued (status → ISSUED) via
    the uniform_sale_issue view. It is restored on cancellation or return via
    cancel_uniform_sale() / return_uniform_sale() in utils.py.
    Creating or editing UniformSaleItems does NOT move stock — items only
    leave (or return to) the warehouse when physically handed over.
    """

    STATUS_CHOICES = [
        ('DRAFT',     'Draft'),
        ('PENDING',   'Pending Payment'),
        ('PAID',      'Paid'),
        ('PARTIAL',   'Partially Paid'),
        ('ISSUED',    'Issued'),
        ('CANCELLED', 'Cancelled'),
        ('RETURNED',  'Returned'),
    ]

    SALE_TYPE_CHOICES = [
        ('SALE',        'Sale'),
        ('ISSUANCE',    'Free Issuance'),
        ('LOAN',        'Temporary Loan'),
        ('REPLACEMENT', 'Replacement'),
    ]

    sale_number = models.CharField(
        "Sale Number", max_length=50, unique=True, db_index=True
    )
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='uniform_sales',
        verbose_name="Student",
    )
    fiscal_period = models.ForeignKey(
        'core.FiscalPeriod',
        on_delete=models.PROTECT,
        related_name='uniform_sales',
        verbose_name="Fiscal Period",
        help_text="Fiscal period when this sale was recorded",
    )
    sale_type = models.CharField(
        "Sale Type", max_length=20, choices=SALE_TYPE_CHOICES, default='SALE'
    )
    sale_date = models.DateField("Sale Date", default=timezone.now, db_index=True)

    # ── Currency ──────────────────────────────────────────────────────────────

    currency = models.CharField(
        "Sale Currency", max_length=3, blank=True,
        help_text="Blank = school's primary currency",
    )
    exchange_rate = models.DecimalField(
        "Exchange Rate",
        max_digits=12,
        decimal_places=6,
        default=Decimal('1.000000'),
        help_text="Rate at time of sale — stored permanently, never recalculated",
    )

    # ── Financial integration ─────────────────────────────────────────────────

    fee_invoice = models.OneToOneField(
        'fees.FeeInvoice',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='uniform_sale',
        verbose_name="Fee Invoice",
    )
    auto_create_invoice = models.BooleanField("Auto-Create Invoice", default=True)

    # ── Amounts ───────────────────────────────────────────────────────────────

    subtotal        = models.DecimalField("Subtotal",        max_digits=12, decimal_places=2, default=Decimal('0.00'))
    discount_amount = models.DecimalField("Discount Amount", max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax_amount      = models.DecimalField("Tax Amount",      max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount    = models.DecimalField("Total Amount",    max_digits=12, decimal_places=2, default=Decimal('0.00'))
    paid_amount     = models.DecimalField("Paid Amount",     max_digits=12, decimal_places=2, default=Decimal('0.00'))
    balance         = models.DecimalField("Balance",         max_digits=12, decimal_places=2, default=Decimal('0.00'))

    total_cost              = models.DecimalField("Total Cost (COGS)", max_digits=12, decimal_places=2, default=Decimal('0.00'))
    gross_profit            = models.DecimalField("Gross Profit",      max_digits=12, decimal_places=2, default=Decimal('0.00'))
    gross_margin_percentage = models.DecimalField("Gross Margin %",    max_digits=5,  decimal_places=2, default=Decimal('0.00'))

    # ── Journal entry ─────────────────────────────────────────────────────────

    journal_entry = models.ForeignKey(
        'finance.JournalEntry',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='uniform_sales',
        verbose_name="Journal Entry",
    )
    auto_create_journal_entry = models.BooleanField("Auto-Create Journal Entry", default=True)

    # ── Status ────────────────────────────────────────────────────────────────

    status = models.CharField(
        "Status", max_length=15, choices=STATUS_CHOICES, default='DRAFT', db_index=True
    )

    # ── Payment ───────────────────────────────────────────────────────────────

    payment_method = models.ForeignKey(
        'core.PaymentMethod',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='uniform_sales',
        verbose_name="Payment Method",
    )
    payment_reference = models.CharField("Payment Reference", max_length=100, blank=True)

    # ── Issuance ──────────────────────────────────────────────────────────────

    issued_by_id = models.CharField("Issued By ID", max_length=50, null=True, blank=True)
    issued_at    = models.DateTimeField("Issued At", null=True, blank=True)
    return_date  = models.DateField(
        "Expected Return Date", null=True, blank=True,
        help_text="For loaned items — when they should be returned",
    )

    # ── Discount ──────────────────────────────────────────────────────────────

    discount_reason         = models.CharField("Discount Reason",         max_length=200, blank=True)
    discount_approved_by_id = models.CharField("Discount Approved By ID", max_length=50,  null=True, blank=True)

    # ── Cancellation ──────────────────────────────────────────────────────────

    cancelled           = models.BooleanField("Cancelled",         default=False, db_index=True)
    cancelled_on        = models.DateTimeField("Cancelled On",     null=True, blank=True)
    cancelled_by_id     = models.CharField("Cancelled By ID",      max_length=50, null=True, blank=True)
    cancellation_reason = models.TextField("Cancellation Reason",  blank=True)
    cancellation_journal_entry = models.ForeignKey(
        'finance.JournalEntry',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='cancelled_uniform_sales',
        verbose_name="Cancellation Journal Entry",
    )

    # ── Return ────────────────────────────────────────────────────────────────

    returned         = models.BooleanField("Returned",     default=False, db_index=True)
    returned_on      = models.DateTimeField("Returned On", null=True, blank=True)
    returned_by_id   = models.CharField("Returned By ID",  max_length=50, null=True, blank=True)
    return_reason    = models.TextField("Return Reason",   blank=True)
    return_condition = models.CharField(
        "Return Condition",
        max_length=20,
        choices=[
            ('GOOD',     'Good Condition — Can Resell'),
            ('FAIR',     'Fair Condition — Can Resell with Discount'),
            ('WORN',     'Worn — Cannot Resell'),
            ('DAMAGED',  'Damaged — Cannot Resell'),
            ('UNUSABLE', 'Unusable — Write Off'),
        ],
        blank=True,
    )
    return_journal_entry = models.ForeignKey(
        'finance.JournalEntry',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='returned_uniform_sales',
        verbose_name="Return Journal Entry",
    )
    partial_return = models.BooleanField("Partial Return", default=False)

    notes          = models.TextField("Notes",          blank=True)
    internal_notes = models.TextField("Internal Notes", blank=True)

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def academic_session(self):
        try:
            return self.fiscal_period.related_academic_session
        except Exception:
            return None

    @property
    def is_active(self):
        return not self.cancelled and not self.returned

    @property
    def effective_total_amount(self):
        return self.total_amount if self.is_active else Decimal('0.00')

    @property
    def sale_state(self):
        if self.cancelled:
            return "CANCELLED"
        if self.returned:
            return "RETURNED"
        return self.status

    @property
    def can_be_cancelled_bool(self):
        ok, _ = self.can_be_cancelled()
        return ok

    @property
    def can_be_returned_bool(self):
        ok, _ = self.can_be_returned()
        return ok

    # ── GL account helpers ────────────────────────────────────────────────────

    def get_inventory_account(self):
        from core.models import FinancialSettings
        settings = FinancialSettings.get_instance()
        if not settings:
            return None
        for item in self.items.select_related('uniform_item').all():
            account = item.uniform_item.get_inventory_account()
            if account:
                return account
        return settings.get_expense_mappings().default_inventory_account

    def get_cogs_account(self):
        from core.models import FinancialSettings
        settings = FinancialSettings.get_instance()
        return settings.get_expense_mappings().default_cogs_account if settings else None

    def get_revenue_account(self):
        from core.models import FinancialSettings
        return FinancialSettings.get_uniform_revenue_account()

    def get_receivable_account(self):
        from core.models import FinancialSettings
        settings = FinancialSettings.get_instance()
        return settings.get_account_mappings().student_receivables_account if settings else None

    # ── Status helpers ────────────────────────────────────────────────────────

    def can_be_cancelled(self):
        if self.cancelled:
            return False, "Sale already cancelled"
        if self.returned:
            return False, "Sale was already returned"
        if self.status == 'ISSUED':
            return False, "Cannot cancel an issued sale — process a return instead"
        if self.fiscal_period and getattr(self.fiscal_period, 'is_closed', False):
            return False, "Cannot cancel a sale from a closed fiscal period"
        return True, "OK"

    def can_be_returned(self):
        if self.cancelled:
            return False, "Sale was cancelled — nothing to return"
        if self.returned:
            return False, "Items already returned"
        if self.status != 'ISSUED':
            return False, f"Items must be issued before return (status: {self.get_status_display()})"
        if self.fiscal_period and getattr(self.fiscal_period, 'is_closed', False):
            return False, "Cannot process a return from a closed fiscal period"
        return True, "OK"

    # ── User helpers ──────────────────────────────────────────────────────────

    def _get_user(self, user_id_field):
        user_id = getattr(self, user_id_field, None)
        if not user_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            return get_user_model().objects.using('default').get(id=user_id)
        except Exception as e:
            logger.error(f"Error fetching user {user_id_field}: {e}")
            return None

    def get_issued_by_user(self):            return self._get_user('issued_by_id')
    def get_discount_approved_by_user(self): return self._get_user('discount_approved_by_id')
    def get_cancelled_by_user(self):         return self._get_user('cancelled_by_id')
    def get_returned_by_user(self):          return self._get_user('returned_by_id')

    # ── Audit trail ───────────────────────────────────────────────────────────

    def get_audit_trail(self):
        trail = [
            {
                'action':    'CREATED',
                'timestamp': self.created_at,
                'user':      self.get_created_by(),
                'details':   f"Uniform sale {self.sale_number} created for {self.student.get_full_name()}",
            }
        ]
        if self.fee_invoice:
            trail.append({
                'action':    'INVOICE_CREATED',
                'timestamp': self.fee_invoice.created_at,
                'details':   f"Fee invoice {self.fee_invoice.invoice_number} generated",
            })
        if self.journal_entry:
            trail.append({
                'action':    'JOURNAL_ENTRY_CREATED',
                'timestamp': self.journal_entry.created_at,
                'details':   f"Journal entry {self.journal_entry.entry_number} created",
            })
        if self.discount_approved_by_id and self.discount_amount > 0:
            trail.append({
                'action':    'DISCOUNT_APPROVED',
                'timestamp': self.updated_at,
                'user':      self.get_discount_approved_by_user(),
                'details':   f"Discount of {self.discount_amount:,.2f} approved: {self.discount_reason}",
            })
        if self.issued_at:
            trail.append({
                'action':    'ITEMS_ISSUED',
                'timestamp': self.issued_at,
                'user':      self.get_issued_by_user(),
                'details':   "Uniforms physically issued to student",
            })
        if self.cancelled and self.cancelled_on:
            trail.append({
                'action':    'CANCELLED',
                'timestamp': self.cancelled_on,
                'user':      self.get_cancelled_by_user(),
                'details':   f"Sale cancelled: {self.cancellation_reason}",
            })
        if self.returned and self.returned_on:
            trail.append({
                'action':    'ITEMS_RETURNED',
                'timestamp': self.returned_on,
                'user':      self.get_returned_by_user(),
                'details':   (
                    f"Items returned in {self.get_return_condition_display()} condition: "
                    f"{self.return_reason}"
                ),
            })
        trail.sort(key=lambda x: x['timestamp'])
        return trail

    # ── Totals ────────────────────────────────────────────────────────────────

    def calculate_totals(self):
        items             = self.items.all()
        self.subtotal     = sum(item.total_price for item in items)
        self.total_cost   = sum(item.total_cost  for item in items)
        self.tax_amount   = sum(item.tax_amount  for item in items)
        self.total_amount = self.subtotal + self.tax_amount - self.discount_amount
        self.balance      = self.total_amount - self.paid_amount
        if self.total_amount > 0:
            self.gross_profit            = self.total_amount - self.total_cost
            self.gross_margin_percentage = (self.gross_profit / self.total_amount) * 100
        else:
            self.gross_profit            = Decimal('0.00')
            self.gross_margin_percentage = Decimal('0.00')
        self.save()

    # ── Validation ────────────────────────────────────────────────────────────

    def clean(self):
        super().clean()
        errors = {}
        if self.cancelled and self.returned:
            errors['cancelled'] = "Sale cannot be both cancelled and returned."
            errors['returned']  = "Sale cannot be both cancelled and returned."
        if self.cancelled and not self.cancellation_reason:
            errors['cancellation_reason'] = "Cancellation reason is required."
        if self.returned:
            if not self.return_reason:
                errors['return_reason'] = "Return reason is required."
            if not self.return_condition:
                errors['return_condition'] = "Return condition is required."
        if (self.cancelled or self.returned) and self.status == 'DRAFT':
            errors['status'] = "Cannot cancel or return a draft sale."
        if self.total_amount < 0:
            errors['total_amount'] = "Total amount cannot be negative."
        if self.paid_amount < 0:
            errors['paid_amount'] = "Paid amount cannot be negative."
        if self.paid_amount > self.total_amount:
            errors['paid_amount'] = "Paid amount cannot exceed total amount."
        if self.exchange_rate <= 0:
            errors['exchange_rate'] = "Exchange rate must be greater than zero."
        if errors:
            raise ValidationError(errors)

    # ── Save ─────────────────────────────────────────────────────────────────

    def save(self, *args, **kwargs):
        if self.total_amount > 0:
            self.gross_profit            = self.total_amount - self.total_cost
            self.gross_margin_percentage = (self.gross_profit / self.total_amount) * 100
        else:
            self.gross_profit            = Decimal('0.00')
            self.gross_margin_percentage = Decimal('0.00')
        if self.cancelled and self.status != 'CANCELLED':
            self.status = 'CANCELLED'
        elif self.returned and self.status != 'RETURNED':
            self.status = 'RETURNED'
        super().save(*args, **kwargs)

    # ── Meta ─────────────────────────────────────────────────────────────────

    class Meta:
        verbose_name        = "Uniform Sale"
        verbose_name_plural = "Uniform Sales"
        ordering            = ['-sale_date', '-created_at']
        indexes = [
            models.Index(fields=['sale_number']),
            models.Index(fields=['student', 'sale_date']),
            models.Index(fields=['status']),
            models.Index(fields=['sale_date']),
            models.Index(fields=['fiscal_period']),
            models.Index(fields=['cancelled']),
            models.Index(fields=['returned']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(total_amount__gte=0),
                name='uniform_sale_total_amount_non_negative',
            ),
            models.CheckConstraint(
                check=models.Q(paid_amount__gte=0),
                name='uniform_sale_paid_amount_non_negative',
            ),
            models.CheckConstraint(
                check=models.Q(discount_amount__gte=0),
                name='uniform_sale_discount_amount_non_negative',
            ),
            models.CheckConstraint(
                check=models.Q(exchange_rate__gt=0),
                name='uniform_sale_exchange_rate_positive',
            ),
        ]

    def __str__(self):
        suffix = (
            " [CANCELLED]" if self.cancelled else
            " [RETURNED]"  if self.returned  else ""
        )
        return (
            f"{self.sale_number} - "
            f"{self.student.get_full_name()} - "
            f"{self.total_amount:,.2f}{suffix}"
        )


# =============================================================================
# UNIFORM SALE ITEM
# =============================================================================

class UniformSaleItem(BaseModel):
    """
    A single line on a uniform sale.

    NOTE ON STOCK:
    Creating or deleting a UniformSaleItem does NOT move stock.
    Stock is decremented only when the sale is issued (uniform_sale_issue view)
    and restored on return (return_uniform_sale in utils.py).
    """

    sale         = models.ForeignKey(UniformSale, on_delete=models.CASCADE, related_name='items')
    uniform_item = models.ForeignKey(UniformItem, on_delete=models.CASCADE, related_name='sale_items')
    size         = models.ForeignKey(
        UniformSize,
        on_delete=models.CASCADE,
        related_name='sale_items',
        null=True, blank=True,
    )

    quantity   = models.PositiveIntegerField("Quantity")
    unit_price = models.DecimalField("Unit Price",        max_digits=10, decimal_places=2)
    unit_cost  = models.DecimalField(
        "Unit Cost",
        max_digits=10,
        decimal_places=2,
        help_text="Cost per unit at time of sale (for COGS calculation)",
    )
    total_price = models.DecimalField("Total Price",       max_digits=12, decimal_places=2)
    total_cost  = models.DecimalField("Total Cost (COGS)", max_digits=12, decimal_places=2)

    tax_rate = models.ForeignKey(
        'core.TaxRate',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='uniform_sale_items',
    )
    tax_percentage = models.DecimalField(
        "Tax %", max_digits=5, decimal_places=2, default=Decimal('0.00')
    )
    tax_amount = models.DecimalField(
        "Tax Amount", max_digits=10, decimal_places=2, default=Decimal('0.00')
    )

    # Line-level discount (e.g. staff-child rate).
    # Sale-wide discounts live on UniformSale.discount_amount.
    discount_percentage = models.DecimalField(
        "Discount %",      max_digits=5,  decimal_places=2, default=Decimal('0.00')
    )
    discount_amount = models.DecimalField(
        "Discount Amount", max_digits=10, decimal_places=2, default=Decimal('0.00')
    )

    notes = models.TextField("Notes", blank=True)

    class Meta:
        verbose_name        = "Uniform Sale Item"
        verbose_name_plural = "Uniform Sale Items"
        ordering            = ['sale', 'uniform_item']

    def __str__(self):
        size_info = f" - Size {self.size.name}" if self.size else ""
        return f"{self.uniform_item.name}{size_info}: {self.quantity} units"

    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        self.total_cost  = self.quantity * self.unit_cost
        if self.discount_percentage > 0:
            self.discount_amount = (self.total_price * self.discount_percentage) / 100
        taxable_amount = self.total_price - self.discount_amount
        if self.tax_percentage > 0:
            self.tax_amount = (taxable_amount * self.tax_percentage) / 100
        super().save(*args, **kwargs)


# =============================================================================
# STUDENT UNIFORM SIZE (RECOMMENDATION)
# =============================================================================

class StudentUniformSize(BaseModel):
    """
    The recommended (or confirmed) uniform size for a student per item per
    academic session.

    Populated automatically by the student_measurement_post_save signal via
    recommend_size_from_measurements() whenever a verified measurement is
    saved. Staff can override by changing recommended_size and setting
    sizing_method to FITTED or PARENT_PROVIDED accordingly.

    confidence_level and alternative_sizes come from the recommendation
    algorithm and give staff context when reviewing or overriding a suggestion.
    """

    SIZING_METHOD_CHOICES = [
        ('MEASURED',        'Based on Measurements'),
        ('FITTED',          'Physically Fitted'),
        ('PREVIOUS_ORDER',  'Based on Previous Order'),
        ('PARENT_PROVIDED', 'Parent Provided'),
        ('ESTIMATED',       'Estimated'),
    ]

    CONFIDENCE_LEVEL_CHOICES = [
        ('HIGH',   'High Confidence'),
        ('MEDIUM', 'Medium Confidence'),
        ('LOW',    'Low Confidence'),
    ]

    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='uniform_sizes',
        verbose_name="Student",
    )
    uniform_item = models.ForeignKey(
        UniformItem,
        on_delete=models.CASCADE,
        related_name='student_size_recommendations',
        verbose_name="Uniform Item",
    )
    recommended_size = models.ForeignKey(
        UniformSize,
        on_delete=models.CASCADE,
        related_name='student_recommendations',
        verbose_name="Recommended Size",
    )
    academic_session = models.ForeignKey(
        'academics.AcademicSession',
        on_delete=models.CASCADE,
        related_name='student_uniform_sizes',
        verbose_name="Academic Session",
    )

    sizing_method = models.CharField(
        "Sizing Method",
        max_length=20,
        choices=SIZING_METHOD_CHOICES,
        default='MEASURED',
    )
    confidence_level = models.CharField(
        "Confidence Level",
        max_length=15,
        choices=CONFIDENCE_LEVEL_CHOICES,
        default='HIGH',
    )
    recommendation_date = models.DateField(
        "Recommendation Date", default=timezone.now
    )
    # Ordered list of alternative UniformSize PKs from the algorithm.
    alternative_sizes = models.JSONField(
        "Alternative Sizes",
        blank=True,
        null=True,
        help_text="Ordered list of alternative size PKs (from recommendation algorithm)",
    )
    growth_allowance = models.BooleanField(
        "Growth Allowance",
        default=True,
        help_text="Whether one size up was applied for expected growth",
    )
    is_current = models.BooleanField("Is Current", default=True, db_index=True)
    notes      = models.TextField("Notes", blank=True)

    class Meta:
        verbose_name        = "Student Uniform Size"
        verbose_name_plural = "Student Uniform Sizes"
        ordering            = ['-recommendation_date']
        indexes = [
            models.Index(fields=['student', 'uniform_item']),
            models.Index(fields=['academic_session']),
            models.Index(fields=['is_current']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'uniform_item', 'academic_session'],
                condition=models.Q(is_current=True),
                name='unique_current_uniform_size_per_student_item_session',
            )
        ]

    def __str__(self):
        return (
            f"{self.student.get_full_name()} — "
            f"{self.uniform_item.name}: Size {self.recommended_size.name}"
        )

    def save(self, *args, **kwargs):
        if self.is_current:
            StudentUniformSize.objects.filter(
                student=self.student,
                uniform_item=self.uniform_item,
                academic_session=self.academic_session,
                is_current=True,
            ).exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)