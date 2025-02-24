import random

from django.utils import timezone
from celery import shared_task
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from hlink import settings


@shared_task
def test_task():
    """Task for debugging purposes"""
    print(f'Test periodic task executed.')


@shared_task
def generate_sensor_data():
    """
    Generate and store sensor readings in InfluxDB.
    This task replaces the functionality of the data-generator container.
    """
    try:
        # Create InfluxDB client
        client = InfluxDBClient(
            url=settings.INFLUXDB_URL,
            token=settings.INFLUXDB_TOKEN,
            org=settings.INFLUXDB_ORG
        )
        write_api = client.write_api(write_options=SYNCHRONOUS)

        data = {
            'temperature': random.uniform(20.0, 30.0),
            'humidity': random.uniform(30.0, 70.0),
            'pressure': random.uniform(980.0, 1020.0)
        }

        point = Point("sensor_readings") \
            .field("temperature", data['temperature']) \
            .field("humidity", data['humidity']) \
            .field("pressure", data['pressure']) \
            .time(timezone.now())

        write_api.write(
            bucket=settings.INFLUXDB_BUCKET,
            org=settings.INFLUXDB_ORG,
            record=point
        )

        client.close()
        return True

    except Exception as e:
        print(f"Error writing to InfluxDB: {e}")
        raise
