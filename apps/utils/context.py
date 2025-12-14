# utils/context.py

from threading import local
import logging

logger = logging.getLogger(__name__)

_thread_locals = local()


def set_request_context(user=None, ip_address=None, user_agent=None, 
                        session_key=None, request_path=None):
    """
    Set request context information for audit logging.
    
    This should be called by middleware to capture request details.
    """
    _thread_locals.request_context = {
        'user': user,
        'ip_address': ip_address,
        'user_agent': user_agent,
        'session_key': session_key,
        'request_path': request_path,
    }


def get_request_context():
    """Get the current request context for audit logging"""
    return getattr(_thread_locals, 'request_context', None)


def clear_request_context():
    """Clear the request context"""
    if hasattr(_thread_locals, 'request_context'):
        delattr(_thread_locals, 'request_context')


def get_client_ip(request):
    """
    Extract the real client IP address from request.
    
    Handles proxy headers like X-Forwarded-For.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        # X-Forwarded-For can contain multiple IPs, get the first one
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    
    return ip


class AuditContextMiddleware:
    """
    Middleware to capture request context for audit logging.
    
    Add this to MIDDLEWARE in settings.py:
        'utils.context.AuditContextMiddleware',
    
    This should come AFTER AuthenticationMiddleware and SchoolDatabaseMiddleware.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Set request context before processing
        set_request_context(
            user=request.user if hasattr(request, 'user') and request.user.is_authenticated else None,
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            session_key=request.session.session_key if hasattr(request, 'session') else None,
            request_path=request.path
        )
        
        try:
            response = self.get_response(request)
        finally:
            # Clear context after request is processed
            clear_request_context()
        
        return response