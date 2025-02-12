from typing import Literal

from django import forms
from django.core.files.uploadedfile import UploadedFile
from django.core.validators import EmailValidator
from django.core.exceptions import ValidationError

from hhelm.settings import EMAIL_CONFIGS_RECIPIENT
from .models import Configuration
from hermes import CONFIG_TYPES

EXPECTED_LEN = {
    "acq": 20,
    "acq0": 20,
    "asic0": 124,
    "asic1": 124,
    "bee": 64,
}

ConfigFileType = Literal[*CONFIG_TYPES]


def check_length(
        file: UploadedFile,
        ftype: ConfigFileType,
):
    """
    Checks length of an uploaded file to match the exepcted value for its type.
    """
    if file.size != EXPECTED_LEN[ftype]:
        raise forms.ValidationError(
            f"Your {ftype} configuration file ({file.name}) size is {file.size} bytes."
            f"Files of type {ftype} must have size {EXPECTED_LEN[ftype]} bytes."
        )


def validate_cc(value):
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
    acq = forms.FileField(validators=[lambda f: check_length(f, "acq")])
    acq0 = forms.FileField(validators=[lambda f: check_length(f, "acq0")])
    asic0 = forms.FileField(validators=[lambda f: check_length(f, "asic0")])
    asic1 = forms.FileField(validators=[lambda f: check_length(f, "asic1")])
    bee = forms.FileField(validators=[lambda f: check_length(f, "bee")])

    def get_model_display(self):
        return dict(Configuration.MODELS)[self.cleaned_data['model']]


class DeliverConfiguration(forms.Form):
    """
    A form emailing configuration.
    """
    recipient = forms.CharField(
        initial=EMAIL_CONFIGS_RECIPIENT,
        disabled=True
    )
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
