import re
from typing import Literal

from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.core.validators import EmailValidator

from hermes import CONFIG_SIZE
from hermes import CONFIG_TYPES
from hlink.settings import EMAIL_CONFIGS_RECIPIENT
from hlink.settings import TIME_ZONE

from .models import Configuration


def check_length(
    file: UploadedFile,
    ftype: Literal[*CONFIG_TYPES],
):
    """
    Checks length of an uploaded file to match the expected value for its type.
    """
    if file.size != CONFIG_SIZE[ftype]:
        raise forms.ValidationError(
            f"Your {ftype} configuration file size is {file.size} bytes. "
            f"Files of type {ftype} must have size {CONFIG_SIZE[ftype]} bytes."
        )


def validate_cc(value: str):
    """
    Validate a list of Cc email addresses. Supports:
     - `prova@dom.com`
     - `prova@dom.com;`
     - `prova@dom.com; lol@dom1.com; ..`
     - `prova@dom.com; lol@dom1.com; ..;`
    """
    value = value.strip()
    if ";" not in value:
        return EmailValidator()(value)
    values = [s.strip() for s in value.split(";")]
    # user can terminate value cc list with ";"
    if values[-1] == "":
        values.pop()
    return all(EmailValidator()(value) for value in values)


class UploadConfiguration(forms.Form):
    """
    A form for uploading configuration files for a specific payload model.
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
    A form for mailing a configuration.
    """

    recipient = forms.CharField(initial=EMAIL_CONFIGS_RECIPIENT, disabled=True)
    cc = forms.CharField(required=False)

    def clean_cc(self):
        value = self.cleaned_data.get("cc").strip()
        if not value:
            return []
        validate = EmailValidator()
        if ";" not in value:
            try:
                validate(value)
            except ValidationError:
                raise ValidationError(f"Email address  '{value}' not valid.")
            return [value]
        values = [s.strip() for s in value.split(";")]
        # user can terminate value cc list with ";"
        if values[-1] == "":
            values.pop()
        for value in values:
            try:
                validate(value)
            except ValidationError:
                raise ValidationError(f"Email address '{value}' not valid.")
        return values


class CommitConfiguration(forms.ModelForm):
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
            raise forms.ValidationError("UTC timestamp must be in format 'YYYY-MM-DDThh:mm:ssZ'. Mind the 'Z'!")

        # uplink_time should follow creation date and submit time.
        uplink_time = self.cleaned_data.get("uplink_time")
        if uplink_time < self.instance.submit_time or uplink_time < self.instance.date:
            raise ValidationError(
                "The uplink time is the time when a configuration is transmitted to a spacecraft.\n"
                "It should always come after the time in which a configuration is created, "
                "and the time in which the configuration is submitted to the MOC."
            )
        return uplink_time
