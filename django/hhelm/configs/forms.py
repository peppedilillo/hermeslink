from typing import Literal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.core.validators import EmailValidator
from hermes import CONFIG_TYPES, CONFIG_SIZE
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
    acq0 = forms.FileField(validators=[lambda f: check_length(f, "acq0")])
    acq = forms.FileField(validators=[lambda f: check_length(f, "acq")])
    asic0 = forms.FileField(validators=[lambda f: check_length(f, "asic0")])
    asic1 = forms.FileField(validators=[lambda f: check_length(f, "asic1")])
    bee = forms.FileField(validators=[lambda f: check_length(f, "bee")])


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
