# accounts/backends.py

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class EmailAuthBackend(ModelBackend):
    """
    Custom authentication backend that:
    - Allows login with email or username
    - Handles account locking and failed login attempt tracking via UserProfile
    - Works with standard Django User model
    """
    
    def authenticate(self, request, username=None, password=None, email=None, **kwargs):
        """
        Authenticate user by email or username.
        
        Args:
            request: The HTTP request object
            username: Can be email or username (for compatibility)
            password: User's password
            email: User's email address
            
        Returns:
            User object if authentication successful, None otherwise
        """
        # Support both 'username' and 'email' parameters
        login_field = email or username
        
        if login_field is None or password is None:
            return None
        
        try:
            # Try to find user by email (case-insensitive) or username
            user = User.objects.filter(
                Q(email__iexact=login_field) | Q(username__iexact=login_field)
            ).first()
            
            if not user:
                # Run the default password hasher to reduce timing difference
                User().set_password(password)
                logger.warning(
                    f"Login attempt for non-existent user: {login_field} from IP: {self._get_client_ip(request)}"
                )
                return None
            
            # Check if account is locked (via profile)
            if hasattr(user, 'profile') and user.profile.account_locked_until:
                if timezone.now() < user.profile.account_locked_until:
                    logger.warning(
                        f"Login attempt for locked account: {user.email} from IP: {self._get_client_ip(request)}"
                    )
                    return None
                else:
                    # Lock period expired, clear it
                    user.profile.account_locked_until = None
                    user.profile.failed_login_attempts = 0
                    user.profile.save(update_fields=['account_locked_until', 'failed_login_attempts'])
            
            # Check if account is active
            if not user.is_active:
                logger.warning(
                    f"Login attempt for inactive account: {user.email}"
                )
                return None
            
            # Check the password
            if user.check_password(password):
                # Successful login - reset failed attempts
                if hasattr(user, 'profile'):
                    if user.profile.failed_login_attempts > 0 or user.profile.account_locked_until:
                        user.profile.failed_login_attempts = 0
                        user.profile.account_locked_until = None
                        user.profile.last_activity = timezone.now()
                        user.profile.save(update_fields=[
                            'failed_login_attempts', 
                            'account_locked_until',
                            'last_activity'
                        ])
                
                logger.info(f"Successful login: {user.email}")
                return user
            else:
                # Failed login - increment failed attempts
                if hasattr(user, 'profile'):
                    user.profile.failed_login_attempts += 1
                    
                    # Lock account after max attempts (e.g., 5)
                    if user.profile.failed_login_attempts >= 5:
                        from datetime import timedelta
                        user.profile.account_locked_until = timezone.now() + timedelta(minutes=30)
                    
                    user.profile.save(update_fields=['failed_login_attempts', 'account_locked_until'])
                    
                    logger.warning(
                        f"Failed login attempt for {user.email}. "
                        f"Attempt {user.profile.failed_login_attempts} from IP: {self._get_client_ip(request)}"
                    )
                return None
                
        except Exception as e:
            logger.error(f"Authentication error for {login_field}: {str(e)}")
            return None
        
        return None
    
    def get_user(self, user_id):
        """
        Get user by ID.
        
        Args:
            user_id: The user's primary key
            
        Returns:
            User object if found, None otherwise
        """
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
        except (TypeError, ValueError) as e:
            logger.error(f"Invalid user_id format: {user_id}, Error: {e}")
            return None
    
    def _get_client_ip(self, request):
        """
        Get the client's IP address from the request.
        
        Args:
            request: The HTTP request object
            
        Returns:
            IP address as string
        """
        if request is None:
            return 'Unknown'
        
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', 'Unknown')
        return ip


class SchoolAuthBackend(EmailAuthBackend):
    """
    Extended authentication backend that also validates school membership.
    Use this if you want to restrict login to users belonging to specific schools.
    """
    
    def authenticate(self, request, username=None, password=None, email=None, school=None, **kwargs):
        """
        Authenticate user by email and optionally validate school membership.
        
        Args:
            request: The HTTP request object
            username: Can be email or username (for compatibility)
            password: User's password
            email: User's email address
            school: Optional School to validate membership against
            
        Returns:
            User object if authentication successful, None otherwise
        """
        # First authenticate using parent class
        user = super().authenticate(request, username, password, email, **kwargs)
        
        if user is None:
            return None
        
        # If school is specified, validate membership (via profile)
        if school:
            if not hasattr(user, 'profile') or user.profile.school != school:
                logger.warning(
                    f"User {user.email} attempted to login to wrong school. "
                    f"User belongs to {user.profile.school if hasattr(user, 'profile') else 'None'}, "
                    f"attempted {school}"
                )
                return None
            
            # Check if school subscription is active
            if user.profile.school and not user.profile.school.is_active_subscription:
                logger.warning(
                    f"User {user.email} attempted to login to school with inactive subscription: {user.profile.school}"
                )
                return None
        
        return user


class PermissionBackend(ModelBackend):
    """
    Custom permission backend for school-specific permissions.
    Checks permissions via UserProfile role.
    """
    
    def get_user(self, user_id):
        """
        Get user by ID.
        
        Args:
            user_id: The user's primary key
            
        Returns:
            User object if found, None otherwise
        """
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
        except (TypeError, ValueError) as e:
            logger.error(f"Invalid user_id format: {user_id}, Error: {e}")
            return None
    
    def has_perm(self, user_obj, perm, obj=None):
        """
        Check if user has a specific permission.
        
        Args:
            user_obj: The user object
            perm: Permission string (e.g., 'app.permission_name')
            obj: Optional object to check permission against
            
        Returns:
            Boolean indicating if user has permission
        """
        if not user_obj.is_active:
            return False
        
        # Superusers have all permissions
        if user_obj.is_superuser:
            return True
        
        # Check if user has profile and check role-based permissions
        if hasattr(user_obj, 'profile'):
            # Administrator and Director of Studies have elevated permissions
            admin_roles = ['Administrator', 'Director of Studies']
            if user_obj.profile.role in admin_roles:
                return True
            
            # Finance Manager has financial permissions
            if 'financial' in perm.lower() or 'fee' in perm.lower():
                if user_obj.profile.role == 'Finance Manager':
                    return True
            
            # Registrar has student/registration permissions
            if 'student' in perm.lower() or 'registration' in perm.lower():
                if user_obj.profile.role in ['Registrar', 'Director of Studies']:
                    return True
        
        # Fall back to Django's default permission checking
        return super().has_perm(user_obj, perm, obj)
    
    def has_module_perms(self, user_obj, app_label):
        """
        Check if user has permissions to access a module.
        
        Args:
            user_obj: The user object
            app_label: The application label
            
        Returns:
            Boolean indicating if user has module permissions
        """
        if not user_obj.is_active:
            return False
        
        # Superusers have access to all modules
        if user_obj.is_superuser:
            return True
        
        # Check via profile if available
        if hasattr(user_obj, 'profile'):
            # Administrators and Directors have access to all modules
            admin_roles = ['Administrator', 'Director of Studies']
            if user_obj.profile.role in admin_roles:
                return True
        
        # Staff users have access to their modules
        if user_obj.is_staff:
            return True
        
        return False