# accounts/models.py

from django.contrib.auth.models import User
from django.db import models
from schoolara.managers import DefaultDatabaseManager
from django_countries.fields import CountryField
from image_cropping import ImageRatioField
from django.core.validators import  MinValueValidator, MaxValueValidator
from utils.models import DefaultDatabaseModel
import pytz

# -----------------------------------------
# SCHOOL MODEL
# -----------------------------------------
class School(DefaultDatabaseModel):
    SCHOOL_TYPE_CHOICES = [
        # Early Childhood Education
        ('KINDERGARTEN', 'Kindergarten/Nursery School'),
        ('KINDERGARTEN_PRIMARY', 'Kindergarten & Primary School'),
        
        # Primary Education
        ('PRIMARY', 'Primary School'),
        
        # Secondary Education
        ('SECONDARY', 'Secondary School'),
        ('HIGH_SCHOOL_GENERAL', 'High School (General)'),
        ('HIGH_SCHOOL_O_LEVEL', 'High School (O Level Only)'),
        ('HIGH_SCHOOL_A_LEVEL', 'High School (A Level Only)'),
        ('HIGH_SCHOOL_O_A_LEVEL', 'High School (O & A Level)'),
        
        # Combined Primary & Secondary
        ('PRIMARY_SECONDARY', 'Primary & Secondary School'),
        ('KINDERGARTEN_PRIMARY_SECONDARY', 'Kindergarten, Primary & Secondary School'),
        
        # Tertiary Education
        ('COLLEGE', 'College'),
        ('UNIVERSITY', 'University'),
        
        # Specialized Education
        ('VOCATIONAL', 'Vocational School'),
        ('TECHNICAL', 'Technical Institute'),
        ('SPECIAL_NEEDS', 'Special Needs School'),
    ]

    SUBSCRIPTION_PLANS = [
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
        ('multi_year', 'Multi-Year'),
        ('lifetime', 'Lifetime'),
    ]

    SCHOOL_BOARDING_TYPE = (
        ('DAY', 'Day School'),
        ('BOARDING', 'Boarding School'),
        ('MIXED', 'Day & Boarding'),
    )

    GENDER_TYPE_CHOICES = (
        ('MIXED', 'Co-educational'),
        ('BOYS', 'Boys Only'),
        ('GIRLS', 'Girls Only'),
    )

    full_name = models.CharField(max_length=191, unique=True)
    domain = models.CharField(
        max_length=191,
        unique=True,
        help_text="Email domain e.g. atepi.palabek.sch"
    )

    # Database alias (matches settings.DATABASES key)
    database_alias = models.CharField(
        max_length=50,
        unique=True,
        help_text="Database key e.g. atepi_palabek"
    )
    short_name = models.CharField(max_length=100, blank=True, null=True)
    receipt_name = models.CharField(max_length=191, blank=True, null=True)
    abbreviation = models.CharField(max_length=20, blank=True, null=True)

    school_type = models.CharField(
        max_length=30,
        choices=SCHOOL_TYPE_CHOICES,
        default='KINDERGARTEN_PRIMARY'
    )

    country = CountryField(blank_label='(Select Country)', null=True, blank=True)
    timezone = models.CharField(
        "Timezone",
        max_length=50, 
        choices=[(tz, tz) for tz in pytz.common_timezones], 
        default='UTC'
    )

    # School type classifications
    boarding_type = models.CharField(max_length=10, choices=SCHOOL_BOARDING_TYPE, default='DAY')
    gender_type = models.CharField(max_length=10, choices=GENDER_TYPE_CHOICES, default='MIXED')

    address = models.TextField()
    contact_phone = models.CharField(max_length=15)
    alternative_contact = models.CharField(max_length=15, null=True, blank=True)

    # Digital presence
    website = models.URLField(blank=True, null=True)
    facebook_page = models.URLField(blank=True, null=True)
    twitter_handle = models.CharField(max_length=50, blank=True, null=True)
    instagram_handle = models.CharField(max_length=50, blank=True, null=True)
    linkedin_page = models.URLField(blank=True, null=True)

    # Administrative details
    established_date = models.DateField()
    school_license = models.CharField(max_length=50, blank=True, null=True)
    student_capacity = models.PositiveIntegerField(default=0)
    operating_hours = models.CharField(max_length=100, help_text="e.g., Mon-Fri 8:00-17:00")

    # Visual branding
    school_logo = models.ImageField(
        upload_to='school_logos/', 
        null=True, 
        blank=True,
        help_text="School logo image (recommended: 512x512px PNG with transparent background)"
    )
    favicon = models.ImageField(
        upload_to='school_favicons/',
        null=True,
        blank=True,
        help_text="School favicon (recommended: 32x32px ICO or PNG format)"
    )
    brand_colors = models.JSONField(
        default=dict,
        blank=True,
        help_text="School brand colors as JSON: {'primary': '#hex', 'secondary': '#hex', 'accent': '#hex'}"
    )

    # Subscription fields
    subscription_plan = models.CharField(
        max_length=20,
        choices=SUBSCRIPTION_PLANS,
        default='monthly'
    )
    subscription_start = models.DateField(null=True, blank=True)
    subscription_end = models.DateField(null=True, blank=True)
    is_active_subscription = models.BooleanField(default=True)

    # Add the custom manager
    objects = DefaultDatabaseManager()

    def __str__(self):
        return self.full_name


# -----------------------------------------
# USER PROFILE MODEL
# -----------------------------------------
class UserProfile(DefaultDatabaseModel):
    USER_ROLES = [
        ('Administrator', 'Administrator'),
        ('Director of Studies', 'Director of Studies'),
        ('Finance Manager', 'Finance Manager'),
        ('Registrar', 'Registrar'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)

    name_of_person_in_charge = models.CharField(max_length=255, blank=True)
    role = models.CharField(max_length=30, choices=USER_ROLES)

    photo = models.ImageField("Photo", upload_to='user_photos/', blank=True, null=True)
    cropping = ImageRatioField('photo', '300x300')   # FIXED FIELD NAME

    # Theme settings
    fixed_header = models.BooleanField(default=False)
    fixed_sidebar = models.BooleanField(default=False)
    fixed_footer = models.BooleanField(default=False)

    header_class = models.CharField(max_length=100, blank=True, default='')
    sidebar_class = models.CharField(max_length=100, blank=True, default='')

    page_tabs_style = models.CharField(
        max_length=50,
        choices=[
            ('body-tabs-shadow', 'Shadow Style'),
            ('body-tabs-line', 'Line Style'),
        ],
        default='body-tabs-shadow'
    )

    theme_color = models.CharField(
        max_length=50,
        choices=[
            ('app-theme-white', 'White Theme'),
            ('app-theme-gray', 'Gray Theme'),
        ],
        default='app-theme-white'
    )

    # Add the custom manager
    objects = DefaultDatabaseManager()

    def __str__(self):
        return f"{self.user.username} - {self.role}"


# -----------------------------------------
# USER MANAGEMENT SETTINGS
# -----------------------------------------
class UserManagementSettings(DefaultDatabaseModel):
    """Configuration model for user management system."""

    # Password Policy
    min_password_length = models.PositiveIntegerField(
        default=8,
        validators=[MinValueValidator(6), MaxValueValidator(128)]
    )
    require_uppercase = models.BooleanField(default=True)
    require_lowercase = models.BooleanField(default=True)
    require_numbers = models.BooleanField(default=True)
    require_special_chars = models.BooleanField(default=True)

    password_expiry_days = models.PositiveIntegerField(
        default=90,
        validators=[MinValueValidator(30), MaxValueValidator(365)]
    )
    password_history_count = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(24)]
    )

    # Session Management
    default_session_timeout_minutes = models.PositiveIntegerField(
        default=480,
        validators=[MinValueValidator(15), MaxValueValidator(1440)]
    )
    max_concurrent_sessions = models.PositiveIntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    session_warning_minutes = models.PositiveIntegerField(
        default=15,
        validators=[MinValueValidator(5), MaxValueValidator(60)]
    )

    # Account Security
    max_failed_login_attempts = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(3), MaxValueValidator(20)]
    )
    account_lockout_duration_minutes = models.PositiveIntegerField(
        default=30,
        validators=[MinValueValidator(5), MaxValueValidator(1440)]
    )
    enable_two_factor_default = models.BooleanField(default=False)
    force_password_change_on_first_login = models.BooleanField(default=True)

    # User Registration
    allow_user_registration = models.BooleanField(default=False)
    require_admin_approval = models.BooleanField(default=True)
    default_user_type = models.CharField(max_length=20, default='STAFF')

    # Notifications
    send_welcome_emails = models.BooleanField(default=True)
    send_password_expiry_warnings = models.BooleanField(default=True)
    password_expiry_warning_days = models.PositiveIntegerField(
        default=7,
        validators=[MinValueValidator(1), MaxValueValidator(30)]
    )

    # Audit & Logging
    log_login_attempts = models.BooleanField(default=True)
    log_permission_changes = models.BooleanField(default=True)

    # Add the custom manager
    objects = DefaultDatabaseManager()

    def __str__(self):
        return f"User Management Settings"
