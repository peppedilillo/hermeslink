import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger("hlink")


class Command(BaseCommand):
    help = "Setup periodic tasks"

    def handle(self, *args, **kwargs):
        logger.info("2024-03-15 07:39: GO GO GO HERMES!")
        logger.info("Hermes Link is alive and well. ")
