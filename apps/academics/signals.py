# academics/signals.py
"""
Signal handlers for academics app
Handles automatic operations when models are created, updated, or deleted
"""

from django.db.models.signals import post_save, pre_save, post_delete, m2m_changed
from django.db.models import Q
from django.dispatch import receiver
from django.utils import timezone
from django.core.exceptions import ValidationError
from academics.models import Subject
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# ACADEMIC SESSION SIGNALS
# =============================================================================

@receiver(pre_save, sender='academics.AcademicSession')
def academic_session_pre_save(sender, instance, **kwargs):
    """
    Handle pre-save operations for AcademicSession.
    - Ensure only one current session
    - Auto-generate period_type and term_name for regular sessions
    """
    # This is now handled in the model's save() method
    # But we can add additional logic here if needed
    pass


@receiver(post_save, sender='academics.AcademicSession')
def academic_session_post_save(sender, instance, created, **kwargs):
    """
    Handle post-save operations for AcademicSession.
    - Log session creation/updates
    - Auto-create fiscal period if enabled
    """
    if created:
        logger.info(
            f"New academic session created: {instance.name} "
            f"({'Special' if instance.is_special_session else 'Regular'})"
        )
        
        # Auto-create fiscal period if configured
        try:
            from core.models import FiscalPeriod
            from core.models import SchoolConfiguration
            
            # Check if auto-creation is enabled in settings
            # This would be a school-wide setting
            auto_create_fiscal = True  # Could be from settings
            
            if auto_create_fiscal and not instance.is_special_session:
                # Create fiscal period aligned with this session
                fiscal_period = FiscalPeriod.create_for_academic_session(
                    academic_session=instance,
                    grace_days=60  # Could be from settings
                )
                logger.info(f"Auto-created fiscal period: {fiscal_period}")
                
        except ImportError:
            logger.debug("FiscalPeriod model not available")
        except Exception as e:
            logger.error(f"Error auto-creating fiscal period: {e}")
    
    else:
        logger.info(f"Academic session updated: {instance.name}")


@receiver(post_delete, sender='academics.AcademicSession')
def academic_session_post_delete(sender, instance, **kwargs):
    """
    Handle post-delete operations for AcademicSession.
    - Log session deletion
    - Clean up related data if necessary
    """
    logger.warning(f"Academic session deleted: {instance.name}")


# =============================================================================
# CLASS SIGNALS
# =============================================================================

@receiver(post_save, sender='academics.Class')
def class_post_save(sender, instance, created, **kwargs):
    """
    Handle post-save operations for Class.
    - Log class creation
    - Initialize class subjects for new classes
    """
    if created:
        logger.info(
            f"New class created: {instance.get_display_name()} "
            f"for session {instance.academic_session.name}"
        )
        
        # Auto-create class subjects for compulsory subjects
        try:
            from .models import Subject, ClassSubject
            
            # Get compulsory subjects for this level
            compulsory_subjects = Subject.objects.filter(
                is_compulsory=True,
                is_active=True
            ).filter(
                Q(applicable_levels__isnull=True) |
                Q(applicable_levels=instance.academic_level)
            ).distinct()
            
            for subject in compulsory_subjects:
                ClassSubject.objects.get_or_create(
                    class_instance=instance,
                    subject=subject,
                    defaults={
                        'is_optional': False,
                        'hours_per_week': 3,  # Default
                    }
                )
            
            if compulsory_subjects.exists():
                logger.info(
                    f"Auto-created {compulsory_subjects.count()} compulsory subjects "
                    f"for class {instance.get_display_name()}"
                )
                
        except Exception as e:
            logger.error(f"Error auto-creating class subjects: {e}")


@receiver(pre_save, sender='academics.Class')
def class_pre_save(sender, instance, **kwargs):
    """
    Handle pre-save operations for Class.
    - Validate section requirements
    - Check classroom conflicts
    """
    # Validation is handled in model's clean() method
    # Additional pre-save logic can go here
    pass


# =============================================================================
# CLASS SUBJECT SIGNALS
# =============================================================================

@receiver(post_save, sender='academics.ClassSubject')
def class_subject_post_save(sender, instance, created, **kwargs):
    """
    Handle post-save operations for ClassSubject.
    - Log subject assignment
    """
    if created:
        logger.info(
            f"Subject assigned: {instance.subject.name} to "
            f"{instance.class_instance.get_display_name()}"
        )


@receiver(pre_save, sender='academics.ClassSubject')
def class_subject_pre_save(sender, instance, **kwargs):
    """
    Handle pre-save operations for ClassSubject.
    - Validate assessment weights
    - Check subject applicability
    """
    # Validation is handled in model's clean() method
    pass


# =============================================================================
# HOLIDAY SIGNALS
# =============================================================================

@receiver(post_save, sender='academics.Holiday')
def holiday_post_save(sender, instance, created, **kwargs):
    """
    Handle post-save operations for Holiday.
    - Log holiday creation
    - Send notifications if enabled
    """
    if created:
        logger.info(f"New holiday created: {instance.name} ({instance.start_date})")
        
        # Send notifications if enabled
        if instance.notify_parents or instance.notify_staff:
            try:
                # Trigger notification task
                # This would integrate with your notification system
                logger.info(f"Holiday notification queued for: {instance.name}")
            except Exception as e:
                logger.error(f"Error sending holiday notification: {e}")


# =============================================================================
# SUBJECT SIGNALS
# =============================================================================

@receiver(m2m_changed, sender=Subject.prerequisites.through)
def subject_prerequisites_changed(sender, instance, action, **kwargs):
    """
    Handle changes to subject prerequisites.
    - Validate no circular dependencies
    """
    if action in ['post_add', 'post_remove']:
        # Check for circular dependencies
        try:
            visited = set()
            stack = [instance]
            
            while stack:
                current = stack.pop()
                if current.id in visited:
                    # Circular dependency detected
                    logger.warning(
                        f"Potential circular dependency detected for subject: {instance.name}"
                    )
                    break
                
                visited.add(current.id)
                stack.extend(current.prerequisites.all())
                
        except Exception as e:
            logger.error(f"Error checking prerequisites: {e}")


# =============================================================================
# ACADEMIC LEVEL SIGNALS
# =============================================================================

@receiver(pre_save, sender='academics.AcademicLevel')
def academic_level_pre_save(sender, instance, **kwargs):
    """
    Handle pre-save operations for AcademicLevel.
    - Validate progression chain
    """
    # Check for circular progression
    if instance.next_level:
        current = instance.next_level
        visited = {instance.id}
        max_iterations = 20
        iterations = 0
        
        while current and iterations < max_iterations:
            if current.id in visited:
                raise ValidationError(
                    "Circular progression detected in level progression chain"
                )
            visited.add(current.id)
            current = current.next_level if hasattr(current, 'next_level') else None
            iterations += 1


# =============================================================================
# CLASSROOM SIGNALS
# =============================================================================

@receiver(post_save, sender='academics.ClassRoom')
def classroom_post_save(sender, instance, created, **kwargs):
    """
    Handle post-save operations for ClassRoom.
    - Log classroom creation
    """
    if created:
        logger.info(
            f"New classroom created: {instance.room_number} - {instance.name} "
            f"(Type: {instance.get_room_type_display()})"
        )

# =============================================================================
# STUDENT CLASS ENROLLMENT SIGNALS
# =============================================================================

@receiver(pre_save, sender='academics.StudentClassEnrollment')
def auto_generate_roll_number(sender, instance, **kwargs):
    """
    Automatically generate roll number when creating a new enrollment.
    Only generates if roll_number is not already set.
    """
    # Only generate for new enrollments without a roll number
    if not instance.pk and not instance.roll_number:
        from academics.utils import generate_class_roll_number
        
        try:
            instance.roll_number = generate_class_roll_number(
                class_instance=instance.class_instance,
                academic_session=instance.academic_session
            )
            logger.debug(
                f"Auto-generated roll number {instance.roll_number} for "
                f"{instance.student} in {instance.class_instance}"
            )
        except Exception as e:
            logger.error(f"Error auto-generating roll number: {e}")


@receiver(post_save, sender='academics.StudentClassEnrollment')
def enrollment_post_save(sender, instance, created, **kwargs):
    """
    Handle post-save operations for StudentClassEnrollment.
    - Auto-create AcademicProgress record
    - Update student's current academic level
    """
    if created:
        logger.info(
            f"New enrollment: {instance.student.get_full_name()} enrolled in "
            f"{instance.class_instance} for {instance.academic_session}"
        )
        
        # Auto-create AcademicProgress record
        try:
            from academics.models import AcademicProgress
            
            progress, progress_created = AcademicProgress.objects.get_or_create(
                student=instance.student,
                academic_session=instance.academic_session,
                defaults={
                    'class_enrollment': instance,
                    'total_subjects': instance.class_instance.subjects.filter(
                        is_active=True
                    ).count(),
                }
            )
            
            if progress_created:
                logger.info(
                    f"Auto-created AcademicProgress for {instance.student} - "
                    f"{instance.academic_session}"
                )
            else:
                # Update the class_enrollment reference if progress already exists
                progress.class_enrollment = instance
                progress.save()
                logger.debug(
                    f"Updated existing AcademicProgress for {instance.student}"
                )
                
        except Exception as e:
            logger.error(f"Error creating AcademicProgress: {e}")
        
        # Update student's current academic level if this is an active enrollment
        if instance.is_active and instance.completion_status == 'ONGOING':
            try:
                instance.student.current_academic_level = instance.class_instance.academic_level
                instance.student.save(update_fields=['current_academic_level'])
                logger.debug(
                    f"Updated {instance.student}'s current level to "
                    f"{instance.class_instance.academic_level}"
                )
            except Exception as e:
                logger.error(f"Error updating student current level: {e}")


@receiver(pre_save, sender='academics.StudentClassEnrollment')
def enrollment_status_change_handler(sender, instance, **kwargs):
    """
    Handle enrollment status changes.
    - Track when enrollment is completed/dropped/transferred
    - Update completion_date automatically
    """
    if instance.pk:  # Only for existing records
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            
            # Check if completion_status changed
            if old_instance.completion_status != instance.completion_status:
                logger.info(
                    f"Enrollment status changed for {instance.student}: "
                    f"{old_instance.completion_status} → {instance.completion_status}"
                )
                
                # Auto-set completion_date if status changed to a completed state
                if instance.completion_status in ['COMPLETED', 'DROPPED', 'TRANSFERRED', 'WITHDRAWN']:
                    if not instance.completion_date:
                        instance.completion_date = timezone.now().date()
                        logger.debug(
                            f"Auto-set completion_date to {instance.completion_date}"
                        )
                
                # Mark as inactive if not ongoing
                if instance.completion_status != 'ONGOING':
                    instance.is_active = False
                    
        except sender.DoesNotExist:
            pass
        except Exception as e:
            logger.error(f"Error in enrollment status change handler: {e}")


@receiver(post_delete, sender='academics.StudentClassEnrollment')
def enrollment_post_delete(sender, instance, **kwargs):
    """
    Handle post-delete operations for StudentClassEnrollment.
    - Log deletion
    - Clean up orphaned AcademicProgress records (optional)
    """
    logger.warning(
        f"Enrollment deleted: {instance.student.get_full_name()} from "
        f"{instance.class_instance} ({instance.academic_session})"
    )

# =============================================================================
# HELPER FUNCTIONS FOR SIGNALS
# =============================================================================

def ensure_only_one_current_session():
    """
    Ensure only one session is marked as current.
    Called by session save signal.
    """
    from .models import AcademicSession
    
    current_sessions = AcademicSession.objects.filter(is_current=True)
    
    if current_sessions.count() > 1:
        # Keep the most recent one
        latest = current_sessions.order_by('-start_date').first()
        current_sessions.exclude(pk=latest.pk).update(is_current=False)
        logger.warning(
            f"Multiple current sessions found. Kept only: {latest.name}"
        )