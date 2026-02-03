from django.apps import AppConfig


class StudentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "students"
    
    def ready(self):
        """Import signals when the app is ready"""
        import students.signals  # noqa