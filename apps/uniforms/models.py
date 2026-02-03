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
"""

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
import logging

from utils.models import BaseModel

logger = logging.getLogger(__name__)


# =============================================================================
# MEASUREMENT TYPE MODEL
# =============================================================================

class MeasurementType(BaseModel):
    """Types of measurements for uniform sizing"""
    
    MEASUREMENT_CATEGORIES = [
        ('UNIFORM', 'Uniform Measurements'),
        ('SPORTS', 'Sports Equipment'),
        ('HEALTH', 'Health Measurements'),
        ('OTHER', 'Other'),
    ]
    
    # -------------------------------------------------------------------------
    # BASIC INFORMATION
    # -------------------------------------------------------------------------
    
    name = models.CharField("Measurement Name", max_length=30)
    code = models.CharField("Code", max_length=20, unique=True, db_index=True)
    category = models.CharField(
        "Category",
        max_length=15,
        choices=MEASUREMENT_CATEGORIES,
        default='UNIFORM',
        db_index=True
    )
    description = models.TextField("Description", blank=True)
    
    # -------------------------------------------------------------------------
    # UNIT OF MEASUREMENT
    # -------------------------------------------------------------------------
    
    unit = models.ForeignKey(
        'core.UnitOfMeasure',
        on_delete=models.PROTECT,
        related_name='measurement_types',
        help_text="Unit of measurement (cm, inches, etc.)"
    )
    
    # -------------------------------------------------------------------------
    # VALIDATION RANGES
    # -------------------------------------------------------------------------
    
    min_value = models.DecimalField(
        "Minimum Value",
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum reasonable value"
    )
    max_value = models.DecimalField(
        "Maximum Value",
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum reasonable value"
    )
    
    # -------------------------------------------------------------------------
    # APPLICABILITY
    # -------------------------------------------------------------------------
    
    applicable_age_min = models.PositiveIntegerField(
        "Minimum Age",
        null=True,
        blank=True
    )
    applicable_age_max = models.PositiveIntegerField(
        "Maximum Age",
        null=True,
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # DISPLAY
    # -------------------------------------------------------------------------
    
    display_order = models.PositiveIntegerField("Display Order", default=100, db_index=True)
    is_required = models.BooleanField("Is Required", default=False)
    is_active = models.BooleanField("Is Active", default=True, db_index=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Measurement Type"
        verbose_name_plural = "Measurement Types"
        ordering = ['category', 'display_order', 'name']
        indexes = [
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['code']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.name} ({self.unit.abbreviation})"
    
    # -------------------------------------------------------------------------
    # VALIDATION METHODS
    # -------------------------------------------------------------------------
    
    def clean(self):
        """Validate min/max values"""
        super().clean()
        if self.min_value and self.max_value:
            if self.min_value >= self.max_value:
                raise ValidationError("Minimum value must be less than maximum value")


# =============================================================================
# STUDENT MEASUREMENT MODEL
# =============================================================================

class StudentMeasurement(BaseModel):
    """Individual student measurements for uniform sizing"""
    
    MEASUREMENT_CONTEXT_CHOICES = [
        ('ADMISSION', 'Admission'),
        ('ANNUAL', 'Annual Check'),
        ('UNIFORM_ORDER', 'Uniform Order'),
        ('HEALTH_CHECK', 'Health Check'),
        ('UPDATE', 'Update/Correction'),
        ('OTHER', 'Other'),
    ]
    
    MEASUREMENT_METHOD_CHOICES = [
        ('MANUAL', 'Manual (Tape Measure)'),
        ('DIGITAL', 'Digital Tool'),
        ('ESTIMATED', 'Estimated'),
        ('SELF_REPORTED', 'Self Reported'),
        ('PARENT_REPORTED', 'Parent Reported'),
    ]
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='measurements',
        verbose_name="Student"
    )
    
    measurement_type = models.ForeignKey(
        MeasurementType,
        on_delete=models.CASCADE,
        related_name='student_measurements',
        verbose_name="Measurement Type"
    )
    
    # -------------------------------------------------------------------------
    # MEASUREMENT VALUE
    # -------------------------------------------------------------------------
    
    value = models.DecimalField(
        "Measurement Value",
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    
    # -------------------------------------------------------------------------
    # CONTEXT
    # -------------------------------------------------------------------------
    
    measurement_date = models.DateField("Measurement Date", default=timezone.now, db_index=True)
    academic_session = models.ForeignKey(
        'academics.AcademicSession',
        on_delete=models.CASCADE,
        related_name='student_measurements',
        verbose_name="Academic Session"
    )
    
    measurement_context = models.CharField(
        "Measurement Context",
        max_length=50,
        choices=MEASUREMENT_CONTEXT_CHOICES,
        default='ANNUAL'
    )
    
    measurement_method = models.CharField(
        "Measurement Method",
        max_length=50,
        choices=MEASUREMENT_METHOD_CHOICES,
        default='MANUAL'
    )
    
    # -------------------------------------------------------------------------
    # VERIFICATION
    # -------------------------------------------------------------------------
    
    is_verified = models.BooleanField("Is Verified", default=False, db_index=True)
    verified_by_id = models.CharField(
        "Verified By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who verified this measurement"
    )
    verification_date = models.DateTimeField("Verification Date", null=True, blank=True)
    
    # -------------------------------------------------------------------------
    # NOTES AND TRACKING
    # -------------------------------------------------------------------------
    
    notes = models.TextField("Notes", blank=True)
    
    is_current = models.BooleanField(
        "Is Current",
        default=True,
        db_index=True,
        help_text="Whether this is the most current measurement"
    )
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Student Measurement"
        verbose_name_plural = "Student Measurements"
        ordering = ['-measurement_date', 'measurement_type__display_order']
        indexes = [
            models.Index(fields=['student', 'measurement_type']),
            models.Index(fields=['measurement_date']),
            models.Index(fields=['is_current']),
            models.Index(fields=['academic_session']),
            models.Index(fields=['is_verified']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'measurement_type'],
                condition=models.Q(is_current=True),
                name='unique_current_measurement_per_student_type'
            )
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.student.get_full_name()} - {self.measurement_type.name}: {self.value} {self.measurement_type.unit.abbreviation}"
    
    # -------------------------------------------------------------------------
    # SAVE METHOD
    # -------------------------------------------------------------------------
    
    def save(self, *args, **kwargs):
        """Mark other measurements as not current"""
        if self.is_current:
            StudentMeasurement.objects.filter(
                student=self.student,
                measurement_type=self.measurement_type,
                is_current=True
            ).exclude(pk=self.pk).update(is_current=False)
        
        super().save(*args, **kwargs)
    
    # -------------------------------------------------------------------------
    # VALIDATION METHODS
    # -------------------------------------------------------------------------
    
    def clean(self):
        """Validate measurement value"""
        super().clean()
        
        # Validate against measurement type constraints
        if self.measurement_type.min_value and self.value < self.measurement_type.min_value:
            raise ValidationError(
                f"Measurement value {self.value} is below minimum allowed value {self.measurement_type.min_value}"
            )
        
        if self.measurement_type.max_value and self.value > self.measurement_type.max_value:
            raise ValidationError(
                f"Measurement value {self.value} is above maximum allowed value {self.measurement_type.max_value}"
            )
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_verified_by_user(self):
        """Get the user who verified this measurement"""
        if not self.verified_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.verified_by_id)
        except Exception as e:
            logger.error(f"Error fetching verified_by user: {e}")
            return None


# =============================================================================
# UNIFORM SIZE MODEL
# =============================================================================

class UniformSize(BaseModel):
    """Standard uniform sizes"""
    
    SIZE_TYPE_CHOICES = [
        ('NUMERIC', 'Numeric (e.g., 32, 34, 36)'),
        ('ALPHA', 'Alphabetic (e.g., S, M, L, XL)'),
        ('AGE_BASED', 'Age-Based (e.g., 6-7 years)'),
        ('CUSTOM', 'Custom'),
    ]
    
    # -------------------------------------------------------------------------
    # BASIC INFORMATION
    # -------------------------------------------------------------------------
    
    name = models.CharField("Size Name", max_length=20)
    code = models.CharField("Size Code", max_length=10, unique=True, db_index=True)
    size_type = models.CharField(
        "Size Type",
        max_length=15,
        choices=SIZE_TYPE_CHOICES,
        default='ALPHA'
    )
    
    # -------------------------------------------------------------------------
    # SIZE RANGES (FOR MEASUREMENTS)
    # -------------------------------------------------------------------------
    
    min_height = models.DecimalField(
        "Minimum Height (cm)",
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True
    )
    max_height = models.DecimalField(
        "Maximum Height (cm)",
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True
    )
    
    min_chest = models.DecimalField(
        "Minimum Chest (cm)",
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True
    )
    max_chest = models.DecimalField(
        "Maximum Chest (cm)",
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True
    )
    
    min_waist = models.DecimalField(
        "Minimum Waist (cm)",
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True
    )
    max_waist = models.DecimalField(
        "Maximum Waist (cm)",
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # AGE RANGE
    # -------------------------------------------------------------------------
    
    min_age = models.PositiveIntegerField("Minimum Age", null=True, blank=True)
    max_age = models.PositiveIntegerField("Maximum Age", null=True, blank=True)
    
    # -------------------------------------------------------------------------
    # ADDITIONAL DETAILS
    # -------------------------------------------------------------------------
    
    description = models.TextField("Description", blank=True)
    display_order = models.PositiveIntegerField("Display Order", default=100, db_index=True)
    is_active = models.BooleanField("Is Active", default=True, db_index=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Uniform Size"
        verbose_name_plural = "Uniform Sizes"
        ordering = ['display_order', 'name']
        indexes = [
            models.Index(fields=['size_type', 'is_active']),
            models.Index(fields=['code']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return self.name


# =============================================================================
# UNIFORM ITEM (INVENTORY)
# =============================================================================

class UniformItem(BaseModel):
    """Uniform items in inventory with full accounting integration"""
    
    ITEM_TYPE_CHOICES = [
        ('UNIFORM', 'School Uniform'),
        ('SPORTS', 'Sports Uniform'),
        ('PE', 'PE Kit'),
        ('ACCESSORY', 'Accessory'),
        ('SHOES', 'Shoes'),
        ('BAG', 'School Bag'),
        ('OTHER', 'Other'),
    ]
    
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('U', 'Unisex'),
    ]
    
    # -------------------------------------------------------------------------
    # BASIC INFORMATION
    # -------------------------------------------------------------------------
    
    name = models.CharField("Item Name", max_length=100)
    code = models.CharField("Item Code", max_length=50, unique=True, db_index=True)
    description = models.TextField("Description", blank=True)
    
    item_type = models.CharField(
        "Item Type",
        max_length=20,
        choices=ITEM_TYPE_CHOICES,
        default='UNIFORM',
        db_index=True
    )
    
    gender = models.CharField(
        "Gender",
        max_length=1,
        choices=GENDER_CHOICES,
        default='U'
    )
    
    # -------------------------------------------------------------------------
    # CATEGORIZATION
    # -------------------------------------------------------------------------
    
    category = models.CharField("Category", max_length=50, blank=True)
    subcategory = models.CharField("Subcategory", max_length=50, blank=True)
    
    # -------------------------------------------------------------------------
    # SIZING
    # -------------------------------------------------------------------------
    
    requires_sizing = models.BooleanField("Requires Sizing", default=True)
    available_sizes = models.ManyToManyField(
        UniformSize,
        blank=True,
        related_name='uniform_items',
        verbose_name="Available Sizes"
    )
    
    # -------------------------------------------------------------------------
    # UNIT OF MEASURE
    # -------------------------------------------------------------------------
    
    unit_of_measure = models.ForeignKey(
        'core.UnitOfMeasure',
        on_delete=models.PROTECT,
        related_name='uniform_items',
        verbose_name="Unit of Measure",
        help_text="Unit of measure for inventory tracking (pcs, dozen, etc.)"
    )
    
    # -------------------------------------------------------------------------
    # PRICING
    # -------------------------------------------------------------------------
    
    unit_cost = models.DecimalField(
        "Unit Cost",
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Cost price per unit (for COGS calculation)"
    )
    
    selling_price = models.DecimalField(
        "Selling Price",
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Selling price per unit"
    )
    
    markup_percentage = models.DecimalField(
        "Markup Percentage",
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Markup percentage (calculated: (selling_price - unit_cost) / unit_cost * 100)"
    )
    
    # -------------------------------------------------------------------------
    # INVENTORY MANAGEMENT
    # -------------------------------------------------------------------------
    
    sku = models.CharField("SKU", max_length=50, blank=True, unique=True, null=True)
    barcode = models.CharField("Barcode", max_length=100, blank=True)
    
    # Inventory levels
    current_stock = models.IntegerField("Current Stock", default=0)
    reorder_level = models.IntegerField("Reorder Level", default=10)
    maximum_stock = models.IntegerField("Maximum Stock", null=True, blank=True)
    
    # -------------------------------------------------------------------------
    # SUPPLIER INFORMATION
    # -------------------------------------------------------------------------
    
    supplier_name = models.CharField("Supplier Name", max_length=100, blank=True)
    supplier_contact = models.CharField("Supplier Contact", max_length=100, blank=True)
    supplier_item_code = models.CharField("Supplier Item Code", max_length=50, blank=True)
    
    # -------------------------------------------------------------------------
    # ADDITIONAL DETAILS
    # -------------------------------------------------------------------------
    
    image = models.ImageField("Item Image", upload_to='uniforms/items/', blank=True, null=True)
    color = models.CharField("Color", max_length=50, blank=True)
    material = models.CharField("Material", max_length=100, blank=True)
    care_instructions = models.TextField("Care Instructions", blank=True)
    
    # -------------------------------------------------------------------------
    # TAX CONFIGURATION
    # -------------------------------------------------------------------------
    
    is_taxable = models.BooleanField("Is Taxable", default=True)
    tax_rate = models.ForeignKey(
        'core.TaxRate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uniform_items',
        help_text="Tax rate to apply (uses default if blank)"
    )
    
    # -------------------------------------------------------------------------
    # STATUS
    # -------------------------------------------------------------------------
    
    is_active = models.BooleanField("Is Active", default=True, db_index=True)
    is_mandatory = models.BooleanField("Is Mandatory", default=False)
    
    notes = models.TextField("Notes", blank=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Uniform Item"
        verbose_name_plural = "Uniform Items"
        ordering = ['item_type', 'name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['item_type', 'is_active']),
            models.Index(fields=['sku']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.name} ({self.code})"
    
    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------
    
    @property
    def is_low_stock(self):
        """Check if stock is below reorder level"""
        return self.current_stock <= self.reorder_level
    
    @property
    def stock_value(self):
        """Calculate total stock value at cost price"""
        return self.current_stock * self.unit_cost
    
    @property
    def stock_value_selling(self):
        """Calculate total stock value at selling price"""
        return self.current_stock * self.selling_price
    
    @property
    def potential_profit(self):
        """Calculate potential profit from current stock"""
        return self.stock_value_selling - self.stock_value
    
    # -------------------------------------------------------------------------
    # SAVE METHOD
    # -------------------------------------------------------------------------
    
    def save(self, *args, **kwargs):
        """Calculate markup percentage automatically"""
        if self.unit_cost > 0:
            markup = ((self.selling_price - self.unit_cost) / self.unit_cost) * 100
            self.markup_percentage = round(markup, 2)
        else:
            self.markup_percentage = Decimal('0.00')
        
        super().save(*args, **kwargs)
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_inventory_account(self):
        """Get inventory account from mappings or use override"""
        if self.inventory_account:  # Use override if set
            return self.inventory_account
        
        from core.models import FinancialSettings
        settings = FinancialSettings.get_instance()
        if settings:
            expense_mappings = settings.get_expense_mappings()
            return expense_mappings.default_inventory_account
        return None
    
    def get_cogs_account(self):
        """Get COGS account from mappings or use override"""
        if self.cogs_account:
            return self.cogs_account
        
        from core.models import FinancialSettings
        settings = FinancialSettings.get_instance()
        if settings:
            expense_mappings = settings.get_expense_mappings()
            return expense_mappings.default_cogs_account
        return None
    
    def get_revenue_account(self):
        """Get revenue account from mappings or use override"""
        if self.revenue_account:
            return self.revenue_account
        
        from core.models import FinancialSettings
        settings = FinancialSettings.get_instance()
        if settings:
            mappings = settings.get_account_mappings()
            if mappings.uniform_and_book_sales_account:
                return mappings.uniform_and_book_sales_account
            return mappings.default_revenue_account
        return None


# =============================================================================
# UNIFORM STOCK (SIZE-SPECIFIC INVENTORY)
# =============================================================================

class UniformStock(BaseModel):
    """Size-specific stock tracking for uniform items"""
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    uniform_item = models.ForeignKey(
        UniformItem,
        on_delete=models.CASCADE,
        related_name='stock_records'
    )
    
    size = models.ForeignKey(
        UniformSize,
        on_delete=models.CASCADE,
        related_name='stock_records'
    )
    
    # -------------------------------------------------------------------------
    # STOCK LEVELS
    # -------------------------------------------------------------------------
    
    quantity = models.IntegerField("Quantity in Stock", default=0)
    reserved_quantity = models.IntegerField(
        "Reserved Quantity", 
        default=0,
        help_text="Quantity reserved in pending sales"
    )
    
    # -------------------------------------------------------------------------
    # LOCATION
    # -------------------------------------------------------------------------
    
    location = models.CharField("Storage Location", max_length=100, blank=True)
    bin_number = models.CharField("Bin Number", max_length=50, blank=True)
    
    # -------------------------------------------------------------------------
    # STOCK VALUE TRACKING
    # -------------------------------------------------------------------------
    
    total_cost_value = models.DecimalField(
        "Total Cost Value",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total value at cost price (quantity * unit_cost)"
    )
    
    total_selling_value = models.DecimalField(
        "Total Selling Value",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total value at selling price (quantity * selling_price)"
    )
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Uniform Stock"
        verbose_name_plural = "Uniform Stock"
        unique_together = ['uniform_item', 'size']
        ordering = ['uniform_item', 'size']
        indexes = [
            models.Index(fields=['uniform_item', 'size']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.uniform_item.name} - Size {self.size.name}: {self.quantity} units"
    
    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------
    
    @property
    def available_quantity(self):
        """Calculate available quantity (total - reserved)"""
        return self.quantity - self.reserved_quantity
    
    # -------------------------------------------------------------------------
    # SAVE METHOD
    # -------------------------------------------------------------------------
    
    def save(self, *args, **kwargs):
        """Calculate total values automatically"""
        self.total_cost_value = self.quantity * self.uniform_item.unit_cost
        self.total_selling_value = self.quantity * self.uniform_item.selling_price
        super().save(*args, **kwargs)


# =============================================================================
# UNIFORM PURCHASE ORDER
# =============================================================================

class UniformPurchaseOrder(BaseModel):
    """Purchase orders for uniform inventory"""
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('SUBMITTED', 'Submitted'),
        ('APPROVED', 'Approved'),
        ('ORDERED', 'Ordered'),
        ('RECEIVED', 'Received'),
        ('PARTIAL', 'Partially Received'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    # -------------------------------------------------------------------------
    # IDENTIFICATION
    # -------------------------------------------------------------------------
    
    po_number = models.CharField("PO Number", max_length=50, unique=True, db_index=True)
    
    # -------------------------------------------------------------------------
    # SUPPLIER INFORMATION
    # -------------------------------------------------------------------------
    
    supplier_name = models.CharField("Supplier Name", max_length=100)
    supplier_contact = models.CharField("Supplier Contact", max_length=100, blank=True)
    supplier_email = models.EmailField("Supplier Email", blank=True)
    supplier_phone = models.CharField("Supplier Phone", max_length=20, blank=True)
    
    # -------------------------------------------------------------------------
    # ORDER DETAILS
    # -------------------------------------------------------------------------
    
    order_date = models.DateField("Order Date", default=timezone.now, db_index=True)
    expected_delivery_date = models.DateField("Expected Delivery Date", null=True, blank=True)
    actual_delivery_date = models.DateField("Actual Delivery Date", null=True, blank=True)
    
    # -------------------------------------------------------------------------
    # FINANCIAL
    # -------------------------------------------------------------------------
    
    subtotal = models.DecimalField("Subtotal", max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax_amount = models.DecimalField("Tax Amount", max_digits=12, decimal_places=2, default=Decimal('0.00'))
    shipping_cost = models.DecimalField("Shipping Cost", max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField("Total Amount", max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    # -------------------------------------------------------------------------
    # PAYMENT TRACKING
    # -------------------------------------------------------------------------
    
    payment_terms = models.CharField("Payment Terms", max_length=100, blank=True)
    paid_amount = models.DecimalField("Paid Amount", max_digits=12, decimal_places=2, default=Decimal('0.00'))
    balance_due = models.DecimalField("Balance Due", max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    # =========================================================================
    # ACCOUNTING INTEGRATION
    # =========================================================================
    
    journal_entry = models.ForeignKey(
        'finance.JournalEntry',
        verbose_name="Journal Entry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uniform_purchase_orders',
        help_text="Journal entry for goods receipt"
    )
    
    auto_create_journal_entry = models.BooleanField(
        "Auto-Create Journal Entry",
        default=True,
        help_text="Automatically create journal entry when goods are received"
    )
    
    # -------------------------------------------------------------------------
    # FISCAL PERIOD
    # -------------------------------------------------------------------------
    
    fiscal_period = models.ForeignKey(
        'core.FiscalPeriod',
        verbose_name="Fiscal Period",
        on_delete=models.PROTECT,
        related_name='uniform_purchase_orders',
        null=True,
        blank=True,
        help_text="Fiscal period when PO was created"
    )
    
    # -------------------------------------------------------------------------
    # STATUS
    # -------------------------------------------------------------------------
    
    status = models.CharField(
        "Status",
        max_length=15,
        choices=STATUS_CHOICES,
        default='DRAFT',
        db_index=True
    )
    
    # -------------------------------------------------------------------------
    # APPROVAL
    # -------------------------------------------------------------------------
    
    approved_by_id = models.CharField("Approved By ID", max_length=50, null=True, blank=True)
    approved_at = models.DateTimeField("Approved At", null=True, blank=True)
    
    # -------------------------------------------------------------------------
    # NOTES
    # -------------------------------------------------------------------------
    
    notes = models.TextField("Notes", blank=True)

    def get_payable_account(self):
        """Get payable account from CoreAccountMappings"""
        from core.models import FinancialSettings
        settings = FinancialSettings.get_instance()
        if settings:
            mappings = settings.get_account_mappings()
            return mappings.default_payable_account
        return None
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Uniform Purchase Order"
        verbose_name_plural = "Uniform Purchase Orders"
        ordering = ['-order_date']
        indexes = [
            models.Index(fields=['po_number']),
            models.Index(fields=['order_date']),
            models.Index(fields=['status']),
            models.Index(fields=['fiscal_period']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"PO {self.po_number} - {self.supplier_name}"
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_approved_by_user(self):
        """Get the user who approved this PO"""
        if not self.approved_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.approved_by_id)
        except Exception as e:
            logger.error(f"Error fetching approved_by user: {e}")
            return None


class UniformPurchaseOrderItem(BaseModel):
    """Line items in a uniform purchase order"""
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    purchase_order = models.ForeignKey(
        UniformPurchaseOrder,
        on_delete=models.CASCADE,
        related_name='items'
    )
    
    uniform_item = models.ForeignKey(
        UniformItem,
        on_delete=models.CASCADE,
        related_name='purchase_order_items'
    )
    
    size = models.ForeignKey(
        UniformSize,
        on_delete=models.CASCADE,
        related_name='purchase_order_items',
        null=True,
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # QUANTITIES
    # -------------------------------------------------------------------------
    
    quantity_ordered = models.PositiveIntegerField("Quantity Ordered")
    quantity_received = models.PositiveIntegerField("Quantity Received", default=0)
    
    # -------------------------------------------------------------------------
    # PRICING
    # -------------------------------------------------------------------------
    
    unit_price = models.DecimalField("Unit Price", max_digits=10, decimal_places=2)
    total_price = models.DecimalField("Total Price", max_digits=12, decimal_places=2)
    
    # -------------------------------------------------------------------------
    # NOTES
    # -------------------------------------------------------------------------
    
    notes = models.TextField("Notes", blank=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Purchase Order Item"
        verbose_name_plural = "Purchase Order Items"
        ordering = ['purchase_order', 'uniform_item']
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        size_info = f" - Size {self.size.name}" if self.size else ""
        return f"{self.uniform_item.name}{size_info}: {self.quantity_ordered} units"
    
    # -------------------------------------------------------------------------
    # SAVE METHOD
    # -------------------------------------------------------------------------
    
    def save(self, *args, **kwargs):
        """Calculate total price"""
        self.total_price = self.quantity_ordered * self.unit_price
        super().save(*args, **kwargs)


# =============================================================================
# UNIFORM SALE/ISSUANCE - FULLY INTEGRATED
# =============================================================================

# uniforms/models.py - UPDATED UniformSale with Cancellation/Return Support

class UniformSale(BaseModel):
    """
    Sales/issuance of uniforms to students with FULL FINANCIAL INTEGRATION.
    
    Automatically creates:
    - Fee invoices (for sales)
    - Journal entries for inventory and revenue
    - Student account transactions
    - Payment records when linked
    
    REVERSAL SCENARIOS:
    1. CANCELLED (before issuance) → Cancel invoice, no inventory movement, process refund if paid
    2. RETURNED (after issuance) → Return to inventory, reverse journal entries, process refund
    
    KEY CONCEPTS:
    - A sale can be EITHER cancelled OR returned, never both
    - Cancellation: Sale never happened (items never left warehouse)
    - Return: Items were issued but came back (inventory adjusted)
    - Both scenarios may require payment refunds if student already paid
    """
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PENDING', 'Pending Payment'),
        ('PAID', 'Paid'),
        ('PARTIAL', 'Partially Paid'),
        ('ISSUED', 'Issued'),
        ('CANCELLED', 'Cancelled'),  # Before items issued
        ('RETURNED', 'Returned'),    # After items issued
    ]
    
    SALE_TYPE_CHOICES = [
        ('SALE', 'Sale'),
        ('ISSUANCE', 'Free Issuance'),
        ('LOAN', 'Temporary Loan'),
        ('REPLACEMENT', 'Replacement'),
    ]
    
    # =========================================================================
    # IDENTIFICATION
    # =========================================================================
    
    sale_number = models.CharField(
        "Sale Number", 
        max_length=50, 
        unique=True, 
        db_index=True
    )
    
    # =========================================================================
    # CORE RELATIONSHIPS
    # =========================================================================
    
    student = models.ForeignKey(
        'students.Student',
        verbose_name="Student",
        on_delete=models.CASCADE,
        related_name='uniform_sales'
    )
    
    academic_session = models.ForeignKey(
        'academics.AcademicSession',
        verbose_name="Academic Session",
        on_delete=models.CASCADE,
        related_name='uniform_sales'
    )
    
    # =========================================================================
    # FISCAL PERIOD
    # =========================================================================
    
    fiscal_period = models.ForeignKey(
        'core.FiscalPeriod',
        verbose_name="Fiscal Period",
        on_delete=models.PROTECT,
        related_name='uniform_sales',
        help_text="Fiscal period when this sale was recorded"
    )
    
    # =========================================================================
    # SALE DETAILS
    # =========================================================================
    
    sale_type = models.CharField(
        "Sale Type",
        max_length=20,
        choices=SALE_TYPE_CHOICES,
        default='SALE'
    )
    
    sale_date = models.DateField(
        "Sale Date", 
        default=timezone.now, 
        db_index=True
    )
    
    # =========================================================================
    # FINANCIAL INTEGRATION - FEE INVOICE
    # =========================================================================
    
    fee_invoice = models.OneToOneField(
        'fees.FeeInvoice',
        verbose_name="Fee Invoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uniform_sale',
        help_text="Invoice generated for this uniform sale"
    )
    
    auto_create_invoice = models.BooleanField(
        "Auto-Create Invoice",
        default=True,
        help_text="Automatically create fee invoice when sale is finalized"
    )
    
    # =========================================================================
    # FINANCIAL AMOUNTS
    # =========================================================================
    
    subtotal = models.DecimalField(
        "Subtotal", 
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Sum of all item prices before tax and discount"
    )
    
    discount_amount = models.DecimalField(
        "Discount Amount", 
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Total discount applied to this sale"
    )
    
    tax_amount = models.DecimalField(
        "Tax Amount", 
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Total tax (VAT) on this sale"
    )
    
    total_amount = models.DecimalField(
        "Total Amount", 
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Final amount: Subtotal + Tax - Discount"
    )
    
    paid_amount = models.DecimalField(
        "Paid Amount", 
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Amount already paid by student"
    )
    
    balance = models.DecimalField(
        "Balance", 
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Remaining balance: Total - Paid"
    )
    
    # =========================================================================
    # COST OF GOODS SOLD TRACKING
    # =========================================================================
    
    total_cost = models.DecimalField(
        "Total Cost (COGS)",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total cost of goods sold (calculated from unit costs)"
    )
    
    gross_profit = models.DecimalField(
        "Gross Profit",
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Gross profit (total_amount - total_cost)"
    )
    
    gross_margin_percentage = models.DecimalField(
        "Gross Margin %",
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Gross margin percentage ((total_amount - total_cost) / total_amount * 100)"
    )
    
    # =========================================================================
    # JOURNAL ENTRY INTEGRATION
    # =========================================================================
    
    journal_entry = models.ForeignKey(
        'finance.JournalEntry',
        verbose_name="Journal Entry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uniform_sales',
        help_text="Journal entry for this uniform sale (COGS and Revenue recognition)"
    )
    
    auto_create_journal_entry = models.BooleanField(
        "Auto-Create Journal Entry",
        default=True,
        help_text="Automatically create journal entries when sale is completed"
    )
    
    # =========================================================================
    # STATUS
    # =========================================================================
    
    status = models.CharField(
        "Status",
        max_length=15,
        choices=STATUS_CHOICES,
        default='DRAFT',
        db_index=True
    )
    
    # =========================================================================
    # PAYMENT
    # =========================================================================
    
    payment_method = models.ForeignKey(
        'core.PaymentMethod',
        verbose_name="Payment Method",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='uniform_sales',
        help_text="How payment was made (if paid immediately)"
    )
    
    payment_reference = models.CharField(
        "Payment Reference", 
        max_length=100, 
        blank=True,
        help_text="Payment reference/transaction number"
    )
    
    # =========================================================================
    # ISSUANCE TRACKING
    # =========================================================================
    
    issued_by_id = models.CharField(
        "Issued By ID", 
        max_length=50, 
        null=True, 
        blank=True,
        help_text="User ID who issued the uniforms to student"
    )
    
    issued_at = models.DateTimeField(
        "Issued At", 
        null=True, 
        blank=True,
        help_text="When uniforms were physically handed to student"
    )
    
    return_date = models.DateField(
        "Expected Return Date", 
        null=True, 
        blank=True, 
        help_text="For loaned items - when they should be returned"
    )
    
    # =========================================================================
    # DISCOUNT TRACKING
    # =========================================================================
    
    discount_reason = models.CharField(
        "Discount Reason",
        max_length=200,
        blank=True,
        help_text="Reason for discount (staff child, sibling discount, bulk purchase, etc.)"
    )
    
    discount_approved_by_id = models.CharField(
        "Discount Approved By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who approved the discount"
    )
    
    # =========================================================================
    # CANCELLATION TRACKING (Before Issuance) ⭐ NEW
    # =========================================================================
    
    cancelled = models.BooleanField(
        "Cancelled",
        default=False,
        db_index=True,
        help_text=(
            "Sale was cancelled before items were issued to student. "
            "No inventory adjustment needed (items never left warehouse)."
        )
    )
    
    cancelled_on = models.DateTimeField(
        "Cancelled On",
        null=True,
        blank=True,
        help_text="When this sale was cancelled"
    )
    
    cancelled_by_id = models.CharField(
        "Cancelled By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who cancelled this sale"
    )
    
    cancellation_reason = models.TextField(
        "Cancellation Reason",
        blank=True,
        help_text=(
            "Detailed reason for cancellation. Examples: "
            "'Student withdrew before receiving items', "
            "'Wrong items selected', "
            "'Parent changed mind before payment/issuance'"
        )
    )
    
    cancellation_journal_entry = models.ForeignKey(
        'finance.JournalEntry',
        verbose_name="Cancellation Journal Entry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cancelled_uniform_sales',
        help_text="Journal entry reversing the original sale (if journal was already created)"
    )
    
    # =========================================================================
    # RETURN TRACKING (After Issuance) ⭐ NEW
    # =========================================================================
    
    returned = models.BooleanField(
        "Returned",
        default=False,
        db_index=True,
        help_text=(
            "Issued items were physically returned by student. "
            "Items are added back to inventory."
        )
    )
    
    returned_on = models.DateTimeField(
        "Returned On",
        null=True,
        blank=True,
        help_text="When items were returned to warehouse"
    )
    
    returned_by_id = models.CharField(
        "Returned By ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID who processed the return"
    )
    
    return_reason = models.TextField(
        "Return Reason",
        blank=True,
        help_text=(
            "Why items were returned. Examples: "
            "'Wrong size issued', "
            "'Student withdrew from school', "
            "'Items defective', "
            "'Parent requested refund'"
        )
    )
    
    return_condition = models.CharField(
        "Return Condition",
        max_length=20,
        choices=[
            ('GOOD', 'Good Condition - Can Resell'),
            ('FAIR', 'Fair Condition - Can Resell with Discount'),
            ('WORN', 'Worn - Cannot Resell'),
            ('DAMAGED', 'Damaged - Cannot Resell'),
            ('UNUSABLE', 'Unusable - Write Off'),
        ],
        blank=True,
        help_text="Condition of returned items (determines if they can be resold)"
    )
    
    return_journal_entry = models.ForeignKey(
        'finance.JournalEntry',
        verbose_name="Return Journal Entry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='returned_uniform_sales',
        help_text="Journal entry for returned inventory (reverses COGS and Revenue)"
    )
    
    partial_return = models.BooleanField(
        "Partial Return",
        default=False,
        help_text="Only some items were returned (not all)"
    )
    
    # =========================================================================
    # NOTES
    # =========================================================================
    
    notes = models.TextField(
        "Notes", 
        blank=True,
        help_text="Public notes visible to parents/students"
    )
    
    internal_notes = models.TextField(
        "Internal Notes", 
        blank=True,
        help_text="Internal notes for staff only (not visible to parents/students)"
    )
    
    # =========================================================================
    # ACCOUNT MAPPING HELPERS
    # =========================================================================
    
    def get_inventory_account(self):
        """
        Get inventory asset account.
        
        Returns:
            Account: Uniform inventory account
        """
        from core.models import FinancialSettings
        
        settings = FinancialSettings.get_instance()
        if not settings:
            logger.error("FinancialSettings not configured")
            return None
        
        # Try to get specific uniform inventory account
        mappings = settings.get_account_mappings()
        
        # Check if there's a specific uniform inventory account
        if hasattr(mappings, 'uniform_inventory_account') and mappings.uniform_inventory_account:
            return mappings.uniform_inventory_account
        
        # Otherwise use default inventory account
        if hasattr(mappings, 'default_inventory_account') and mappings.default_inventory_account:
            return mappings.default_inventory_account
        
        logger.error("No inventory account configured")
        return None
    
    def get_cogs_account(self):
        """
        Get Cost of Goods Sold expense account.
        
        Returns:
            Account: COGS account
        """
        from core.models import FinancialSettings
        
        settings = FinancialSettings.get_instance()
        if not settings:
            logger.error("FinancialSettings not configured")
            return None
        
        mappings = settings.get_account_mappings()
        
        # Try specific uniform COGS account
        if hasattr(mappings, 'uniform_cogs_account') and mappings.uniform_cogs_account:
            return mappings.uniform_cogs_account
        
        # Otherwise use default COGS
        if hasattr(mappings, 'default_cogs_account') and mappings.default_cogs_account:
            return mappings.default_cogs_account
        
        logger.error("No COGS account configured")
        return None
    
    def get_revenue_account(self):
        """
        Get uniform sales revenue account.
        
        Returns:
            Account: Revenue account for uniform sales
        """
        from core.models import FinancialSettings
        
        settings = FinancialSettings.get_instance()
        if not settings:
            logger.error("FinancialSettings not configured")
            return None
        
        mappings = settings.get_account_mappings()
        
        # Try specific uniform sales revenue account
        if hasattr(mappings, 'uniform_sales_revenue_account') and mappings.uniform_sales_revenue_account:
            return mappings.uniform_sales_revenue_account
        
        # Try combined uniform and book sales account
        if hasattr(mappings, 'uniform_and_book_sales_account') and mappings.uniform_and_book_sales_account:
            return mappings.uniform_and_book_sales_account
        
        # Otherwise use default revenue
        if hasattr(mappings, 'default_revenue_account') and mappings.default_revenue_account:
            return mappings.default_revenue_account
        
        logger.error("No revenue account configured for uniform sales")
        return None
    
    def get_receivable_account(self):
        """
        Get student receivables account.
        
        Returns:
            Account: Student receivables account
        """
        from core.models import FinancialSettings
        
        settings = FinancialSettings.get_instance()
        if not settings:
            logger.error("FinancialSettings not configured")
            return None
        
        mappings = settings.get_account_mappings()
        
        if hasattr(mappings, 'student_receivables_account') and mappings.student_receivables_account:
            return mappings.student_receivables_account
        
        logger.error("No student receivables account configured")
        return None
    
    # =========================================================================
    # VALIDATION
    # =========================================================================
    
    def clean(self):
        """Validate uniform sale data"""
        super().clean()
        errors = {}
        
        # Cannot be both cancelled AND returned
        if self.cancelled and self.returned:
            errors['cancelled'] = "Sale cannot be both cancelled and returned. Choose one."
            errors['returned'] = "Sale cannot be both cancelled and returned. Choose one."
        
        # If cancelled, must have reason
        if self.cancelled and not self.cancellation_reason:
            errors['cancellation_reason'] = "Cancellation reason is required for cancelled sales"
        
        # If returned, must have reason and condition
        if self.returned:
            if not self.return_reason:
                errors['return_reason'] = "Return reason is required for returned sales"
            if not self.return_condition:
                errors['return_condition'] = "Return condition is required for returned sales"
        
        # Cannot cancel/return a draft
        if self.cancelled or self.returned:
            if self.status == 'DRAFT':
                errors['status'] = "Cannot cancel or return a draft sale. Delete it instead."
        
        # Amounts validation
        if self.total_amount < 0:
            errors['total_amount'] = "Total amount cannot be negative"
        
        if self.paid_amount < 0:
            errors['paid_amount'] = "Paid amount cannot be negative"
        
        if self.paid_amount > self.total_amount:
            errors['paid_amount'] = "Paid amount cannot exceed total amount"
        
        if errors:
            raise ValidationError(errors)
    
    # =========================================================================
    # STATUS PROPERTIES ⭐ NEW
    # =========================================================================
    
    @property
    def is_active(self):
        """
        Check if sale is still active (not cancelled or returned).
        
        Active sales count toward revenue and inventory.
        Inactive sales are kept for audit trail only.
        
        Returns:
            bool: True if sale is active
        """
        return not self.cancelled and not self.returned
    
    @property
    def effective_total_amount(self):
        """
        Get effective total amount (0 if cancelled/returned).
        
        Returns:
            Decimal: Total amount if active, 0 if inactive
        """
        if not self.is_active:
            return Decimal('0.00')
        return self.total_amount
    
    @property
    def sale_state(self):
        """
        Get human-readable sale state.
        
        Returns:
            str: Current state of sale
        """
        if self.cancelled:
            return "CANCELLED"
        elif self.returned:
            return "RETURNED"
        else:
            return self.status
    
    def can_be_cancelled(self):
        """
        Check if this sale can be cancelled.
        
        Cancellation is for sales that never completed (items never issued).
        
        Returns:
            tuple: (can_cancel: bool, reason: str)
        """
        if self.cancelled:
            return False, "Sale already cancelled"
        
        if self.returned:
            return False, "Sale was already returned (cannot cancel after return)"
        
        if self.status == 'ISSUED':
            return False, "Cannot cancel issued sale (items already given to student). Use RETURN instead."
        
        # Check if fiscal period is closed
        if self.fiscal_period and hasattr(self.fiscal_period, 'is_closed'):
            if self.fiscal_period.is_closed:
                return False, "Cannot cancel sale from closed fiscal period"
        
        return True, "OK"
    
    def can_be_returned(self):
        """
        Check if items can be returned.
        
        Return is for sales where items were issued but are coming back.
        
        Returns:
            tuple: (can_return: bool, reason: str)
        """
        if self.cancelled:
            return False, "Sale was cancelled (items were never issued, so nothing to return)"
        
        if self.returned:
            return False, "Items already returned"
        
        if self.status != 'ISSUED':
            return False, "Items must be issued before they can be returned (current status: {})".format(
                self.get_status_display()
            )
        
        # Check if fiscal period is closed
        if self.fiscal_period and hasattr(self.fiscal_period, 'is_closed'):
            if self.fiscal_period.is_closed:
                return False, "Cannot process return from closed fiscal period"
        
        return True, "OK"
    
    # =========================================================================
    # USER RETRIEVAL HELPERS
    # =========================================================================
    
    def get_issued_by_user(self):
        """Get the user who issued this sale"""
        if not self.issued_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.issued_by_id)
        except Exception as e:
            logger.error(f"Error fetching issued_by user: {e}")
            return None
    
    def get_discount_approved_by_user(self):
        """Get the user who approved the discount"""
        if not self.discount_approved_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.discount_approved_by_id)
        except Exception as e:
            logger.error(f"Error fetching discount_approved_by user: {e}")
            return None
    
    def get_cancelled_by_user(self):
        """Get user who cancelled this sale"""
        if not self.cancelled_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.cancelled_by_id)
        except Exception as e:
            logger.error(f"Error fetching cancelled_by user: {e}")
            return None
    
    def get_returned_by_user(self):
        """Get user who processed return"""
        if not self.returned_by_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.returned_by_id)
        except Exception as e:
            logger.error(f"Error fetching returned_by user: {e}")
            return None
    
    # =========================================================================
    # AUDIT TRAIL HELPERS
    # =========================================================================
    
    def get_audit_trail(self):
        """
        Get complete audit trail for this uniform sale.
        
        Returns:
            list: Chronological audit trail
        """
        trail = []
        
        # Creation
        trail.append({
            'action': 'CREATED',
            'timestamp': self.created_at,
            'user': self.get_created_by_user(),
            'details': f"Uniform sale {self.sale_number} created for {self.student.get_full_name()}"
        })
        
        # Invoice creation
        if self.fee_invoice:
            trail.append({
                'action': 'INVOICE_CREATED',
                'timestamp': self.fee_invoice.created_at,
                'details': f"Fee invoice {self.fee_invoice.invoice_number} generated"
            })
        
        # Journal entry
        if self.journal_entry:
            trail.append({
                'action': 'JOURNAL_ENTRY_CREATED',
                'timestamp': self.journal_entry.created_at,
                'details': f"Journal entry {self.journal_entry.entry_number} created"
            })
        
        # Discount approval
        if self.discount_approved_by_id and self.discount_amount > 0:
            trail.append({
                'action': 'DISCOUNT_APPROVED',
                'timestamp': self.updated_at,  # Approximate
                'user': self.get_discount_approved_by_user(),
                'details': f"Discount of {self.discount_amount:,.2f} approved: {self.discount_reason}"
            })
        
        # Issuance
        if self.issued_at:
            trail.append({
                'action': 'ITEMS_ISSUED',
                'timestamp': self.issued_at,
                'user': self.get_issued_by_user(),
                'details': "Uniforms physically issued to student"
            })
        
        # Cancellation
        if self.cancelled and self.cancelled_on:
            trail.append({
                'action': 'CANCELLED',
                'timestamp': self.cancelled_on,
                'user': self.get_cancelled_by_user(),
                'details': f"Sale cancelled: {self.cancellation_reason}"
            })
            
            if self.cancellation_journal_entry:
                trail.append({
                    'action': 'CANCELLATION_JOURNAL_ENTRY',
                    'timestamp': self.cancellation_journal_entry.created_at,
                    'details': f"Cancellation journal entry {self.cancellation_journal_entry.entry_number} created"
                })
        
        # Return
        if self.returned and self.returned_on:
            trail.append({
                'action': 'ITEMS_RETURNED',
                'timestamp': self.returned_on,
                'user': self.get_returned_by_user(),
                'details': f"Items returned in {self.get_return_condition_display()} condition: {self.return_reason}"
            })
            
            if self.return_journal_entry:
                trail.append({
                    'action': 'RETURN_JOURNAL_ENTRY',
                    'timestamp': self.return_journal_entry.created_at,
                    'details': f"Return journal entry {self.return_journal_entry.entry_number} created"
                })
        
        # Sort by timestamp
        trail.sort(key=lambda x: x['timestamp'])
        
        return trail
    
    # =========================================================================
    # CALCULATION METHODS
    # =========================================================================
    
    def calculate_totals(self):
        """
        Calculate all totals from sale items.
        
        Should be called after adding/modifying items.
        """
        items = self.items.all()
        
        # Calculate subtotal and cost
        self.subtotal = sum(item.total_price for item in items)
        self.total_cost = sum(item.total_cost for item in items)
        
        # Calculate tax
        self.tax_amount = sum(item.tax_amount for item in items)
        
        # Calculate total
        self.total_amount = self.subtotal + self.tax_amount - self.discount_amount
        
        # Calculate balance
        self.balance = self.total_amount - self.paid_amount
        
        # Calculate gross profit and margin
        if self.total_amount > 0:
            self.gross_profit = self.total_amount - self.total_cost
            self.gross_margin_percentage = (self.gross_profit / self.total_amount) * 100
        else:
            self.gross_profit = Decimal('0.00')
            self.gross_margin_percentage = Decimal('0.00')
        
        self.save()
    
    # =========================================================================
    # META CLASS
    # =========================================================================
    
    class Meta:
        verbose_name = "Uniform Sale"
        verbose_name_plural = "Uniform Sales"
        ordering = ['-sale_date', '-created_at']
        indexes = [
            models.Index(fields=['sale_number']),
            models.Index(fields=['student', 'sale_date']),
            models.Index(fields=['status']),
            models.Index(fields=['sale_date']),
            models.Index(fields=['fiscal_period']),
            models.Index(fields=['academic_session']),
            # NEW indexes for cancellation/return tracking
            models.Index(fields=['cancelled']),
            models.Index(fields=['returned']),
            models.Index(fields=['cancelled_on']),
            models.Index(fields=['returned_on']),
        ]
        constraints = [
            # Ensure amounts are non-negative
            models.CheckConstraint(
                check=models.Q(total_amount__gte=0),
                name='uniform_sale_total_amount_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(paid_amount__gte=0),
                name='uniform_sale_paid_amount_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(discount_amount__gte=0),
                name='uniform_sale_discount_amount_non_negative'
            ),
        ]
    
    # =========================================================================
    # STRING REPRESENTATION
    # =========================================================================
    
    def __str__(self):
        state_suffix = ""
        if self.cancelled:
            state_suffix = " [CANCELLED]"
        elif self.returned:
            state_suffix = " [RETURNED]"
        
        return f"{self.sale_number} - {self.student.get_full_name()} - {self.total_amount:,.2f}{state_suffix}"
    
    # =========================================================================
    # SAVE METHOD
    # =========================================================================
    
    def save(self, *args, **kwargs):
        """Calculate gross profit and margin automatically"""
        # Calculate gross profit and margin
        if self.total_amount > 0:
            self.gross_profit = self.total_amount - self.total_cost
            self.gross_margin_percentage = (self.gross_profit / self.total_amount) * 100
        else:
            self.gross_profit = Decimal('0.00')
            self.gross_margin_percentage = Decimal('0.00')
        
        # Update status based on cancellation/return
        if self.cancelled and self.status != 'CANCELLED':
            self.status = 'CANCELLED'
        elif self.returned and self.status != 'RETURNED':
            self.status = 'RETURNED'
        
        super().save(*args, **kwargs)


class UniformSaleItem(BaseModel):
    """Line items in a uniform sale with cost tracking"""
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    sale = models.ForeignKey(
        UniformSale,
        on_delete=models.CASCADE,
        related_name='items'
    )
    
    uniform_item = models.ForeignKey(
        UniformItem,
        on_delete=models.CASCADE,
        related_name='sale_items'
    )
    
    size = models.ForeignKey(
        UniformSize,
        on_delete=models.CASCADE,
        related_name='sale_items',
        null=True,
        blank=True
    )
    
    # -------------------------------------------------------------------------
    # QUANTITIES
    # -------------------------------------------------------------------------
    
    quantity = models.PositiveIntegerField("Quantity")
    
    # -------------------------------------------------------------------------
    # PRICING
    # -------------------------------------------------------------------------
    
    unit_price = models.DecimalField(
        "Unit Price", 
        max_digits=10, 
        decimal_places=2
    )
    
    unit_cost = models.DecimalField(
        "Unit Cost",
        max_digits=10,
        decimal_places=2,
        help_text="Cost per unit (for COGS calculation)"
    )
    
    total_price = models.DecimalField(
        "Total Price", 
        max_digits=12, 
        decimal_places=2
    )
    
    total_cost = models.DecimalField(
        "Total Cost (COGS)",
        max_digits=12,
        decimal_places=2,
        help_text="Total cost of goods sold for this line"
    )
    
    # -------------------------------------------------------------------------
    # TAX
    # -------------------------------------------------------------------------
    
    tax_rate = models.ForeignKey(
        'core.TaxRate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uniform_sale_items'
    )
    
    tax_percentage = models.DecimalField(
        "Tax Percentage",
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00')
    )
    
    tax_amount = models.DecimalField(
        "Tax Amount",
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )
    
    # -------------------------------------------------------------------------
    # DISCOUNT
    # -------------------------------------------------------------------------
    
    discount_percentage = models.DecimalField(
        "Discount Percentage",
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00')
    )
    
    discount_amount = models.DecimalField(
        "Discount Amount",
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )
    
    # -------------------------------------------------------------------------
    # NOTES
    # -------------------------------------------------------------------------
    
    notes = models.TextField("Notes", blank=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Uniform Sale Item"
        verbose_name_plural = "Uniform Sale Items"
        ordering = ['sale', 'uniform_item']
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        size_info = f" - Size {self.size.name}" if self.size else ""
        return f"{self.uniform_item.name}{size_info}: {self.quantity} units"
    
    # -------------------------------------------------------------------------
    # SAVE METHOD
    # -------------------------------------------------------------------------
    
    def save(self, *args, **kwargs):
        """Calculate total price and cost"""
        # Calculate totals
        self.total_price = self.quantity * self.unit_price
        self.total_cost = self.quantity * self.unit_cost
        
        # Calculate discount
        if self.discount_percentage > 0:
            self.discount_amount = (self.total_price * self.discount_percentage) / 100
        
        # Calculate tax (on price after discount)
        taxable_amount = self.total_price - self.discount_amount
        if self.tax_percentage > 0:
            self.tax_amount = (taxable_amount * self.tax_percentage) / 100
        
        super().save(*args, **kwargs)


# =============================================================================
# STUDENT UNIFORM SIZE (RECOMMENDATION)
# =============================================================================

class StudentUniformSize(BaseModel):
    """Recommended uniform sizes for students"""
    
    SIZING_METHOD_CHOICES = [
        ('MEASURED', 'Based on Measurements'),
        ('FITTED', 'Physically Fitted'),
        ('PREVIOUS_ORDER', 'Based on Previous Order'),
        ('PARENT_PROVIDED', 'Parent Provided'),
        ('ESTIMATED', 'Estimated'),
    ]
    
    CONFIDENCE_LEVEL_CHOICES = [
        ('HIGH', 'High Confidence'),
        ('MEDIUM', 'Medium Confidence'),
        ('LOW', 'Low Confidence'),
    ]
    
    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='uniform_sizes',
        verbose_name="Student"
    )
    
    uniform_item = models.ForeignKey(
        UniformItem,
        on_delete=models.CASCADE,
        related_name='student_size_recommendations',
        verbose_name="Uniform Item"
    )
    
    recommended_size = models.ForeignKey(
        UniformSize,
        on_delete=models.CASCADE,
        related_name='student_recommendations',
        verbose_name="Recommended Size"
    )
    
    # -------------------------------------------------------------------------
    # CONTEXT
    # -------------------------------------------------------------------------
    
    academic_session = models.ForeignKey(
        'academics.AcademicSession',
        on_delete=models.CASCADE,
        related_name='student_uniform_sizes',
        verbose_name="Academic Session"
    )
    
    # -------------------------------------------------------------------------
    # SIZING METHOD
    # -------------------------------------------------------------------------
    
    sizing_method = models.CharField(
        "Sizing Method",
        max_length=20,
        choices=SIZING_METHOD_CHOICES,
        default='MEASURED'
    )
    
    confidence_level = models.CharField(
        "Confidence Level",
        max_length=15,
        choices=CONFIDENCE_LEVEL_CHOICES,
        default='HIGH'
    )
    
    # -------------------------------------------------------------------------
    # DATES
    # -------------------------------------------------------------------------
    
    recommendation_date = models.DateField("Recommendation Date", default=timezone.now)
    
    # -------------------------------------------------------------------------
    # ALTERNATIVE SIZES
    # -------------------------------------------------------------------------
    
    alternative_sizes = models.JSONField(
        "Alternative Sizes",
        blank=True,
        null=True,
        help_text="List of alternative size IDs"
    )
    
    # -------------------------------------------------------------------------
    # GROWTH ALLOWANCE
    # -------------------------------------------------------------------------
    
    growth_allowance = models.BooleanField("Growth Allowance", default=True)
    
    # -------------------------------------------------------------------------
    # TRACKING
    # -------------------------------------------------------------------------
    
    is_current = models.BooleanField("Is Current", default=True, db_index=True)
    notes = models.TextField("Notes", blank=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Student Uniform Size"
        verbose_name_plural = "Student Uniform Sizes"
        ordering = ['-recommendation_date']
        indexes = [
            models.Index(fields=['student', 'uniform_item']),
            models.Index(fields=['academic_session']),
            models.Index(fields=['is_current']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'uniform_item', 'academic_session'],
                condition=models.Q(is_current=True),
                name='unique_current_uniform_size_per_student_item_session'
            )
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.student.get_full_name()} - {self.uniform_item.name}: Size {self.recommended_size.name}"
    
    # -------------------------------------------------------------------------
    # SAVE METHOD
    # -------------------------------------------------------------------------
    
    def save(self, *args, **kwargs):
        """Mark other sizes as not current"""
        if self.is_current:
            StudentUniformSize.objects.filter(
                student=self.student,
                uniform_item=self.uniform_item,
                academic_session=self.academic_session,
                is_current=True
            ).exclude(pk=self.pk).update(is_current=False)
        
        super().save(*args, **kwargs)


# =============================================================================
# MEASUREMENT SESSION MODEL
# =============================================================================

class MeasurementSession(BaseModel):
    """Group measurements taken during a single session"""
    
    SESSION_TYPES = [
        ('ADMISSION', 'Admission Measurements'),
        ('ANNUAL', 'Annual Measurement Drive'),
        ('CLASS_BASED', 'Class-based Measurements'),
        ('INDIVIDUAL', 'Individual Measurement'),
        ('UNIFORM_ORDER', 'Uniform Order Measurements'),
    ]
    
    STATUS_CHOICES = [
        ('PLANNED', 'Planned'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    # -------------------------------------------------------------------------
    # SESSION DETAILS
    # -------------------------------------------------------------------------
    
    session_name = models.CharField("Session Name", max_length=100)
    session_type = models.CharField("Session Type", max_length=20, choices=SESSION_TYPES, db_index=True)
    
    # -------------------------------------------------------------------------
    # DATE AND TIME
    # -------------------------------------------------------------------------
    
    session_date = models.DateField("Session Date", db_index=True)
    start_time = models.TimeField("Start Time", null=True, blank=True)
    end_time = models.TimeField("End Time", null=True, blank=True)
    
    # -------------------------------------------------------------------------
    # ACADEMIC CONTEXT
    # -------------------------------------------------------------------------
    
    academic_session = models.ForeignKey(
        'academics.AcademicSession',
        on_delete=models.CASCADE,
        related_name='measurement_sessions',
        verbose_name="Academic Session"
    )
    
    # -------------------------------------------------------------------------
    # SCOPE
    # -------------------------------------------------------------------------
    
    target_classes = models.ManyToManyField(
        'academics.Class',
        blank=True,
        related_name='measurement_sessions',
        verbose_name="Target Classes"
    )
    
    target_students = models.ManyToManyField(
        'students.Student',
        blank=True,
        related_name='measurement_sessions',
        verbose_name="Target Students"
    )
    
    # -------------------------------------------------------------------------
    # STATUS
    # -------------------------------------------------------------------------
    
    status = models.CharField(
        "Status",
        max_length=15,
        choices=STATUS_CHOICES,
        default='PLANNED',
        db_index=True
    )
    
    # -------------------------------------------------------------------------
    # STATISTICS
    # -------------------------------------------------------------------------
    
    total_students_measured = models.PositiveIntegerField(
        "Total Students Measured",
        default=0
    )
    total_measurements_taken = models.PositiveIntegerField(
        "Total Measurements Taken",
        default=0
    )
    
    # -------------------------------------------------------------------------
    # COORDINATOR
    # -------------------------------------------------------------------------
    
    coordinator_id = models.CharField(
        "Coordinator ID",
        max_length=50,
        null=True,
        blank=True,
        help_text="User ID of session coordinator"
    )
    
    # -------------------------------------------------------------------------
    # NOTES
    # -------------------------------------------------------------------------
    
    notes = models.TextField("Notes", blank=True)
    
    # -------------------------------------------------------------------------
    # META CLASS
    # -------------------------------------------------------------------------
    
    class Meta:
        verbose_name = "Measurement Session"
        verbose_name_plural = "Measurement Sessions"
        ordering = ['-session_date']
        indexes = [
            models.Index(fields=['session_date', 'status']),
            models.Index(fields=['academic_session']),
        ]
    
    # -------------------------------------------------------------------------
    # STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    def __str__(self):
        return f"{self.session_name} - {self.session_date}"
    
    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_coordinator(self):
        """Get the coordinator user"""
        if not self.coordinator_id:
            return None
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.using('default').get(id=self.coordinator_id)
        except Exception as e:
            logger.error(f"Error fetching coordinator user: {e}")
            return None