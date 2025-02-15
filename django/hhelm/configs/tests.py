"""
Tests for `configs` application.

MODEL TESTS:
* Test that a configuration can be created with valid data
* Test that binary data is preserved correctly when stored and retrieved
* Test that only valid satellite model choices (H1-H6) are accepted
* Test that binary fields enforce exact size constraints (ACQ: 20 bytes, ASIC: 124 bytes, BEE: 64 bytes)
* Test that configurations are protected from author deletion via foreign key constraints
* Test that creation timestamp is automatically assigned
* Test that delivery and upload flags default to False with null timestamps
* Test that delivery and upload timestamps can be properly set and retrieved

FORM TESTS:
* Test file upload form validation including file size constraints
* Test satellite model selection validation
* Test email delivery form validation including CC field formatting

VIEWS TESTS:
* Test authentication requirements for all views
* Test view access and template usage
* Test successful file upload flow and session data creation
* Test handling of files with wrong sizes
* Test navigation flow and access restrictions
* Test session data handling:
  - Missing session data
  - Invalid session data
  - Partial session data
  - Session timeout
  - Session data persistence
  - Concurrent sessions
* Test configuration validation:
  - Well-formed configurations
  - Mismatched ASIC configurations
  - Wrong ASIC0/ASIC1 configurations
* Test file content preservation throughout the process
* Test session cleanup after delivery

EMAIL DELIVERY TESTS:
* Test successful email delivery with correct attachments
* Test email content verification
* Test CC field handling
* Test failure handling and rollback

FILE SYSTEM TESTS:
* Test that files are cleaned up after delivery
* Test that files are preserved on delivery failure
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch
from smtplib import SMTPException

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.conf import settings

from hhelm.settings import BASE_DIR
from .models import Configuration
from .forms import UploadConfiguration, DeliverConfiguration


User = get_user_model()


class ConfigurationModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.test_user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

        cls.valid_len_acq_data = 20  # 20 bytes
        cls.valid_len_asic_data = 124  # 124 bytes
        cls.valid_len_bee_data = 64  # 64 bytes
        cls.valid_models = ("H1", "H2", "H3", "H4", "H5", "H6")

        cls.valid_length_data = {
            "acq" : b'x' * cls.valid_len_acq_data,
            "acq0" : b'x' * cls.valid_len_acq_data,
            "asic0" : b'x' * cls.valid_len_asic_data,
            "asic1" : b'x' * cls.valid_len_asic_data,
            "bee" : b'x' * cls.valid_len_bee_data,
        }

        cls.valid_config = Configuration.objects.create(
            author=cls.test_user,
            model='1',  # H1
            acq=b'x' * cls.valid_len_acq_data,
            acq0=b'x' * cls.valid_len_acq_data,
            asic0=b'x' * cls.valid_len_asic_data,
            asic1=b'x' * cls.valid_len_asic_data,
            bee=b'x' * cls.valid_len_bee_data,
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
                model='7',  # Invalid model number
                **self.valid_length_data,
            )
            config.full_clean()

    def test_binary_field_size_validation(self):
        """Test that binary fields enforce size constraints"""
        invalid_sizes = {
            'acq': b'x' * 21,  # Too large
            'acq0': b'x' * 19,  # Too small
            'asic0': b'x' * 125,  # Too large
            'asic1': b'x' * 123,  # Too small
            'bee': b'x' * 65,  # Too large
        }
        valid_sizes = {k: v for k, v in self.valid_length_data.items()}

        for field, invalid_data in invalid_sizes.items():
            sizes = {k: v for k, v in valid_sizes.items()}
            sizes[field] = invalid_data
            with self.assertRaises(ValidationError):
                config = Configuration(
                    author=self.test_user,
                    model='1',
                    **invalid_sizes
                )
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
        test_time = timezone.now()
        self.valid_config.upload_time = test_time
        self.valid_config.deliver_time = test_time
        self.valid_config.save()

        self.valid_config.refresh_from_db()
        self.assertEqual(self.valid_config.upload_time, test_time)
        self.assertEqual(self.valid_config.deliver_time, test_time)


class ConfigurationFormTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.valid_len_acq_data = 20
        cls.valid_len_asic_data = 124
        cls.valid_len_bee_data = 64

        cls.valid_files = {
            'acq': SimpleUploadedFile(
                'acq.bin',
                b'x' * cls.valid_len_acq_data
            ),
            'acq0': SimpleUploadedFile(
                'acq0.bin',
                b'x' * cls.valid_len_acq_data
            ),
            'asic0': SimpleUploadedFile(
                'asic0.bin',
                b'x' * cls.valid_len_asic_data
            ),
            'asic1': SimpleUploadedFile(
                'asic1.bin',
                b'x' * cls.valid_len_asic_data
            ),
            'bee': SimpleUploadedFile(
                'bee.bin',
                b'x' * cls.valid_len_bee_data
            ),
        }

    def test_upload_form_valid_data(self):
        """Test that form accepts valid data"""
        form_data = {'model': 'H1'}
        form = UploadConfiguration(data=form_data, files=self.valid_files)
        self.assertTrue(form.is_valid())

    def test_upload_form_file_size_validation(self):
        """Test file size validation for each config type"""
        invalid_sizes = {
            'acq': self.valid_len_acq_data + 1,
            'acq0': self.valid_len_acq_data - 1,
            'asic0': self.valid_len_asic_data + 1,
            'asic1': self.valid_len_asic_data - 1,
            'bee': self.valid_len_bee_data + 1,
        }

        for field, size in invalid_sizes.items():
            files = self.valid_files.copy()
            files[field] = SimpleUploadedFile(
                f'{field}.cfg',
                b'x' * size
            )

            form_data = {'model': '1'}
            form = UploadConfiguration(data=form_data, files=files)
            self.assertFalse(form.is_valid())
            self.assertIn(field, form.errors)

    def test_upload_form_model_validation(self):
        """Test model choice validation"""
        form_data = {'model': 'H7'}  # Invalid model
        form = UploadConfiguration(data=form_data, files=self.valid_files)
        self.assertFalse(form.is_valid())
        self.assertIn('model', form.errors)

    def test_deliver_form_valid_data(self):
        """Test that delivery form accepts valid data"""
        form_data = {
            'subject': 'Test Subject',
            'recipient': 'test@example.com',
            'cc': 'cc@example.com'
        }
        form = DeliverConfiguration(data=form_data)
        self.assertTrue(form.is_valid())

    def test_deliver_form_cc_validation(self):
        """Test CC field validation with various formats"""
        valid_cc_formats = [
            'test@example.com',
            'test@example.com; another@example.com',
            'test@example.com;another@example.com',
            'test@example.com; another@example.com;',  # Trailing semicolon
        ]

        invalid_cc_formats = [
            'not-an-email',
            'test@example.com; not-an-email',
            'test@example.com;;another@example.com',  # Double semicolon
            '@example.com',
        ]

        for cc in valid_cc_formats:
            form_data = {
                'subject': 'Test Subject',
                'recipient': 'test@example.com',
                'cc': cc
            }
            form = DeliverConfiguration(data=form_data)
            self.assertTrue(form.is_valid(), f"Failed for CC: {cc}")

        for cc in invalid_cc_formats:
            form_data = {
                'subject': 'Test Subject',
                'recipient': 'test@example.com',
                'cc': cc
            }
            form = DeliverConfiguration(data=form_data)
            self.assertFalse(form.is_valid(), f"Should have failed for CC: {cc}")
            self.assertIn('cc', form.errors)

    def test_deliver_form_subject_validation(self):
        """Test subject field validation"""
        # Test empty subject
        form_data = {
            'recipient': 'test@example.com',
            'subject': '',
        }
        form = DeliverConfiguration(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('subject', form.errors)

        # Test whitespace-only subject
        form_data['subject'] = '   '
        form = DeliverConfiguration(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('subject', form.errors)


def f2c(file: Path):
    """File to binary string helper"""
    with open(file, 'rb') as f:
        return f.read()


class ConfigurationViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

        cls.valid_len_acq_data = 20
        cls.valid_len_asic_data = 124
        cls.valid_len_bee_data = 64

        cls.files_dummy_valid_length = {
            'acq': SimpleUploadedFile(
                'acq.bin',
                b'x' * cls.valid_len_acq_data
            ),
            'acq0': SimpleUploadedFile(
                'acq0.bin',
                b'x' * cls.valid_len_acq_data
            ),
            'asic0': SimpleUploadedFile(
                'asic0.bin',
                b'x' * cls.valid_len_asic_data
            ),
            'asic1': SimpleUploadedFile(
                'asic1.bin',
                b'x' * cls.valid_len_asic_data
            ),
            'bee': SimpleUploadedFile(
                'bee.bin',
                b'x' * cls.valid_len_bee_data
            ),
        }

        cls.files_dummy_wrong_length = {
            'acq': SimpleUploadedFile(
                'acq.bin',
                b'x' * (cls.valid_len_acq_data + 1)
            ),
            'acq0': SimpleUploadedFile(
                'acq0.bin',
                b'x' * (cls.valid_len_acq_data - 1)
            ),
            'asic0': SimpleUploadedFile(
                'asic0.bin',
                b'x' * (cls.valid_len_asic_data + 1)
            ),
            'asic1': SimpleUploadedFile(
                'asic1.bin',
                b'x' * (cls.valid_len_asic_data - 1)
            ),
            'bee': SimpleUploadedFile(
                'bee.bin',
                b'x' * (cls.valid_len_bee_data + 1)
            ),
        }

        cls.files_fm6 = {
            'acq': SimpleUploadedFile(
                name="acq.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/acq_FM6.cfg"),
            ),
            'acq0': SimpleUploadedFile(
                name="acq0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/acq0_FM6.cfg"),
            ),
            'asic0': SimpleUploadedFile(
                name="asic0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/asic0_FM6.cfg"),
            ),
            'asic1': SimpleUploadedFile(
                name="asic1.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/asic1_FM6_thr105.cfg"),
            ),
            'bee': SimpleUploadedFile(
                name="bee.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/BEE_FM6.cfg"),
            ),
        }

        cls.files_fm2 = {
            'acq': SimpleUploadedFile(
                name="acq.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/acq_FM2.cfg"),
            ),
            'acq0': SimpleUploadedFile(
                name="acq0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/acq0_FM2.cfg"),
            ),
            'asic0': SimpleUploadedFile(
                name="asic0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/asic0_FM2.cfg"),
            ),
            'asic1': SimpleUploadedFile(
                name="asic1.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/asic1_FM2_thr105.cfg"),
            ),
            'bee': SimpleUploadedFile(
                name="bee.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/BEE_FM2.cfg"),
            ),
        }

        cls.files_fm1 = {
            'acq': SimpleUploadedFile(
                name="acq.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm1/acq_FM1.cfg"),
            ),
            'acq0': SimpleUploadedFile(
                name="acq0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm1/acq0_FM1.cfg"),
            ),
            'asic0': SimpleUploadedFile(
                name="asic0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm1/asic0_FM1.cfg"),
            ),
            'asic1': SimpleUploadedFile(
                name="asic1.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm1/asic1_FM1_thr105.cfg"),
            ),
            'bee': SimpleUploadedFile(
                name="bee.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm1/BEE_FM1.cfg"),
            ),
        }

        cls.files_wrong_asic1 = {
            'acq': SimpleUploadedFile(
                name="acq.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/acq_FM6.cfg"),
            ),
            'acq0': SimpleUploadedFile(
                name="acq0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/acq0_FM6.cfg"),
            ),
            'asic0': SimpleUploadedFile(
                name="asic0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/asic0_FM6.cfg"),
            ),
            'asic1': SimpleUploadedFile(  # Using asic0 content for asic1
                name="asic1.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/asic0_FM6.cfg"),
            ),
            'bee': SimpleUploadedFile(
                name="bee.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/BEE_FM6.cfg"),
            ),
        }

        cls.files_wrong_asic0 = {
            'acq': SimpleUploadedFile(
                name="acq.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/acq_FM2.cfg"),
            ),
            'acq0': SimpleUploadedFile(
                name="acq0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/acq0_FM2.cfg"),
            ),
            'asic0': SimpleUploadedFile(
                name="asic0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/asic1_FM2_thr105.cfg"),
            ),
            'asic1': SimpleUploadedFile(  # Using asic1 content for asic0
                name="asic1.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/asic1_FM2_thr105.cfg"),
            ),
            'bee': SimpleUploadedFile(
                name="bee.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm2/BEE_FM2.cfg"),
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
        self.client.login(username='testuser', password='testpass123')

    def login_and_upload_fileset(self, model: str, files: dict):
        """Helper method to perform a valid file upload"""
        self.login()
        response = self.client.post(
            reverse('configs:upload'),
            data={"model": model, **files},
            follow=True
        )
        return response

    def test_authentication_required(self):
        """Test that all views require authentication"""
        urls = [
            reverse('configs:upload'),
            reverse('configs:test'),
            reverse('configs:deliver'),
        ]

        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith('/accounts/login/'))

    def test_upload_view_get(self):
        """Test GET request to upload view"""
        self.login()
        response = self.client.get(reverse('configs:upload'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'configs/upload.html')
        self.assertIsInstance(response.context['form'], UploadConfiguration)

    def test_upload_view_post_success(self):
        """Test successful file upload"""
        response = self.login_and_upload_fileset('H6', self.files_fm6)
        self.assertRedirects(response, reverse('configs:test'))

        self.assertIn('config_id', self.client.session)
        self.assertIn('config_hash', self.client.session)
        self.assertIn('config_model', self.client.session)

    def test_upload_view_post_error(self):
        """Test not going further when uploading files with wrong size"""
        response = self.login_and_upload_fileset('6', self.files_dummy_wrong_length)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'configs/upload.html')
        # TODO: add test for proper error display

    def test_test_view_without_session(self):
        """Test accessing test view without required session data"""
        self.login()
        response = self.client.get(reverse('configs:test'))
        self.assertRedirects(response, reverse('configs:upload'))

    def test_test_view_with_valid_session(self):
        """Test test view with valid context data"""
        self.login_and_upload_fileset('H2', self.files_fm2)

        response = self.client.get(reverse('configs:test'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'configs/test.html')

        self.assertIn('results', response.context)
        self.assertIn('contents', response.context)
        self.assertIn('can_proceed', response.context)

    def test_test_session_data_persistence(self):
        """Test that session data persists correctly through the workflow"""
        _ = self.login_and_upload_fileset('H6', self.files_fm6)
        session_data = {
            'config_id': self.client.session['config_id'],
            'config_hash': self.client.session['config_hash'],
            'config_model': self.client.session['config_model']
        }

        _ = self.client.get(reverse('configs:test'))
        for key, value in session_data.items():
            self.assertEqual(self.client.session[key], value)

    def test_concurrent_sessions(self):
        """Test handling of concurrent sessions"""
        client1 = Client()
        client2 = Client()

        client1.login(username='testuser', password='testpass123')
        client2.login(username='testuser', password='testpass123')

        form_data = {'model': 'H6'}
        _ = client1.post(
            reverse('configs:upload'),
            data={**form_data, **self.files_fm6},
            follow=True
        )
        _ = client2.post(
            reverse('configs:upload'),
            data={**form_data, **self.files_fm6},
            follow=True
        )

        self.assertNotEqual(
            client1.session.get('config_id'),
            client2.session.get('config_id')
        )

    def test_test_view_pass_matching_data_fm6(self):
        """Test test view does not report warning and error for a well-formed configuration"""
        self.login_and_upload_fileset('H6', self.files_fm6)

        response = self.client.get(reverse('configs:test'))
        results = response.context['results']
        self.assertFalse(any(
            test['status'] == 'WARNING'
            for file_tests in results.values()
            for test in file_tests
        ))
        self.assertFalse(any(
            test['status'] == 'ERROR'
            for file_tests in results.values()
            for test in file_tests
        ))

    def test_test_view_pass_matching_data_fm2(self):
        """Test test view does not report warning and error for a well-formed configuration"""
        self.login_and_upload_fileset('H2', self.files_fm2)

        response = self.client.get(reverse('configs:test'))
        results = response.context['results']
        self.assertFalse(any(
            test['status'] == 'WARNING'
            for file_tests in results.values()
            for test in file_tests
        ))
        self.assertFalse(any(
            test['status'] == 'ERROR'
            for file_tests in results.values()
            for test in file_tests
        ))

    def test_test_view_warns_mismatched_data(self):
        """Test test view reports on mismatch asic1"""
        files_mixed_up = self.files_fm6.copy()
        files_mixed_up["asic1"] = self.files_fm2["asic1"]

        self.login_and_upload_fileset('H6', files_mixed_up)
        response = self.client.get(reverse('configs:test'))
        results = response.context['results']

        self.assertTrue(any(
            test['status'] == 'WARNING'
            for file_tests in results.values()
            for test in file_tests
        ))

    def test_test_view_warns_wrong_asic1_data(self):
        """Test test view reports on asic0 given in place of asic1"""
        # i'm creating a new dataset for this because reading through a
        # file will consume it and i want to read the same file twice.
        self.login_and_upload_fileset('H6', self.files_wrong_asic1)
        response = self.client.get(reverse('configs:test'))
        results = response.context['results']

        self.assertTrue(any(
            test['status'] == 'WARNING'
            for file_tests in results.values()
            for test in file_tests
        ))

    def test_test_view_warns_wrong_asic0_data(self):
        """Test test view reports on asic1 given in place of asic0"""
        # i'm creating a new dataset for this because reading through a
        # file will consume it and i want to read the same file twice.
        self.login_and_upload_fileset('H2', self.files_wrong_asic0)
        response = self.client.get(reverse('configs:test'))
        results = response.context['results']

        self.assertTrue(any(
            test['status'] == 'WARNING'
            for file_tests in results.values()
            for test in file_tests
        ))

    def test_deliver_view_without_session(self):
        """Test deliver view input validation"""
        self.login()
        response = self.client.get(reverse('configs:deliver'))
        self.assertRedirects(response, reverse('configs:upload'))

    def test_deliver_view_with_valid_session(self):
        _ = self.login_and_upload_fileset('H6', self.files_fm6)
        self.client.get(reverse('configs:test'))
        response = self.client.get(reverse('configs:deliver'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'configs/deliver.html')

    def test_session_cleanup(self):
        """Test session cleanup after delivery"""
        from hhelm.settings import EMAIL_CONFIGS_RECIPIENT

        _ = self.login_and_upload_fileset('6', self.files_fm6)
        form_data = {
            'recipient': EMAIL_CONFIGS_RECIPIENT,
            'subject': 'Test Subject',
        }
        _ = self.client.post(reverse('configs:deliver'), data=form_data)

        self.assertNotIn('config_id', self.client.session)
        self.assertNotIn('config_hash', self.client.session)
        self.assertNotIn('config_model', self.client.session)

    def test_file_content_preservation(self):
        """Test that file content is preserved throughout the process"""
        _ = self.login_and_upload_fileset('H6', self.files_fm6)

        response = self.client.get(reverse('configs:test'))
        contents = response.context['contents']

        for field, original_file in self.files_fm6.items():
            original_file.seek(0)
            original_content = original_file.read().hex()
            self.assertEqual(contents[field], original_content)

    def test_session_timeout(self):
        """Test handling of session timeout"""
        _ = self.login_and_upload_fileset('6', self.files_fm6)

        self.client.session.flush()

        response = self.client.get(reverse('configs:test'))
        self.assertRedirects(response, '/accounts/login/?next=/configs/test/')

    # TODO: This test should succeed but at moment, it doesn't. Fix it.
    def test_invalid_session_data(self):
        """Test handling of corrupted session data"""
        self.login()

        session = self.client.session
        session['config_id'] = 'invalid-id'
        session['config_hash'] = 'invalid-hash'
        session['config_model'] = 'invalid-model'
        session.save()

        response = self.client.get(reverse('configs:test'))
        self.assertRedirects(response, reverse('configs:upload'))

    def test_partial_session_data(self):
        """Test handling of partial session data"""
        self.login()

        session = self.client.session
        session['config_id'] = 'test-id'
        session.save()

        response = self.client.get(reverse('configs:test'))
        self.assertRedirects(response, reverse('configs:upload'))

    def test_navigation_flow(self):
        """Test proper navigation flow enforcement"""
        self.login()

        response = self.client.get(reverse('configs:test'))
        self.assertRedirects(response, reverse('configs:upload'))

        response = self.client.get(reverse('configs:deliver'))
        self.assertRedirects(response, reverse('configs:upload'))

        _ = self.login_and_upload_fileset('H6', self.files_fm6)
        response = self.client.get(reverse('configs:test'))
        self.assertEqual(response.status_code, 200)

        session = self.client.session
        session['can_proceed'] = True
        session.save()

        # Can access deliver
        response = self.client.get(reverse('configs:deliver'))
        self.assertEqual(response.status_code, 200)


class ConfigurationEmailTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Create test user
        cls.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

        # Setup test files - using real configuration files for proper validation
        cls.files_fm6 = {
            'acq': SimpleUploadedFile(
                name="acq.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/acq_FM6.cfg"),
            ),
            'acq0': SimpleUploadedFile(
                name="acq0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/acq0_FM6.cfg"),
            ),
            'asic0': SimpleUploadedFile(
                name="asic0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/asic0_FM6.cfg"),
            ),
            'asic1': SimpleUploadedFile(
                name="asic1.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/asic1_FM6_thr105.cfg"),
            ),
            'bee': SimpleUploadedFile(
                name="bee.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/BEE_FM6.cfg"),
            ),
        }

    def setUp(self):
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
        # Clear the test outbox
        mail.outbox = []

    def prepare_delivery_session(self):
        """Helper to setup a valid delivery session"""
        response = self.client.post(
            reverse('configs:upload'),
            data={'model': 'H6', **self.files_fm6},
            follow=True
        )
        self.client.get(reverse('configs:test'))
        return response

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_successful_email_delivery(self):
        """Test that email is sent successfully with correct content"""
        self.prepare_delivery_session()

        form_data = {
            'recipient': settings.EMAIL_CONFIGS_RECIPIENT,
            'subject': 'Test Configuration Delivery',
            'cc': 'cc@example.com'
        }

        response = self.client.post(reverse('configs:deliver'), data=form_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'configs/deliver_success.html')

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        # Verify email content
        self.assertEqual(email.subject, 'Test Configuration Delivery')
        self.assertEqual(email.to, [settings.EMAIL_CONFIGS_RECIPIENT])
        self.assertEqual(email.cc, ['cc@example.com'])

        # Verify attachments
        self.assertEqual(len(email.attachments), 5)  # Should have all config files
        attachment_names = [att[0] for att in email.attachments]
        self.assertTrue(all(f"{type}.cfg" in attachment_names
                            for type in ['acq', 'acq0', 'asic0', 'asic1', 'bee']))

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_delivery_with_multiple_cc(self):
        """Test email delivery with multiple CC recipients"""
        self.prepare_delivery_session()

        form_data = {
            'recipient': settings.EMAIL_CONFIGS_RECIPIENT,
            'subject': 'Test Configuration Delivery',
            'cc': 'cc1@example.com; cc2@example.com'
        }

        response = self.client.post(reverse('configs:deliver'), data=form_data)
        self.assertEqual(response.status_code, 200)

        email = mail.outbox[0]
        self.assertEqual(email.cc, ['cc1@example.com', 'cc2@example.com'])

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_email_failure_rollback(self):
        """Test that database changes are rolled back if email fails"""
        self.prepare_delivery_session()

        form_data = {
            'recipient': settings.EMAIL_CONFIGS_RECIPIENT,
            'subject': 'Test Configuration Delivery',
        }

        with patch('django.core.mail.EmailMessage.send', side_effect=SMTPException('SMTP Error')):
            response = self.client.post(reverse('configs:deliver'), data=form_data)

            self.assertTemplateUsed(response, 'configs/deliver_error.html')

            self.assertEqual(Configuration.objects.count(), 0)

            # Session should still be valid
            self.assertIn('config_id', self.client.session)
            self.assertIn('config_hash', self.client.session)
            self.assertIn('config_model', self.client.session)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_attachment_content_verification(self):
        """Test that email attachments contain correct file content"""
        self.prepare_delivery_session()

        form_data = {
            'recipient': settings.EMAIL_CONFIGS_RECIPIENT,
            'subject': 'Test Configuration Delivery',
        }

        response = self.client.post(reverse('configs:deliver'), data=form_data)
        email = mail.outbox[0]

        # Verify each attachment's content
        for attachment in email.attachments:
            name, content, mime = attachment
            file_type = name.split('.')[0]

            # Compare with original content
            original_file = self.files_fm6[file_type]
            original_file.seek(0)
            self.assertEqual(content, original_file.read())

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_delivery_database_record(self):
        """Test that successful delivery creates correct database record"""
        self.prepare_delivery_session()

        form_data = {
            'recipient': settings.EMAIL_CONFIGS_RECIPIENT,
            'subject': 'Test Configuration Delivery',
        }

        self.client.post(reverse('configs:deliver'), data=form_data)

        # Verify configuration record
        config = Configuration.objects.last()
        self.assertIsNotNone(config)
        self.assertTrue(config.delivered)
        self.assertIsNotNone(config.deliver_time)
        self.assertEqual(config.model, 'H6')
        self.assertEqual(config.author, self.user)

        # Verify file contents
        for file_type in ["acq", "acq0", "asic0", "asic1", "bee"]:
            original_file = self.files_fm6[file_type]
            original_file.seek(0)
            self.assertEqual(getattr(config, file_type), original_file.read())


class ConfigurationFileSystemTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Create test user
        cls.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )


        # Setup test files
        cls.files_fm6 = {
            'acq': SimpleUploadedFile(
                name="acq.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/acq_FM6.cfg"),
            ),
            'acq0': SimpleUploadedFile(
                name="acq0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/acq0_FM6.cfg"),
            ),
            'asic0': SimpleUploadedFile(
                name="asic0.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/asic0_FM6.cfg"),
            ),
            'asic1': SimpleUploadedFile(
                name="asic1.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/asic1_FM6_thr105.cfg"),
            ),
            'bee': SimpleUploadedFile(
                name="bee.cfg",
                content=f2c(BASE_DIR / "configs/tests/configs_fm6/BEE_FM6.cfg"),
            ),
        }

    def setUp(self):
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
        self.media_root = settings.MEDIA_ROOT
        if Path(self.media_root / "configs").exists():
            shutil.rmtree(Path(self.media_root / "configs"))

    def tearDown(self):
        if Path(self.media_root / "configs").exists():
            shutil.rmtree(Path(self.media_root / "configs"))

    def test_successful_file_cleanup(self):
        """Test that files are cleaned up after successful delivery"""
        _ = self.client.post(
            reverse('configs:upload'),
            data={'model': 'H6', **self.files_fm6},
            follow=True
        )

        config_id = self.client.session['config_id']
        config_dir = Path(self.media_root) / f"configs/{config_id}"

        # Verify files were created
        self.assertTrue(config_dir.exists())
        for file_type in ["acq", "acq0", "asic0", "asic1", "bee"]:
            self.assertTrue((config_dir / f"{file_type}.cfg").exists())

        # Complete the delivery process
        self.client.get(reverse('configs:test'))
        response = self.client.post(
            reverse('configs:deliver'),
            data={
                'recipient': settings.EMAIL_CONFIGS_RECIPIENT,
                'subject': 'Test Configuration Delivery',
            }
        )

        # Verify files were cleaned up
        self.assertFalse(config_dir.exists())

    def test_files_preserved_on_delivery_failure(self):
        """Test that files are preserved when delivery fails"""
        response = self.client.post(
            reverse('configs:upload'),
            data={'model': 'H6', **self.files_fm6},
            follow=True
        )

        config_id = self.client.session['config_id']
        config_dir = Path(self.media_root) / f"configs/{config_id}"

        self.client.get(reverse('configs:test'))

        # Simulate delivery failure
        with patch('django.core.mail.EmailMessage.send', side_effect=SMTPException('SMTP Error')):
            response = self.client.post(
                reverse('configs:deliver'),
                data={
                    'recipient': settings.EMAIL_CONFIGS_RECIPIENT,
                    'subject': 'Test Configuration Delivery',
                }
            )

        # Verify files still exist
        self.assertTrue(config_dir.exists())
        for file_type in ['acq', 'acq0', 'asic0', 'asic1', 'bee']:
            self.assertTrue((config_dir / f"{file_type}.cfg").exists())
