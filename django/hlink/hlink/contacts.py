import logging
import os

from configs.validators import parse_multiple_emails
from configs.validators import validate_multiple_emails
from django.core.exceptions import ValidationError


def _get_and_validate_emails(env_key: str) -> set[str]:
    env_value = os.environ.get(env_key)
    if not env_value:
        raise ValidationError("Empty environment variable: {}".format(env_key))
    emails = parse_multiple_emails(env_value)
    validate_multiple_emails(emails)
    return set(emails)


EMAILS_STAFF = _get_and_validate_emails("CONTACTS_EMAILS_STAFF")
EMAILS_MOC = _get_and_validate_emails("CONTACTS_EMAILS_MOC")
EMAILS_SOC = _get_and_validate_emails("CONTACTS_EMAILS_SOC")
