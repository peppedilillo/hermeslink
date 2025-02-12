import uuid
from shutil import rmtree
from smtplib import SMTPException

from django.http import HttpRequest, HttpResponse
from django.core.files.storage import FileSystemStorage
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMessage
from django.db import transaction
from django.conf import settings
from django.utils import timezone
from pathlib import Path

from . import forms
from . import models
from . import validators
from hermes import CONFIG_TYPES


@login_required
def upload(request: HttpRequest) -> HttpResponse:
    """
    This view is intended to accept configuration files for a target model
    from the user, store them in memory and return them to the next view.
    """
    if request.method == 'POST':
        form = forms.UploadConfiguration(request.POST, request.FILES)
        if form.is_valid():
            config_id = str(uuid.uuid4())
            upload_dir = Path(FileSystemStorage().location) / f"configs/{config_id}"
            upload_dir.mkdir(exist_ok=False, parents=True)

            files = {}
            for field in CONFIG_TYPES:
                path = upload_dir / f"{field}.cfg"
                with open(path, 'wb') as f:
                    f.write(form.cleaned_data[field].read())
                files[field] = str(path)

            request.session['config_id'] = config_id
            request.session['config_files'] = files
            request.session['config_model'] = form.get_model_display()
            return redirect('configs:test')

    form = forms.UploadConfiguration()
    return render(request, 'configs/upload.html', {'form': form})


@login_required
def test(request: HttpRequest) -> HttpResponse:
    """
    This view displays the configuration files just uploaded and the results of the
    sanity checks performed on them. If the sanity checks pass without errors, it
    displays a "next" button, otherwise it displays a "go back to upload" button.
    """
    if (
            "config_id" not in request.session or
            "config_files" not in request.session or
            "config_model" not in request.session
    ):
        return redirect('configs:new')

    files = {k: Path(v) for k, v in request.session['config_files'].items()}

    results, can_proceed = validators.validate_configuration(
        request.session["config_files"],
        request.session["config_model"],
    )
    request.session["can_proceed"] = can_proceed

    contents = {}
    for fname, fpath in files.items():
        with open(fpath, 'rb') as f:
            contents[fname] = f.read().hex()

    return render(
        request,
        'configs/test.html',
        {
            'results': results,
            'contents': contents,
            'can_proceed': can_proceed,
        })


@login_required
def deliver(request: HttpRequest) -> HttpResponse:
    """
    This view asks user to submit the configuration to the recipient, as defined
    in `settings.EMAIL_CONFIGS_RECIPIENT`. On POST, it sends the email, then records
    the configuration to the database. If an error is encountered, the user is
    taken to an error page, else a success page is shown.
    """
    def send_email():
        """Prepares the email with the configuration attachments."""
        email = EmailMessage(
            subject=f'New Configuration Delivery',
            body=f'Configuration files uploaded by {request.user.username}',
            from_email=settings.EMAIL_HOST_USER,
            cc=form.cleaned_data["cc"],
            to=(form.cleaned_data["recipient"],),
        )
        for field_name, file_path in request.session['config_files'].items():
            print(field_name, file_path)
            email.attach_file(file_path)
        email.send()

    def record_configuration():
        """Record delivered configuration to db."""
        model_key = {v: k for k, v in dict(models.Configuration.MODELS).items()}[
            request.session['config_model']]
        config_entry = models.Configuration(
            author=request.user,
            delivered=True,
            uploaded=False,
            upload_time=timezone.now(),
            model=model_key,
        )
        for field in ['acq', 'acq0', 'asic0', 'asic1', 'bee']:
            file_path = Path(request.session['config_files'][field])
            with open(file_path, 'rb') as f:
                setattr(config_entry, field, f.read())
        config_entry.save()

    def cleanup():
        """Cleans up temporary files and resets session."""
        upload_dir = Path(FileSystemStorage().location) / f"configs/{request.session['config_id']}"
        if upload_dir.exists():  # Only cleanup if directory exists
            rmtree(upload_dir)
        for key in ['config_id', 'config_files', 'config_model', 'can_proceed']:
            request.session.pop(key, None)  # Safely remove keys

    # Session validation
    if (
            "config_id" not in request.session or
            "config_files" not in request.session or
            "config_model" not in request.session or
            "can_proceed" not in request.session
    ):
        return redirect('configs:upload')

    if not request.session["can_proceed"]:
        return redirect('configs:test')

    if request.method == "POST":
        form = forms.DeliverConfiguration(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    record_configuration()
                    send_email()
            except SMTPException as e:
                print(f"Email delivery failed: {str(e)}")
                return render(request, 'configs/deliver_error.html',
                              {'error': 'Failed to send email'})
            except IOError as e:
                print(f"File operation failed: {str(e)}")
                return render(request, 'configs/deliver_error.html',
                              {'error': 'Failed to process files'})
            except Exception as e:
                print(f"Unexpected error during delivery: {str(e)}")
                return render(request, 'configs/deliver_error.html',
                              {'error': 'An unexpected error occurred'})
            finally:
                cleanup()
            return render(request, "configs/deliver_success.html", {})

    form = forms.DeliverConfiguration()
    return render(
        request,
        "configs/deliver.html",
        {"form": form},
    )