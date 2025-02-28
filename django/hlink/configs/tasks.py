from datetime import datetime
from io import BytesIO
import logging
import os
from smtplib import SMTPException
from socket import error as socket_error
from typing import Literal
from zoneinfo import ZoneInfo

from celery import shared_task
from configs.downloads import write_archive
from configs.models import Configuration
from django.core.mail import EmailMessage
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from hermes import CONFIG_SIZE
from hermes import SPACECRAFTS_NAMES
from influxdb_client import InfluxDBClient
from influxdb_client import Point
from influxdb_client.client.write_api import SYNCHRONOUS
import paramiko
from paramiko import ssh_exception

from hlink import contacts
from hlink import settings

logger = logging.getLogger(__name__)


def email_error_to_admin(
    error_message: str,
    task_name: str,
    config_id: int | None = None,
):
    """
    Sends an error notification email to administrators.
    """
    subject = f"[HERMES] ERROR: {task_name}" + (f" - Config #{config_id}" if config_id else "")

    body = (
        f"Task: {task_name}\n"
        f"Error: {error_message}\n"
        f"Config ID: {config_id if config_id else 'N/A'}\n"
        f"Time: {timezone.now()}\n\n"
        f"This is an automated message from Hermes Link."
    )

    try:
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.EMAIL_HOST_USER,
            to=contacts.EMAILS_ADMIN,
        )
        email.send()
    except SMTPException:
        logger.error(f"Failed to send admin error notification: {email}")
        return
    except Exception as e:
        logger.error(f"An unexpected error occurred trying to submit admin email notification: {e}")
        return

    logger.info(f"Admin error notification sent for {task_name}" + (f", config {config_id}" if config_id else ""))
    return


def log_error_and_notify_admin(
    level: int,
    error_message: str,
    task_name: str,
    config_id: int | None = None,
):
    """
    Simple utility wrapper to admin notification email.
    """
    logger.log(level=level, msg=error_message)
    return email_error_to_admin(error_message, task_name, config_id)


def parse_update_caldb_command(
    filepath: str,
    config_id: int,
    dt: datetime,
    model: Literal[*SPACECRAFTS_NAMES],
    dryrun: bool,
) -> str:
    """
    Helper method.
    Constructs a shell command to update the calibration database with a new ASIC configuration.
    The command will run the asic2caldb utility on the specified filepath with appropriate
    arguments and redirects output to log files.
    """
    model = model.lower()
    flag_update_caldb = "0" if dryrun else "1"
    dirname = "test/" if dryrun else ""

    datetime_arg_str = dt.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S.000")
    datetime_fname_str = datetime_arg_str.replace(" ", "_").replace(".", "dot")
    out_filename = (
        f"caldb_update/hlink_logs/{dirname}out_{model}_{datetime_fname_str}_{flag_update_caldb}_id{config_id}.log"
    )
    err_filename = (
        f"caldb_update/hlink_logs/{dirname}err_{model}_{datetime_fname_str}_{flag_update_caldb}_id{config_id}.log"
    )
    command = f"./caldb_update/asic2caldb {filepath} {model} {datetime_arg_str} {flag_update_caldb} 1>{out_filename} 2>{err_filename} &"
    return command


def parse_remote_asic1_path(
    config_id: int,
    dryrun: bool,
):
    """
    Helper method.
    Constructs the remote filepath where the ASIC1 configuration will be stored.
    """
    dirname = "test/" if dryrun else ""
    return f"/home/hermesman/caldb_update/hlink_logs/{dirname}configs/asic1_id{config_id}.cfg"


def email_uplink_to_soc(
    config_id: int,
    model: Literal[*SPACECRAFTS_NAMES],
    remote_asic1_path: str,
    shell_cmd: str,
    username: str,
):
    email = EmailMessage(
        subject=f"[HERMES] {model} Automatic CALDB Update - {config_id}",
        body=f"Hermes Link attempted running a CALDB update.\n\n"
        f"Configuration file remote path: {remote_asic1_path}\n"
        f"Script executed: {shell_cmd}\n"
        f"Username: {username}\n\n"
        f"This is an automated message from Hermes Link",
        from_email=settings.EMAIL_HOST_USER,
        to=contacts.EMAILS_SOC,
    )
    try:
        email.send()
    except SMTPException:
        logging.error(f"Failed to send CALDB update email notification: {email}")
        return
    except Exception as e:
        return log_error_and_notify_admin(
            logging.WARNING,
            f"An unexpected error occurred during CALDB update notification email delivery: {e}",
            "email_uplink_to_soc",
            config_id,
        )
    logger.info(f"CALDB update notification email sent for configuration {config_id}.")
    return


@shared_task(
    bind=True,
    autoretry_for=(
        ssh_exception.SSHException,
        TimeoutError,
    ),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
    retry_jitter=True,
)
def ssh_update_caldb(
    self,
    config_id: int,
    timeout: int = 5,  # seconds
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    dryrun: bool | None = None,
):
    """
    Updates the calibration database on a remote server by uploading the ASIC1 configuration
    file and triggering the calibration update process.

    This asynchronous task connects to a remote server via SSH, transfers the ASIC1
    configuration file via SFTP, and executes a shell command to update the calibration
    database. Errors during any stage will trigger a retry with exponential backoff.
    """
    if host is None:
        host = os.environ.get("SSH_HERMESPROC1_HOST")
    if username is None:
        username = os.environ.get("SSH_HERMESPROC1_USER")
    if password is None:
        password = os.environ.get("SSH_HERMESPROC1_PASSWORD")
    if not (host and username and password):
        return log_error_and_notify_admin(
            logging.WARNING,
            "SSH credentials missing.",
            "ssh_update_caldb",
            config_id,
        )

    if dryrun is None:
        dryrun = bool(int(os.environ.get("SSH_HERMESPROC1_DRYRUN", default="1")))

    try:
        config = Configuration.objects.get(pk=config_id)
    except Configuration.DoesNotExist:
        return log_error_and_notify_admin(
            logging.WARNING,
            f"Configuration {config_id} does not exist.",
            "ssh_update_caldb",
            config_id,
        )
    if not config.uplink_time:
        return log_error_and_notify_admin(
            logging.WARNING,
            f"Configuration {config_id} has not been uplinked.",
            "ssh_update_caldb",
            config_id,
        )
    if not config.asic1:
        return log_error_and_notify_admin(
            logging.WARNING,
            f"Configuration {config_id} contains no asic1 file.",
            "ssh_update_caldb",
            config_id,
        )

    with paramiko.SSHClient() as ssh:
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(host, username=username, password=password, timeout=timeout)
        except (
            ssh_exception.BadHostKeyException,
            ssh_exception.AuthenticationException,
            ssh_exception.NoValidConnectionsError,
            socket_error,
        ) as e:
            return log_error_and_notify_admin(
                logging.WARNING,
                f"SSH connection failed: {e}",
                "ssh_update_caldb",
                config_id,
            )

        # we transfer the asic1.cfg file
        remote_asic1_path = parse_remote_asic1_path(config_id, dryrun=dryrun)
        try:
            sftp = ssh.open_sftp()
            sftp.putfo(
                fl=BytesIO(config.asic1),
                remotepath=remote_asic1_path,
                file_size=CONFIG_SIZE["asic1"],
                confirm=True,
            )
        except Exception as e:
            return log_error_and_notify_admin(
                logging.WARNING,
                f"SFTP transfer of asic1 file from configuration {config_id} failed: {e}",
                "ssh_update_caldb",
                config_id,
            )
        finally:
            if sftp:
                sftp.close()

        # launch caldb update
        shell_cmd = parse_update_caldb_command(
            filepath=remote_asic1_path,
            config_id=config_id,
            dt=config.uplink_time.astimezone(ZoneInfo("UTC")),
            model=config.model,
            dryrun=dryrun,
        )
        try:
            # exec_command only raises SSHException, which we are retrying via celery
            _ = ssh.exec_command(shell_cmd)
        except Exception as e:
            return log_error_and_notify_admin(
                logging.WARNING,
                f"Execution of caldb update shell command failed: {e}",
                "ssh_update_caldb",
                config_id,
            )

        logger.info(f"Successfully launched caldb update at {host} for configuration {config_id} (dryrun={dryrun}).")
        return email_uplink_to_soc(config_id, config.model, remote_asic1_path, shell_cmd, username)


@shared_task(
    bind=True,
    autoretry_for=(SMTPException,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
    retry_jitter=True,
)
def email_config_to_moc(
    self,
    config_id: int,
    cc: list[str],
    domain: str,
    protocol: str,
):
    """
    Sends an email notification for a configuration that has been submitted.

    This asynchronous task atomically marks a configuration as submitted and sends
    an email notification to the specified recipients with configuration details and
    a ZIP attachment containing the configuration files.

    The task uses database transactions to ensure that the configuration is marked as
    submitted only if the email is sent successfully. Failures will trigger retries
    with exponential backoff.
    """
    try:
        with transaction.atomic():
            # select_for_update will lock the row for the transaction duration
            config = Configuration.objects.select_for_update().get(pk=config_id)
            if config.submitted:
                logger.warning(f"Configuration {config_id} already marked as submitted")
                return

            timestamp = timezone.now()
            email_body = render_to_string(
                "configs/submit_email.html",
                context={
                    "config": config,
                    "submission_date": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    "timezone": settings.TIME_ZONE,
                    "files": ", ".join(config.non_null_configs_keys()),
                    "domain": domain,
                    "protocol": protocol,
                },
            )
            email = EmailMessage(
                subject=f"[HERMES] {config.model} Payload Configuration Update - {config_id}",
                body=email_body,
                from_email=settings.EMAIL_HOST_USER,
                cc=cc,
                to=contacts.EMAILS_MOC,
            )
            dirname = f"{config.filestring()}"
            archive_content = write_archive(config, "zip", dirname=dirname)
            email.attach(f"{dirname}.zip", archive_content, "application/zip")

            email.send()

            config.submitted = True
            config.submit_time = timestamp
            config.save()
            logger.info(f"Email sent for configuration {config_id} after {self.request.retries} retries")
            return

    except Configuration.DoesNotExist:
        return log_error_and_notify_admin(
            logging.WARNING,
            f"Configuration {config_id} not found",
            "email_config_to_moc",
            config_id,
        )
    except SMTPException:
        logger.warning(f"SMTP error sending email for config {config_id}, will retry")
        raise  # re-raise so Celery sees it
    except Exception as e:
        return log_error_and_notify_admin(
            logging.WARNING,
            f"Unexpected attempting to send config {config_id}: {str(e)}",
            "email_config_to_moc",
            config_id,
        )


@shared_task
def test_task():
    """Task for debugging purposes"""
    logger.info(f"Test periodic task executed.")


@shared_task
def generate_sensor_data():
    """
    Generate and store sensor readings in InfluxDB.
    This task replaces the functionality of the data-generator container.
    """
    from random import uniform

    try:
        # Create InfluxDB client
        client = InfluxDBClient(url=settings.INFLUXDB_URL, token=settings.INFLUXDB_TOKEN, org=settings.INFLUXDB_ORG)
        write_api = client.write_api(write_options=SYNCHRONOUS)

        data = {
            "temperature": uniform(20.0, 30.0),
            "humidity": uniform(30.0, 70.0),
            "pressure": uniform(980.0, 1020.0),
        }

        point = (
            Point("sensor_readings")
            .field("temperature", data["temperature"])
            .field("humidity", data["humidity"])
            .field("pressure", data["pressure"])
            .time(timezone.now())
        )

        write_api.write(bucket=settings.INFLUXDB_BUCKET, org=settings.INFLUXDB_ORG, record=point)

        client.close()
        return True

    except Exception as e:
        logger.error(f"Error writing to InfluxDB: {e}")
        raise
