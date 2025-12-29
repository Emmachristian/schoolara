# finance/apps.py

from django.apps import AppConfig


class FinanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "finance"
    verbose_name = "Finance & Accounting"
    
    def ready(self):
        """
        Import signal handlers when the app is ready.
        This ensures signals are connected when Django starts.
        """
        # Import signals to register them
        try:
            import finance.signals  # noqa: F401
        except ImportError:
            pass