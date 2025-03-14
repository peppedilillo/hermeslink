import logging

from django.contrib.auth.signals import user_logged_in
from django.contrib.auth.signals import user_logged_out
from django.contrib.auth.signals import user_login_failed
from django.dispatch import receiver

logger = logging.getLogger("hlink")


@receiver(user_logged_in)
def post_login(sender, request, user, **kwargs):
    logger.warning(f"User: {user.username} logged in")


@receiver(user_logged_out)
def post_logout(sender, request, user, **kwargs):
    logger.warning(f"An user logged out")


@receiver(user_login_failed)
def post_login_fail(sender, credentials, request, **kwargs):
    logger.warning(f"Login failed with username: {credentials['username']}")
