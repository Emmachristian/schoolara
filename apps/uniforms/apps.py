# uniforms/apps.py

from django.apps import AppConfig


class UniformsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "uniforms"
    verbose_name = "Uniform Management"
    
    def ready(self):
        """
        Import signal handlers when the app is ready.
        This ensures signals are connected when Django starts.
        """
        # Import signals to register them
        try:
            import uniforms.signals  # noqa: F401
        except ImportError:
            pass