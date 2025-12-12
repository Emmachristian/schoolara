from django.db import models
from schoolara.managers import SchoolManager
from django_countries.fields import CountryField
from utils.models import BaseModel

# Create your models here.
class Student(BaseModel):
    """Enhanced model for comprehensive student information"""
    
    GENDER_CHOICES = (
        ('M', 'Male'),
        ('F', 'Female'),
    )
    
    ENROLLMENT_STATUS_CHOICES = (
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('dismissed', 'Dismissed'),
        ('graduated', 'Graduated'),
        ('transferred', 'Transferred'),
        ('withdrawn', 'Withdrawn'),
        ('deceased', 'Deceased'),
        ('deferred', 'Deferred'),
    )
    
    RELIGIOUS_AFFILIATION_CHOICES = (
        ('catholic', 'Catholic'),
        ('protestant', 'Protestant'),
        ('anglican', 'Anglican'),
        ('baptist', 'Baptist'),
        ('pentecostal', 'Pentecostal'),
        ('evangelical', 'Evangelical'),
        ('adventist', 'Adventist'),
        ('islam', 'Islam'),
        ('hindu', 'Hindu'),
        ('buddhist', 'Buddhist'),
        ('jewish', 'Jewish'),
        ('traditional', 'Traditional'),
        ('none', 'No Religion'),
        ('other', 'Other'),
    )
    
    HEALTH_CONDITION_CHOICES = (
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
        ('chronic', 'Chronic Condition'),
        ('recovering', 'Recovering'),
        ('special_Needs', 'Special Needs'),
        ('other', 'Other'),
    )
    
    BLOOD_TYPE_CHOICES = (
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
        ('Unknown', 'Unknown'),
    )
    
    # Identification & Basic Info
    admission_number = models.CharField("Admission Number", max_length=20, unique=True)
    admission_date = models.DateField("Admission Date")
    national_student_number = models.CharField("National Student Number", max_length=30, unique=True, null=True, blank=True)
    birth_certificate_number = models.CharField("Birth Certificate Number", max_length=50, blank=True)
    first_name = models.CharField("First Name", max_length=50)
    middle_name = models.CharField("Middle Name", max_length=50, blank=True)
    last_name = models.CharField("Last Name", max_length=50)
    date_of_birth = models.DateField("Date of Birth")
    gender = models.CharField("Gender", max_length=1, choices=GENDER_CHOICES)
    
    # Academic Information
    current_academic_level = models.ForeignKey('academic_management.AcademicLevel', verbose_name="Current Academic Level", on_delete=models.SET_NULL, null=True, blank=True, related_name='current_students')
    admission_academic_level = models.ForeignKey('academic_management.AcademicLevel', verbose_name="Admission Academic Level", on_delete=models.SET_NULL, null=True, blank=True, related_name='admitted_students')
    
    # Demographics & Cultural Info
    nationality = CountryField("Nationality", default='UG')
    ethnicity = models.CharField("Ethnicity", max_length=50, blank=True)
    birth_place = models.CharField("Place of Birth", max_length=100, blank=True)
    birth_country = CountryField(verbose_name="Country of Birth", blank=True, null=True)
    religious_affiliation = models.CharField("Religious Affiliation", max_length=20, choices=RELIGIOUS_AFFILIATION_CHOICES, blank=True)
    
    # Contact & Address Information
    personal_email = models.EmailField("Personal Email", blank=True)
    phone_number = models.CharField("Phone Number", max_length=20, blank=True)
    home_address = models.TextField("Home Address")
    mailing_address = models.TextField("Mailing Address", blank=True)
    district = models.CharField("District", max_length=50, blank=True)
    region = models.CharField("Region/Province", max_length=50, blank=True)
    country_of_residence = CountryField(verbose_name="Country of Residence", default='UG')
    
    # Health & Medical Information
    health_condition = models.CharField("Health Condition", max_length=20, choices=HEALTH_CONDITION_CHOICES, default='Good')
    blood_type = models.CharField("Blood Type", max_length=10, choices=BLOOD_TYPE_CHOICES, default='Unknown')
    medical_conditions = models.TextField("Medical Conditions", blank=True)
    allergies = models.TextField("Allergies", blank=True)
    medications = models.TextField("Current Medications", blank=True)
    special_medical_needs = models.TextField("Special Medical Needs", blank=True)
    emergency_medical_contact = models.CharField("Emergency Medical Contact", max_length=20, blank=True)
    preferred_hospital = models.CharField("Preferred Hospital", max_length=100, blank=True)
    medical_insurance = models.CharField("Medical Insurance", max_length=100, blank=True)
    insurance_policy_number = models.CharField("Insurance Policy Number", max_length=50, blank=True)
    
    # Special Needs & Accommodations
    has_special_needs = models.BooleanField("Has Special Needs", default=False)
    special_needs_description = models.TextField("Special Needs Description", blank=True)
    requires_special_diet = models.BooleanField("Requires Special Diet", default=False)
    special_diet_details = models.TextField("Special Diet Details", blank=True)
    learning_disabilities = models.TextField("Learning Disabilities", blank=True)
    learning_accommodations = models.TextField("Learning Accommodations", blank=True)
    
    # Transport Information
    transportation_required = models.BooleanField("Transportation Required", default=False)
    transport_route = models.CharField("Transport Route", max_length=50, blank=True)
    pickup_point = models.CharField("Pickup Point", max_length=50, blank=True)
    pickup_time = models.TimeField("Pickup Time", null=True, blank=True)
    
    # Previous Education
    previous_school = models.CharField("Previous School", max_length=100, blank=True)
    previous_school_address = models.TextField("Previous School Address", blank=True)
    previous_academic_level = models.ForeignKey('academic_management.AcademicLevel', verbose_name="Previous Academic Level", on_delete=models.SET_NULL, null=True, blank=True, related_name='previous_students')
    transfer_reason = models.TextField("Reason for Transfer", blank=True)
    transfer_certificate_number = models.CharField("Transfer Certificate Number", max_length=50, blank=True)
    previous_school_completion_date = models.DateField("Previous School Completion Date", null=True, blank=True)
    
    # Media & Documents
    photo = models.ImageField('Photo', upload_to='students/photos', blank=True, null=True)
    
    # Guardian Relationships
    guardians = models.ManyToManyField('Guardian', verbose_name="Guardians", through='StudentGuardian', blank=True)
    
    # Status & Tracking
    enrollment_status = models.CharField("Enrollment Status", max_length=20, choices=ENROLLMENT_STATUS_CHOICES, default='active')
    graduation_date = models.DateField("Graduation Date", null=True, blank=True)
    withdrawal_date = models.DateField("Withdrawal Date", null=True, blank=True)

    # Add the custom manager
    objects = SchoolManager()

    class Meta:
        db_table = 'pupils_table'
        app_label = 'pupils_management'
    
    def __str__(self):
        return f"{self.get_full_name()} ({self.admission_number})"
    
    def get_full_name(self):
        """Get student's full name"""
        if self.middle_name:
            return f"{self.first_name} {self.middle_name} {self.last_name}"
        return f"{self.first_name} {self.last_name}"
    
    def get_age(self):
        from datetime import date
        today = date.today()
        age = today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        return age