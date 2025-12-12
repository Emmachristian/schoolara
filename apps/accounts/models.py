from django.contrib.auth.models import User
from django.db import models
from django_countries.fields import CountryField
import os
from image_cropping import ImageRatioField
from sorl.thumbnail import ImageField

from django.db import models
from django_countries.fields import CountryField

class School(models.Model):
    SCHOOL_TYPE_CHOICES = [
        ('Primary', 'Primary School'),
        ('Secondary', 'Secondary School'),
        ('University', 'University'),
    ]

    full_name = models.CharField(max_length=191, unique=True)  # Full name of the school
    domain = models.CharField(max_length=191, unique=True)  # e.g., 'example.school'
    short_name = models.CharField(max_length=100, blank=True, null=True)  # Optional short name
    receipt_name = models.CharField(max_length=191, blank=True, null=True)  # New field for receipt name
    abbreviation = models.CharField(max_length=20, blank=True, null=True)  # Optional abbreviation
    school_type = models.CharField(
        max_length=10,
        choices=SCHOOL_TYPE_CHOICES,
        default='Primary',  # Set default as Primary School
        verbose_name='School Type'
    )
    logo = models.ImageField(
        upload_to='school_logos/',
        null=True,
        blank=True,
        verbose_name='School Logo'
    )  # Optional field for the school logo
    country = CountryField(blank_label='(Select Country)', null=True, blank=True)  # Country field

    def __str__(self):
        return self.full_name  # Return the full name of the school

    class Meta:
        db_table = 'schools_table'

        
def user_profile_image_upload_path(instance, filename):
    """
    Generate a file path for new user profile images.
    Format: 'user_profile_images/<school_id>_<user_id>.ext'
    """
    extension = os.path.splitext(filename)[-1]  # Extract file extension
    school_id = instance.school.id if instance.school else 'unknown_school'
    profile_id = instance.id or 'unknown_user_profile'  
    return f"user_profile_images/{school_id}_{profile_id}{extension}"

class UserProfile(models.Model):
    USER_ROLES = [
        ('Administrator', 'Administrator'),
        ('Director of Studies', 'Director of Studies'),
        ('Finance Manager', 'Finance Manager'),
        ('Registrar', 'Registrar'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)
    name_of_person_in_charge = models.CharField(max_length=255, blank=True)
    role = models.CharField(max_length=20, choices=USER_ROLES)
    profile_image = ImageField(
        upload_to=user_profile_image_upload_path, 
        null=True, 
        blank=True,
        help_text="Upload a profile picture."
    )
    cropping = ImageRatioField('profile_image', '300x300')  # Cropping size (300x300)
    layout_preference = models.CharField(
        max_length=50,
        choices=[
            ("compact-sidebar", "Compact Sidebar"),
            ("icon-sidebar", "Icon Sidebar"),
            ("horizontal", "Horizontal Layout"),
            ("default", "Default Layout"),
        ],
        default="default",
    )

    class Meta:
        db_table = 'user_profiles'
        constraints = [
            models.UniqueConstraint(fields=['school', 'role'], name='unique_role_per_school')
        ]
        indexes = [
            models.Index(fields=['school', 'role'], name='school_role_idx', db_tablespace='default')
        ]

    def __str__(self):
        return f"{self.user.username} - {self.role}"