import logging
import random
from smtplib import SMTPException

from celery import shared_task
from configs.downloads import write_archive
from configs.models import Configuration
from django.core.mail import EmailMessage
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from influxdb_client import InfluxDBClient
from influxdb_client import Point
from influxdb_client.client.write_api import SYNCHRONOUS

from hlink import settings

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(SMTPException,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
    retry_jitter=True,
)
def send_config_email(
    self,
    config_id: int,
    cc: list[str],
    recipients: list[str],
    domain: str,
    protocol: str,
):
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
                to=recipients,
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
        logger.error(f"Configuration {config_id} not found")
        return
    except Exception as e:
        logger.error(f"Unexpected error for config {config_id}: {str(e)}")
        return


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
    try:
        # Create InfluxDB client
        client = InfluxDBClient(url=settings.INFLUXDB_URL, token=settings.INFLUXDB_TOKEN, org=settings.INFLUXDB_ORG)
        write_api = client.write_api(write_options=SYNCHRONOUS)

        data = {
            "temperature": random.uniform(20.0, 30.0),
            "humidity": random.uniform(30.0, 70.0),
            "pressure": random.uniform(980.0, 1020.0),
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
