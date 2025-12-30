# accounts/models.py

from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_countries.fields import CountryField
from django.core.validators import RegexValidator, MaxValueValidator, MinValueValidator
from django.core.exceptions import ValidationError
import logging
from zoneinfo import available_timezones

# Import DefaultDatabaseModel from utils
from utils.models import DefaultDatabaseModel

logger = logging.getLogger(__name__)


# =============================================================================
# VALIDATORS
# =============================================================================

phone_validator = RegexValidator(
    regex=r'^\+?1?\d{9,15}$',
    message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
)


# =============================================================================
# SCHOOL MODEL
# =============================================================================

class School(DefaultDatabaseModel):
    """School model to represent different schools in the system"""
    
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
        ('quarterly', 'Quarterly'),
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

    # -------------------------------------------------------------------------
    # BASIC INFORMATION
    # -------------------------------------------------------------------------
    
    full_name = models.CharField(
        "Full School Name",
        max_length=191,
        unique=True,
        help_text="Official full name of the school"
    )
    short_name = models.CharField(
        "Short Name",
        max_length=100,
        blank=True,
        null=True,
        help_text="Abbreviated school name"
    )
    receipt_name = models.CharField(
        "Receipt Name",
        max_length=191,
        blank=True,
        null=True,
        help_text="Name to appear on receipts and invoices"
    )
    abbreviation = models.CharField(
        "Abbreviation",
        max_length=20,
        blank=True,
        null=True,
        help_text="School acronym (e.g., 'KHS' for Kampala High School)"
    )
    description = models.TextField(
        "Description",
        blank=True,
        null=True,
        help_text="Brief description of the school"
    )

    # -------------------------------------------------------------------------
    # SYSTEM CONFIGURATION
    # -------------------------------------------------------------------------
    
    domain = models.CharField(
        "Email Domain",
        max_length=191,
        unique=True,
        help_text="Email domain e.g. kampala.sch.ug"
    )
    database_alias = models.CharField(
        "Database Alias",
        max_length=50,
        unique=True,
        help_text="Database key e.g. kampala_high_school"
    )

    # -------------------------------------------------------------------------
    # SCHOOL CLASSIFICATION
    # -------------------------------------------------------------------------
    
    school_type = models.CharField(
        "School Type",
        max_length=30,
        choices=SCHOOL_TYPE_CHOICES,
        default='PRIMARY_SECONDARY',
        help_text="Educational level(s) offered"
    )
    boarding_type = models.CharField(
        "Boarding Type",
        max_length=10,
        choices=SCHOOL_BOARDING_TYPE,
        default='DAY',
        help_text="Day, boarding, or mixed"
    )
    gender_type = models.CharField(
        "Gender Type",
        max_length=10,
        choices=GENDER_TYPE_CHOICES,
        default='MIXED',
        help_text="Co-ed, boys only, or girls only"
    )

    # -------------------------------------------------------------------------
    # LOCATION & CONTACT
    # -------------------------------------------------------------------------
    
    address = models.TextField("Physical Address")
    city = models.CharField("City/Town", max_length=100, blank=True, null=True)
    state_province = models.CharField(
        "State/Province/Region",
        max_length=100,
        blank=True,
        null=True
    )
    postal_code = models.CharField("Postal Code", max_length=20, blank=True, null=True)
    country = CountryField(
        "Country",
        blank_label='(Select Country)',
        default='UG'
    )
    
    contact_phone = models.CharField(
        "Primary Phone",
        max_length=15,
        validators=[phone_validator]
    )
    alternative_contact = models.CharField(
        "Alternative Phone",
        max_length=15,
        null=True,
        blank=True,
        validators=[phone_validator]
    )
    contact_email = models.EmailField(
        "Contact Email",
        blank=True,
        null=True,
        help_text="General school contact email"
    )

    # -------------------------------------------------------------------------
    # SYSTEM SETTINGS
    # -------------------------------------------------------------------------
    
    timezone = models.CharField(
        "Timezone",
        max_length=50,
        choices=[(tz, tz) for tz in sorted(available_timezones())],
        default='Africa/Kampala',
        help_text="School's timezone for scheduling"
    )
    language = models.CharField(
        "Primary Language",
        max_length=10,
        choices=[
            ('en', 'English'),
            ('fr', 'French'),
            ('es', 'Spanish'),
            ('sw', 'Swahili'),
            ('lg', 'Luganda'),
            ('ar', 'Arabic'),
        ],
        default='en',
        help_text="Primary language of instruction"
    )

    # -------------------------------------------------------------------------
    # DIGITAL PRESENCE
    # -------------------------------------------------------------------------
    
    website = models.URLField("Website", blank=True, null=True)
    facebook_page = models.URLField("Facebook Page", blank=True, null=True)
    twitter_handle = models.CharField(
        "Twitter Handle",
        max_length=50,
        blank=True,
        null=True,
        help_text="Without @ symbol"
    )
    instagram_handle = models.CharField(
        "Instagram Handle",
        max_length=50,
        blank=True,
        null=True,
        help_text="Without @ symbol"
    )
    linkedin_page = models.URLField("LinkedIn Page", blank=True, null=True)
    youtube_channel = models.URLField("YouTube Channel", blank=True, null=True)

    # -------------------------------------------------------------------------
    # ADMINISTRATIVE DETAILS
    # -------------------------------------------------------------------------
    
    established_date = models.DateField("Date Established")
    school_license = models.CharField(
        "School License Number",
        max_length=50,
        blank=True,
        null=True,
        help_text="Government registration/license number"
    )
    registration_number = models.CharField(
        "Registration Number",
        max_length=50,
        blank=True,
        null=True,
        help_text="Ministry of Education registration number"
    )
    tax_id = models.CharField(
        "Tax ID/TIN",
        max_length=50,
        blank=True,
        null=True,
        help_text="Tax Identification Number"
    )
    student_capacity = models.PositiveIntegerField(
        "Student Capacity",
        default=0,
        help_text="Maximum number of students the school can accommodate"
    )
    operating_hours = models.CharField(
        "Operating Hours",
        max_length=100,
        help_text="e.g., Mon-Fri 7:30 AM - 5:00 PM"
    )

    # -------------------------------------------------------------------------
    # VISUAL BRANDING
    # -------------------------------------------------------------------------
    
    school_logo = models.ImageField(
        "School Logo",
        upload_to='school_logos/',
        null=True,
        blank=True,
        help_text="School logo image (recommended: 512x512px PNG with transparent background)"
    )
    favicon = models.ImageField(
        "Favicon",
        upload_to='school_favicons/',
        null=True,
        blank=True,
        help_text="School favicon (recommended: 32x32px ICO or PNG format)"
    )
    brand_colors = models.JSONField(
        "Brand Colors",
        default=dict,
        blank=True,
        help_text="School brand colors as JSON: {'primary': '#hex', 'secondary': '#hex', 'accent': '#hex'}"
    )
    school_motto = models.CharField(
        "School Motto",
        max_length=200,
        blank=True,
        null=True,
        help_text="School motto or slogan"
    )

    # -------------------------------------------------------------------------
    # SUBSCRIPTION & BILLING
    # -------------------------------------------------------------------------
    
    subscription_plan = models.CharField(
        "Subscription Plan",
        max_length=20,
        choices=SUBSCRIPTION_PLANS,
        default='yearly'
    )
    subscription_start = models.DateField(
        "Subscription Start Date",
        null=True,
        blank=True
    )
    subscription_end = models.DateField(
        "Subscription End Date",
        null=True,
        blank=True
    )
    is_active_subscription = models.BooleanField(
        "Active Subscription",
        default=True,
        help_text="Whether the school's subscription is currently active"
    )
    
    # -------------------------------------------------------------------------
    # ADDITIONAL SETTINGS
    # -------------------------------------------------------------------------
    
    enable_online_applications = models.BooleanField(
        "Enable Online Applications",
        default=True,
        help_text="Allow students to apply online"
    )
    enable_parent_portal = models.BooleanField(
        "Enable Parent Portal",
        default=True,
        help_text="Allow parents to access the portal"
    )
    enable_student_portal = models.BooleanField(
        "Enable Student Portal",
        default=True,
        help_text="Allow students to access the portal"
    )

    # -------------------------------------------------------------------------
    # META & METHODS
    # -------------------------------------------------------------------------
    
    class Meta:
        db_table = 'schools'
        verbose_name = "School"
        verbose_name_plural = "Schools"
        ordering = ['full_name']
        indexes = [
            models.Index(fields=['domain']),
            models.Index(fields=['database_alias']),
            models.Index(fields=['is_active_subscription']),
        ]

    def __str__(self):
        return self.full_name

    def clean(self):
        """Validate school data"""
        super().clean()
        errors = {}
        
        # Validate domain format
        if self.domain and ' ' in self.domain:
            errors['domain'] = "Domain cannot contain spaces"
        
        # Validate database alias format
        if self.database_alias:
            if not self.database_alias.replace('_', '').isalnum():
                errors['database_alias'] = "Database alias can only contain letters, numbers, and underscores"
        
        if errors:
            raise ValidationError(errors)

    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------
    
    @property
    def active_users_count(self):
        """Get count of active users in this school"""
        return UserProfile.objects.filter(school=self, user__is_active=True).count()
    
    @property
    def active_students_count(self):
        """Get count of active students in this school"""
        try:
            from students.models import Student
            return Student.objects.filter(enrollment_status='ACTIVE').count()
        except ImportError:
            return 0
    
    @property
    def active_teachers_count(self):
        from hr.models import Teacher
        return Teacher.objects.filter(
            staff__is_active=True,
            staff__date_of_leaving__isnull=True
        ).count()
    
    @property
    def display_name(self):
        """Get display name (short name if available, otherwise full name)"""
        return self.short_name or self.full_name
    
    @property
    def is_subscription_active(self):
        """Check if subscription is currently active"""
        if not self.is_active_subscription:
            return False
        
        if self.subscription_end:
            from django.utils import timezone
            return timezone.now().date() <= self.subscription_end
        
        return True
    
    @property
    def subscription_status(self):
        """Get human-readable subscription status"""
        if self.is_subscription_active:
            return "Active"
        elif self.subscription_end:
            from django.utils import timezone
            if timezone.now().date() > self.subscription_end:
                return "Expired"
        return "Inactive"

    # -------------------------------------------------------------------------
    # METHODS
    # -------------------------------------------------------------------------
    
    def get_social_media_links(self):
        """Get all social media links"""
        links = {}
        if self.facebook_page:
            links['facebook'] = self.facebook_page
        if self.twitter_handle:
            links['twitter'] = f"https://twitter.com/{self.twitter_handle}"
        if self.instagram_handle:
            links['instagram'] = f"https://instagram.com/{self.instagram_handle}"
        if self.linkedin_page:
            links['linkedin'] = self.linkedin_page
        if self.youtube_channel:
            links['youtube'] = self.youtube_channel
        return links
    
    def get_contact_info(self):
        """Get complete contact information"""
        return {
            'email': self.contact_email,
            'phone': self.contact_phone,
            'alternative_phone': self.alternative_contact,
            'address': self.address,
            'city': self.city,
            'country': str(self.country.name) if self.country else None,
        }


# =============================================================================
# USER PROFILE MODEL
# =============================================================================

class UserProfile(DefaultDatabaseModel):
    """Extended profile information for school users"""

    USER_ROLES = [
        ('SUPER_ADMIN', 'Super Administrator'),
        ('ADMINISTRATOR', 'School Administrator'),
        ('DIRECTOR_STUDIES', 'Director of Studies'),
        ('FINANCE_MANAGER', 'Finance Manager'),
        ('REGISTRAR', 'Registrar'),
        ('HEAD_TEACHER', 'Head Teacher'),
        ('DEPUTY_HEAD', 'Deputy Head Teacher'),
        ('DEAN', 'Dean'),
        ('HOD', 'Head of Department'),
        ('TEACHER', 'Teacher'),
        ('LIBRARIAN', 'Librarian'),
        ('NURSE', 'School Nurse'),
        ('COUNSELOR', 'Counselor'),
        ('IT_ADMIN', 'IT Administrator'),
        ('ACCOUNTANT', 'Accountant'),
        ('RECEPTIONIST', 'Receptionist'),
        ('SECURITY', 'Security Staff'),
        ('SUPPORT_STAFF', 'Support Staff'),
    ]

    EMPLOYMENT_TYPE_CHOICES = [
        ('FULL_TIME', 'Full Time'),
        ('PART_TIME', 'Part Time'),
        ('CONTRACT', 'Contract'),
        ('TEMPORARY', 'Temporary'),
        ('VOLUNTEER', 'Volunteer'),
    ]

    GENDER_CHOICES = (
        ('MALE', 'Male'),
        ('FEMALE', 'Female'),
    )

    LANGUAGE_CHOICES = (
        ('en', 'English'),
        ('fr', 'French'),
        ('es', 'Spanish'),
        ('sw', 'Swahili'),
        ('lg', 'Luganda'),
        ('ar', 'Arabic'),
    )

    # -------------------------------------------------------------------------
    # CORE RELATIONSHIPS
    # -------------------------------------------------------------------------
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='staff_profiles'
    )
    role = models.CharField(
        "Role",
        max_length=30,
        choices=USER_ROLES,
        default='TEACHER'
    )

    # -------------------------------------------------------------------------
    # PERSONAL INFORMATION
    # -------------------------------------------------------------------------
    
    photo = models.ImageField(
        "Profile Photo",
        upload_to='user_photos/',
        null=True,
        blank=True
    )
    mobile = models.CharField(
        "Mobile Number",
        max_length=15,
        null=True,
        blank=True,
        validators=[phone_validator]
    )
    date_of_birth = models.DateField(
        "Date of Birth",
        null=True,
        blank=True
    )
    gender = models.CharField(
        "Gender",
        max_length=20,
        choices=GENDER_CHOICES,
        null=True,
        blank=True
    )
    national_id = models.CharField(
        "National ID",
        max_length=50,
        blank=True,
        null=True,
        help_text="National ID or Passport number"
    )

    # -------------------------------------------------------------------------
    # LOCATION
    # -------------------------------------------------------------------------
    
    address = models.TextField("Home Address", null=True, blank=True)
    city = models.CharField("City/Town", max_length=100, null=True, blank=True)
    state_province = models.CharField(
        "State/Province",
        max_length=100,
        null=True,
        blank=True
    )
    postal_code = models.CharField("Postal Code", max_length=20, null=True, blank=True)
    country = CountryField(
        "Country",
        blank_label='(Select Country)',
        default='UG'
    )

    # -------------------------------------------------------------------------
    # LOCALIZATION
    # -------------------------------------------------------------------------
    
    language = models.CharField(
        "Preferred Language",
        max_length=10,
        choices=LANGUAGE_CHOICES,
        default='en'
    )
    timezone = models.CharField(
        "Timezone",
        max_length=50,
        choices=[(tz, tz) for tz in sorted(available_timezones())],
        default='Africa/Kampala'
    )

    # -------------------------------------------------------------------------
    # EMPLOYMENT DETAILS
    # -------------------------------------------------------------------------
    
    employee_id = models.CharField(
        "Employee ID",
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        help_text="Unique staff identifier"
    )
    department = models.CharField(
        "Department",
        max_length=100,
        blank=True,
        null=True,
        help_text="e.g., Mathematics, Science, Administration"
    )
    position = models.CharField(
        "Position/Title",
        max_length=100,
        blank=True,
        null=True,
        help_text="Official job title"
    )
    employment_type = models.CharField(
        "Employment Type",
        max_length=20,
        choices=EMPLOYMENT_TYPE_CHOICES,
        default='FULL_TIME'
    )
    date_of_appointment = models.DateField(
        "Date of Appointment",
        null=True,
        blank=True,
        help_text="Date when staff member joined the school"
    )
    qualification = models.CharField(
        "Highest Qualification",
        max_length=200,
        blank=True,
        null=True,
        help_text="e.g., Bachelor's Degree in Education, Master's in Mathematics"
    )
    specialization = models.CharField(
        "Area of Specialization",
        max_length=200,
        blank=True,
        null=True,
        help_text="Subject or area of expertise"
    )

    # -------------------------------------------------------------------------
    # REPORTING STRUCTURE
    # -------------------------------------------------------------------------
    
    reports_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subordinates',
        help_text="Direct supervisor/manager"
    )

    # -------------------------------------------------------------------------
    # EMERGENCY CONTACT
    # -------------------------------------------------------------------------
    
    emergency_contact_name = models.CharField(
        "Emergency Contact Name",
        max_length=100,
        blank=True,
        null=True
    )
    emergency_contact_phone = models.CharField(
        "Emergency Contact Phone",
        max_length=15,
        blank=True,
        null=True,
        validators=[phone_validator]
    )
    emergency_contact_relationship = models.CharField(
        "Relationship to Emergency Contact",
        max_length=50,
        blank=True,
        null=True,
        help_text="e.g., Spouse, Parent, Sibling"
    )

    # -------------------------------------------------------------------------
    # PERMISSIONS - STUDENT DATA
    # -------------------------------------------------------------------------
    
    can_view_student_data = models.BooleanField(
        "Can View Student Data",
        default=False,
        help_text="Can view student records and information"
    )
    can_edit_student_data = models.BooleanField(
        "Can Edit Student Data",
        default=False,
        help_text="Can modify student records"
    )

    # -------------------------------------------------------------------------
    # PERMISSIONS - FINANCIAL DATA
    # -------------------------------------------------------------------------
    
    can_view_financial_data = models.BooleanField(
        "Can View Financial Data",
        default=False,
        help_text="Can view financial reports and transactions"
    )
    can_edit_financial_data = models.BooleanField(
        "Can Edit Financial Data",
        default=False,
        help_text="Can process payments and modify financial records"
    )

    # -------------------------------------------------------------------------
    # PERMISSIONS - ACADEMIC DATA
    # -------------------------------------------------------------------------
    
    can_view_academic_data = models.BooleanField(
        "Can View Academic Data",
        default=False,
        help_text="Can view grades, assessments, and academic records"
    )
    can_edit_academic_data = models.BooleanField(
        "Can Edit Academic Data",
        default=False,
        help_text="Can enter grades and modify academic records"
    )

    # -------------------------------------------------------------------------
    # PERMISSIONS - HR DATA
    # -------------------------------------------------------------------------
    
    can_view_hr_data = models.BooleanField(
        "Can View HR Data",
        default=False,
        help_text="Can view staff records and HR information"
    )
    can_edit_hr_data = models.BooleanField(
        "Can Edit HR Data",
        default=False,
        help_text="Can modify staff records and HR data"
    )

    # -------------------------------------------------------------------------
    # PERMISSIONS - INVENTORY
    # -------------------------------------------------------------------------
    
    can_view_inventory_data = models.BooleanField(
        "Can View Inventory Data",
        default=False,
        help_text="Can view inventory and stock levels"
    )
    can_edit_inventory_data = models.BooleanField(
        "Can Edit Inventory Data",
        default=False,
        help_text="Can manage inventory and stock"
    )

    # -------------------------------------------------------------------------
    # THEME PREFERENCES
    # -------------------------------------------------------------------------
    
    theme_color = models.CharField(
        "Theme Color",
        max_length=50,
        choices=[
            ('app-theme-white', 'White Theme'),
            ('app-theme-gray', 'Gray Theme'),
        ],
        default='app-theme-white'
    )
    fixed_header = models.BooleanField("Fixed Header", default=False)
    fixed_sidebar = models.BooleanField("Fixed Sidebar", default=False)
    fixed_footer = models.BooleanField("Fixed Footer", default=False)
    header_class = models.CharField("Header Class", max_length=100, blank=True, default='')
    sidebar_class = models.CharField("Sidebar Class", max_length=100, blank=True, default='')
    page_tabs_style = models.CharField(
        "Page Tabs Style",
        max_length=50,
        choices=[
            ('body-tabs-shadow', 'Shadow Style'),
            ('body-tabs-line', 'Line Style'),
        ],
        default='body-tabs-shadow'
    )

    # -------------------------------------------------------------------------
    # SECURITY FIELDS
    # -------------------------------------------------------------------------
    
    password_changed_at = models.DateTimeField(
        "Password Last Changed",
        null=True,
        blank=True
    )
    failed_login_attempts = models.PositiveIntegerField(
        "Failed Login Attempts",
        default=0
    )
    account_locked_until = models.DateTimeField(
        "Account Locked Until",
        null=True,
        blank=True
    )
    last_activity = models.DateTimeField(
        "Last Activity",
        null=True,
        blank=True
    )
    two_factor_enabled = models.BooleanField(
        "Two-Factor Authentication Enabled",
        default=False
    )
    force_password_change = models.BooleanField(
        "Force Password Change",
        default=False,
        help_text="User must change password on next login"
    )

    # -------------------------------------------------------------------------
    # NOTIFICATION PREFERENCES
    # -------------------------------------------------------------------------
    
    email_notifications = models.BooleanField(
        "Email Notifications",
        default=True,
        help_text="Receive email notifications"
    )
    sms_notifications = models.BooleanField(
        "SMS Notifications",
        default=False,
        help_text="Receive SMS notifications"
    )

    # -------------------------------------------------------------------------
    # META & STRING REPRESENTATION
    # -------------------------------------------------------------------------
    
    class Meta:
        db_table = 'user_profiles'
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'
        ordering = ['user__username']
        indexes = [
            models.Index(fields=['school', 'role']),
            models.Index(fields=['employee_id']),
            models.Index(fields=['user']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    # -------------------------------------------------------------------------
    # PERMISSION HELPER METHODS
    # -------------------------------------------------------------------------
    
    def is_admin_user(self):
        """Check if user has admin privileges"""
        return self.role in ['SUPER_ADMIN', 'ADMINISTRATOR', 'DIRECTOR_STUDIES'] or self.user.is_superuser

    def can_manage_users(self):
        """Check if user can manage other users"""
        return self.role in ['SUPER_ADMIN', 'ADMINISTRATOR', 'DIRECTOR_STUDIES'] or self.user.is_superuser

    def can_manage_finances(self):
        """Check if user can manage financial operations"""
        return (
            self.role in ['SUPER_ADMIN', 'ADMINISTRATOR', 'FINANCE_MANAGER', 'ACCOUNTANT']
            or self.user.is_superuser
            or self.can_edit_financial_data
        )

    def can_manage_academics(self):
        """Check if user can manage academic operations"""
        return (
            self.role in ['SUPER_ADMIN', 'ADMINISTRATOR', 'DIRECTOR_STUDIES', 'HEAD_TEACHER', 'DEPUTY_HEAD']
            or self.user.is_superuser
            or self.can_edit_academic_data
        )

    def can_manage_hr(self):
        """Check if user can manage HR operations"""
        return (
            self.role in ['SUPER_ADMIN', 'ADMINISTRATOR', 'DIRECTOR_STUDIES']
            or self.user.is_superuser
            or self.can_edit_hr_data
        )

    def can_manage_students(self):
        """Check if user can manage student records"""
        return (
            self.role in ['SUPER_ADMIN', 'ADMINISTRATOR', 'DIRECTOR_STUDIES', 'REGISTRAR']
            or self.user.is_superuser
            or self.can_edit_student_data
        )

    def can_manage_inventory(self):
        """Check if user can manage inventory"""
        return (
            self.role in ['SUPER_ADMIN', 'ADMINISTRATOR']
            or self.user.is_superuser
            or self.can_edit_inventory_data
        )

    def is_teacher(self):
        """Check if user is a teacher"""
        return self.role in ['TEACHER', 'HEAD_TEACHER', 'DEPUTY_HEAD', 'HOD']

    def is_senior_staff(self):
        """Check if user is senior staff"""
        return self.role in [
            'SUPER_ADMIN', 'ADMINISTRATOR', 'DIRECTOR_STUDIES',
            'HEAD_TEACHER', 'DEPUTY_HEAD', 'FINANCE_MANAGER'
        ]

    # -------------------------------------------------------------------------
    # QUERY HELPER METHODS
    # -------------------------------------------------------------------------
    
    def get_school_users(self):
        """Get all active users in the same school"""
        if self.school:
            return User.objects.filter(
                profile__school=self.school,
                is_active=True
            ).select_related('profile')
        return User.objects.none()

    def get_subordinates(self):
        """Get all users who report to this user"""
        return User.objects.filter(
            profile__reports_to=self.user,
            is_active=True
        ).select_related('profile')

    def get_supervisor(self):
        """Get the user's supervisor"""
        return self.reports_to

    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------
    
    @property
    def school_name(self):
        """Get school name"""
        return self.school.full_name if self.school else None

    @property
    def full_name(self):
        """Get user's full name"""
        return self.user.get_full_name() or self.user.username

    @property
    def age(self):
        """Calculate user's age"""
        if self.date_of_birth:
            from django.utils import timezone
            today = timezone.now().date()
            return (
                today.year - self.date_of_birth.year
                - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
            )
        return None

    @property
    def years_of_service(self):
        """Calculate years of service"""
        if self.date_of_appointment:
            from django.utils import timezone
            today = timezone.now().date()
            years = (
                today.year - self.date_of_appointment.year
                - ((today.month, today.day) < (self.date_of_appointment.month, self.date_of_appointment.day))
            )
            return max(0, years)
        return None

    @property
    def is_account_locked(self):
        """Check if account is currently locked"""
        if self.account_locked_until:
            from django.utils import timezone
            return timezone.now() < self.account_locked_until
        return False

    # -------------------------------------------------------------------------
    # METHODS
    # -------------------------------------------------------------------------
    
    def get_display_name(self):
        """Get display name for UI"""
        full_name = self.user.get_full_name()
        if full_name:
            return full_name
        return self.user.username

    def get_contact_info(self):
        """Get complete contact information"""
        return {
            'email': self.user.email,
            'mobile': self.mobile,
            'address': self.address,
            'city': self.city,
            'country': str(self.country.name) if self.country else None,
        }

    def get_emergency_contact(self):
        """Get emergency contact information"""
        return {
            'name': self.emergency_contact_name,
            'phone': self.emergency_contact_phone,
            'relationship': self.emergency_contact_relationship,
        }

    def reset_failed_login_attempts(self):
        """Reset failed login attempts counter"""
        self.failed_login_attempts = 0
        self.account_locked_until = None
        self.save(update_fields=['failed_login_attempts', 'account_locked_until'])

    def increment_failed_login_attempts(self):
        """Increment failed login attempts and lock account if necessary"""
        from django.utils import timezone
        from datetime import timedelta
        
        self.failed_login_attempts += 1
        
        # Get settings to determine lockout threshold
        try:
            settings = UserManagementSettings.objects.first()
            max_attempts = settings.max_failed_login_attempts if settings else 5
            lockout_duration = settings.account_lockout_duration_minutes if settings else 30
        except:
            max_attempts = 5
            lockout_duration = 30
        
        if self.failed_login_attempts >= max_attempts:
            self.account_locked_until = timezone.now() + timedelta(minutes=lockout_duration)
        
        self.save(update_fields=['failed_login_attempts', 'account_locked_until'])

    def update_last_activity(self):
        """Update last activity timestamp"""
        from django.utils import timezone
        self.last_activity = timezone.now()
        self.save(update_fields=['last_activity'])


# =============================================================================
# USER MANAGEMENT SETTINGS
# =============================================================================

class UserManagementSettings(DefaultDatabaseModel):
    """Configuration model for user management system"""
    
    # -------------------------------------------------------------------------
    # PASSWORD POLICY
    # -------------------------------------------------------------------------
    
    min_password_length = models.PositiveIntegerField(
        "Minimum Password Length",
        default=8,
        validators=[MinValueValidator(6), MaxValueValidator(128)],
        help_text="Minimum number of characters required in passwords"
    )
    require_uppercase = models.BooleanField(
        "Require Uppercase Letters",
        default=True,
        help_text="Passwords must contain at least one uppercase letter"
    )
    require_lowercase = models.BooleanField(
        "Require Lowercase Letters",
        default=True,
        help_text="Passwords must contain at least one lowercase letter"
    )
    require_numbers = models.BooleanField(
        "Require Numbers",
        default=True,
        help_text="Passwords must contain at least one number"
    )
    require_special_chars = models.BooleanField(
        "Require Special Characters",
        default=True,
        help_text="Passwords must contain at least one special character"
    )
    
    password_expiry_days = models.PositiveIntegerField(
        "Password Expiry (Days)",
        default=90,
        validators=[MinValueValidator(30), MaxValueValidator(365)],
        help_text="Number of days before passwords expire"
    )
    password_history_count = models.PositiveIntegerField(
        "Password History Count",
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(24)],
        help_text="Number of previous passwords to remember"
    )
    
    # -------------------------------------------------------------------------
    # SESSION MANAGEMENT
    # -------------------------------------------------------------------------
    
    default_session_timeout_minutes = models.PositiveIntegerField(
        "Default Session Timeout (Minutes)",
        default=480,
        validators=[MinValueValidator(15), MaxValueValidator(1440)],
        help_text="Session timeout in minutes (default: 8 hours)"
    )
    max_concurrent_sessions = models.PositiveIntegerField(
        "Max Concurrent Sessions",
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Maximum number of active sessions per user"
    )
    session_warning_minutes = models.PositiveIntegerField(
        "Session Warning (Minutes)",
        default=15,
        validators=[MinValueValidator(5), MaxValueValidator(60)],
        help_text="Minutes before session expires to show warning"
    )
    
    # -------------------------------------------------------------------------
    # ACCOUNT SECURITY
    # -------------------------------------------------------------------------
    
    max_failed_login_attempts = models.PositiveIntegerField(
        "Max Failed Login Attempts",
        default=5,
        validators=[MinValueValidator(3), MaxValueValidator(20)],
        help_text="Number of failed login attempts before account lockout"
    )
    account_lockout_duration_minutes = models.PositiveIntegerField(
        "Account Lockout Duration (Minutes)",
        default=30,
        validators=[MinValueValidator(5), MaxValueValidator(1440)],
        help_text="How long to lock account after max failed attempts"
    )
    enable_two_factor_default = models.BooleanField(
        "Enable Two-Factor by Default",
        default=False,
        help_text="Enable two-factor authentication for new users"
    )
    force_password_change_on_first_login = models.BooleanField(
        "Force Password Change on First Login",
        default=True,
        help_text="Require new users to change password on first login"
    )
    
    # -------------------------------------------------------------------------
    # USER REGISTRATION
    # -------------------------------------------------------------------------
    
    allow_user_registration = models.BooleanField(
        "Allow User Registration",
        default=False,
        help_text="Allow users to self-register"
    )
    require_admin_approval = models.BooleanField(
        "Require Admin Approval",
        default=True,
        help_text="New registrations require admin approval"
    )
    default_user_role = models.CharField(
        "Default User Role",
        max_length=30,
        default='TEACHER',
        help_text="Default role assigned to new users"
    )
    
    # -------------------------------------------------------------------------
    # NOTIFICATIONS
    # -------------------------------------------------------------------------
    
    send_welcome_emails = models.BooleanField(
        "Send Welcome Emails",
        default=True,
        help_text="Send welcome email to new users"
    )
    send_password_expiry_warnings = models.BooleanField(
        "Send Password Expiry Warnings",
        default=True,
        help_text="Send email warnings before password expires"
    )
    password_expiry_warning_days = models.PositiveIntegerField(
        "Password Expiry Warning (Days)",
        default=7,
        validators=[MinValueValidator(1), MaxValueValidator(30)],
        help_text="Days before expiry to send warning"
    )
    send_account_lockout_notifications = models.BooleanField(
        "Send Account Lockout Notifications",
        default=True,
        help_text="Notify users when their account is locked"
    )
    
    # -------------------------------------------------------------------------
    # AUDIT & LOGGING
    # -------------------------------------------------------------------------
    
    log_login_attempts = models.BooleanField(
        "Log Login Attempts",
        default=True,
        help_text="Log all login attempts (successful and failed)"
    )
    log_permission_changes = models.BooleanField(
        "Log Permission Changes",
        default=True,
        help_text="Log changes to user permissions and roles"
    )
    log_password_changes = models.BooleanField(
        "Log Password Changes",
        default=True,
        help_text="Log when users change their passwords"
    )
    
    # -------------------------------------------------------------------------
    # IP RESTRICTIONS
    # -------------------------------------------------------------------------
    
    enable_ip_whitelist = models.BooleanField(
        "Enable IP Whitelist",
        default=False,
        help_text="Only allow logins from whitelisted IP addresses"
    )
    whitelisted_ips = models.JSONField(
        "Whitelisted IP Addresses",
        default=list,
        blank=True,
        help_text="List of allowed IP addresses"
    )
    
    # -------------------------------------------------------------------------
    # META
    # -------------------------------------------------------------------------
    
    class Meta:
        db_table = 'user_management_settings'
        verbose_name = _('User Management Settings')
        verbose_name_plural = _('User Management Settings')
    
    def __str__(self):
        return "User Management Settings"
    
    # -------------------------------------------------------------------------
    # SINGLETON PATTERN
    # -------------------------------------------------------------------------
    
    @classmethod
    def get_instance(cls):
        """Get or create the singleton instance"""
        instance, created = cls.objects.get_or_create(
            pk=cls.objects.first().pk if cls.objects.exists() else None,
            defaults={
                'min_password_length': 8,
                'require_uppercase': True,
                'require_lowercase': True,
                'require_numbers': True,
                'require_special_chars': True,
                'password_expiry_days': 90,
                'password_history_count': 5,
                'default_session_timeout_minutes': 480,
                'max_concurrent_sessions': 3,
                'session_warning_minutes': 15,
                'max_failed_login_attempts': 5,
                'account_lockout_duration_minutes': 30,
                'enable_two_factor_default': False,
                'force_password_change_on_first_login': True,
                'allow_user_registration': False,
                'require_admin_approval': True,
                'default_user_role': 'TEACHER',
                'send_welcome_emails': True,
                'send_password_expiry_warnings': True,
                'password_expiry_warning_days': 7,
                'send_account_lockout_notifications': True,
                'log_login_attempts': True,
                'log_permission_changes': True,
                'log_password_changes': True,
                'enable_ip_whitelist': False,
                'whitelisted_ips': [],
            }
        )
        return instance
    
    def save(self, *args, **kwargs):
        """Ensure only one instance exists"""
        if not self.pk and UserManagementSettings.objects.exists():
            existing = UserManagementSettings.objects.first()
            self.pk = existing.pk
        super().save(*args, **kwargs)
    
    # -------------------------------------------------------------------------
    # VALIDATION METHODS
    # -------------------------------------------------------------------------
    
    def validate_password(self, password):
        """Validate password against policy"""
        errors = []
        
        if len(password) < self.min_password_length:
            errors.append(f"Password must be at least {self.min_password_length} characters long")
        
        if self.require_uppercase and not any(c.isupper() for c in password):
            errors.append("Password must contain at least one uppercase letter")
        
        if self.require_lowercase and not any(c.islower() for c in password):
            errors.append("Password must contain at least one lowercase letter")
        
        if self.require_numbers and not any(c.isdigit() for c in password):
            errors.append("Password must contain at least one number")
        
        if self.require_special_chars:
            special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
            if not any(c in special_chars for c in password):
                errors.append("Password must contain at least one special character")
        
        return errors
    
    def get_password_requirements(self):
        """Get human-readable password requirements"""
        requirements = []
        
        requirements.append(f"At least {self.min_password_length} characters")
        
        if self.require_uppercase:
            requirements.append("One uppercase letter")
        if self.require_lowercase:
            requirements.append("One lowercase letter")
        if self.require_numbers:
            requirements.append("One number")
        if self.require_special_chars:
            requirements.append("One special character (!@#$%^&*)")
        
        return requirements