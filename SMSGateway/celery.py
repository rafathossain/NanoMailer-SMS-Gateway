"""
Celery configuration for SMSGateway project.

This module configures Celery for asynchronous task processing.
Redis is used as the message broker and result backend.
"""
import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SMSGateway.settings')

# Create Celery app
app = Celery('SMSGateway')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

# Celery configuration
app.conf.update(
    # Broker settings (Redis)
    broker_url=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    
    # Result backend (Redis)
    result_backend=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    
    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    
    # Task execution settings
    task_track_started=True,
    task_time_limit=300,  # 5 minutes
    task_soft_time_limit=240,  # 4 minutes (warning before hard limit)
    
    # Result settings
    result_expires=3600,  # Results expire after 1 hour
    
    # Worker settings
    worker_prefetch_multiplier=4,
    worker_max_tasks_per_child=1000,
    
    # Retry settings
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,
    
    # Timezone
    timezone='Asia/Dhaka',
    enable_utc=True,
)


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task to verify Celery is working."""
    print(f'Request: {self.request!r}')
