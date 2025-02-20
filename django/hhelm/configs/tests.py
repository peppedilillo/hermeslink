"""
Tests for `configs` application.

MODEL TESTS:
* Test that a configuration can be created with valid data
* Test that binary data is preserved correctly when stored and retrieved
* Test that only valid satellite model choices (H1-H6) are accepted
* Test that binary fields enforce exact size constraints
* Test that at least one configuration file must be provided
* Test that configurations are protected from author deletion via foreign key constraints
* Test that creation timestamp is automatically assigned
* Test that delivery and upload flags default to False with null timestamps
* Test that delivery and upload timestamps can be properly set and retrieved
* Test that partial configurations can be created and stored

FORM TESTS:
* Test file upload form validation including file size constraints
* Test file upload form handling of optional configurations:
  - No files provided
  - Single file provided
  - Partial file sets provided
* Test satellite model selection validation
* Test email delivery form validation including CC field formatting

VIEWS TESTS:
* Test authentication requirements for all views
* Test view access and template usage
* Test successful file upload flow and session data creation:
  - Complete configuration sets
  - Single configuration files
  - Various combinations of configuration files
* Test session data handling and validation:
  - Missing session data
  - Invalid session data format
  - Hex encoding/decoding preservation
  - Configuration data order preservation
* Test configuration validation:
  - Well-formed configurations
  - Mismatched ASIC configurations
  - Wrong ASIC0/ASIC1 configurations
* Test file content preservation throughout the process
* Test session cleanup after delivery
* Test session expiration at logout

EMAIL DELIVERY TESTS:
* Test successful email delivery with correct attachments
* Test email content verification
* Test CC field handling
* Test failure handling and rollback
* Test partial configuration delivery:
  - Correct archive contents
  - Database record accuracy
  - Email attachment verification
"""

from io import BytesIO
from pathlib import Path
import shutil
from smtplib import SMTPException
import tempfile
from unittest.mock import patch
import zipfile

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import ProtectedError
from django.test import Client
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from hermes import CONFIG_TYPES, STANDARD_FILENAMES
from hhelm.settings import BASE_DIR

from .forms import DeliverConfiguration
from .forms import UploadConfiguration
from .models import Configuration
from .validators import Status

User = get_user_model()


class ConfigurationModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.test_user = User.objects.create_user(username="testuser", password="testpass123")

        cls.valid_len_acq_data = 20  # bytes
        cls.valid_len_asic_data = 124
        cls.valid_len_bee_data = 64
        cls.valid_len_obs_data = 5
        cls.valid_len_liktrg_data = 38
        cls.valid_models = ("H1", "H2", "H3", "H4", "H5", "H6")

        cls.valid_length_data = {
            "acq": b"x" * cls.valid_len_acq_data,
            "acq0": b"x" * cls.valid_len_acq_data,
            "asic0": b"x" * cls.valid_len_asic_data,
            "asic1": b"x" * cls.valid_len_asic_data,
            "bee": b"x" * cls.valid_len_bee_data,
            "obs": b"x" * cls.valid_len_obs_data,
            "liktrg": b"x" * cls.valid_len_liktrg_data,
        }

        cls.valid_config = Configuration.objects.create(
            author=cls.test_user,
            model="H1",  # H1
            acq=b"x" * cls.valid_len_acq_data,
            acq0=b"x" * cls.valid_len_acq_data,
            asic0=b"x" * cls.valid_len_asic_data,
            asic1=b"x" * cls.valid_len_asic_data,
            bee=b"x" * cls.valid_len_bee_data,
            obs=b"x" * cls.valid_len_obs_data,
            liktrg=b"x" * cls.valid_len_liktrg_data,
        )

    def test_configuration_creation(self):
        """Test that a configuration can be created with valid data"""
        self.assertTrue(isinstance(self.valid_config, Configuration))

    def test_binary_field_preservation(self):
        """Test that binary data is preserved correctly"""
        config = Configuration.objects.get(id=self.valid_config.id)
        self.assertEqual(config.acq, self.valid_length_data["acq"])
        self.assertEqual(config.acq0, self.valid_length_data["acq0"])
        self.assertEqual(config.asic0, self.valid_length_data["asic0"])
        self.assertEqual(config.asic1, self.valid_length_data["asic1"])
        self.assertEqual(config.bee, self.valid_length_data["bee"])
        self.assertEqual(config.obs, self.valid_length_data["obs"])
        self.assertEqual(config.liktrg, self.valid_length_data["liktrg"])

    def test_model_choices_validation(self):
        """Test that only valid model choices are accepted"""
        for model in self.valid_models:
            config = Configuration(
                author=self.test_user,
                model=model,
                **self.valid_length_data,
            )
            config.full_clean()

        with self.assertRaises(ValidationError):
            config = Configuration(
                author=self.test_user,
                model="7",  # Invalid model number
                **self.valid_length_data,
            )
            config.full_clean()

    def test_binary_field_size_validation(self):
        """Test that binary fields enforce size constraints"""
        invalid_sizes = {
            "acq": b"x" * 21,  # Too large
            "acq0": b"x" * 19,  # Too small
            "asic0": b"x" * 125,  # Too large
            "asic1": b"x" * 123,  # Too small
            "bee": b"x" * 65,  # Too large
            "obs": b"x" * 37,  # Too large
            "liktrg": b"x" * 4,  # Too large
        }
        valid_sizes = {k: v for k, v in self.valid_length_data.items()}

        for field, invalid_data in invalid_sizes.items():
            sizes = {k: v for k, v in valid_sizes.items()}
            sizes[field] = invalid_data
            with self.assertRaises(ValidationError):
                config = Configuration(author=self.test_user, model="H1", **invalid_sizes)
                config.full_clean()

    def test_author_protection(self):
        """Test that deleting a user doesn't delete their configurations"""
        with self.assertRaises(ProtectedError):
            self.test_user.delete()

    def test_timestamp_auto_assignment(self):
        """Test that date is automatically assigned on creation"""
        self.assertIsNotNone(self.valid_config.date)
        self.assertTrue(isinstance(self.valid_config.date, timezone.datetime))

    def test_default_flags(self):
        """Test that delivered and uploaded flags default to False"""
        self.assertFalse(self.valid_config.delivered)
        self.assertFalse(self.valid_config.uploaded)
        self.assertIsNone(self.valid_config.upload_time)
        self.assertIsNone(self.valid_config.deliver_time)

    def test_time_assignment(self):
        """Test upload_time field assignment"""
        upload_time = timezone.now()
        deliver_time = upload_time - timezone.timedelta(hours=1)

        self.valid_config.deliver_time = deliver_time
        self.valid_config.delivered = True
        self.valid_config.upload_time = upload_time
        self.valid_config.uploaded = True
        self.valid_config.save()

        self.valid_config.refresh_from_db()
        self.assertEqual(self.valid_config.upload_time, upload_time)
        self.assertEqual(self.valid_config.deliver_time, deliver_time)

    def test_configuration_creation_with_partial_data(self):
        """Test that a configuration can be created with only some config files"""
        partial_config = Configuration.objects.create(
            author=self.test_user,
            model="H1",
            acq=b"x" * self.valid_len_acq_data,
            bee=b"x" * self.valid_len_bee_data,
        )
        self.assertTrue(isinstance(partial_config, Configuration))

    def test_clean_validation_requires_at_least_one_config(self):
        """Test that at least one configuration file must be provided"""
        with self.assertRaises(ValidationError):
            config = Configuration(
                author=self.test_user,
                model="H1",
            )
            config.full_clean()

    def test_deliver_time_requires_delivered_flag(self):
        """Test that a configuration with non-null deliver_time must have delivered=True"""
        config = Configuration(
            author=self.test_user,
            model="H1",
            acq=b"x" * self.valid_len_acq_data,
            deliver_time=timezone.now(),
            delivered=False  # This violates the constraint
        )
        with self.assertRaises(ValidationError):
            config.full_clean()

        # Fix the constraint violation
        config.delivered = True
        config.full_clean()  # Should not raise an exception

    def test_upload_time_requires_uploaded_flag(self):
        """Test that a configuration with non-null upload_time must have uploaded=True"""
        config = Configuration(
            author=self.test_user,
            model="H1",
            acq=b"x" * self.valid_len_acq_data,
            upload_time=timezone.now(),
            uploaded=False,  # This violates the constraint
        )
        with self.assertRaises(ValidationError):
            config.full_clean()

        # Fix the constraint violation
        config.delivered = True
        config.uploaded = True
        config.full_clean()  # Should not raise an exception

    def test_uploaded_implies_delivered(self):
        config = Configuration(
            author=self.test_user,
            model="H1",
            acq=b"x" * self.valid_len_acq_data,
            upload_time=None,
            uploaded=False,
            delivered=True,
            deliver_time=timezone.now(),
        )
        config.full_clean()


    def test_upload_time_after_deliver_time(self):
        """Test that upload_time must be later than deliver_time if both exist"""
        test_time = timezone.now()

        # Case 1: deliver_time is earlier than upload_time
        config = Configuration(
            author=self.test_user,
            model="H1",
            acq=b"x" * self.valid_len_acq_data,
            deliver_time=test_time,
            delivered=True,
            upload_time=test_time + timezone.timedelta(hours=1),
            uploaded=True,
        )
        with self.assertRaises(ValidationError):
            config.full_clean()

        # Case 2: deliver_time equals upload_time
        config.deliver_time = test_time
        config.upload_time = test_time
        with self.assertRaises(ValidationError):
            config.full_clean()

        # Case 3: deliver_time is later than upload_time (valid)
        config.deliver_time = test_time
        config.upload_time = test_time - timezone.timedelta(hours=2)
        with self.assertRaises(ValidationError):
            config.full_clean()

        # note for the next test the flags are still set
        self.assertTrue(config.uploaded)
        self.assertTrue(config.delivered)

        # Case 4: Only deliver_time is set (valid)
        config.upload_time = None
        config.full_clean()  # Should not raise an exception

        # Case 5: Only upload_time is set (valid)
        config.deliver_time = None
        config.upload_time = test_time
        config.full_clean()  # Should not raise an exception

        # Case 6: Neither time is set (valid)
        config.deliver_time = None
        config.upload_time = None
        config.full_clean()  # Should not raise an exception


class ConfigurationFormTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.valid_len_acq_data = 20  # bytes
        cls.valid_len_asic_data = 124
        cls.valid_len_bee_data = 64
        cls.valid_len_obs_data = 5
        cls.valid_len_liktrg_data = 38

        cls.valid_files = {
            "acq": SimpleUploadedFile("acq.cfg", b"x" * cls.valid_len_acq_data),
            "acq0": SimpleUploadedFile("acq0.cfg", b"x" * cls.valid_len_acq_data),
            "asic0": SimpleUploadedFile("asic0.cfg", b"x" * cls.valid_len_asic_data),
            "asic1": SimpleUploadedFile("asic1.cfg", b"x" * cls.valid_len_asic_data),
            "bee": SimpleUploadedFile("bee.cfg", b"x" * cls.valid_len_bee_data),
            "obs": SimpleUploadedFile("obs.cfg", b"x" * cls.valid_len_obs_data),
            "liktrg": SimpleUploadedFile("liktrg.par", b"x" * cls.valid_len_liktrg_data),
        }

    def test_upload_form_valid_data(self):
        """Test that form accepts valid data"""
        form_data = {"model": "H1"}
        form = UploadConfiguration(data=form_data, files=self.valid_files)
        self.assertTrue(form.is_valid())

    def test_upload_form_no_files(self):
        """Test that form rejects submission with no configuration files"""
        form_data = {"model": "H1"}
        form = UploadConfiguration(data=form_data, files={})
        self.assertFalse(form.is_valid())

    def test_upload_form_partial_data(self):
        """Test that form accepts partial configuration files"""
        form_data = {"model": "H1"}
        partial_files = {
            "acq": self.valid_files["acq"],
            "bee": self.valid_files["bee"]
        }
        form = UploadConfiguration(data=form_data, files=partial_files)
        self.assertTrue(form.is_valid())

    def test_upload_form_file_size_validation(self):
        """Test file size validation for each config type"""
        invalid_sizes = {
            "acq": self.valid_len_acq_data + 1,
            "acq0": self.valid_len_acq_data - 1,
            "asic0": self.valid_len_asic_data + 1,
            "asic1": self.valid_len_asic_data - 1,
            "bee": self.valid_len_bee_data + 1,
            "obs": self.valid_len_obs_data + 1,
            "liktrg": self.valid_len_liktrg_data + 1,
        }

        for field, size in invalid_sizes.items():
            files = self.valid_files.copy()
            files[field] = SimpleUploadedFile(f"{field}.cfg", b"x" * size)

            form_data = {"model": "H1"}
            form = UploadConfiguration(data=form_data, files=files)
            self.assertFalse(form.is_valid())
            self.assertIn(field, form.errors)

    def test_upload_form_model_validation(self):
        """Test model choice validation"""
        for model in ["H7", "1", "kurdosesso"]:
            form_data = {"model": model}  # Invalid model
            form = UploadConfiguration(data=form_data, files=self.valid_files)
            self.assertFalse(form.is_valid())
            self.assertIn("model", form.errors)

    def test_deliver_form_valid_data(self):
        """Test that delivery form accepts valid data"""
        form_data = {"subject": "Test Subject", "recipient": "test@example.com", "cc": "cc@example.com"}
        form = DeliverConfiguration(data=form_data)
        self.assertTrue(form.is_valid())

    def test_deliver_form_cc_validation(self):
        """Test CC field validation with various formats"""
        valid_cc_formats = [
            "test@example.com",
            "test@example.com; another@example.com",
            "test@example.com;another@example.com",
            "test@example.com; another@example.com;",  # Trailing semicolon
        ]

        invalid_cc_formats = [
            "not-an-email",
            "test@example.com; not-an-email",
            "test@example.com;;another@example.com",  # Double semicolon
            "@example.com",
        ]

        for cc in valid_cc_formats:
            form_data = {"subject": "Test Subject", "recipient": "test@example.com", "cc": cc}
            form = DeliverConfiguration(data=form_data)
            self.assertTrue(form.is_valid(), f"Failed for CC: {cc}")

        for cc in invalid_cc_formats:
            form_data = {"subject": "Test Subject", "recipient": "test@example.com", "cc": cc}
            form = DeliverConfiguration(data=form_data)
            self.assertFalse(form.is_valid(), f"Should have failed for CC: {cc}")
            self.assertIn("cc", form.errors)

    def test_deliver_form_subject_validation(self):
        """Test subject field validation"""
        # Test empty subject
        form_data = {
            "recipient": "test@example.com",
            "subject": "",
        }
        form = DeliverConfiguration(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("subject", form.errors)

        # Test whitespace-only subject
        form_data["subject"] = "   "
        form = DeliverConfiguration(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("subject", form.errors)


def f2c(file: Path):
    """File to binary string helper"""
    with open(file, "rb") as f:
        return f.read()


class ConfigurationViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="testuser", password="testpass123")

        cls.valid_len_acq_data = 20  # bytes
        cls.valid_len_asic_data = 124
        cls.valid_len_bee_data = 64
        cls.valid_len_obs_data = 5
        cls.valid_len_liktrg_data = 38

        cls.files_dummy_valid_length = {
            "acq": SimpleUploadedFile("ACQ.cfg", b"x" * cls.valid_len_acq_data),
            "acq0": SimpleUploadedFile("ACQ0.cfg", b"x" * cls.valid_len_acq_data),
            "asic0": SimpleUploadedFile("ASIC0.cfg", b"x" * cls.valid_len_asic_data),
            "asic1": SimpleUploadedFile("ASIC1.cfg", b"x" * cls.valid_len_asic_data),
            "bee": SimpleUploadedFile("BEE.cfg", b"x" * cls.valid_len_bee_data),
            "obs": SimpleUploadedFile("OBS.cfg", b"x" * cls.valid_len_obs_data),
            "liktrg": SimpleUploadedFile("LIKTRG.par", b"x" * cls.valid_len_liktrg_data),
        }

        cls.files_dummy_wrong_length = {
            "acq": SimpleUploadedFile("ACQ.cfg", b"x" * (cls.valid_len_acq_data + 1)),
            "acq0": SimpleUploadedFile("ACQ.cfg", b"x" * (cls.valid_len_acq_data - 1)),
            "asic0": SimpleUploadedFile("ASIC0.cfg", b"x" * (cls.valid_len_asic_data + 1)),
            "asic1": SimpleUploadedFile("ASIC1.cfg", b"x" * (cls.valid_len_asic_data - 1)),
            "bee": SimpleUploadedFile("BEE.cfg", b"x" * (cls.valid_len_bee_data + 1)),
            "obs": SimpleUploadedFile("OBS.cfg", b"x" * (cls.valid_len_obs_data + 1)),
            "liktrg": SimpleUploadedFile("LIKTRG.par", b"x" * (cls.valid_len_liktrg_data + 1)),
        }

        cls.files_fm6 = {
            "acq": SimpleUploadedFile(
                name="acq.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/acq_FM6.cfg"),
            ),
            "acq0": SimpleUploadedFile(
                name="acq0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/acq0_FM6.cfg"),
            ),
            "asic0": SimpleUploadedFile(
                name="asic0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/asic0_FM6.cfg"),
            ),
            "asic1": SimpleUploadedFile(
                name="asic1.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/asic1_FM6_thr105.cfg"),
            ),
            "bee": SimpleUploadedFile(
                name="bee.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/BEE_FM6.cfg"),
            ),
            "obs": SimpleUploadedFile(
                name="obs.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/obs.cfg"),
            ),
            "liktrg": SimpleUploadedFile(
                name="liktrg.par",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/liktrg.par"),
            ),
        }

        cls.files_fm2 = {
            "acq": SimpleUploadedFile(
                name="acq.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/acq_FM2.cfg"),
            ),
            "acq0": SimpleUploadedFile(
                name="acq0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/acq0_FM2.cfg"),
            ),
            "asic0": SimpleUploadedFile(
                name="asic0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/asic0_FM2.cfg"),
            ),
            "asic1": SimpleUploadedFile(
                name="asic1.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/asic1_FM2_thr105.cfg"),
            ),
            "bee": SimpleUploadedFile(
                name="bee.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/BEE_FM2.cfg"),
            ),
            "obs": SimpleUploadedFile(
                name="obs.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/obs.cfg"),
            ),
            "liktrg": SimpleUploadedFile(
                name="liktrg.par",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/liktrg.par"),
            ),
        }

        cls.files_fm1 = {
            "acq": SimpleUploadedFile(
                name="acq.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm1/acq_FM1.cfg"),
            ),
            "acq0": SimpleUploadedFile(
                name="acq0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm1/acq0_FM1.cfg"),
            ),
            "asic0": SimpleUploadedFile(
                name="asic0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm1/asic0_FM1.cfg"),
            ),
            "asic1": SimpleUploadedFile(
                name="asic1.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm1/asic1_FM1_thr105.cfg"),
            ),
            "bee": SimpleUploadedFile(
                name="bee.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm1/BEE_FM1.cfg"),
            ),
        }

        cls.files_wrong_asic1 = {
            "acq": SimpleUploadedFile(
                name="acq.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/acq_FM6.cfg"),
            ),
            "acq0": SimpleUploadedFile(
                name="acq0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/acq0_FM6.cfg"),
            ),
            "asic0": SimpleUploadedFile(
                name="asic0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/asic0_FM6.cfg"),
            ),
            "asic1": SimpleUploadedFile(  # Using asic0 content for asic1
                name="asic1.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/asic0_FM6.cfg"),
            ),
            "bee": SimpleUploadedFile(
                name="bee.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/BEE_FM6.cfg"),
            ),
            "obs": SimpleUploadedFile(
                name="obs.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/obs.cfg"),
            ),
            "liktrg": SimpleUploadedFile(
                name="liktrg.par",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/liktrg.par"),
            ),
        }

        cls.files_wrong_asic0 = {
            "acq": SimpleUploadedFile(
                name="acq.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/acq_FM2.cfg"),
            ),
            "acq0": SimpleUploadedFile(
                name="acq0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/acq0_FM2.cfg"),
            ),
            "asic0": SimpleUploadedFile(
                name="asic0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/asic1_FM2_thr105.cfg"),
            ),
            "asic1": SimpleUploadedFile(  # Using asic1 content for asic0
                name="asic1.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/asic1_FM2_thr105.cfg"),
            ),
            "bee": SimpleUploadedFile(
                name="bee.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/BEE_FM2.cfg"),
            ),
            "obs": SimpleUploadedFile(
                name="obs.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/obs.cfg"),
            ),
            "liktrg": SimpleUploadedFile(
                name="liktrg.par",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/liktrg.par"),
            ),
        }

    def setUp(self):
        # Create a new client for each test
        self.client = Client()

        # Create a temporary directory for uploads
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir)

    def login(self):
        """Helper method to login test user"""
        self.client.login(username="testuser", password="testpass123")

    def login_and_upload_fileset(self, model: str, files: dict):
        """Helper method to perform a valid file upload"""
        self.login()
        response = self.client.post(reverse("configs:upload"), data={"model": model, **files}, follow=True)
        return response

    def test_authentication_required(self):
        """Test that all views require authentication"""
        urls = [
            reverse("configs:upload"),
            reverse("configs:test"),
            reverse("configs:deliver"),
        ]

        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith("/accounts/login/"))

    def test_upload_view_get(self):
        """Test GET request to upload view"""
        self.login()
        response = self.client.get(reverse("configs:upload"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "configs/upload.html")
        self.assertIsInstance(response.context["form"], UploadConfiguration)

    def test_upload_view_post_success(self):
        """Test successful file upload"""
        response = self.login_and_upload_fileset("H6", self.files_fm6)
        self.assertRedirects(response, reverse("configs:test"))

        self.assertIn("config_model", self.client.session)
        self.assertIn("config_data", self.client.session)
        self.assertIn("config_hash", self.client.session)

    def test_upload_view_post_single_file_success(self):
        """Test successful file upload"""
        for ftype in ["acq", "acq0", "asic0", "asic1", "bee", "obs", "liktrg"]:
            response = self.login_and_upload_fileset("H6", {ftype: self.files_fm6[ftype]})
            self.assertRedirects(response, reverse("configs:test"))

            self.assertIn("config_model", self.client.session)
            self.assertIn("config_data", self.client.session)
            self.assertIn("config_hash", self.client.session)

    def test_upload_view_post_permutation_file_success(self):
        """Testing all remaining combinations of uploads. Kinda slow."""
        from itertools import combinations

        file_contents = {
            ftype: self.files_fm6[ftype].read()
            for ftype in self.files_fm6
        }

        ftypes = ["acq", "acq0", "asic0", "asic1", "bee", "obs", "liktrg"]
        combs = list([s for r in range(2, 7) for s in combinations(ftypes, r)])
        for comb in combs:
            files = {
                ftype: SimpleUploadedFile(
                    f"{ftype}.cfg",
                    file_contents[ftype]
                ) for ftype in comb
            }
            response = self.login_and_upload_fileset("H6", files)
            self.assertRedirects(response, reverse("configs:test"))

            self.assertIn("config_model", self.client.session)
            self.assertIn("config_data", self.client.session)
            self.assertIn("config_hash", self.client.session)

    def test_upload_view_post_error(self):
        """Test not going further when uploading files with wrong size"""
        response = self.login_and_upload_fileset("6", self.files_dummy_wrong_length)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "configs/upload.html")
        # TODO: add test for proper error display

    def test_test_view_without_session(self):
        """Test accessing test view without required session data"""
        self.login()
        response = self.client.get(reverse("configs:test"))
        self.assertRedirects(response, reverse("configs:upload"))

    def test_test_view_with_valid_session(self):
        """Test test view with valid context data"""
        self.login_and_upload_fileset("H2", self.files_fm2)

        response = self.client.get(reverse("configs:test"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "configs/test.html")

        self.assertIn("results", response.context)

    def test_test_session_data_persistence(self):
        """Test that session data persists correctly through the workflow"""
        _ = self.login_and_upload_fileset("H6", self.files_fm6)
        session_data = {
            "config_model": self.client.session["config_model"],
            "config_data": self.client.session["config_data"],
            "config_hash": self.client.session["config_hash"],
        }

        _ = self.client.get(reverse("configs:test"))
        for key, value in session_data.items():
            self.assertEqual(self.client.session[key], value)

    def test_test_view_pass_matching_data_fm6(self):
        """Test test view does not report warning and error for a well-formed configuration"""
        self.login_and_upload_fileset("H6", self.files_fm6)

        response = self.client.get(reverse("configs:test"))
        test_result = self.client.session["test_status"]
        self.assertTrue(test_result == Status.PASSED)

    def test_test_view_pass_matching_data_fm2(self):
        """Test test view does not report warning and error for a well-formed configuration"""
        self.login_and_upload_fileset("H2", self.files_fm2)

        response = self.client.get(reverse("configs:test"))
        test_result = self.client.session["test_status"]
        self.assertTrue(test_result == Status.PASSED)

    def test_test_view_warns_mismatched_data(self):
        """Test test view reports on mismatch asic1"""
        files_mixed_up = self.files_fm6.copy()
        files_mixed_up["asic1"] = self.files_fm2["asic1"]

        self.login_and_upload_fileset("H6", files_mixed_up)
        response = self.client.get(reverse("configs:test"))
        test_result = self.client.session["test_status"]
        self.assertTrue(test_result == Status.WARNING)

    def test_test_view_warns_wrong_asic1_data(self):
        """Test test view reports on asic0 given in place of asic1"""
        # i'm creating a new dataset for this because reading through a
        # file will consume it and i want to read the same file twice.
        self.login_and_upload_fileset("H6", self.files_wrong_asic1)
        response = self.client.get(reverse("configs:test"))
        test_result = self.client.session["test_status"]
        self.assertTrue(test_result == Status.WARNING)

    def test_test_view_warns_wrong_asic0_data(self):
        """Test test view reports on asic1 given in place of asic0"""
        # i'm creating a new dataset for this because reading through a
        # file will consume it and i want to read the same file twice.
        self.login_and_upload_fileset("H2", self.files_wrong_asic0)
        response = self.client.get(reverse("configs:test"))
        test_result = self.client.session["test_status"]
        self.assertTrue(test_result == Status.WARNING)

    def test_deliver_view_without_session(self):
        """Test deliver view input validation"""
        self.login()
        response = self.client.get(reverse("configs:deliver"))
        self.assertRedirects(response, reverse("configs:upload"))

    def test_deliver_view_with_valid_session(self):
        _ = self.login_and_upload_fileset("H6", self.files_fm6)
        self.client.get(reverse("configs:test"))
        response = self.client.get(reverse("configs:deliver"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "configs/deliver.html")

    def test_session_cleanup(self):
        """Test session cleanup after delivery"""
        from hhelm.settings import EMAIL_CONFIGS_RECIPIENT

        _ = self.login_and_upload_fileset("6", self.files_fm6)
        form_data = {
            "recipient": EMAIL_CONFIGS_RECIPIENT,
            "subject": "Test Subject",
        }
        _ = self.client.post(reverse("configs:deliver"), data=form_data)

        self.assertNotIn("config_model", self.client.session)
        self.assertNotIn("config_data", self.client.session)
        self.assertNotIn("config_hash", self.client.session)

    def test_session_expires_at_logout(self):
        """Test handling of session at logout"""
        _ = self.login_and_upload_fileset("6", self.files_fm6)

        self.client.session.flush()

        response = self.client.get(reverse("configs:test"))
        self.assertRedirects(response, "/accounts/login/?next=/configs/test/")

    def test_invalid_session_data(self):
        """Test handling of corrupted session data"""
        self.login()

        session = self.client.session
        session["config_data"] = {"invalid_key": "invalid_data"}  # Wrong structure
        session["config_hash"] = "invalid_hash"
        session["config_model"] = "invalid-model"
        session.save()

        response = self.client.get(reverse("configs:test"))
        self.assertRedirects(response, reverse("configs:upload"))

    def test_partial_session_data(self):
        """Test handling of partial session data"""
        self.login()

        session = self.client.session
        session["config_model"] = "H2"
        session.save()

        response = self.client.get(reverse("configs:test"))
        self.assertRedirects(response, reverse("configs:upload"))

    def test_navigation_flow(self):
        """Test proper navigation flow enforcement"""
        self.login()

        # redirection to upload if no data was uploaded
        response = self.client.get(reverse("configs:test"))
        self.assertRedirects(response, reverse("configs:upload"))

        response = self.client.get(reverse("configs:deliver"))
        self.assertRedirects(response, reverse("configs:upload"))

        # uploads good data, then check test and deliver are accessible
        _ = self.login_and_upload_fileset("H6", self.files_fm6)
        response = self.client.get(reverse("configs:test"))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse("configs:deliver"))
        self.assertEqual(response.status_code, 200)

    def test_hex_encoding_preservation(self):
        """Test that hex encoding preserves binary data exactly"""
        from .views import decode_config_data

        self.login_and_upload_fileset("H6", self.files_fm6)

        session_data = self.client.session["config_data"]
        decoded_data = decode_config_data(session_data)

        for field, original_file in self.files_fm6.items():
            original_file.seek(0)
            self.assertEqual(decoded_data[field], original_file.read())

    def test_config_data_order_preservation(self):
        """Test that configuration data order is preserved through encoding/decoding"""
        self.login_and_upload_fileset("H6", self.files_fm6)

        session_data = self.client.session["config_data"]
        self.assertEqual(tuple(session_data.keys()), CONFIG_TYPES)


class ConfigurationEmailTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Create test user
        cls.user = User.objects.create_user(username="testuser", password="testpass123")

        # Setup test files - using real configuration files for proper validation
        cls.files_fm6 = {
            "acq": SimpleUploadedFile(
                name="acq.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/acq_FM6.cfg"),
            ),
            "acq0": SimpleUploadedFile(
                name="acq0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/acq0_FM6.cfg"),
            ),
            "asic0": SimpleUploadedFile(
                name="asic0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/asic0_FM6.cfg"),
            ),
            "asic1": SimpleUploadedFile(
                name="asic1.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/asic1_FM6_thr105.cfg"),
            ),
            "bee": SimpleUploadedFile(
                name="bee.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/BEE_FM6.cfg"),
            ),
        }

    def setUp(self):
        self.client = Client()
        self.client.login(username="testuser", password="testpass123")
        # Clear the test outbox
        mail.outbox = []

    def prepare_delivery_session(self):
        """Helper to setup a valid delivery session"""
        response = self.client.post(reverse("configs:upload"), data={"model": "H6", **self.files_fm6}, follow=True)
        response = self.client.get(reverse("configs:test"))
        return response

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_successful_email_delivery(self):
        """Test that email is sent successfully with correct content"""
        self.prepare_delivery_session()

        form_data = {
            "recipient": settings.EMAIL_CONFIGS_RECIPIENT,
            "subject": "Test Configuration Delivery",
            "cc": "cc@example.com",
        }

        response = self.client.post(reverse("configs:deliver"), data=form_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "configs/deliver_success.html")

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        # Verify email content
        self.assertEqual(email.subject, "Test Configuration Delivery")
        self.assertEqual(email.to, [settings.EMAIL_CONFIGS_RECIPIENT])
        self.assertEqual(email.cc, ["cc@example.com"])

        # Verify attachments
        self.assertEqual(len(email.attachments), 1)
        with zipfile.ZipFile(BytesIO(email.attachments[0][1])) as zf:
            filenames = zf.namelist()
        self.assertTrue(all(STANDARD_FILENAMES[ftype] in filenames for ftype in ["acq", "acq0", "asic0", "asic1", "bee"]))

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_delivery_with_multiple_cc(self):
        """Test email delivery with multiple CC recipients"""
        self.prepare_delivery_session()

        form_data = {
            "recipient": settings.EMAIL_CONFIGS_RECIPIENT,
            "subject": "Test Configuration Delivery",
            "cc": "cc1@example.com; cc2@example.com",
        }

        response = self.client.post(reverse("configs:deliver"), data=form_data)
        self.assertEqual(response.status_code, 200)

        email = mail.outbox[0]
        self.assertEqual(email.cc, ["cc1@example.com", "cc2@example.com"])

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_failure_rollback(self):
        """Test that database changes are rolled back if email fails"""
        self.prepare_delivery_session()

        form_data = {
            "recipient": settings.EMAIL_CONFIGS_RECIPIENT,
            "subject": "Test Configuration Delivery",
        }

        with patch("django.core.mail.EmailMessage.send", side_effect=SMTPException("SMTP Error")):
            response = self.client.post(reverse("configs:deliver"), data=form_data)

            self.assertTemplateUsed(response, "configs/deliver_error.html")

            self.assertEqual(Configuration.objects.count(), 0)

            # Session should still be valid
            self.assertIn("config_model", self.client.session)
            self.assertIn("config_data", self.client.session)
            self.assertIn("config_hash", self.client.session)
            self.assertIn("test_status", self.client.session)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_attachment_content_verification(self):
        """Test that email attachments contain correct file content"""
        self.prepare_delivery_session()

        form_data = {
            "recipient": settings.EMAIL_CONFIGS_RECIPIENT,
            "subject": "Test Configuration Delivery",
        }

        response = self.client.post(reverse("configs:deliver"), data=form_data)
        email = mail.outbox[0]
        self.assertEqual(len(email.attachments), 1)
        with zipfile.ZipFile(BytesIO(email.attachments[0][1])) as zf:
            filenames = zf.namelist()
            filenames = [*filter(lambda fn: not fn.startswith("readme"), filenames)]
            self.assertTrue(any(filenames))
            for filename in filenames:
                ftype = filename.split(".")[0].lower()
                content = zf.read(filename)
                original_file = self.files_fm6[ftype].open().read()
                self.assertEqual(content, original_file)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_delivery_database_record(self):
        """Test that successful delivery creates correct database record"""
        self.prepare_delivery_session()

        form_data = {
            "recipient": settings.EMAIL_CONFIGS_RECIPIENT,
            "subject": "Test Configuration Delivery",
        }

        self.client.post(reverse("configs:deliver"), data=form_data)

        # Verify configuration record
        config = Configuration.objects.last()
        self.assertIsNotNone(config)
        self.assertTrue(config.delivered)
        self.assertIsNotNone(config.deliver_time)
        self.assertEqual(config.model, "H6")
        self.assertEqual(config.author, self.user)

        # Verify file contents
        for file_type in ["acq", "acq0", "asic0", "asic1", "bee"]:
            original_file = self.files_fm6[file_type]
            original_file.seek(0)
            self.assertEqual(getattr(config, file_type), original_file.read())

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_partial_config_delivery(self):
        """Test delivery of partial configuration files"""
        partial_files = {
            "acq": self.files_fm6["acq"],
            "bee": self.files_fm6["bee"]
        }
        self.client.post(reverse("configs:upload"),
                         data={"model": "H6", **partial_files},
                         follow=True)
        self.client.get(reverse("configs:test"))

        form_data = {
            "recipient": settings.EMAIL_CONFIGS_RECIPIENT,
            "subject": "Test Partial Configuration",
        }
        response = self.client.post(reverse("configs:deliver"), data=form_data)

        # email attachment contains only uploaded files
        email = mail.outbox[0]
        with zipfile.ZipFile(BytesIO(email.attachments[0][1])) as zf:
            filenames = set(fn for fn in zf.namelist() if not fn.startswith("readme"))
            self.assertEqual(filenames, {STANDARD_FILENAMES["acq"], STANDARD_FILENAMES["bee"]})

        # check database record
        config = Configuration.objects.last()
        self.assertIsNotNone(getattr(config, "acq"))
        self.assertIsNotNone(getattr(config, "bee"))
        self.assertIsNone(getattr(config, "acq0"))
        self.assertIsNone(getattr(config, "asic0"))
        self.assertIsNone(getattr(config, "asic1"))