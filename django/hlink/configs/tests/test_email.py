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
import zipfile
from unittest.mock import patch

from accounts.models import CustomUser
from configs.models import Configuration
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from configs.tasks import EMAIL_HEADER_ERROR
from hermes import STANDARD_FILENAMES
from hlink.settings import BASE_DIR

from hlink import contacts


def f2c(file: Path):
    """File to binary string helper"""
    with open(file, "rb") as f:
        return f.read()


class ConfigurationEmailTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Create test user
        cls.user_soc = CustomUser.objects.create_user(
            username="testuser-soc",
            password="testpass123",
            gang=CustomUser.Gang.SOC,
        )
        cls.user_moc = CustomUser.objects.create_user(
            username="testuser-moc",
            password="testpass123",
            gang=CustomUser.Gang.MOC,
        )
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
        self.client_soc = Client()
        self.client_soc.login(username="testuser-soc", password="testpass123")
        self.client_moc = Client()
        self.client_moc.login(username="testuser-moc", password="testpass123")
        # Clear the test outbox
        mail.outbox = []

    def prepare_submit_session(self):
        """Helper to setup a valid submit session"""
        self.client_soc.post(reverse("configs:upload"), data={"model": "H6", **self.files_fm6}, follow=True)
        response = self.client_soc.get(reverse("configs:test"))

    def prepare_commit_session(self):
        """Helper to setup a valid submit session"""
        self.client_soc.post(reverse("configs:upload"), data={"model": "H6", **self.files_fm6}, follow=True)
        self.client_soc.get(reverse("configs:test"))
        self.client_soc.post(reverse("configs:submit"))
        config = Configuration.objects.filter(model="H6").first()
        past_time = timezone.now() - timezone.timedelta(days=1)
        config.submit_time = past_time
        config.date = past_time
        config.save()
        return config

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_submit_session_sends_right_email(self):
        """Test that email is sent successfully with correct content"""
        self.prepare_submit_session()

        form_data = {
            "cc": "cc1@example.com;",
        }

        response = self.client_soc.post(reverse("configs:submit"), data=form_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "configs/submit_success.html")

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        # check email destinataries
        self.assertEqual(tuple(sorted(email.to)), tuple(sorted([*contacts.EMAILS_MOC])))
        self.assertEqual(
            tuple(sorted(email.cc)),
            tuple(sorted(["cc1@example.com", *(contacts.EMAILS_STAFF - set(email.to))])),
        )

        # check attachments
        self.assertEqual(len(email.attachments), 1)
        with zipfile.ZipFile(BytesIO(email.attachments[0][1])) as zf:
            filenames = [Path(fn).name for fn in zf.namelist()]
        self.assertTrue(all(STANDARD_FILENAMES[ftype] in filenames for ftype in self.files_fm6.keys()))
        self.assertTrue("readme.txt" in filenames)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_submit_with_multiple_cc(self):
        """Test email submit with multiple CC recipients"""
        self.prepare_submit_session()
        form_data = {
            "cc": "cc1@example.com; cc2@example.com",
        }
        response = self.client_soc.post(reverse("configs:submit"), data=form_data)
        self.assertEqual(response.status_code, 200)
        email, *_ = mail.outbox
        # email reach intended recipients
        self.assertEqual(tuple(sorted(email.to)), tuple(sorted([*contacts.EMAILS_MOC])))
        self.assertEqual(
            sorted(email.cc),
            sorted(["cc1@example.com", "cc2@example.com", *(contacts.EMAILS_STAFF - set(email.to))]),
        )
        # no double emails
        self.assertTrue(len(email.to + email.cc) == len(set(email.to + email.cc)))

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_submit_with_overlapping_cc(self):
        """Test """
        self.prepare_submit_session()
        form_data = {
            "cc": [*contacts.EMAILS_STAFF][:1],
        }
        response = self.client_soc.post(reverse("configs:submit"), data=form_data)
        self.assertEqual(response.status_code, 200)
        email, *_ = mail.outbox
        # email reach intended recipients
        self.assertEqual(tuple(sorted(email.to)), tuple(sorted([*contacts.EMAILS_MOC])))
        self.assertEqual(
            sorted(email.cc),
            sorted([*(contacts.EMAILS_STAFF - set(email.to))]),
        )
        # no double emails
        self.assertTrue(len(email.to + email.cc) == len(set(email.to + email.cc)))

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    # this guarantees the ssh behave af it is there, and that we will not check
    # an error email instead of the one confirming script execution
    @patch("configs.tasks.paramiko.SSHClient")
    def test_commit_with_overlapping_cc(self, mock_ssh_client):
        """Test """
        config = self.prepare_commit_session()
        mail.outbox = []
        uplink_time = timezone.now() - timezone.timedelta(minutes=1)
        response = self.client_moc.post(
            reverse("configs:commit", args=[config.id]),
            {"uplink_time": uplink_time.strftime("%Y-%m-%dT%H:%M:%SZ")},
        )
        self.assertTemplateUsed(response, "configs/commit_success.html")

        config.refresh_from_db()
        self.assertEqual(len(mail.outbox), 2)
        email_soc, email_caldb = mail.outbox
        # email reach intended recipients
        self.assertEqual(tuple(sorted(email_soc.to)), tuple(sorted([*contacts.EMAILS_SOC])))
        self.assertEqual(
            sorted(email_soc.cc),
            sorted([*(contacts.EMAILS_STAFF - set(email_soc.to))]),
        )
        # no double emails
        self.assertTrue(len(email_soc.to + email_soc.cc) == len(set(email_soc.to + email_soc.cc)))

        # error email reach intended recipients
        self.assertEqual(tuple(sorted(email_caldb.to)), tuple(sorted([*contacts.EMAILS_STAFF])))
        # we mocking ssh so we expect no error
        self.assertFalse(EMAIL_HEADER_ERROR in email_caldb.subject)
        self.assertEqual(
            sorted(email_caldb.cc),
            sorted([*(contacts.EMAILS_STAFF - set(email_caldb.to))]),
        )
        # no double emails
        self.assertTrue(len(email_caldb.to + email_caldb.cc) == len(set(email_caldb.to + email_caldb.cc)))

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_commit_with_no_ssh_results_in_email_error(self):
        """Test """
        config = self.prepare_commit_session()
        mail.outbox = []
        uplink_time = timezone.now() - timezone.timedelta(minutes=1)
        response = self.client_moc.post(
            reverse("configs:commit", args=[config.id]),
            {"uplink_time": uplink_time.strftime("%Y-%m-%dT%H:%M:%SZ")},
        )
        self.assertTemplateUsed(response, "configs/commit_success.html")

        config.refresh_from_db()
        self.assertEqual(len(mail.outbox), 2)
        email_soc, email_error = mail.outbox

        # email reach intended recipients
        self.assertEqual(tuple(sorted(email_soc.to)), tuple(sorted([*contacts.EMAILS_SOC])))
        self.assertEqual(
            sorted(email_soc.cc),
            sorted([*(contacts.EMAILS_STAFF - set(email_soc.to))]),
        )
        # no double emails
        self.assertTrue(len(email_soc.to + email_soc.cc) == len(set(email_soc.to + email_soc.cc)))
        # ssh is not there, so we should get an error
        self.assertTrue(EMAIL_HEADER_ERROR in email_error.subject)
        # error email reach intended recipients
        self.assertEqual(tuple(sorted(email_error.to)), tuple(sorted([*contacts.EMAILS_STAFF])))
        self.assertEqual(
            sorted(email_error.cc),
            sorted([*(contacts.EMAILS_STAFF - set(email_error.to))]),
        )
        # no double emails
        self.assertTrue(len(email_error.to + email_error.cc) == len(set(email_error.to + email_error.cc)))

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_attachment_content_verification(self):
        """Test that email attachments contain correct file content"""
        self.prepare_submit_session()
        _ = self.client_soc.post(reverse("configs:submit"), data={})
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


    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_partial_config_submit(self):
        """Test submit of partial configuration files"""
        partial_files = {"acq": self.files_fm6["acq"], "bee": self.files_fm6["bee"]}
        self.client_soc.post(reverse("configs:upload"), data={"model": "H6", **partial_files}, follow=True)
        self.client_soc.get(reverse("configs:test"))
        _ = self.client_soc.post(reverse("configs:submit"))

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

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    # this guarantees the ssh behave af it is there, and that we will not check
    # an error email instead of the one confirming script execution
    @patch("configs.tasks.paramiko.SSHClient")
    def test_no_asic1_no_soc_notification_mail(self, mock_ssh_client):
        """Test that configurations without asic1 don't trigger SOC notification emails"""
        # Upload just the acq file (no asic1)
        files_fm6 = {
            "acq": SimpleUploadedFile(
                name="acq.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/acq_FM6.cfg"),
            ),
        }
        self.assertEqual(Configuration.objects.filter(model="H6").count(), 0)

        self.client_soc.post(reverse("configs:upload"), data={"model": "H6", **files_fm6}, follow=True)
        self.client_soc.get(reverse("configs:test"))
        self.assertEqual(Configuration.objects.filter(model="H6").count(), 0)

        response = self.client_soc.post(reverse("configs:submit"))
        config = Configuration.objects.filter(model="H6").first()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

        # email reach intended recipients
        email = mail.outbox[0]
        self.assertEqual(tuple(sorted(email.to)), tuple(sorted([*contacts.EMAILS_MOC])))
        self.assertEqual(
            sorted(email.cc),
            sorted([*(contacts.EMAILS_STAFF - set(email.to))]),
        )
        # no double emails
        self.assertTrue(len(email.to + email.cc) == len(set(email.to + email.cc)))

        # configuration was recorded
        self.assertEqual(Configuration.objects.filter(model="H6").count(), 1)
        self.assertIsNotNone(config)
        self.assertIsNone(config.asic1)

        self.client_soc.logout()
        mail.outbox.clear()

        past_time = timezone.now() - timezone.timedelta(days=1)
        config.submit_time = past_time
        config.date = past_time
        config.save()
        config.refresh_from_db()

        self.client_moc.login(username="testuser-moc", password="testpass123")
        uplink_time = timezone.now() - timezone.timedelta(minutes=1)
        response = self.client_moc.post(
            reverse("configs:commit", args=[config.id]),
            {"uplink_time": uplink_time.strftime("%Y-%m-%dT%H:%M:%SZ")},
        )
        self.assertTemplateUsed(response, "configs/commit_success.html")

        # email reach intended recipients
        email = mail.outbox[0]
        self.assertEqual(tuple(sorted(email.to)), tuple(sorted([*contacts.EMAILS_SOC])))
        self.assertEqual(
            sorted(email.cc),
            sorted([*(contacts.EMAILS_STAFF - set(email.to))]),
        )
        # no double emails
        self.assertTrue(len(email.to + email.cc) == len(set(email.to + email.cc)))

        # configuration was indeed updated
        config.refresh_from_db()
        self.assertTrue(config.uplinked)
        self.assertIsNotNone(config.uplink_time)
        self.assertEqual(len(mail.outbox), 1)
