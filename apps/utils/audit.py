# utils/audit.py

import json
import logging
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from utils.models import AuditLog
from academics.models import AcademicSession

audit_logger = logging.getLogger("academic_audit")
logger = logging.getLogger(__name__)

def log_financial_activity(
    action,
    user=None,
    request=None,
    target_object=None,
    amount=None,
    student=None,
    academic_session=None,
    old_values=None,
    new_values=None,
    notes=None,
    risk_level='LOW',
    additional_data=None,
    batch_id=None,
    is_automated=False,
    currency=None,
):
    """
    Log financial activity for audit purposes using FinancialAuditLog.

    Args:
        action (str): Type of financial action (e.g., PAYMENT_RECEIVE).
        user (User instance, optional): User performing the action.
        request (HttpRequest, optional): To log IP, session info, path.
        target_object (Model instance, optional): Object affected (Invoice, Payment, etc.).
        amount (Decimal, optional): Amount involved in the action.
        student (Student instance, optional): Related student.
        academic_session (AcademicSession instance or str, optional): Context session.
        old_values (dict, optional): Values before the change.
        new_values (dict, optional): Values after the change.
        notes (str, optional): Additional notes or comments.
        risk_level (str, optional): Risk level ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL').
        additional_data (dict, optional): Extra context-specific data.
        batch_id (str, optional): For grouping bulk operations.
        is_automated (bool, optional): Whether action is automated.
        currency (str, optional): Currency code, e.g., 'UGX'.
    """
    try:
        # Lazy import to avoid circular dependency
        from utils.models import FinancialAuditLog

        # Try to infer user from request if not provided
        if not user and request and hasattr(request, 'user') and request.user.is_authenticated:
            user = request.user

        # Auto-assign academic session if not provided
        if not academic_session:
            try:
                from academics.models import AcademicSession
                academic_session = AcademicSession.get_current()
            except Exception:
                academic_session = None

        # Call the FinancialAuditLog method with all parameters
        FinancialAuditLog.log_financial_action(
            action=action,
            user=user,
            request=request,
            target_object=target_object,
            amount=amount,
            currency=currency,
            student=student,
            academic_session=academic_session,
            old_values=old_values,
            new_values=new_values,
            notes=notes,
            risk_level=risk_level,
            additional_data=additional_data or {},
            batch_id=batch_id,
            is_automated=is_automated,
        )

    except ImportError:
        logger.warning("FinancialAuditLog model not available for audit logging")
    except Exception as e:
        logger.error(f"Error in financial activity logging: {e}", exc_info=True)