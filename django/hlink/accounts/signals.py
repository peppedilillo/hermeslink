from django.contrib.auth.signals import user_logged_in, user_login_failed, user_logged_out
from django.dispatch import receiver
import logging


logger = logging.getLogger("hlink")

@receiver(user_logged_in)
def post_login(sender, request, user, **kwargs):
    logger.warning(f'User: {user.username} logged in')

@receiver(user_logged_out)
def post_logout(sender, request, user, **kwargs):
    logger.warning(f'An user logged out')

@receiver(user_login_failed)
def post_login_fail(sender, credentials, request, **kwargs):
    logger.warning(f"Login failed with username: {credentials['username']}")
