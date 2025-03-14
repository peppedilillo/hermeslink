import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger("hlink")


class Command(BaseCommand):
    help = "Setup periodic tasks"

    def handle(self, *args, **kwargs):
        logger.info("I'm alive. Let's fucking go HERMES!!")
