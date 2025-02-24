"""
FORM TESTS:

* Test file upload form validation including file size constraints
* Test file upload form handling of optional configurations:
  - No files provided
  - Single file provided
  - Partial file sets provided
* Test satellite model selection validation
* Test email submit form validation including CC field formatting
"""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from configs.forms import UploadConfiguration, SubmitConfiguration


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
        partial_files = {"acq": self.valid_files["acq"], "bee": self.valid_files["bee"]}
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

    def test_submit_form_valid_data(self):
        """Test that submit form accepts valid data"""
        form_data = {"subject": "Test Subject", "recipient": "test@example.com", "cc": "cc@example.com"}
        form = SubmitConfiguration(data=form_data)
        self.assertTrue(form.is_valid())

    def test_submit_form_cc_validation(self):
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
            form = SubmitConfiguration(data=form_data)
            self.assertTrue(form.is_valid(), f"Failed for CC: {cc}")

        for cc in invalid_cc_formats:
            form_data = {"subject": "Test Subject", "recipient": "test@example.com", "cc": cc}
            form = SubmitConfiguration(data=form_data)
            self.assertFalse(form.is_valid(), f"Should have failed for CC: {cc}")
            self.assertIn("cc", form.errors)
