# academics/apps.py

from django.apps import AppConfig

class AcademicsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'academics'
    verbose_name = 'Academics'
    
    def ready(self):
        """Import signals when app is ready"""
        import academics.signals  # ← CRITICAL: This registers all signals
        
        # Log to verify signals are loaded
        import logging
        logger = logging.getLogger(__name__)
        logger.info("Academics app signals loaded")