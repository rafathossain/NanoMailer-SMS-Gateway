# Celery Setup for SMS Gateway

This document describes how to set up and run Celery for asynchronous SMS processing.

## Architecture

```
User Request → API View → process_sms_request() → Celery Queue → send_sms_task() → SMS Provider
                                      ↓
                                Create Log
                                Deduct Balance
                                Status = QUEUED
```

## Prerequisites

1. **Redis** - Message broker and result backend
   ```bash
   # macOS
   brew install redis
   brew services start redis
   
   # Ubuntu/Debian
   sudo apt-get install redis-server
   sudo service redis-server start
   
   # Docker
   docker run -d -p 6379:6379 redis:latest
   ```

2. **Environment Variable** (optional)
   ```bash
   # Set Redis URL (defaults to localhost if not set)
   export REDIS_URL=redis://localhost:6379/0
   ```

## Running Celery

### 1. Start Celery Worker

```bash
# From project root
cd /Users/rafathossain/PycharmProjects/SMSGateway

# Start worker (handles SMS sending)
celery -A SMSGateway worker -l info

# Start worker with specific queue
celery -A SMSGateway worker -l info -Q celery

# Start worker in background (production)
celery -A SMSGateway worker -l info --detach
```

## Monitoring

### Flower (Celery Monitoring Tool)

```bash
# Install flower
pip install flower

# Run flower
celery -A SMSGateway flower --port=5555

# Access at http://localhost:5555
```

## Tasks

### 1. send_sms_task

Sends SMS asynchronously through the configured provider.

```python
from sms_gateway.tasks import send_sms_task

# Queue SMS for sending
send_sms_task.delay(log_id=123)
```

### 2. process_bulk_sms

Process multiple SMS logs in bulk.

```python
from sms_gateway.tasks import process_bulk_sms

# Queue multiple SMS
process_bulk_sms.delay([1, 2, 3, 4, 5])
```

## Configuration

### Settings (settings.py)

```python
# Celery Configuration
CELERY_BROKER_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300  # 5 minutes
```

## Testing

```bash
# Test Celery is working
python manage.py shell

>>> from sms_gateway.tasks import debug_task
>>> debug_task.delay()

# Test SMS task
>>> from sms_gateway.tasks import send_sms_task
>>> result = send_sms_task.delay(log_id=1)
>>> result.get(timeout=10)  # Wait for result
```

## Production Deployment

### Supervisor Configuration

Create `/etc/supervisor/conf.d/smsgateway-celery.conf`:

```ini
[program:smsgateway-celery]
command=/path/to/venv/bin/celery -A SMSGateway worker -l info
directory=/Users/rafathossain/PycharmProjects/SMSGateway
user=www-data
numprocs=1
stdout_logfile=/var/log/celery/worker.log
stderr_logfile=/var/log/celery/worker.error.log
autostart=true
autorestart=true
startsecs=10
stopwaitsecs=600
killasgroup=true
priority=998
```

### Systemd Service

Create `/etc/systemd/system/smsgateway-celery.service`:

```ini
[Unit]
Description=SMSGateway Celery Worker
After=network.target redis.service

[Service]
Type=forking
User=www-data
Group=www-data
WorkingDirectory=/Users/rafathossain/PycharmProjects/SMSGateway
Environment=DJANGO_SETTINGS_MODULE=SMSGateway.settings
Environment=REDIS_URL=redis://localhost:6379/0
ExecStart=/path/to/venv/bin/celery -A SMSGateway worker -l info --detach
ExecStop=/path/to/venv/bin/celery -A SMSGateway control shutdown
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable smsgateway-celery
sudo systemctl start smsgateway-celery
```

## Troubleshooting

### Worker not processing tasks

1. Check Redis is running: `redis-cli ping`
2. Check worker is running: `celery -A SMSGateway status`
3. Check logs for errors

### Tasks stuck in queue

```bash
# Clear queue (WARNING: deletes all pending tasks)
redis-cli FLUSHDB

# Or use celery purge
celery -A SMSGateway purge
```

### Check task results

```python
from celery.result import AsyncResult
from SMSGateway.celery import app

result = AsyncResult('task-id', app=app)
print(result.status)  # PENDING, STARTED, SUCCESS, FAILURE
print(result.result)  # Task return value
```
