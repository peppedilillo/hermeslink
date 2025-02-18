from typing import Literal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.core.validators import EmailValidator
from hermes import CONFIG_SIZE
from hermes import CONFIG_TYPES
from hhelm.settings import EMAIL_CONFIGS_RECIPIENT

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
    A form emailing configuration.
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
