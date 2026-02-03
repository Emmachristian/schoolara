# hr/signals.py

"""
Human Resources Signals
Handles automatic operations on model save/delete:
- Staff ID generation (century-safe format)
- Contract number generation (century-safe format)
- Age validation
- Date validations using school timezone
- Automatic field population
- Relationship integrity
- Contract status tracking
- Designation management
- Teacher profile synchronization

All number generation is delegated to utils.py for clean separation.
Uses school timezone from core.utils for all date operations.
"""

from django.db.models.signals import pre_save, post_save, post_delete, m2m_changed
from django.dispatch import receiver
from django.utils import timezone
from django.db import transaction as db_transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import date, timedelta
import logging

from .models import (
    Department,
    Designation,
    Contract,
    Staff,
    StaffDesignation,
    Teacher,
    Attendance,
    Payroll,
    SalaryHistory,
    ContractBenefit,
)

logger = logging.getLogger(__name__)


# =============================================================================
# STAFF SIGNALS
# =============================================================================

@receiver(pre_save, sender=Staff)
def generate_staff_id(sender, instance, **kwargs):
    """
    Generate staff ID if not set.
    Delegates to utils.generate_staff_id() for generation logic.
    
    Format: YY/SCHOOL/[DEPT/]TYPE-NNN or AYY/SCHOOL/[DEPT/]TYPE-NNN (century-safe)
    Examples: 24/SCH/TCH-001, A25/SCH/MATH/ADM-001 (for year 2125)
    
    Staff ID is PERMANENT and never changes once set.
    """
    if not instance.staff_id:
        from .utils import generate_staff_id
        from accounts.models import School
        from schoolara.managers import get_current_db
        
        # Get the current database alias
        current_db = get_current_db()
        
        # Find the school that matches this database
        try:
            school = School.objects.get(database_alias=current_db)
        except School.DoesNotExist:
            # Fallback: try to get from default database
            school = School.objects.using('default').filter(
                database_alias=current_db
            ).first()
        
        # Generate staff ID with school context - ONLY ONCE
        instance.staff_id = generate_staff_id(
            school=school,
            joining_year=instance.date_of_joining.year if instance.date_of_joining else None,
            department=instance.primary_department,
            employment_status=instance.employment_status,
            is_teaching=False  # Default to False; Teacher profile is separate
        )
        
        logger.info(f"Generated staff ID: {instance.staff_id}")


@receiver(pre_save, sender=Staff)
def validate_staff_dates(sender, instance, **kwargs):
    """
    Validate staff dates before save.
    Uses school timezone from core.utils. ⭐
    """
    from core.utils import get_school_today
    
    today = get_school_today()  # ⭐ USE SCHOOL TIMEZONE
    
    # Validate date of birth
    if instance.date_of_birth:
        if instance.date_of_birth > today:
            raise ValidationError("Date of birth cannot be in the future.")
        
        # Calculate age
        age = today.year - instance.date_of_birth.year - (
            (today.month, today.day) < (instance.date_of_birth.month, instance.date_of_birth.day)
        )
        
        if age < 18:
            raise ValidationError("Staff member must be at least 18 years old.")
        
        if age > 75:
            logger.warning(f"Staff {instance.first_name} has unusual age: {age}")
    
    # Validate date of joining
    if instance.date_of_joining:
        if instance.date_of_joining > today:
            raise ValidationError("Date of joining cannot be in the future.")
        
        # Validate joining date is after date of birth
        if instance.date_of_birth and instance.date_of_joining < instance.date_of_birth:
            raise ValidationError("Date of joining cannot be before date of birth.")
        
        # Validate not too far in the past (50 years)
        if instance.date_of_joining < (today - timedelta(days=50*365)):
            logger.warning(f"Staff {instance.first_name} has very old joining date")
    
    # Validate date of leaving
    if instance.date_of_leaving:
        if instance.date_of_joining and instance.date_of_leaving < instance.date_of_joining:
            raise ValidationError("Date of leaving cannot be before date of joining.")


@receiver(pre_save, sender=Staff)
def validate_staff_uniqueness(sender, instance, **kwargs):
    """
    Ensure critical staff identifiers are unique.
    """
    # Validate national ID uniqueness if provided
    if instance.national_id:
        existing = Staff.objects.filter(
            national_id=instance.national_id
        ).exclude(pk=instance.pk).exists()
        
        if existing:
            raise ValidationError(
                f"National ID {instance.national_id} is already in use."
            )
    
    # Validate passport number uniqueness if provided
    if instance.passport_number:
        existing = Staff.objects.filter(
            passport_number=instance.passport_number
        ).exclude(pk=instance.pk).exists()
        
        if existing:
            logger.warning(
                f"Passport number {instance.passport_number} is already in use by another staff member."
            )


@receiver(post_save, sender=Staff)
def log_staff_creation(sender, instance, created, **kwargs):
    """
    Log when a new staff member is created.
    """
    if created:
        logger.info(
            f"New staff member created: {instance.full_name()} "
            f"({instance.staff_id})"
        )


@receiver(pre_save, sender=Staff)
def update_employment_status_on_leaving(sender, instance, **kwargs):
    """
    Automatically update employment status when staff leaves.
    """
    if instance.pk:
        try:
            old_instance = Staff.objects.get(pk=instance.pk)
            
            # If date_of_leaving is set and status is still active
            if instance.date_of_leaving and instance.employment_status in ['FT', 'PT', 'CT', 'PR']:
                # Set to resigned or terminated based on context
                if not old_instance.date_of_leaving:
                    instance.employment_status = 'RS'  # Resigned
                    logger.info(
                        f"Auto-updated employment status to Resigned for {instance.full_name()}"
                    )
                    
        except Staff.DoesNotExist:
            pass


# =============================================================================
# DEPARTMENT SIGNALS
# =============================================================================

@receiver(pre_save, sender=Department)
def validate_department_hierarchy(sender, instance, **kwargs):
    """
    Prevent circular department hierarchy.
    """
    if instance.parent_department:
        # Check if parent is self
        if instance.pk and instance.parent_department.pk == instance.pk:
            raise ValidationError("A department cannot be its own parent.")
        
        # Check for circular reference (parent's parent is self)
        parent = instance.parent_department
        max_depth = 10  # Prevent infinite loops
        depth = 0
        
        while parent and depth < max_depth:
            if parent.parent_department and parent.parent_department.pk == instance.pk:
                raise ValidationError(
                    "Circular department hierarchy detected. "
                    "This would create an infinite loop."
                )
            parent = parent.parent_department
            depth += 1


@receiver(post_save, sender=Department)
def log_department_creation(sender, instance, created, **kwargs):
    """
    Log when a new department is created.
    """
    if created:
        logger.info(
            f"New department created: {instance.name} ({instance.code})"
        )


# =============================================================================
# DESIGNATION SIGNALS
# =============================================================================

@receiver(pre_save, sender=Designation)
def validate_designation_hierarchy(sender, instance, **kwargs):
    """
    Prevent circular designation reporting hierarchy.
    """
    if instance.reports_to:
        # Check if reports_to is self
        if instance.pk and instance.reports_to.pk == instance.pk:
            raise ValidationError("A designation cannot report to itself.")
        
        # Check for circular reference
        reports_to = instance.reports_to
        max_depth = 10  # Prevent infinite loops
        depth = 0
        
        while reports_to and depth < max_depth:
            if reports_to.reports_to and reports_to.reports_to.pk == instance.pk:
                raise ValidationError(
                    "Circular reporting structure detected. "
                    "This would create an infinite loop."
                )
            reports_to = reports_to.reports_to
            depth += 1


@receiver(post_save, sender=Designation)
def log_designation_creation(sender, instance, created, **kwargs):
    """
    Log when a new designation is created.
    """
    if created:
        logger.info(
            f"New designation created: {instance.name} ({instance.code}) "
            f"in {instance.department.name}"
        )


# =============================================================================
# CONTRACT SIGNALS
# =============================================================================

@receiver(pre_save, sender=Contract)
def generate_contract_number(sender, instance, **kwargs):
    """
    Generate contract number if not set.
    Delegates to utils.generate_contract_number() for generation logic.
    
    Format: CONT/YYYY/TYPE/NNNN or CONT/AYYY/TYPE/NNNN (century-safe)
    Examples: CONT/2024/PERM/0001, CONT/A125/TEMP/0001 (for year 2125)
    """
    if not instance.contract_number:
        from .utils import generate_contract_number
        
        # Generate using contract start date's year
        contract_year = instance.start_date.year if instance.start_date else timezone.now().year
        
        instance.contract_number = generate_contract_number(
            contract_year=contract_year,
            contract_type=instance.contract_type
        )
        
        logger.info(f"Generated contract number: {instance.contract_number}")


@receiver(pre_save, sender=Contract)
def validate_contract_dates(sender, instance, **kwargs):
    """
    Validate contract dates before save.
    Uses school timezone from core.utils. ⭐
    """
    from core.utils import get_school_today
    
    today = get_school_today()  # ⭐ USE SCHOOL TIMEZONE
    
    # Validate start date
    if instance.start_date:
        # Allow reasonable past dates (10 years)
        if instance.start_date < (today - timedelta(days=10*365)):
            logger.warning(
                f"Contract {instance.contract_number} has very old start date: {instance.start_date}"
            )
    
    # Validate end date
    if instance.end_date:
        if instance.start_date and instance.end_date <= instance.start_date:
            raise ValidationError("End date must be after start date.")
    
    # Validate termination date
    if instance.termination_date:
        if instance.start_date and instance.termination_date < instance.start_date:
            raise ValidationError("Termination date cannot be before contract start date.")
        
        if instance.end_date and instance.termination_date > instance.end_date:
            raise ValidationError("Termination date cannot be after contract end date.")
    
    # Permanent contracts should not have end dates
    if instance.contract_type == 'PERMANENT' and instance.end_date:
        raise ValidationError("Permanent contracts should not have an end date.")
    
    # Fixed term contracts must have end dates
    if instance.contract_type in ['FIXED_TERM', 'PROBATION', 'TEMPORARY', 'SEASONAL', 'PROJECT_BASED']:
        if not instance.end_date:
            raise ValidationError(
                f"{dict(Contract.CONTRACT_TYPE_CHOICES)[instance.contract_type]} must have an end date."
            )


@receiver(pre_save, sender=Contract)
def auto_populate_fiscal_year(sender, instance, **kwargs):
    """
    Auto-populate fiscal year from period if available.
    """
    if instance.period and hasattr(instance.period, 'fiscal_year'):
        instance.fiscal_year = instance.period.fiscal_year


@receiver(post_save, sender=Contract)
def log_contract_creation(sender, instance, created, **kwargs):
    """
    Log when a new contract is created.
    """
    if created:
        logger.info(
            f"New contract created: {instance.contract_number} "
            f"for {instance.staff.full_name()} "
            f"({instance.get_contract_type_display()})"
        )


@receiver(post_save, sender=Contract)
def check_expired_contracts(sender, instance, **kwargs):
    """
    Check if contract has expired and log warning.
    Uses school timezone. ⭐
    """
    if instance.status == 'ACTIVE' and instance.end_date:
        from core.utils import get_school_today
        
        today = get_school_today()  # ⭐ USE SCHOOL TIMEZONE
        
        if instance.end_date < today:
            logger.warning(
                f"Contract {instance.contract_number} has expired but is still marked as ACTIVE. "
                f"End date: {instance.end_date}"
            )


@receiver(pre_save, sender=Contract)
def track_contract_status_changes(sender, instance, **kwargs):
    """
    Track contract status changes and update timestamps.
    Uses school timezone. ⭐
    """
    if instance.pk:
        try:
            old_instance = Contract.objects.get(pk=instance.pk)
            
            # Status changed to ACTIVE
            if old_instance.status != 'ACTIVE' and instance.status == 'ACTIVE':
                if not instance.approved_at:
                    instance.approved_at = timezone.now()
                logger.info(
                    f"Contract {instance.contract_number} activated for {instance.staff.full_name()}"
                )
            
            # Status changed to SIGNED
            if old_instance.status != 'SIGNED' and instance.status == 'SIGNED':
                if not instance.signed_at:
                    instance.signed_at = timezone.now()
                    from core.utils import get_school_today
                    if not instance.signed_date:
                        instance.signed_date = get_school_today()  # ⭐
                logger.info(
                    f"Contract {instance.contract_number} signed by {instance.staff.full_name()}"
                )
            
            # Status changed to TERMINATED
            if old_instance.status != 'TERMINATED' and instance.status == 'TERMINATED':
                if not instance.terminated_at:
                    instance.terminated_at = timezone.now()
                    from core.utils import get_school_today
                    if not instance.termination_date:
                        instance.termination_date = get_school_today()  # ⭐
                logger.info(
                    f"Contract {instance.contract_number} terminated for {instance.staff.full_name()}"
                )
                
        except Contract.DoesNotExist:
            pass


# =============================================================================
# STAFF DESIGNATION SIGNALS - ⭐ TEACHER PROFILE SYNCHRONIZATION
# =============================================================================

@receiver(pre_save, sender=StaffDesignation)
def enforce_single_primary_designation(sender, instance, **kwargs):
    """
    Ensure only one primary designation per staff member.
    When setting a designation as primary, unset others.
    """
    if instance.is_primary:
        # Find other primary designations for this staff
        StaffDesignation.objects.filter(
            staff=instance.staff,
            is_primary=True
        ).exclude(pk=instance.pk).update(is_primary=False)
        
        logger.info(
            f"Set {instance.designation.name} as primary designation "
            f"for {instance.staff.full_name()}"
        )


@receiver(pre_save, sender=StaffDesignation)
def validate_designation_dates(sender, instance, **kwargs):
    """
    Validate designation assignment dates.
    Uses school timezone. ⭐
    """
    from core.utils import get_school_today
    
    today = get_school_today()  # ⭐ USE SCHOOL TIMEZONE
    
    if instance.start_date:
        # Don't allow start dates too far in the past
        if instance.start_date < (today - timedelta(days=10*365)):
            logger.warning(
                f"Designation assignment has very old start date: {instance.start_date}"
            )
    
    if instance.end_date:
        if instance.start_date and instance.end_date < instance.start_date:
            raise ValidationError("End date cannot be before start date.")


@receiver(pre_save, sender=StaffDesignation)
def set_default_start_date(sender, instance, **kwargs):
    """
    Set default start date if not provided.
    Uses school timezone. ⭐
    """
    if not instance.start_date:
        from core.utils import get_school_today
        instance.start_date = get_school_today()  # ⭐


@receiver(post_save, sender=StaffDesignation)
def auto_create_teacher_profile(sender, instance, created, **kwargs):
    """
    ⭐ OPTION 3 - STEP 1: AUTO-CREATE TEACHER PROFILE
    
    Automatically create teacher profile when a teaching designation is assigned.
    This ensures consistency between designations and teacher profiles.
    """
    # Only process if designation is teaching and is active
    if instance.designation.is_teaching and instance.is_active:
        # Check if teacher profile already exists
        if not hasattr(instance.staff, 'teacher'):
            try:
                # Create teacher profile with defaults
                teacher = Teacher.objects.create(
                    staff=instance.staff,
                    specialization=instance.designation.name,
                    max_hours_per_week=40,
                    current_teaching_load=0,
                    digital_literacy_level='BASIC',
                    is_class_teacher=False,
                    can_teach_online=False,
                )
                
                logger.info(
                    f"✓ Auto-created teacher profile for {instance.staff.full_name()} "
                    f"due to teaching designation: {instance.designation.name}"
                )
                
            except Exception as e:
                logger.error(
                    f"✗ Failed to auto-create teacher profile for {instance.staff.full_name()}: {e}"
                )
        else:
            logger.debug(
                f"Teacher profile already exists for {instance.staff.full_name()}"
            )


@receiver(post_save, sender=StaffDesignation)
def log_designation_assignment(sender, instance, created, **kwargs):
    """
    Log when a designation is assigned to staff.
    """
    if created:
        primary_str = " (PRIMARY)" if instance.is_primary else ""
        teaching_str = " [TEACHING]" if instance.designation.is_teaching else ""
        logger.info(
            f"Designation assigned: {instance.staff.full_name()} → "
            f"{instance.designation.name}{primary_str}{teaching_str}"
        )

@receiver(post_delete, sender=StaffDesignation)
def check_teacher_profile_on_designation_delete(sender, instance, **kwargs):
    if instance.designation.is_teaching and hasattr(instance.staff, 'teacher'):
        other_teaching_designations = StaffDesignation.objects.filter(
            staff=instance.staff,
            designation__is_teaching=True,
            is_active=True
        ).exclude(pk=instance.pk).exists()
        
        if not other_teaching_designations:
            # ⭐ OPTION C: Soft delete - mark as inactive
            instance.staff.teacher.is_active = False
            instance.staff.teacher.save()
            
            logger.info(
                f"✓ Deactivated teacher profile for {instance.staff.full_name()} "
                f"(no active teaching designations)"
            )

@receiver(post_delete, sender=StaffDesignation)
def log_designation_removal(sender, instance, **kwargs):
    """
    Log when a designation assignment is removed.
    """
    teaching_str = " [TEACHING]" if instance.designation.is_teaching else ""
    logger.info(
        f"Designation removed: {instance.staff.full_name()} ← "
        f"{instance.designation.name}{teaching_str}"
    )

@receiver(post_save, sender=StaffDesignation)
def auto_reactivate_teacher_profile(sender, instance, created, **kwargs):
    """
    ⭐ OPTION C: AUTO-REACTIVATE teacher profile when teaching designation is added
    
    If a teacher profile exists but is inactive, reactivate it when a teaching
    designation is assigned.
    """
    if instance.designation.is_teaching and instance.is_active:
        if hasattr(instance.staff, 'teacher'):
            teacher = instance.staff.teacher
            if not teacher.is_active:
                teacher.is_active = True
                teacher.save(update_fields=['is_active', 'updated_at'])
                
                logger.info(
                    f"✓ Reactivated teacher profile for {instance.staff.full_name()} "
                    f"due to teaching designation assignment: {instance.designation.name}"
                )


# =============================================================================
# TEACHER SIGNALS - ⭐ TEACHER/DESIGNATION SYNCHRONIZATION
# =============================================================================

@receiver(post_save, sender=Teacher)
def log_teacher_creation(sender, instance, created, **kwargs):
    """
    Log when a teacher profile is created.
    Also check for designation consistency.
    """
    if created:
        logger.info(
            f"Teacher profile created for: {instance.staff.full_name()} "
            f"(Specialization: {instance.specialization})"
        )
        
        # ⭐ Check if staff has teaching designation
        has_teaching_designation = StaffDesignation.objects.filter(
            staff=instance.staff,
            designation__is_teaching=True,
            is_active=True
        ).exists()
        
        if not has_teaching_designation:
            logger.warning(
                f"⚠ INCONSISTENCY DETECTED: Teacher profile created for {instance.staff.full_name()} "
                f"but staff has no active teaching designation. "
                f"Consider assigning a teaching designation."
            )


@receiver(pre_save, sender=Teacher)
def validate_teaching_load(sender, instance, **kwargs):
    """
    Validate teaching load doesn't exceed max hours.
    """
    if instance.current_teaching_load > instance.max_hours_per_week:
        logger.warning(
            f"Teacher {instance.staff.full_name()} is overloaded: "
            f"{instance.current_teaching_load}/{instance.max_hours_per_week} hours"
        )


@receiver(post_delete, sender=Teacher)
def log_teacher_deletion(sender, instance, **kwargs):
    """
    ⭐ Log when teacher profile is deleted and check for teaching designations.
    """
    logger.info(f"Teacher profile deleted for: {instance.staff.full_name()}")
    
    # Check if staff still has teaching designations
    has_teaching_designation = StaffDesignation.objects.filter(
        staff=instance.staff,
        designation__is_teaching=True,
        is_active=True
    ).exists()
    
    if has_teaching_designation:
        logger.warning(
            f"⚠ INCONSISTENCY DETECTED: Teacher profile deleted for {instance.staff.full_name()} "
            f"but staff still has active teaching designations. "
            f"Consider removing teaching designations or recreating teacher profile."
        )


# =============================================================================
# ATTENDANCE SIGNALS
# =============================================================================

@receiver(pre_save, sender=Attendance)
def validate_attendance_date(sender, instance, **kwargs):
    """
    Validate attendance date.
    Uses school timezone. ⭐
    """
    from core.utils import get_school_today
    
    today = get_school_today()  # ⭐ USE SCHOOL TIMEZONE
    
    if instance.date:
        # Don't allow future dates
        if instance.date > today:
            raise ValidationError("Attendance date cannot be in the future.")
        
        # Don't allow too far in the past (30 days)
        if instance.date < (today - timedelta(days=30)):
            raise ValidationError(
                "Attendance date cannot be more than 30 days in the past."
            )


@receiver(pre_save, sender=Attendance)
def calculate_work_hours_on_save(sender, instance, **kwargs):
    """
    Auto-calculate work hours if check-in and check-out are provided.
    """
    if instance.check_in and instance.check_out and not instance.work_hours:
        duration = instance.check_out - instance.check_in
        hours = Decimal(str(duration.total_seconds() / 3600))
        instance.work_hours = hours.quantize(Decimal('0.01'))
        
        logger.info(
            f"Auto-calculated work hours for {instance.staff.full_name()}: "
            f"{instance.work_hours} hours"
        )


@receiver(post_save, sender=Attendance)
def log_attendance_record(sender, instance, created, **kwargs):
    """
    Log attendance record creation.
    """
    if created:
        logger.info(
            f"Attendance recorded: {instance.staff.full_name()} - "
            f"{instance.date} - {instance.get_status_display()}"
        )


# =============================================================================
# PAYROLL SIGNALS
# =============================================================================

@receiver(pre_save, sender=Payroll)
def auto_populate_payroll_fiscal_year(sender, instance, **kwargs):
    """
    Auto-populate fiscal year from period.
    """
    if instance.period and hasattr(instance.period, 'fiscal_year'):
        instance.fiscal_year = instance.period.fiscal_year


@receiver(pre_save, sender=Payroll)
def validate_payroll_date(sender, instance, **kwargs):
    """
    Validate payroll payment date.
    Uses school timezone. ⭐
    """
    from core.utils import get_school_today
    
    today = get_school_today()  # ⭐ USE SCHOOL TIMEZONE
    
    if instance.payment_date:
        # Allow reasonable past/future dates (90 days)
        if instance.payment_date < (today - timedelta(days=90)):
            logger.warning(f"Payroll payment date is very old: {instance.payment_date}")
        
        if instance.payment_date > (today + timedelta(days=90)):
            logger.warning(f"Payroll payment date is far in future: {instance.payment_date}")


@receiver(post_save, sender=Payroll)
def log_payroll_creation(sender, instance, created, **kwargs):
    """
    Log when payroll is created.
    """
    if created:
        logger.info(
            f"Payroll created: {instance.staff.full_name()} - "
            f"{instance.period.name} - Net: {instance.net_pay}"
        )


@receiver(pre_save, sender=Payroll)
def track_payroll_status_changes(sender, instance, **kwargs):
    """
    Track payroll status changes.
    """
    if instance.pk:
        try:
            old_instance = Payroll.objects.get(pk=instance.pk)
            
            # Status changed to APPROVED
            if old_instance.status != 'APPROVED' and instance.status == 'APPROVED':
                if not instance.approved_at:
                    instance.approved_at = timezone.now()
                logger.info(
                    f"Payroll approved for {instance.staff.full_name()} - {instance.period.name}"
                )
            
            # Status changed to PAID
            if old_instance.status != 'PAID' and instance.status == 'PAID':
                logger.info(
                    f"Payroll paid for {instance.staff.full_name()} - {instance.period.name}"
                )
                
        except Payroll.DoesNotExist:
            pass


# =============================================================================
# SALARY HISTORY SIGNALS
# =============================================================================

@receiver(pre_save, sender=SalaryHistory)
def validate_salary_change(sender, instance, **kwargs):
    """
    Validate salary change data.
    """
    if instance.previous_salary and instance.new_salary:
        if instance.new_salary < 0:
            raise ValidationError("New salary cannot be negative.")
        
        # Calculate change percentage if not provided
        if not instance.change_percentage:
            if instance.previous_salary > 0:
                change = ((instance.new_salary - instance.previous_salary) / instance.previous_salary) * 100
                instance.change_percentage = Decimal(str(change)).quantize(Decimal('0.01'))


@receiver(pre_save, sender=SalaryHistory)
def set_salary_effective_date(sender, instance, **kwargs):
    """
    Set effective date if not provided.
    Uses school timezone. ⭐
    """
    if not instance.effective_date:
        from core.utils import get_school_today
        instance.effective_date = get_school_today()  # ⭐


@receiver(post_save, sender=SalaryHistory)
def log_salary_change(sender, instance, created, **kwargs):
    """
    Log salary changes.
    """
    if created:
        change_str = ""
        if instance.change_percentage:
            change_str = f" ({instance.change_percentage:+.2f}%)"
        
        logger.info(
            f"Salary change recorded: {instance.staff.full_name()} - "
            f"{instance.previous_salary} → {instance.new_salary}{change_str}"
        )


# =============================================================================
# CONTRACT BENEFIT SIGNALS
# =============================================================================

@receiver(pre_save, sender=ContractBenefit)
def validate_benefit_dates(sender, instance, **kwargs):
    """
    Validate benefit dates.
    """
    if instance.end_date:
        if instance.start_date and instance.end_date < instance.start_date:
            raise ValidationError("Benefit end date cannot be before start date.")


@receiver(post_save, sender=ContractBenefit)
def log_benefit_assignment(sender, instance, created, **kwargs):
    """
    Log when benefit is assigned to contract.
    """
    if created:
        logger.info(
            f"Benefit assigned: {instance.get_benefit_type_display()} → "
            f"{instance.contract.staff.full_name()} "
            f"(Contract: {instance.contract.contract_number})"
        )


# =============================================================================
# DATA INTEGRITY CHECKS
# =============================================================================

@receiver(pre_save, sender=Staff)
def validate_phone_numbers(sender, instance, **kwargs):
    """
    Validate phone number formats.
    """
    import re
    
    phone_pattern = r'^\+?1?\d{9,15}$'
    
    if instance.phone_number:
        cleaned = re.sub(r'[^\d+]', '', instance.phone_number)
        if not re.match(phone_pattern, cleaned):
            logger.warning(f"Invalid phone number format: {instance.phone_number}")
    
    if instance.alternative_phone:
        cleaned = re.sub(r'[^\d+]', '', instance.alternative_phone)
        if not re.match(phone_pattern, cleaned):
            logger.warning(f"Invalid alternative phone format: {instance.alternative_phone}")


@receiver(pre_save, sender=Contract)
def validate_salary_amounts(sender, instance, **kwargs):
    """
    Validate salary amounts are positive.
    """
    if instance.basic_salary <= 0:
        raise ValidationError("Basic salary must be greater than zero.")


# =============================================================================
# CACHE INVALIDATION (if using caching)
# =============================================================================

@receiver(post_save, sender=Staff)
@receiver(post_delete, sender=Staff)
def invalidate_staff_cache(sender, instance, **kwargs):
    """
    Invalidate cached staff data when staff changes.
    """
    from django.core.cache import cache
    
    # Clear staff-specific caches
    cache_keys = [
        f'staff_{instance.pk}',
        f'staff_id_{instance.staff_id}',
        'staff_list',
        'staff_stats',
        'active_staff_count',
    ]
    
    for key in cache_keys:
        cache.delete(key)


@receiver(post_save, sender=Contract)
@receiver(post_delete, sender=Contract)
def invalidate_contract_cache(sender, instance, **kwargs):
    """
    Invalidate cached contract data.
    """
    from django.core.cache import cache
    
    cache_keys = [
        f'contract_{instance.pk}',
        f'staff_contracts_{instance.staff.pk}',
        f'active_contract_{instance.staff.pk}',
        'contract_list',
        'expiring_contracts',
    ]
    
    for key in cache_keys:
        cache.delete(key)


@receiver(post_save, sender=Payroll)
@receiver(post_delete, sender=Payroll)
def invalidate_payroll_cache(sender, instance, **kwargs):
    """
    Invalidate cached payroll data.
    """
    from django.core.cache import cache
    
    cache_keys = [
        f'payroll_{instance.pk}',
        f'staff_payroll_{instance.staff.pk}_{instance.period.pk}',
        'payroll_list',
    ]
    
    for key in cache_keys:
        cache.delete(key)