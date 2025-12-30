# utils/middleware.py

import logging
from utils.context import set_request_context, clear_request_context, get_request_context

logger = logging.getLogger(__name__)


class AuditContextMiddleware:
    """
    Middleware to capture request context for audit logging.
    Now also captures school timezone to prevent recursion.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Set context with individual parameters (not a dict!)
        set_request_context(
            user=request.user if request.user.is_authenticated else None,
            ip_address=self._get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            session_key=request.session.session_key if hasattr(request, 'session') else '',
            request_path=request.path,
        )
        
        # Add school timezone to context if available
        context = get_request_context()
        if context and hasattr(request, 'school_timezone'):
            context['school_timezone'] = request.school_timezone
        
        try:
            response = self.get_response(request)
        finally:
            # Always clear context after request
            clear_request_context()
        
        return response
    
    def process_exception(self, request, exception):
        """Clean up context on exception"""
        clear_request_context()
        return None
    
    def _get_client_ip(self, request):
        """
        Get the real client IP address, accounting for proxies.
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        
        if x_forwarded_for:
            # X-Forwarded-For can contain multiple IPs, take the first one
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        
        return ip