import uuid
from pathlib import Path

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, redirect
from django.core.files.storage import FileSystemStorage
from django.contrib.auth.decorators import login_required
from django.http import Http404

from . import forms
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
    if "config_files" not in request.session or "config_model" not in request.session:
        return redirect('configs:new')

    files = {k: Path(v) for k, v in request.session['config_files'].items()}

    results, can_proceed = validators.validate_configuration(
        request.session["config_files"],
        request.session["config_model"],
    )
    # Store for delivery view
    request.session['validation_results'] = results

    # Read file contents for display
    contents = {}
    for fname, fpath in files.items():
        with open(fpath, 'rb') as f:
            contents[fname] = f.read().hex()

    return render(request, 'configs/test.html', {
        'results': results,
        'contents': contents,
        'can_proceed': can_proceed,
    })


@login_required
def deliver(request: HttpRequest) -> HttpResponse:
    raise Http404("Question does not exist")
