import logging
import re
from typing import Literal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from hermes import CONFIG_SIZE
from hermes import CONFIG_TYPES
from hlink.contacts import EMAILS_MOC

from django import forms

from .models import Configuration
from .validators import parse_multiple_emails
from .validators import validate_multiple_emails

logger = logging.getLogger("hlink")


def check_length(
    file: UploadedFile,
    ftype: Literal[*CONFIG_TYPES],
):
    """Validates that an uploaded file's size matches the expected size for its type.
    Raises ValidationError if the size doesn't match the expected value."""
    if file.size != CONFIG_SIZE[ftype]:
        raise forms.ValidationError(
            f"Your {ftype} configuration file size is {file.size} bytes. "
            f"Files of type {ftype} must have size {CONFIG_SIZE[ftype]} bytes."
        )


class UploadConfiguration(forms.Form):
    """
    A form for uploading configuration files for a specific payload model.
    Validates file sizes against expected values for each configuration type.
    Ensures at least one configuration file is provided.
    """

    model = forms.ChoiceField(choices=Configuration.MODELS)

    acq0 = forms.FileField(required=False, validators=[lambda f: check_length(f, "acq0") if f else None])
    acq = forms.FileField(required=False, validators=[lambda f: check_length(f, "acq0") if f else None])
    asic0 = forms.FileField(required=False, validators=[lambda f: check_length(f, "asic0") if f else None])
    asic1 = forms.FileField(required=False, validators=[lambda f: check_length(f, "asic1") if f else None])
    bee = forms.FileField(required=False, validators=[lambda f: check_length(f, "bee") if f else None])
    liktrg = forms.FileField(required=False, validators=[lambda f: check_length(f, "liktrg") if f else None])
    obs = forms.FileField(required=False, validators=[lambda f: check_length(f, "obs") if f else None])

    def clean(self):
        cleaned_data = super().clean()

        if not any(cleaned_data.get(ftype) for ftype in CONFIG_TYPES):
            raise forms.ValidationError("At least one configuration file must be provided.")

        return cleaned_data


class SubmitConfiguration(forms.Form):
    """
    A form for submitting a configuration to the Mission Operation Center.
    Validates email recipients and handles CC email addresses.
    """

    recipients = forms.CharField(
        # note, this is just for displaying purpose in form.
        initial=";".join(EMAILS_MOC),
        disabled=True,
    )
    cc = forms.CharField(required=False)

    @staticmethod
    def clean_recipients() -> tuple[str]:
        return EMAILS_MOC

    def clean_cc(self):
        emails = parse_multiple_emails(self.cleaned_data.get("cc"))
        try:
            validate_multiple_emails(emails)
        except ValidationError as e:
            logger.error(f"Invalid Cc list: {e}")
            raise ValidationError("Some of the addresses in the Cc list are invalid.")
        return emails


class CommitConfiguration(forms.ModelForm):
    """
    A form for committing an uplink timestamp for a configuration.
    Validates that the timestamp format is correct and that the timestamp
    occurs after the configuration's submission time.
    """

    uplink_time = forms.DateTimeField(
        required=True,
        help_text="A UTC timestamp string formatted as `{YYYY}-{MM}-{DD}T{HH}:{MM}:{SS}Z`.",
    )

    class Meta:
        model = Configuration
        fields = ["uplink_time"]

    def clean_uplink_time(self):
        # we only accept patterns like "2024-12-22T12:12:12" or "2024-12-22T12:12:12Z"
        format_patterns = [
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
        ]
        valid_format = any(re.match(pattern, self.data.get("uplink_time")) for pattern in format_patterns)
        if not valid_format:
            raise forms.ValidationError(
                "UTC timestamp must be in format 'YYYY-MM-DDThh:mm:ssZ'. Mind the 'Z', it means UTC!"
            )

        # uplink_time should follow creation date and submit time.
        uplink_time = self.cleaned_data.get("uplink_time")
        if uplink_time < self.instance.submit_time or uplink_time < self.instance.date:
            raise ValidationError(
                "The uplink time is the time when a configuration is transmitted to a spacecraft.\n"
                "It should always come after the time in which a configuration is created, "
                "and the time in which the configuration is submitted to the MOC."
            )
        return uplink_time
