# academics/apps.py

from django.apps import AppConfig


class AcademicsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "academics"
    
    def ready(self):
        """Import signals when app is ready"""
        import academics.signals  # noqa