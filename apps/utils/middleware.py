# utils/middleware.py

"""
Middleware for setting request context for audit logging.
"""

import logging
from utils.context import set_request_context, clear_request_context

logger = logging.getLogger(__name__)


class AuditContextMiddleware:
    """
    Middleware that captures request information and stores it in thread-local
    storage for use by audit logging throughout the request lifecycle.
    
    This middleware should be placed early in the MIDDLEWARE list, but after
    authentication middleware so that request.user is available.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Set the request context at the start of the request
        try:
            set_request_context(request=request)
            logger.debug(f"Set audit context for {request.path}")
        except Exception as e:
            logger.error(f"Error setting audit context: {e}", exc_info=True)
        
        # Process the request
        response = self.get_response(request)
        
        # Clear the request context after the request is complete
        try:
            clear_request_context()
        except Exception as e:
            logger.error(f"Error clearing audit context: {e}", exc_info=True)
        
        return response
    
    def process_exception(self, request, exception):
        """Clear context even if an exception occurs"""
        try:
            clear_request_context()
        except Exception as e:
            logger.error(f"Error clearing audit context on exception: {e}", exc_info=True)
        return None  # Let Django handle the exception normally