from collections import OrderedDict
from functools import partial
from hashlib import sha256
import logging
from typing import Literal

from accounts.models import CustomUser
from configs import forms
import configs.downloads
from configs.models import config_to_sha256
from configs.models import Configuration
from configs.reports import write_test_report_html
from configs.tasks import email_config_to_moc
from configs.tasks import ssh_update_caldb
from configs.validators import Status
from configs.validators import validate_configurations
from django.contrib.auth.decorators import login_required
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import redirect
from django.shortcuts import render
from hermes import CONFIG_TYPES
from hermes import SPACECRAFTS_NAMES
from hlink.contacts import EMAILS_ADMIN

logger = logging.getLogger("hlink")


# in this module we will deal with OrderedDict for mantaining the configuration file data.
# this choice is driven by the need of an unambiguous order to keep track of the sha256, which we
# computed on the concatenated files.
def encode_config_data(config_data: OrderedDict[str, bytes]) -> dict[str, str]:
    """Encodes binary configuration data for session storage using hex"""
    return OrderedDict((ftype, content.hex()) for ftype, content in config_data.items())


def decode_config_data(encoded_data: OrderedDict[str, str]) -> dict[str, bytes]:
    """Decodes hex-encoded configuration data from session storage"""
    return OrderedDict((ftype, bytes.fromhex(content)) for ftype, content in encoded_data.items())


@login_required
def upload(request: HttpRequest) -> HttpResponse:
    """
    This view is intended to accept configuration files for a target model from the user,
    store them in memory and move the user to the next view.
    """
    if request.method == "POST":
        form = forms.UploadConfiguration(request.POST, request.FILES)
        # form will perform file size validation
        if form.is_valid():
            hasher = sha256()
            config_data = OrderedDict()

            # we compute a hash as we first cycle through the uploaded files
            for ftype in CONFIG_TYPES:
                if form.cleaned_data.get(ftype) is not None:
                    content = form.cleaned_data[ftype].read()
                    config_data[ftype] = content
                    hasher.update(content)

            request.session["config_data"] = encode_config_data(config_data)
            request.session["config_hash"] = hasher.hexdigest()
            request.session["config_model"] = form.cleaned_data["model"]
            return redirect("configs:test")
        return render(request, "configs/upload.html", {"form": form})

    form = forms.UploadConfiguration()
    return render(request, "configs/upload.html", {"form": form})


def validate_config_model(model: Literal[*SPACECRAFTS_NAMES]) -> bool:
    """Checks config model to be allowed"""
    model_keys, _ = zip(*Configuration.MODELS)
    return model in model_keys


# TODO: consider if worth to give this check more depth
def validate_config_data(config_data: dict[str, str]):
    """Verifies that at least one configuration file is present in the data."""
    return any(config_data)


def session_is_valid(request: HttpRequest) -> bool:
    """
    Checks hash to be present, model to be well set and all files to be online.
    """
    if (
        ("config_model" in request.session and validate_config_model(request.session["config_model"]))
        and ("config_data" in request.session and validate_config_data(request.session["config_data"]))
        and ("config_hash" in request.session)
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

    # we sanity check the configuration file content
    results = validate_configurations(
        decode_config_data(request.session["config_data"]),
        request.session["config_model"],
    )

    test_status = Status.PASSED
    for result in [r for k, v in results.items() for r in v]:
        if result.status == Status.ERROR:
            test_status = Status.ERROR
            break
        elif result.status == Status.WARNING:
            test_status = Status.WARNING

    request.session["test_status"] = test_status
    return render(
        request,
        "configs/test.html",
        {
            "results": write_test_report_html(results, request.session["config_data"]),
        },
    )


class HashError(Exception):
    """Inconsitent configuration hashes"""


@login_required
def submit(request: HttpRequest) -> HttpResponse:
    """
    This view asks user to submit the configuration to the recipient, as defined
    in `settings.EMAIL_CONFIGS_RECIPIENT`. On POST, it sends the email, then records
    the configuration to the database. If an error is encountered, the user is
    taken to an error page, else a success page is shown.
    """

    def create_and_check_configuration():
        """Record submitted configuration to db."""
        config_data = decode_config_data(request.session["config_data"])

        config_entry = Configuration(
            author=request.user,
            submitted=False,
            submit_time=None,
            uplinked=False,
            uplink_time=None,
            model=request.session["config_model"],
        )
        for ftype, content in config_data.items():
            setattr(config_entry, ftype, content)

        record_hash, _ = config_to_sha256(
            config_entry,
            ordered_keys=config_data.keys(),
        )
        if request.session["config_hash"] != record_hash:
            raise HashError("Input file hash does not match configuration record.")
        return config_entry

    def cleanup():
        """Cleans up session data."""
        for key in ["config_data", "config_hash", "config_model", "test_status"]:
            request.session.pop(key, None)

    if not session_is_valid(request) or "test_status" not in request.session:
        return redirect("configs:upload")

    if request.session["test_status"] == Status.ERROR:
        return redirect("configs:test")

    if request.method == "POST":
        if request.user.gang != CustomUser.Gang.SOC and not request.user.is_staff:
            raise PermissionDenied

        form = forms.SubmitConfiguration(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    config = create_and_check_configuration()
                    config.save()
                    cleanup()

                email_config_to_moc.delay(
                    config_id=config.id,
                    cc=form.cleaned_data["cc"],
                    domain=get_current_site(request).domain,
                    protocol="https" if request.is_secure() else "http",
                )

            except HashError as e:
                logger.error(f"Integrity error: {str(e)}")
                return render(
                    request,
                    "configs/submit_error.html",
                    {
                        "error": "Compromised input integrity.",
                        "contact_admin": ", ".join(EMAILS_ADMIN),
                    },
                )
            except Exception as e:
                logger.error(f"Unexpected error submitting email: {str(e)}")
                return render(
                    request,
                    "configs/submit_error.html",
                    {
                        "error": "An unexpected error occurred.",
                        "contact_admin": ", ".join(EMAILS_ADMIN),
                    },
                )
            logger.info(f"A new configuration with id {config.id} was submitted by user {request.user.username}.")
            return render(request, "configs/submit_success.html")

    form = forms.SubmitConfiguration()
    return render(
        request,
        "configs/submit.html",
        {"form": form},
    )


@login_required
def _index(
    request: HttpRequest,
    order_by: tuple[str],
    filter_by: dict,
    header: str,
    empty_message: str,
) -> HttpResponse:
    """
    View to display all recorded configurations.
    """
    configurations = Configuration.objects.filter(**filter_by).order_by(*order_by)
    paginator = Paginator(configurations, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    return render(
        request,
        "configs/index.html",
        {
            "page_obj": page_obj,
            "empty_message": empty_message,
            "header": header,
        },
    )


history = partial(
    _index,
    header="History",
    filter_by={},
    order_by=("-date",),
    empty_message="No configuration has been uplinked yet.",
)
pending = partial(
    _index,
    header="Pending",
    filter_by={"uplinked": False},
    order_by=("-date",),
    empty_message="No pending configuration.",
)


@login_required
def download(request, config_id: int, format: Literal["zip", "tar"] = "zip"):
    """
    View function to download a configuration archive.
    """
    if format not in ["zip", "tar"]:
        return HttpResponse("400: Invalid format specified", status=400)

    try:
        config = Configuration.objects.get(pk=config_id)
    except Configuration.DoesNotExist:
        return HttpResponse("404: Configuration not found", status=404)

    archive_content = configs.downloads.write_archive(config, format)
    filename = f"{config.filestring()}.{'tar.gz' if format == 'tar' else 'zip'}"

    response = HttpResponse(archive_content)
    response["Content-Type"] = "application/zip" if format == "zip" else "application/x-tar"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response


@login_required
def commit(request, config_id: int):
    try:
        config = Configuration.objects.get(pk=config_id)
    except Configuration.DoesNotExist:
        return HttpResponse("404: Configuration not found", status=404)

    if config.uplinked:
        return HttpResponse("403: Configuration has already been committed", status=403)

    if request.method == "POST":
        if request.user.gang != CustomUser.Gang.MOC and not request.user.is_staff:
            raise PermissionDenied

        form = forms.CommitConfiguration(request.POST, instance=config)
        if form.is_valid():
            try:
                config.uplinked = True
                config.uplinked_by = request.user
                config.uplink_time = form.cleaned_data["uplink_time"]
                form.save()
            except Exception as e:
                logger.error(f"Unexpected error committing uplink time: {str(e)}")
                return render(request, "configs/commit_error.html", context={"contact_admin": ", ".join(EMAILS_ADMIN)})

            if config.asic1 is not None:
                ssh_update_caldb.delay(config_id=config_id)
            logger.info(f"An uplink time has been committed for configuration {config.id} by {request.user.username}.")
            return render(request, "configs/commit_success.html", context={"asic1": config.asic1 is not None})
    else:
        form = forms.CommitConfiguration(instance=config)

    return render(
        request,
        "configs/commit.html",
        {
            "form": form,
            "config": config,
        },
    )
