# schoolara/timezone_middleware.py

"""
Timezone middleware for School Management System.

This middleware activates the school's operational timezone for each request,
ensuring all datetime operations use the correct timezone.

CRITICAL: This middleware must run AFTER SchoolDatabaseMiddleware but BEFORE
any business logic that uses dates/times.

How it works:
1. Gets timezone from request.school_timezone (set by SchoolDatabaseMiddleware)
2. Activates timezone using Django's timezone.activate()
3. All subsequent datetime operations use this timezone
4. Timezone remains active until next request

This ensures:
- auto_now and auto_now_add use correct timezone
- Date calculations use school's timezone
- Reports show correct dates/times
- Deadlines are calculated correctly
"""

import logging
from django.utils import timezone
from zoneinfo import ZoneInfo
from django.conf import settings

logger = logging.getLogger(__name__)


class SchoolTimezoneMiddleware:
    """
    Middleware to activate school's operational timezone for each request.
    
    **CRITICAL**: This middleware must run AFTER SchoolDatabaseMiddleware.
    
    The SchoolDatabaseMiddleware sets request.school_timezone by querying
    the database directly. This middleware then activates that timezone
    using Django's timezone.activate(), which makes it the active timezone
    for all datetime operations during this request.
    
    **Why this is important:**
    
    Without this middleware:
    - Django uses settings.TIME_ZONE (typically UTC)
    - auto_now_add timestamps would be in UTC
    - Date comparisons would use wrong timezone
    - Deadlines would be calculated incorrectly
    
    With this middleware:
    - All operations use school's timezone (e.g., Africa/Kampala)
    - Timestamps are correct for the school's location
    - Business logic works as expected

    
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        logger.info("SchoolTimezoneMiddleware initialized")
    
    def __call__(self, request):
        """
        Process request with school's timezone activated.
        
        Flow:
        1. Get timezone from request.school_timezone (set by SchoolDatabaseMiddleware)
        2. Activate timezone using Django's timezone.activate()
        3. Process request with timezone active
        4. Return response (timezone remains active until next request)
        """
        # Activate school timezone BEFORE processing request
        self.activate_school_timezone(request)
        
        # Process the request with timezone active
        response = self.get_response(request)
        
        # Timezone remains active until next request
        # Django will automatically handle cleanup
        return response
    
    def activate_school_timezone(self, request):
        """
        Activate the operational timezone for the current school.
        
        Gets timezone from request.school_timezone (set by SchoolDatabaseMiddleware).
        Falls back to Africa/Kampala if timezone is not set or invalid.
        
        Args:
            request: HTTP request object
        """
        try:
            # Get timezone from request (set by SchoolDatabaseMiddleware)
            tz_str = getattr(request, 'school_timezone', None)
            
            if tz_str:
                try:
                    # Activate the school's configured timezone
                    tz = ZoneInfo(tz_str)
                    timezone.activate(tz)
                    logger.debug(f"✓ Activated timezone: {tz_str}")
                    return  # Success - timezone activated
                    
                except Exception as tz_error:
                    # Invalid timezone string
                    logger.warning(
                        f"Invalid timezone '{tz_str}' in request. "
                        f"Falling back to Africa/Kampala. Error: {tz_error}"
                    )
            else:
                # No timezone in request (might be system path or error)
                logger.debug("No school_timezone in request, using default fallback")
            
            # Fallback: activate default timezone for East Africa
            timezone.activate(ZoneInfo('Africa/Kampala'))
            logger.debug("✓ Activated fallback timezone: Africa/Kampala")
                
        except Exception as e:
            logger.error(f"Error activating school timezone: {e}", exc_info=True)
            
            # Last resort fallback to Africa/Kampala
            try:
                timezone.activate(ZoneInfo('Africa/Kampala'))
                logger.debug("✓ Activated emergency fallback timezone: Africa/Kampala")
            except Exception as fallback_error:
                logger.critical(
                    f"Could not activate any timezone: {fallback_error}. "
                    f"System will use Django's default TIME_ZONE setting."
                )
    
    def process_exception(self, request, exception):
        """
        Ensure timezone state is clean even if an exception occurs.
        
        This is called by Django if an exception occurs during request processing.
        We don't need to do anything special - Django will handle cleanup.
        
        Args:
            request: HTTP request object
            exception: Exception that occurred
            
        Returns:
            None: Let Django handle the exception normally
        """
        logger.debug(f"Exception occurred during request processing: {exception.__class__.__name__}")
        return None  # Let Django handle the exception normally