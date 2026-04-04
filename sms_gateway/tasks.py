"""
SMS Gateway Celery Tasks

This module contains Celery tasks for asynchronous SMS processing.
"""
import logging
from celery import shared_task
from django.db import transaction

from .models import SMSLog
from .utils import send_sms_via_provider

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_sms_task(self, log_id):
    """
    Celery task to send SMS asynchronously.
    
    This task is called after SMS log is created and balance is deducted.
    It sends the SMS through the provider and updates the log status.
    
    Args:
        log_id: SMSLog ID to process
        
    Returns:
        dict: Result of the SMS sending operation
    """
    try:
        # Get the SMS log
        log = SMSLog.objects.select_related('user', 'provider').get(id=log_id)
        
        logger.info(f"Processing SMS log {log_id} for user {log.user.id}")
        
        # Update status to SENT (we're about to send)
        log.status = 'SENT'
        log.save(update_fields=['status'])
        
        # Send SMS via provider
        result = send_sms_via_provider(
            log_id=log.id,
            recipient=log.recipient,
            message=log.message,
            sender_id=log.sender_id,
            provider=log.provider
        )
        
        if result.get('success'):
            logger.info(f"SMS {log_id} sent successfully. Message ID: {result.get('message_id')}")
            
            # Update log with success
            log.status = 'DELIVERED'
            log.message_id = result.get('message_id')
            log.response_data = result.get('response', {})
            log.save(update_fields=['status', 'message_id', 'response_data'])
            
            return {
                'success': True,
                'log_id': log_id,
                'message_id': result.get('message_id'),
                'status': 'DELIVERED'
            }
        else:
            # Sending failed
            error_msg = result.get('message', 'Unknown error')
            logger.error(f"SMS {log_id} failed: {error_msg}")
            
            # Update log with failure
            log.status = 'FAILED'
            log.error_message = error_msg
            log.response_data = result.get('response', {})
            log.save(update_fields=['status', 'error_message', 'response_data'])
            
            # Note: The signal will automatically refund the balance
            
            return {
                'success': False,
                'log_id': log_id,
                'error': error_msg,
                'status': 'FAILED'
            }
            
    except SMSLog.DoesNotExist:
        logger.error(f"SMS log {log_id} not found")
        return {
            'success': False,
            'log_id': log_id,
            'error': 'SMS log not found'
        }
    except Exception as e:
        logger.exception(f"Error processing SMS {log_id}: {str(e)}")
        
        # Try to update log status if possible
        try:
            log = SMSLog.objects.get(id=log_id)
            log.status = 'FAILED'
            log.error_message = f'Task error: {str(e)}'
            log.save(update_fields=['status', 'error_message'])
        except:
            pass
        
        # Retry the task
        logger.warning(f"Retrying SMS {log_id} (attempt {self.request.retries + 1}/3)")
        raise self.retry(exc=e)
