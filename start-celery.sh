#!/bin/bash

echo "Starting Celery worker"
cd app && uv run celery -A SMSGateway worker -n default@%h --loglevel=INFO --concurrency=50
