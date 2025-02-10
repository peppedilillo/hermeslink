FROM python:3.9-slim

WORKDIR /app

# Install dependencies
RUN pip install influxdb-client

# Copy the script
COPY script.py .

CMD ["python", "script.py"]