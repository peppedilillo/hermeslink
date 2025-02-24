"""
EMAIL SUBMIT TESTS:

* Test successful email submit with correct attachments
* Test email content verification
* Test CC field handling
* Test failure handling and rollback
* Test partial configuration submit:
  - Correct archive contents
  - Database record accuracy
  - Email attachment verification
"""

from io import BytesIO
from pathlib import Path
from smtplib import SMTPException
from unittest.mock import patch
import zipfile

from configs.models import Configuration
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse
from hermes import STANDARD_FILENAMES
from hlink.settings import BASE_DIR

User = get_user_model()


def f2c(file: Path):
    """File to binary string helper"""
    with open(file, "rb") as f:
        return f.read()


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

    def prepare_submit_session(self):
        """Helper to setup a valid submit session"""
        _ = self.client.post(reverse("configs:upload"), data={"model": "H6", **self.files_fm6}, follow=True)
        response = self.client.get(reverse("configs:test"))
        return response

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_successful_email_submit(self):
        """Test that email is sent successfully with correct content"""
        self.prepare_submit_session()

        form_data = {
            "recipient": settings.EMAIL_CONFIGS_RECIPIENT,
            "cc": "cc@example.com",
        }

        response = self.client.post(reverse("configs:submit"), data=form_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "configs/submit_success.html")

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        # Verify email content
        self.assertEqual(email.to, [settings.EMAIL_CONFIGS_RECIPIENT])
        self.assertEqual(email.cc, ["cc@example.com"])

        # Verify attachments
        self.assertEqual(len(email.attachments), 1)
        with zipfile.ZipFile(BytesIO(email.attachments[0][1])) as zf:
            filenames = [Path(fn).name for fn in zf.namelist()]
        self.assertTrue(all(STANDARD_FILENAMES[ftype] in filenames for ftype in self.files_fm6.keys()))
        self.assertTrue("readme.txt" in filenames)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_submit_with_multiple_cc(self):
        """Test email submit with multiple CC recipients"""
        self.prepare_submit_session()
        form_data = {
            "recipient": settings.EMAIL_CONFIGS_RECIPIENT,
            "cc": "cc1@example.com; cc2@example.com",
        }
        response = self.client.post(reverse("configs:submit"), data=form_data)
        self.assertEqual(response.status_code, 200)
        email, *_ = mail.outbox
        self.assertEqual(email.cc, ["cc1@example.com", "cc2@example.com"])

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_failure_rollback(self):
        """Test that database changes are rolled back if email fails"""
        self.prepare_submit_session()
        with patch("django.core.mail.EmailMessage.send", side_effect=SMTPException("SMTP Error")):
            response = self.client.post(reverse("configs:submit"), data={})

            self.assertTemplateUsed(response, "configs/submit_error.html")
            self.assertEqual(Configuration.objects.count(), 0)
            # session should still be valid
            self.assertIn("config_model", self.client.session)
            self.assertIn("config_data", self.client.session)
            self.assertIn("config_hash", self.client.session)
            self.assertIn("test_status", self.client.session)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_attachment_content_verification(self):
        """Test that email attachments contain correct file content"""
        self.prepare_submit_session()
        _ = self.client.post(reverse("configs:submit"), data={})
        email, *_ = mail.outbox
        self.assertEqual(len(email.attachments), 1)
        with zipfile.ZipFile(BytesIO(email.attachments[0][1])) as zf:
            filenames = [*filter(lambda fn: not fn.stem == "readme", [Path(fn) for fn in zf.namelist()])]
            self.assertTrue(any(filenames))
            for filename in filenames:
                ftype = filename.stem.lower()
                content = zf.read(str(filename))
                original_file = self.files_fm6[ftype].open().read()
                self.assertEqual(content, original_file)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_submit_database_record(self):
        """Test that successful submit creates correct database record"""
        self.prepare_submit_session()
        self.client.post(reverse("configs:submit"))

        config = Configuration.objects.last()
        self.assertIsNotNone(config)
        self.assertTrue(config.submitted)
        self.assertIsNotNone(config.submit_time)
        self.assertEqual(config.model, "H6")
        self.assertEqual(config.author, self.user)

        # Verify file contents
        for file_type in ["acq", "acq0", "asic0", "asic1", "bee"]:
            original_file = self.files_fm6[file_type]
            original_file.seek(0)
            self.assertEqual(getattr(config, file_type), original_file.read())

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_partial_config_submit(self):
        """Test submit of partial configuration files"""
        partial_files = {"acq": self.files_fm6["acq"], "bee": self.files_fm6["bee"]}
        self.client.post(reverse("configs:upload"), data={"model": "H6", **partial_files}, follow=True)
        self.client.get(reverse("configs:test"))
        _ = self.client.post(reverse("configs:submit"))

        # email attachment contains only uploaded files
        email = mail.outbox[0]
        with zipfile.ZipFile(BytesIO(email.attachments[0][1])) as zf:
            filenames = {*filter(lambda fn: not fn == "readme.txt", [Path(fn).name for fn in zf.namelist()])}
            self.assertEqual(filenames, {STANDARD_FILENAMES["acq"], STANDARD_FILENAMES["bee"]})

        # check database record
        config = Configuration.objects.last()
        self.assertIsNotNone(getattr(config, "acq"))
        self.assertIsNotNone(getattr(config, "bee"))
        self.assertIsNone(getattr(config, "acq0"))
        self.assertIsNone(getattr(config, "asic0"))
        self.assertIsNone(getattr(config, "asic1"))
