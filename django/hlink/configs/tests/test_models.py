"""
MODEL TESTS:

* Test that a configuration can be created with valid data
* Test that binary data is preserved correctly when stored and retrieved
* Test that only valid satellite model choices (H1-H6) are accepted
* Test that binary fields enforce exact size constraints
* Test that at least one configuration file must be provided
* Test that configurations are protected from author deletion via foreign key constraints
* Test that creation timestamp is automatically assigned
* Test that submitted and uplinked flags default to False with null timestamps
* Test that submit and uplink timestamps can be properly set and retrieved
* Test that partial configurations can be created and stored
"""

from configs.models import Configuration
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone

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
        """Test that submit and uplinked flags default to False"""
        self.assertFalse(self.valid_config.submitted)
        self.assertFalse(self.valid_config.uplinked)
        self.assertIsNone(self.valid_config.uplink_time)
        self.assertIsNone(self.valid_config.submit_time)

    def test_time_assignment(self):
        """Test uplink_time field assignment"""
        uplink_time = timezone.now()
        submit_time = uplink_time - timezone.timedelta(hours=1)

        self.valid_config.submit_time = submit_time
        self.valid_config.submitted = True
        self.valid_config.uplink_time = uplink_time
        self.valid_config.uplinked_by = self.test_user
        self.valid_config.uplinked = True
        self.valid_config.save()

        self.valid_config.refresh_from_db()
        self.assertEqual(self.valid_config.uplink_time, uplink_time)
        self.assertEqual(self.valid_config.submit_time, submit_time)

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

    def test_submit_time_requires_submitted_flag(self):
        """Test that a configuration with non-null submit_time must have submitted=True"""
        config = Configuration(
            author=self.test_user,
            model="H1",
            acq=b"x" * self.valid_len_acq_data,
            submit_time=timezone.now(),
            submitted=False,  # This violates the constraint
        )
        with self.assertRaises(ValidationError):
            config.full_clean()

        # Fix the constraint violation
        config.submitted = True
        config.full_clean()  # Should not raise an exception

    def test_uplink_time_requires_uplinked_flag(self):
        """Test that a configuration with non-null uplink_time must have uplinked=True"""
        config = Configuration(
            author=self.test_user,
            model="H1",
            acq=b"x" * self.valid_len_acq_data,
            uplink_time=timezone.now(),
            uplinked=False,  # This violates the constraint
        )
        with self.assertRaises(ValidationError):
            config.full_clean()

        config.submitted = True
        config.uplinked = True
        config.uplinked_by = self.test_user
        config.full_clean()  # Should not raise an exception

    def test_uplinked_implies_submitted(self):
        config = Configuration(
            author=self.test_user,
            model="H1",
            acq=b"x" * self.valid_len_acq_data,
            uplink_time=None,
            uplinked=False,
            submitted=True,
            submit_time=timezone.now(),
        )
        config.full_clean()

    def test_uplink_time_after_submit_time(self):
        """Test that uplink_time must be later than submit_time if both exist"""
        test_time = timezone.now()

        # Case 1: submit_time is earlier than uplink_time
        config = Configuration(
            author=self.test_user,
            model="H1",
            acq=b"x" * self.valid_len_acq_data,
            submit_time=test_time,
            submitted=True,
            uplink_time=test_time + timezone.timedelta(hours=1),
            uplinked_by=self.test_user,
            uplinked=True,
        )
        with self.assertRaises(ValidationError):
            config.full_clean()

        # Case 2: submit_time equals uplink_time
        config.submit_time = test_time
        config.uplink_time = test_time
        with self.assertRaises(ValidationError):
            config.full_clean()

        # Case 3: submit_time is later than uplink_time (valid)
        config.submit_time = test_time
        config.uplink_time = test_time - timezone.timedelta(hours=2)
        with self.assertRaises(ValidationError):
            config.full_clean()

        # note for the next test the flags are still set
        self.assertTrue(config.uplinked)
        self.assertTrue(config.submitted)

        # Case 4: Only submit_time is set (valid)
        config.uplink_time = None
        config.full_clean()  # Should not raise an exception

        # Case 5: Only uplink_time is set (valid)
        config.submit_time = None
        config.uplink_time = test_time
        config.full_clean()  # Should not raise an exception

        # Case 6: Neither time is set (valid)
        config.submit_time = None
        config.uplink_time = None
        config.full_clean()  # Should not raise an exception
