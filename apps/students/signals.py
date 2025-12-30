# students/signals.py

"""
Students Signals
Handles automatic operations on model save/delete:
- Admission number generation (century-safe format)
- Age calculation and validation
- Primary guardian enforcement
- Enrollment status tracking
- Student number validation
- Automatic field population
- Relationship integrity

All number generation is delegated to utils.py for clean separation.
"""

from django.db.models.signals import pre_save, post_save, post_delete, m2m_changed
from django.dispatch import receiver
from django.utils import timezone
from django.db import transaction as db_transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import date
import logging

from .models import (
    Student,
    Guardian,
    StudentGuardian,
    SiblingRelationship,
    EnrollmentStatusHistory,
)

logger = logging.getLogger(__name__)


# =============================================================================
# STUDENT SIGNALS
# =============================================================================

@receiver(pre_save, sender=Student)
def generate_admission_number(sender, instance, **kwargs):
    """
    Generate admission number if not set.
    Delegates to utils.generate_student_admission_number() for generation logic.
    
    Format: YY/ABBR/NNNN or AYY/ABBR/NNNN (century-safe)
    Examples: 24/SCH/0001, A25/SCH/0001 (for year 2125)
    """
    if not instance.admission_number:
        from .utils import generate_student_admission_number
        
        # Generate using admission date's year
        admission_year = instance.admission_date.year if instance.admission_date else timezone.now().year
        
        instance.admission_number = generate_student_admission_number(
            admission_year=admission_year
        )
        
        logger.info(f"Generated admission number: {instance.admission_number}")


@receiver(pre_save, sender=Student)
def validate_student_dates(sender, instance, **kwargs):
    """
    Validate student dates before save.
    Uses school timezone from core.utils.
    """
    from core.utils import get_school_today
    
    today = get_school_today()
    
    # Validate date of birth
    if instance.date_of_birth:
        if instance.date_of_birth > today:
            raise ValidationError("Date of birth cannot be in the future.")
        
        # Calculate age
        age = today.year - instance.date_of_birth.year - (
            (today.month, today.day) < (instance.date_of_birth.month, instance.date_of_birth.day)
        )
        
        if age < 2 or age > 30:
            logger.warning(f"Student {instance.first_name} has unusual age: {age}")
    
    # Validate admission date
    if instance.admission_date:
        if instance.admission_date > today:
            raise ValidationError("Admission date cannot be in the future.")
        
        # Validate admission date is after date of birth
        if instance.date_of_birth and instance.admission_date < instance.date_of_birth:
            raise ValidationError("Admission date cannot be before date of birth.")
    
    # Validate graduation/withdrawal dates
    if instance.graduation_date:
        if instance.admission_date and instance.graduation_date < instance.admission_date:
            raise ValidationError("Graduation date cannot be before admission date.")
    
    if instance.withdrawal_date:
        if instance.admission_date and instance.withdrawal_date < instance.admission_date:
            raise ValidationError("Withdrawal date cannot be before admission date.")


@receiver(post_save, sender=Student)
def track_enrollment_status_change(sender, instance, created, **kwargs):
    """
    Track enrollment status changes in history.
    """
    if not created and instance.pk:
        try:
            # Get old instance from database
            old_instance = Student.objects.get(pk=instance.pk)
            
            # Check if status changed
            if old_instance.enrollment_status != instance.enrollment_status:
                # Get current academic session if available
                try:
                    from academics.models import AcademicSession
                    current_session = AcademicSession.objects.filter(
                        is_current=True
                    ).first()
                except ImportError:
                    current_session = None
                
                # Create history record
                EnrollmentStatusHistory.objects.create(
                    student=instance,
                    previous_status=old_instance.enrollment_status,
                    new_status=instance.enrollment_status,
                    effective_date=timezone.now().date(),
                    academic_session=current_session,
                    reason=f"Status changed from {old_instance.get_enrollment_status_display()} to {instance.get_enrollment_status_display()}"
                )
                
                logger.info(
                    f"Enrollment status changed for {instance.get_full_name()}: "
                    f"{old_instance.enrollment_status} → {instance.enrollment_status}"
                )
        except Student.DoesNotExist:
            pass


@receiver(pre_save, sender=Student)
def set_graduation_date_on_status(sender, instance, **kwargs):
    """
    Automatically set graduation/withdrawal dates when status changes.
    """
    if instance.pk:
        try:
            old_instance = Student.objects.get(pk=instance.pk)
            
            # Set graduation date if status changed to GRADUATED
            if (old_instance.enrollment_status != 'GRADUATED' and 
                instance.enrollment_status == 'GRADUATED' and 
                not instance.graduation_date):
                from core.utils import get_school_today
                instance.graduation_date = get_school_today()
                logger.info(f"Set graduation date for {instance.get_full_name()}")
            
            # Set withdrawal date if status changed to WITHDRAWN
            if (old_instance.enrollment_status != 'WITHDRAWN' and 
                instance.enrollment_status == 'WITHDRAWN' and 
                not instance.withdrawal_date):
                from core.utils import get_school_today
                instance.withdrawal_date = get_school_today()
                logger.info(f"Set withdrawal date for {instance.get_full_name()}")
                
        except Student.DoesNotExist:
            pass


@receiver(post_save, sender=Student)
def log_student_creation(sender, instance, created, **kwargs):
    """
    Log when a new student is created.
    """
    if created:
        logger.info(
            f"New student created: {instance.get_full_name()} "
            f"({instance.admission_number})"
        )


# =============================================================================
# GUARDIAN SIGNALS
# =============================================================================

@receiver(post_save, sender=Guardian)
def log_guardian_creation(sender, instance, created, **kwargs):
    """
    Log when a new guardian is created.
    """
    if created:
        logger.info(
            f"New guardian created: {instance.get_full_name()} "
            f"({instance.guardian_type})"
        )


# =============================================================================
# STUDENT-GUARDIAN RELATIONSHIP SIGNALS
# =============================================================================

@receiver(pre_save, sender=StudentGuardian)
def enforce_single_primary_guardian(sender, instance, **kwargs):
    """
    Ensure only one primary guardian per student.
    When setting a relationship as primary, unset others.
    """
    if instance.is_primary:
        # Find other primary relationships for this student
        StudentGuardian.objects.filter(
            student=instance.student,
            is_primary=True
        ).exclude(pk=instance.pk).update(is_primary=False)
        
        logger.info(
            f"Set {instance.guardian.get_full_name()} as primary guardian "
            f"for {instance.student.get_full_name()}"
        )


@receiver(pre_save, sender=StudentGuardian)
def validate_relationship_dates(sender, instance, **kwargs):
    """
    Validate relationship dates.
    """
    if instance.relationship_start_date and instance.relationship_end_date:
        if instance.relationship_end_date < instance.relationship_start_date:
            raise ValidationError(
                "Relationship end date cannot be before start date."
            )


@receiver(pre_save, sender=StudentGuardian)
def set_default_start_date(sender, instance, **kwargs):
    """
    Set default relationship start date if not provided.
    """
    if not instance.relationship_start_date:
        from core.utils import get_school_today
        instance.relationship_start_date = get_school_today()


@receiver(post_save, sender=StudentGuardian)
def log_guardian_assignment(sender, instance, created, **kwargs):
    """
    Log when a guardian is assigned to a student.
    """
    if created:
        logger.info(
            f"Guardian relationship created: {instance.guardian.get_full_name()} "
            f"({instance.get_relationship_display()}) → {instance.student.get_full_name()}"
        )


@receiver(post_delete, sender=StudentGuardian)
def log_guardian_removal(sender, instance, **kwargs):
    """
    Log when a guardian relationship is removed.
    """
    logger.info(
        f"Guardian relationship removed: {instance.guardian.get_full_name()} "
        f"← {instance.student.get_full_name()}"
    )


# =============================================================================
# SIBLING RELATIONSHIP SIGNALS
# =============================================================================

@receiver(pre_save, sender=SiblingRelationship)
def validate_sibling_relationship(sender, instance, **kwargs):
    """
    Validate sibling relationship before save.
    """
    # Prevent self-sibling relationships
    if instance.from_student == instance.to_student:
        raise ValidationError("A student cannot be their own sibling.")
    
    # Check for duplicate relationships
    if not instance.pk:
        existing = SiblingRelationship.objects.filter(
            from_student=instance.from_student,
            to_student=instance.to_student
        ).exists()
        
        if existing:
            raise ValidationError(
                "This sibling relationship already exists."
            )


@receiver(post_save, sender=SiblingRelationship)
def create_reciprocal_sibling_relationship(sender, instance, created, **kwargs):
    """
    Automatically create the reciprocal sibling relationship.
    If A → B is created, also create B → A.
    """
    if created:
        # Check if reciprocal relationship exists
        reciprocal_exists = SiblingRelationship.objects.filter(
            from_student=instance.to_student,
            to_student=instance.from_student
        ).exists()
        
        if not reciprocal_exists:
            # Create reciprocal relationship
            SiblingRelationship.objects.create(
                from_student=instance.to_student,
                to_student=instance.from_student,
                relationship_type=instance.relationship_type,
                is_verified=instance.is_verified,
                notes=f"Reciprocal of relationship #{instance.pk}"
            )
            
            logger.info(
                f"Created reciprocal sibling relationship: "
                f"{instance.to_student.get_full_name()} → {instance.from_student.get_full_name()}"
            )


@receiver(post_delete, sender=SiblingRelationship)
def delete_reciprocal_sibling_relationship(sender, instance, **kwargs):
    """
    Delete the reciprocal sibling relationship when one is deleted.
    """
    try:
        reciprocal = SiblingRelationship.objects.get(
            from_student=instance.to_student,
            to_student=instance.from_student
        )
        reciprocal.delete()
        
        logger.info(
            f"Deleted reciprocal sibling relationship: "
            f"{instance.to_student.get_full_name()} ← {instance.from_student.get_full_name()}"
        )
    except SiblingRelationship.DoesNotExist:
        pass


@receiver(post_save, sender=SiblingRelationship)
def log_sibling_relationship_creation(sender, instance, created, **kwargs):
    """
    Log when sibling relationship is created.
    """
    if created:
        logger.info(
            f"Sibling relationship created: {instance.from_student.get_full_name()} "
            f"({instance.get_relationship_type_display()}) → {instance.to_student.get_full_name()}"
        )


# =============================================================================
# ENROLLMENT STATUS HISTORY SIGNALS
# =============================================================================

@receiver(pre_save, sender=EnrollmentStatusHistory)
def set_history_effective_date(sender, instance, **kwargs):
    """
    Set effective date if not provided.
    """
    if not instance.effective_date:
        from core.utils import get_school_today
        instance.effective_date = get_school_today()


@receiver(post_save, sender=EnrollmentStatusHistory)
def log_status_history_creation(sender, instance, created, **kwargs):
    """
    Log when enrollment status history is created.
    """
    if created:
        logger.info(
            f"Enrollment status history created for {instance.student.get_full_name()}: "
            f"{instance.previous_status} → {instance.new_status}"
        )


# =============================================================================
# DATA INTEGRITY CHECKS
# =============================================================================

@receiver(pre_save, sender=Student)
def validate_national_student_number_uniqueness(sender, instance, **kwargs):
    """
    Ensure national student number is unique if provided.
    """
    if instance.national_student_number:
        existing = Student.objects.filter(
            national_student_number=instance.national_student_number
        ).exclude(pk=instance.pk).exists()
        
        if existing:
            raise ValidationError(
                f"National student number {instance.national_student_number} is already in use."
            )


@receiver(pre_save, sender=Guardian)
def validate_guardian_email_uniqueness(sender, instance, **kwargs):
    """
    Warn if guardian email is not unique (but allow it).
    """
    if instance.email:
        existing_count = Guardian.objects.filter(
            email=instance.email
        ).exclude(pk=instance.pk).count()
        
        if existing_count > 0:
            logger.warning(
                f"Guardian email {instance.email} is used by {existing_count} other guardian(s)"
            )


# =============================================================================
# CACHE INVALIDATION (if using caching)
# =============================================================================

@receiver(post_save, sender=Student)
@receiver(post_delete, sender=Student)
def invalidate_student_cache(sender, instance, **kwargs):
    """
    Invalidate cached student data when student changes.
    """
    from django.core.cache import cache
    
    # Clear student-specific caches
    cache_keys = [
        f'student_{instance.pk}',
        f'student_admission_{instance.admission_number}',
        'student_list',
        'student_stats',
    ]
    
    for key in cache_keys:
        cache.delete(key)


@receiver(post_save, sender=StudentGuardian)
@receiver(post_delete, sender=StudentGuardian)
def invalidate_guardian_relationship_cache(sender, instance, **kwargs):
    """
    Invalidate cached guardian relationship data.
    """
    from django.core.cache import cache
    
    cache.delete(f'student_guardians_{instance.student.pk}')
    cache.delete(f'guardian_students_{instance.guardian.pk}')

