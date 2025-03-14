import logging

from django.apps import AppConfig


logger = logging.getLogger("hlink")

class MainConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "main"

    def ready(self):
        import accounts.signals  # noqa

        logger.info("HL is alive. Godspeed HERMES!!")