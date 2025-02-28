"""
CONFIGURATION VIEWS TESTS:

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
* Test session cleanup after submit
* Test session expiration at logout
* MOC user can't submit configurations

UPLINK TIMESTAMP VIEW TEST:

* Requires authentication
* Valid timestamps go through
* Invalid timestamps don't
* Test against configurations already timestamped, or non existent
* SOC user can't commit uplink time

DOWNLOAD VIEW TEST

* Requires authentication
* Both tars and zip contains all file, and their content match
* Tests against non-existent configuration and wrong formats
"""

from io import BytesIO
from pathlib import Path
import tarfile
from time import sleep
import unittest
import zipfile

from accounts.models import CustomUser
from configs.forms import CommitConfiguration
from configs.forms import UploadConfiguration
from configs.models import Configuration
from configs.validators import Status
from configs.views import decode_config_data
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from hermes import CONFIG_TYPES
from hlink.settings import BASE_DIR


def f2c(file: Path):
    """File to binary string helper"""
    with open(file, "rb") as f:
        return f.read()


class ConfigurationViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = CustomUser.objects.create_user(username="testuser", password="testpass123", gang=CustomUser.Gang.SOC)

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
            reverse("configs:submit"),
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

    @unittest.skip
    def test_upload_view_post_permutation_file_success(self):
        """Testing all remaining combinations of uploads. It's slow."""
        from itertools import combinations

        file_contents = {ftype: self.files_fm6[ftype].read() for ftype in self.files_fm6}

        ftypes = ["acq", "acq0", "asic0", "asic1", "bee", "obs", "liktrg"]
        combs = list([s for r in range(2, 7) for s in combinations(ftypes, r)])
        for comb in combs:
            files = {ftype: SimpleUploadedFile(f"{ftype}.cfg", file_contents[ftype]) for ftype in comb}
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

    def test_submit_view_without_session(self):
        """Test submit view input validation"""
        self.login()
        response = self.client.get(reverse("configs:submit"))
        self.assertRedirects(response, reverse("configs:upload"))

    def test_submit_view_with_valid_session(self):
        _ = self.login_and_upload_fileset("H6", self.files_fm6)
        self.client.get(reverse("configs:test"))
        response = self.client.get(reverse("configs:submit"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "configs/submit.html")

    def test_session_cleanup(self):
        """Test session cleanup after submit"""
        _ = self.login_and_upload_fileset("6", self.files_fm6)
        form_data = {
            "recipient": "recipient@email.com",
            "subject": "Test Subject",
        }
        _ = self.client.post(reverse("configs:submit"), data=form_data)

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

        response = self.client.get(reverse("configs:submit"))
        self.assertRedirects(response, reverse("configs:upload"))

        # uploads good data, then check test and submit are accessible
        _ = self.login_and_upload_fileset("H6", self.files_fm6)
        response = self.client.get(reverse("configs:test"))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse("configs:submit"))
        self.assertEqual(response.status_code, 200)

    def test_hex_encoding_preservation(self):
        """Test that hex encoding preserves binary data exactly"""
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

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_moc_user_cannot_submit(self):
        """MOC user attempting to submit a config is forbidden"""
        user = CustomUser.objects.create_user(username="testuser-moc", password="testpass123", gang=CustomUser.Gang.MOC)
        self.client = Client()
        self.client.login(username="testuser-moc", password="testpass123")

        response = self.client.post(reverse("configs:upload"), data={"model": "H6", **self.files_fm6}, follow=True)
        self.client.get(reverse("configs:test"))
        response = self.client.get(reverse("configs:submit"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "configs/submit.html")
        response = self.client.post(reverse("configs:submit"))
        self.assertEqual(response.status_code, 403)


class UplinkViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Create test user
        cls.user = CustomUser.objects.create_user(username="testuser", password="testpass123", gang=CustomUser.Gang.MOC)

        # Create base configuration data
        cls.valid_config_data = {
            "acq": b"x" * 20,  # 20 bytes as per CONFIG_SIZE
            "acq0": b"x" * 20,
            "asic0": b"x" * 124,
            "asic1": b"x" * 124,
            "bee": b"x" * 64,
        }

        # Create a test configuration
        cls.config = Configuration.objects.create(
            author=cls.user,
            model="H1",
            submitted=True,
            submit_time=timezone.now() - timezone.timedelta(days=1),
            uplinked=False,
            **cls.valid_config_data,
        )
        # work around, otherwise date will be set as per submit time
        cls.config.date = cls.config.submit_time
        cls.config.save()

    def setUp(self):
        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    def test_commit_view_get(self):
        """Test GET request to commit view displays form correctly"""
        response = self.client.get(reverse("configs:commit", args=[self.config.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "configs/commit.html")
        self.assertIsInstance(response.context["form"], CommitConfiguration)
        self.assertEqual(response.context["config"], self.config)

    def test_commit_view_authentication_required(self):
        """Test that commit view requires authentication"""
        self.client.logout()
        response = self.client.get(reverse("configs:commit", args=[self.config.id]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/accounts/login/"))

    def test_commit_view_post_success_fmt(self):
        """Test successful commit with valid uplink time"""
        uplink_time = timezone.now() - timezone.timedelta(hours=12)
        response = self.client.post(
            reverse("configs:commit", args=[self.config.id]),
            {"uplink_time": uplink_time.strftime("%Y-%m-%dT%H:%M:%SZ")},
            follow=True,
        )

        # Check redirect
        self.assertRedirects(response, reverse("configs:history"))

        # Refresh config from db and verify changes
        self.config.refresh_from_db()
        self.assertTrue(self.config.uplinked)
        self.assertIsNotNone(self.config.uplink_time)

    def test_commit_view_invalid_time_format(self):
        """Test commit with invalid time format"""
        for invalid_time_format in [
            "invalid_string",
            (timezone.now() - timezone.timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%S"),
            (timezone.now() - timezone.timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%S[Europe/Rome]"),
            (timezone.now() - timezone.timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M"),
            (timezone.now() - timezone.timedelta(hours=12)).strftime("%Y-%m-%dT%H:%MZ"),
            (timezone.now() - timezone.timedelta(hours=12)).strftime("%Y-%m-%dZ"),
            (timezone.now() - timezone.timedelta(hours=12)).strftime("%Y-%m-%d %H:%MZ"),
        ]:
            response = self.client.post(
                reverse("configs:commit", args=[self.config.id]),
                {"uplink_time": invalid_time_format},
            )
            self.assertEqual(response.status_code, 200)
            self.assertFalse(self.config.uplinked)
            self.assertIsNone(self.config.uplink_time)

    def test_commit_view_time_before_submit(self):
        """Test commit with uplink time before submit time"""
        uplink_time = self.config.submit_time - timezone.timedelta(hours=1)
        response = self.client.post(
            reverse("configs:commit", args=[self.config.id]),
            {"uplink_time": uplink_time.strftime("%Y-%m-%dT%H:%M:%SZ")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.config.uplinked)
        self.assertIsNone(self.config.uplink_time)

    def test_commit_view_time_in_future(self):
        """Test commit with uplink time before submit time"""
        uplink_time = timezone.now() + timezone.timedelta(hours=1)
        response = self.client.post(
            reverse("configs:commit", args=[self.config.id]),
            {"uplink_time": uplink_time.strftime("%Y-%m-%dT%H:%M:%SZ")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.config.uplinked)
        self.assertIsNone(self.config.uplink_time)

    def test_commit_view_nonexistent_config(self):
        """Test accessing commit view with non-existent configuration ID"""
        response = self.client.get(reverse("configs:commit", args=[99999]))
        self.assertEqual(response.status_code, 404)

    def test_commit_view_already_uplinked(self):
        """Test attempting to commit an already uplinked configuration"""
        self.config.uplinked = True
        self.config.uplink_time = timezone.now()
        self.config.save()

        response = self.client.get(reverse("configs:commit", args=[self.config.id]))
        self.assertEqual(response.status_code, 403)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_soc_user_cannot_uplink(self):
        """SOC user attempting to commit a uplink time is forbidden"""
        files_fm6 = {
            "asic1": SimpleUploadedFile(
                name="asic1.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/asic1_FM6_thr105.cfg"),
            ),
        }

        user = CustomUser.objects.create_user(username="testuser-soc", password="testpass123", gang=CustomUser.Gang.SOC)
        self.client = Client()
        self.client.login(username="testuser-soc", password="testpass123")

        response = self.client.post(reverse("configs:upload"), data={"model": "H6", **files_fm6}, follow=True)
        self.client.get(reverse("configs:test"))
        response = self.client.get(reverse("configs:submit"))
        self.assertEqual(response.status_code, 200)

        self.assertTemplateUsed(response, "configs/submit.html")
        response = self.client.post(reverse("configs:submit"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "configs/submit_success.html")

        config = Configuration.objects.last()
        config.submit_time = timezone.now() - timezone.timedelta(hours=1)
        config.save()

        response = self.client.post(
            reverse("configs:commit", args=[config.id]),
            {"uplink_time": timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ")},
            follow=True,
        )
        self.assertEqual(response.status_code, 403)


class DownloadViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = CustomUser.objects.create_user(username="testuser", password="testpass123")

        # Create base configuration data
        cls.config_data = {
            "acq": b"x" * 20,
            "acq0": b"x" * 20,
            "asic0": b"x" * 124,
            "asic1": b"x" * 124,
            "bee": b"x" * 64,
        }

        cls.config = Configuration.objects.create(
            author=cls.user, model="H1", submitted=True, submit_time=timezone.now(), **cls.config_data
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    def test_download_zip_format(self):
        """Test downloading configuration in ZIP format"""
        response = self.client.get(reverse("configs:download", args=[self.config.id, "zip"]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")

        # Verify ZIP content
        with zipfile.ZipFile(BytesIO(response.content)) as zf:
            all_paths = zf.namelist()
            self.assertTrue(len(all_paths) > 0, "ZIP file is empty")
            dirname = Path(all_paths[0]).parent.name

            self.assertTrue(f"{dirname}/ACQ.cfg" in all_paths)
            self.assertTrue(f"{dirname}/ACQ0.cfg" in all_paths)
            self.assertTrue(f"{dirname}/ASIC0.cfg" in all_paths)
            self.assertTrue(f"{dirname}/ASIC1.cfg" in all_paths)
            self.assertTrue(f"{dirname}/BEE.cfg" in all_paths)
            self.assertTrue(f"{dirname}/readme.txt" in all_paths)

            self.assertEqual(zf.read(f"{dirname}/ACQ.cfg"), self.config_data["acq"])
            self.assertEqual(zf.read(f"{dirname}/ASIC0.cfg"), self.config_data["asic0"])

    def test_download_tar_format(self):
        """Test downloading configuration in TAR format"""
        response = self.client.get(reverse("configs:download", args=[self.config.id, "tar"]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/x-tar")

        with tarfile.open(fileobj=BytesIO(response.content), mode="r:gz") as tf:
            names = [Path(fn).name for fn in tf.getnames()]
            self.assertTrue("ACQ.cfg" in names)
            self.assertTrue("ACQ0.cfg" in names)
            self.assertTrue("ASIC0.cfg" in names)
            self.assertTrue("ASIC1.cfg" in names)
            self.assertTrue("BEE.cfg" in names)
            self.assertTrue("readme.txt" in names)

    def test_download_invalid_format(self):
        """Test downloading with invalid format specification"""
        response = self.client.get(reverse("configs:download", args=[self.config.id, "invalid"]))
        self.assertEqual(response.status_code, 400)

    def test_download_nonexistent_config(self):
        """Test downloading non-existent configuration"""
        response = self.client.get(reverse("configs:download", args=[99999, "zip"]))
        self.assertEqual(response.status_code, 404)

    def test_download_authentication_required(self):
        """Test that download view requires authentication"""
        self.client.logout()
        response = self.client.get(reverse("configs:download", args=[self.config.id, "zip"]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/accounts/login/"))


class IndexViewsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = CustomUser.objects.create_user(username="testuser", password="testpass123")

        # Create a few simple configurations for testing
        base_time = timezone.now() - timezone.timedelta(days=5)

        # Create one submitted but not uplinked config
        cls.submitted_config = Configuration.objects.create(
            author=cls.user,
            model="H1",
            submitted=True,
            submit_time=base_time,
            uplinked=False,
            acq=b"x" * 20,
            asic0=b"x" * 124,
        )

        # Create one submitted and uplink config
        cls.uplinked_config = Configuration.objects.create(
            author=cls.user,
            model="H2",
            submitted=True,
            submit_time=base_time - timezone.timedelta(days=1),
            uplinked=True,
            uplink_time=base_time,
            acq=b"x" * 20,
            asic0=b"x" * 124,
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    def test_history_view(self):
        """Test history view displays all configurations"""
        response = self.client.get(reverse("configs:history"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "configs/index.html")

        # Check that all configurations are shown
        self.assertEqual(response.context["page_obj"].paginator.count, 2)

    def test_pending_view(self):
        """Test pending view shows only non-uplinked configurations"""
        response = self.client.get(reverse("configs:pending"))
        self.assertEqual(response.status_code, 200)

        # Verify only non-uplinked configs are shown
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        if response.context["page_obj"]:
            config = response.context["page_obj"][0]
            self.assertEqual(config.id, self.submitted_config.id)
            self.assertFalse(config.uplinked)

    def test_history_view_empty(self):
        """Test history view with no configurations"""
        Configuration.objects.all().delete()
        response = self.client.get(reverse("configs:history"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No configuration has been uplinked yet.")

    def test_pending_view_empty(self):
        """Test pending view with no pending configurations"""
        # Mark all configs as uplinked
        self.submitted_config.uplinked = True
        self.submitted_config.uplink_time = timezone.now()
        self.submitted_config.save()

        response = self.client.get(reverse("configs:pending"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No pending configuration.")

    def test_pending_authentication_required(self):
        """Test that download view requires authentication"""
        self.client.logout()
        response = self.client.get(reverse("configs:pending"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/accounts/login/"))

    def test_history_authentication_required(self):
        """Test that download view requires authentication"""
        self.client.logout()
        response = self.client.get(reverse("configs:history"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/accounts/login/"))
