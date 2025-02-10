import os
import time
from datetime import datetime
import random
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

url = "http://influxdb2:8086"
token = os.environ['DOCKER_INFLUXDB_INIT_ADMIN_TOKEN']
org = os.environ['DOCKER_INFLUXDB_INIT_ORG']
bucket = os.environ['DOCKER_INFLUXDB_INIT_BUCKET']

client = InfluxDBClient(url=url, token=token, org=org)
write_api = client.write_api(write_options=SYNCHRONOUS)

def generate_sensor_data():
    """Generate dummy sensor data"""
    return {
        'temperature': random.uniform(20.0, 30.0),
        'humidity': random.uniform(30.0, 70.0),
        'pressure': random.uniform(980.0, 1020.0)
    }

def write_data():
    """Write data points to InfluxDB"""
    while True:
        try:
            time.sleep(5)
            data = generate_sensor_data()
            
            point = Point("sensor_readings") \
                .field("temperature", data['temperature']) \
                .field("humidity", data['humidity']) \
                .field("pressure", data['pressure']) \
                .time(datetime.utcnow())

            write_api.write(bucket=bucket, org=org, record=point)                        
        except Exception as e:
            print(f"Error writing to InfluxDB: {e}")
            time.sleep(2)  # Wait a bit longer before retrying on error

if __name__ == "__main__":
    print("Starting data generator...")
    write_data()