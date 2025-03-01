"""
TASK MODULE TESTS:

* Test error email notifications to admins
* Test error logging and notification functions
* Test command parsing for CALDB updates [TODO]
* Test remote filepath generation
* Test notification emails to SOC
* Test SSH connection and CALDB updates
"""

import logging
import os
from unittest.mock import MagicMock
from unittest.mock import patch

from configs.models import Configuration
from configs.tasks import email_error_to_admin
from configs.tasks import email_uplink_to_soc
from configs.tasks import log_error_and_notify_admin
from configs.tasks import ssh_update_caldb
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from django.test import TestCase
from django.utils import timezone

from hlink import contacts

User = get_user_model()


class TasksTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="testuser", password="testpass123")
        cls.test_config = Configuration.objects.create(
            author=cls.user,
            model="H1",
            acq=b"x" * 20,
            asic1=b"x" * 124,
        )
        cls.uplinked_config = Configuration.objects.create(
            author=cls.user,
            model="H1",
            acq=b"x" * 20,
            asic1=b"x" * 124,
            submitted=True,
            submit_time=timezone.now() - timezone.timedelta(hours=2),
            uplinked=True,
            uplinked_by=cls.user,
            uplink_time=timezone.now() - timezone.timedelta(hours=1),
        )

    def setUp(self):
        # Clear the test outbox
        mail.outbox = []

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_error_to_admin(self):
        """Test error notification to admins is sent correctly."""
        # Call the function
        error_msg = "Test error message"
        task_name = "test_task_name"
        config_id = 424242

        email_error_to_admin(error_msg, task_name, config_id)

        # Check email was sent
        self.assertEqual(len(mail.outbox), 1)

        # Verify email contains key information without exact string matching
        email = mail.outbox[0]
        self.assertIn(str(config_id), email.subject)
        self.assertIn(task_name, email.subject)
        self.assertIn(error_msg, email.body)
        self.assertIn(str(config_id), email.body)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_log_error_and_notify_admin(self):
        """Test error logging and admin notification."""
        with self.assertLogs(level="WARNING") as cm:
            log_error_and_notify_admin(logging.WARNING, "Test warning message", "test_task_name", 42)
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertTrue(len(email.to) == len(contacts.EMAILS_ADMIN))
        self.assertTrue(all(x == y for x, y in zip(email.to, contacts.EMAILS_ADMIN)))

    def test_parse_update_caldb_command(self):
        """Test CALDB update command generation."""
        raise NotImplementedError("This test has yet to be implemented!")

    def test_parse_remote_asic1_path(self):
        """Test remote ASIC1 filepath generation."""
        raise NotImplementedError("This test has yet to be implemented!")


    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_uplink_to_soc(self):
        """Test SOC notification email is sent successfully."""
        # Parameters for the function
        config_id = 42
        model = "H1"
        filepath = "/path/to/asic1.cfg"
        command = "shell_command"
        username = "username"

        # Call the function
        email_uplink_to_soc(config_id, model, filepath, command, username)

        # Check email was sent
        self.assertEqual(len(mail.outbox), 1)

        # Verify email contains key information without exact string matching
        email = mail.outbox[0]
        self.assertIn(model, email.subject)
        self.assertIn(str(config_id), email.subject)

        # Check key parameters are included
        body = email.body
        self.assertIn(filepath, body)
        self.assertIn(command, body)
        self.assertIn(username, body)

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertTrue(len(email.to) == len(contacts.EMAILS_SOC))
        self.assertTrue(all(x == y for x, y in zip(email.to, contacts.EMAILS_SOC)))

    @patch("configs.tasks.paramiko.SSHClient")
    def test_ssh_update_caldb(self, mock_ssh_client):
        """Test CALDB update via SSH."""
        # Setup mock SSH client and SFTP
        mock_ssh = MagicMock()
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp
        mock_ssh_client.return_value.__enter__.return_value = mock_ssh

        # Set environment variables required for the function
        original_host = os.environ.get("SSH_HERMESPROC1_HOST")
        original_user = os.environ.get("SSH_HERMESPROC1_USER")
        original_pass = os.environ.get("SSH_HERMESPROC1_PASSWORD")

        try:
            os.environ["SSH_HERMESPROC1_HOST"] = "example.com"
            os.environ["SSH_HERMESPROC1_USER"] = "testuser"
            os.environ["SSH_HERMESPROC1_PASSWORD"] = "testpass"

            # Call the function with our uplinked config
            with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
                ssh_update_caldb(self.uplinked_config.id, dryrun=True)

            # Check SSH client was connected properly
            mock_ssh.connect.assert_called_once_with("example.com", username="testuser", password="testpass", timeout=5)

            # Check SFTP file transfer occurred
            self.assertTrue(mock_sftp.putfo.called)

            # Verify the remote path contains the config ID
            _, kwargs = mock_sftp.putfo.call_args_list[0]
            self.assertIn(f"asic1_id{self.uplinked_config.id}", kwargs["remotepath"])

            # Check shell command was executed
            self.assertTrue(mock_ssh.exec_command.called)

            # Check notification email was sent
            self.assertEqual(len(mail.outbox), 1)
            self.assertIn(str(self.uplinked_config.id), mail.outbox[0].subject)

        finally:
            # Restore environment variables
            if original_host:
                os.environ["SSH_HERMESPROC1_HOST"] = original_host
            else:
                os.environ.pop("SSH_HERMESPROC1_HOST", None)

            if original_user:
                os.environ["SSH_HERMESPROC1_USER"] = original_user
            else:
                os.environ.pop("SSH_HERMESPROC1_USER", None)

            if original_pass:
                os.environ["SSH_HERMESPROC1_PASSWORD"] = original_pass
            else:
                os.environ.pop("SSH_HERMESPROC1_PASSWORD", None)
