from typing import Literal
import re

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.core.validators import EmailValidator
from hermes import CONFIG_SIZE
from hermes import CONFIG_TYPES
from hhelm.settings import EMAIL_CONFIGS_RECIPIENT, TIME_ZONE

from django import forms

from .models import Configuration


def check_length(
    file: UploadedFile,
    ftype: Literal[*CONFIG_TYPES],
):
    """
    Checks length of an uploaded file to match the exepcted value for its type.
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
            raise forms.ValidationError(
                "At least one configuration file must be provided."
            )

        return cleaned_data


class DeliverConfiguration(forms.Form):
    """
    A form for mailing a configuration.
    """
    recipient = forms.CharField(initial=EMAIL_CONFIGS_RECIPIENT, disabled=True)
    subject = forms.CharField(initial="HERMES configuration files")
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
    upload_time = forms.DateTimeField(
        input_formats=['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S'],
        required=True,
        help_text="A string formatted as `{YYYY}-{MM}-{DD}T{HH}:{MM}:{SS}Z` or `{YYYY}-{MM}-{DD}T{HH}:{MM}:{SS}`.\n "
                  "The 'Z' stands for 'Zero timezone'. If the strings ends with `Z`, UTC timezone is assumed. Otherwise timezone is automatically set to 'Europe/Rome'.\n",
    )

    class Meta:
        model = Configuration
        fields = ['upload_time']

    def clean_upload_time(self):
        # we only accept patterns like "2024-12-22T12:12:12" or "2024-12-22T12:12:12Z"
        format_patterns = [
            r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?$',
            r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?',
        ]
        valid_format = any(
            re.match(pattern, self.data.get("upload_time"))
            for pattern in format_patterns
        )
        if not valid_format:
            raise forms.ValidationError("Time must be in format YYYY-MM-DDThh:mm:ssZ or YYYY-MM-DDThh:mm:ss")

        # upload_time should follow creation date and deliver time.
        upload_time = self.cleaned_data.get("upload_time")
        if upload_time < self.instance.deliver_time or upload_time < self.instance.date:
            raise ValidationError(
                "The upload time is the time when a configuration is uplinked to a spacecraft.\n"
                "It should always come after the time in which a configuration is created, "
                "and the time in which the configuration is submitted to the MOC."
            )
        return upload_time