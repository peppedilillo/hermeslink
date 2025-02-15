from pathlib import Path
from collections import OrderedDict
from shutil import rmtree
from smtplib import SMTPException
from typing import Literal
import uuid
from hashlib import sha256

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.storage import FileSystemStorage
from django.core.mail import EmailMessage
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import redirect
from django.shortcuts import render
from django.utils import timezone
from hermes import CONFIG_TYPES
from hermes import payloads

from . import forms
from . import models
from . import validators
from .models import Configuration, config_to_sha256


def config_dir_path(config_id: str) -> Path:
    """Return the path of the config directory on file system."""
    return Path(FileSystemStorage().location) / f"configs/{config_id}"

def config_files_path(config_id: str) -> OrderedDict[str, Path]:
    """Return a dictionary of the path to the config files on file system."""
    config_dir = config_dir_path(config_id)
    return OrderedDict((c, config_dir / f"{c}.cfg") for c in CONFIG_TYPES)

@login_required
def upload(request: HttpRequest) -> HttpResponse:
    """
    This view is intended to accept configuration files for a target model
    from the user, store them in memory and return them to the next view.
    """
    if request.method == "POST":
        form = forms.UploadConfiguration(request.POST, request.FILES)
        # form will perform file size validation
        if form.is_valid():
            config_id = str(uuid.uuid4())
            upload_dir = config_dir_path(config_id)
            upload_dir.mkdir(exist_ok=False, parents=True)

            hasher = sha256()
            files = config_files_path(config_id)
            for ftype, filepath in files.items():
                with open(filepath, "wb") as f:
                    content = form.cleaned_data[ftype].read()
                    hasher.update(content)
                    f.write(content)

            request.session["config_id"] = config_id
            request.session["config_hash"] = hasher.hexdigest()
            request.session["config_model"] = form.cleaned_data["model"]
            return redirect("configs:test")
        return render(request, "configs/upload.html", {'form': form})

    form = forms.UploadConfiguration()
    return render(request, "configs/upload.html", {"form": form})

def validate_config_model(model: Literal[*payloads.NAMES]) -> bool:
    """Checks config model to be allowed"""
    model_keys, _  = zip(*models.Configuration.MODELS)
    return model in model_keys

def validate_config_id(config_id: str) -> bool:
    """Checks config ID to map to directory containing all configuration files."""
    config_files = config_files_path(config_id)
    return (
        # user provided all the necessary files
        all(c in config_files for c in CONFIG_TYPES) and
        # the files exists on filesystem
        all(Path(v).is_file() for v in config_files.values())
    )

def session_is_valid(request: HttpRequest) -> bool:
    """
    Checks hash to be present, model to be well set and all files to be online.
    """
    if (
            ("config_model" in request.session and validate_config_model(request.session["config_model"])) and
            ("config_id" in request.session and validate_config_id(request.session["config_id"])) and
            ("config_hash" in request.session)
    ):
        return True
    return False


@login_required
def test(request: HttpRequest) -> HttpResponse:
    """
    This view displays the configuration files just uploaded and the results of the
    sanity checks performed on them. If the sanity checks pass without errors, it
    displays a "next" button, otherwise it displays a "go back to upload" button.
    """
    if not session_is_valid(request):
        return redirect("configs:upload")

    config_files = config_files_path(request.session["config_id"])

    # we sanity check the configuration file content
    results, can_proceed = validators.validate_configuration(
        config_files,
        request.session["config_model"],
    )
    request.session["can_proceed"] = can_proceed

    # we will display file content
    contents = {}
    for ftype, fpath in config_files.items():
        with open(fpath, "rb") as f:
            contents[ftype] = f.read().hex()

    return render(
        request,
        "configs/test.html",
        {
            "results": results,
            "contents": contents,
            "can_proceed": can_proceed,
        },
    )

class HashError(Exception):
    """Inconsitent configuration hashes"""

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
            subject=form.cleaned_data["subject"],
            body=f"Configuration files uploaded by {request.user.username}",
            from_email=settings.EMAIL_HOST_USER,
            cc=form.cleaned_data["cc"],
            to=(form.cleaned_data["recipient"],),
        )
        for _, fpath in config_files.items():
            email.attach_file(fpath)
        email.send()

    def create_and_check_configuration():
        """Record delivered configuration to db."""
        config_entry = models.Configuration(
            author=request.user,
            delivered=False,
            deliver_time=None,
            uploaded=False,
            upload_time=None,
            model=request.session["config_model"],
        )
        for ftype in CONFIG_TYPES:
            file_path = Path(config_files[ftype])
            with open(file_path, "rb") as f:
                setattr(config_entry, ftype, f.read())

        record_hash, _ = config_to_sha256(config_entry, ordered_keys=config_files.keys())
        if request.session["config_hash"] != record_hash:
            raise HashError("Input file hash does not match configuration record.")
        return config_entry

    def commit_configuration(config_entry: models.Configuration):
        config_entry.delivered = True
        config_entry.deliver_time = timezone.now()
        config_entry.save()

    def cleanup():
        """Cleans up temporary files and resets session."""
        upload_dir = config_dir_path(request.session["config_id"])
        if upload_dir.exists():  # Only cleanup if directory exists
            rmtree(upload_dir)
        for key in ["config_id", "config_model", "can_proceed"]:
            request.session.pop(key, None)  # Safely remove keys


    if not session_is_valid(request) or "can_proceed" not in request.session:
        return redirect("configs:upload")

    if not request.session["can_proceed"]:
        return redirect("configs:test")


    config_files = config_files_path(request.session["config_id"])

    if request.method == "POST":
        form = forms.DeliverConfiguration(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    config = create_and_check_configuration()
                    send_email()
                    commit_configuration(config)
                    cleanup()
            except HashError as e:
                print(f"Integrity error: {str(e)}")
                return render(request, "configs/deliver_error.html", {"error": "Compromised input integrity."})
            except SMTPException as e:
                print(f"Email delivery failed: {str(e)}")
                return render(request, "configs/deliver_error.html", {"error": "Failed to send email"})
            except IOError as e:
                print(f"File operation failed: {str(e)}")
                return render(request, "configs/deliver_error.html", {"error": "Failed to process files"})
            except Exception as e:
                print(f"Unexpected error during delivery: {str(e)}")
                return render(request, "configs/deliver_error.html", {"error": "An unexpected error occurred"})
            return render(request, "configs/deliver_success.html", {})

    form = forms.DeliverConfiguration()
    return render(
        request,
        "configs/deliver.html",
        {"form": form},
    )

EMPTY_HISTORY_MESSAGE = "No configuration has been uploaded yet."

@login_required
def history(request: HttpRequest) -> HttpResponse:
    """
    View to display all recorded configurations.
    """
    configurations = models.Configuration.objects.order_by("-date")
    paginator = Paginator(configurations, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    return render(
        request,
        "configs/history.html",
        {"page_obj": page_obj, "empty_message": EMPTY_HISTORY_MESSAGE},
    )


@login_required
def download_config(request, config_id: int, format: Literal["zip", "tar"] = "zip"):
    """
    View function to download a configuration archive.
    """
    if format not in ["zip", "tar"]:
        return HttpResponse("404: Invalid format specified", status=400)

    try:
        config = Configuration.objects.get(id=config_id)
    except Configuration.DoesNotExist:
        return HttpResponse("404: Configuration not found", status=404)

    archive_content = models.config_to_archive(config, format)
    filename = f"hermes_cfg_{config_id}.{'tar.gz' if format == 'tar' else 'zip'}"

    response = HttpResponse(archive_content)
    response['Content-Type'] = 'application/zip' if format == "zip" else 'application/x-tar'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    return response
