# hr/apps.py

from django.apps import AppConfig


class HrConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "hr"
    verbose_name = "Human Resources & Payroll"
    
    def ready(self):
        """
        Import signal handlers when the app is ready.
        """
        try:
            import hr.signals  # noqa: F401
        except ImportError:
            pass