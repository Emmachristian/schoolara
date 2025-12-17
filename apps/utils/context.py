# utils/context.py

"""
Thread-local request context for audit logging.

This module provides thread-local storage for request information
that needs to be accessible throughout the request lifecycle,
particularly for audit logging purposes.
"""

from threading import local
import logging

logger = logging.getLogger(__name__)

# Thread-local storage
_thread_locals = local()


def set_request_context(user=None, ip_address=None, user_agent=None, 
                       session_key=None, request_path=None, request=None):
    """
    Set the current request context for this thread.
    
    This should be called by middleware at the start of each request.
    
    Args:
        user: The authenticated user (or None)
        ip_address: Client IP address
        user_agent: Browser user agent string
        session_key: Session key
        request_path: The request path/URL
        request: The full request object (alternative to individual params)
    """
    if request:
        # Extract info from request object
        user = getattr(request, 'user', None)
        ip_address = _get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        session_key = getattr(request.session, 'session_key', '') if hasattr(request, 'session') else ''
        request_path = getattr(request, 'path', '')
    
    # Store in thread-local
    _thread_locals.request_context = {
        'user': user if user and user.is_authenticated else None,
        'ip_address': ip_address,
        'user_agent': user_agent or '',
        'session_key': session_key or '',
        'request_path': request_path or '',
    }
    
    logger.debug(f"Set request context: user={user}, ip={ip_address}")


def get_request_context():
    """
    Get the current request context for this thread.
    
    Returns:
        dict: Request context containing user, ip_address, user_agent, etc.
              Returns None if no context is set.
    """
    return getattr(_thread_locals, 'request_context', None)


def clear_request_context():
    """Clear the request context for this thread."""
    if hasattr(_thread_locals, 'request_context'):
        delattr(_thread_locals, 'request_context')
        logger.debug("Cleared request context")


def _get_client_ip(request):
    """
    Extract the client's real IP address from the request.
    
    Handles X-Forwarded-For header for proxied requests.
    """
    try:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            # X-Forwarded-For can contain multiple IPs, take the first one
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    except Exception as e:
        logger.warning(f"Error extracting client IP: {e}")
        return None


# ============================================================================
# CONTEXT MANAGER
# ============================================================================

class RequestContext:
    """
    Context manager for temporarily setting request context.
    
    Useful for background tasks or management commands that need
    to set audit context.
    
    Example:
        with RequestContext(user=some_user, ip_address='127.0.0.1'):
            student.save()  # Will be audited with the provided context
    """
    
    def __init__(self, user=None, ip_address=None, user_agent=None, 
                 session_key=None, request_path=None):
        self.context = {
            'user': user,
            'ip_address': ip_address,
            'user_agent': user_agent or '',
            'session_key': session_key or '',
            'request_path': request_path or '',
        }
        self.previous_context = None
    
    def __enter__(self):
        self.previous_context = get_request_context()
        _thread_locals.request_context = self.context
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.previous_context:
            _thread_locals.request_context = self.previous_context
        else:
            clear_request_context()


# ============================================================================
# DECORATOR
# ============================================================================

def with_request_context(user=None, ip_address=None, **kwargs):
    """
    Decorator to execute a function with request context.
    
    Example:
        @with_request_context(user=request.user, ip_address='127.0.0.1')
        def create_records():
            Student.objects.create(...)
    """
    def decorator(func):
        def wrapper(*args, **func_kwargs):
            with RequestContext(user=user, ip_address=ip_address, **kwargs):
                return func(*args, **func_kwargs)
        return wrapper
    return decorator