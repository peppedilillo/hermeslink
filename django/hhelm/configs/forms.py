from typing import Literal

from django import forms
from django.core.files.uploadedfile import UploadedFile

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


class UploadConfiguration(forms.Form):
    """
    A form for uploading configuration files for a specific payload model.
    """
    model = forms.ChoiceField(choices=Configuration.MODELS)
    acq = forms.FileField(validators=[lambda f: check_length(f, "acq")])
    acq0 = forms.FileField(validators=[lambda f: check_length(f, "acq0")])
    asic1 = forms.FileField(validators=[lambda f: check_length(f, "asic1")])
    asic0 = forms.FileField(validators=[lambda f: check_length(f, "asic0")])
    bee = forms.FileField(validators=[lambda f: check_length(f, "bee")])

    def get_model_display(self):
        return dict(Configuration.MODELS)[self.cleaned_data['model']]