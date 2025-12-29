# fees/apps.py

from django.apps import AppConfig


class FeesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "fees"
    verbose_name = "Fee Management"
    
    def ready(self):
        """
        Import signal handlers when the app is ready.
        This ensures signals are connected when Django starts.
        """
        # Import signals to register them
        try:
            import fees.signals  # noqa: F401
        except ImportError:
            pass