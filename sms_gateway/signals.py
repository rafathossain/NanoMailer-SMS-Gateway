"""
SMS Gateway Signals - Automatic balance refund on SMS failure

This module uses Django signals to automatically refund user balance
when an SMS fails to deliver after balance has been deducted.
"""
import logging
from django.db import transaction
from django.db.models.signals import post_save

logger = logging.getLogger(__name__)


def refund_on_sms_failure(sender, instance, created, **kwargs):
    """
    Signal handler to automatically refund balance when an SMS fails.
    
    This is triggered whenever an SMSLog is saved. If:
    1. The status is FAILED
    2. Balance was deducted for this SMS
    3. Balance hasn't been refunded yet
    
    Then the deducted amount is refunded to the user's balance.
    
    Note: We don't refund for DELIVERED or SENT status as those indicate
    successful SMS delivery through the gateway.
    """
    # Only process if status is FAILED
    if instance.status != 'FAILED':
        return
    
    # Only refund if balance was deducted and not already refunded
    if not instance.balance_deducted or instance.deducted_amount <= 0:
        return
    
    # Use atomic transaction to prevent race conditions
    with transaction.atomic():
        # Re-fetch the log with select_for_update to prevent concurrent updates
        try:
            log = sender.objects.select_for_update().get(pk=instance.pk)
        except sender.DoesNotExist:
            return
        
        # Double-check conditions after locking
        if log.status != 'FAILED' or not log.balance_deducted or log.deducted_amount <= 0:
            return
        
        # Get user profile with lock
        try:
            from core.models import Profile
            profile = Profile.objects.select_for_update().get(user=log.user)
        except Profile.DoesNotExist:
            logger.error(f"Cannot refund SMS {log.id}: Profile not found for user {log.user.id}")
            return
        
        # Calculate refund amount
        refund_amount = log.deducted_amount
        
        # Refund the balance
        profile.balance += refund_amount
        profile.save(update_fields=['balance'])
        
        # Update log to mark as refunded (by clearing deducted fields)
        log.balance_deducted = False
        log.deducted_amount = 0
        # Keep the cost field for record purposes, just mark as refunded
        log.save(update_fields=['balance_deducted', 'deducted_amount'])
        
        logger.info(
            f"Balance refunded for failed SMS {log.id}: {refund_amount} BDT "
            f"to user {log.user.id}. New balance: {profile.balance} BDT"
        )


def connect_signals():
    """Connect signal handlers. Called from AppConfig.ready()"""
    from .models import SMSLog
    post_save.connect(refund_on_sms_failure, sender=SMSLog)
    logger.info("SMS refund signal connected to SMSLog model")


def check_and_refund_failed_sms(log_id=None):
    """
    Utility function to manually trigger refund check for a specific SMS or all failed SMS.
    
    This can be used:
    - For manual refund of specific SMS
    - In management commands to cleanup any missed refunds
    - In Celery tasks for bulk refund processing
    
    Args:
        log_id: Specific SMSLog ID to check. If None, checks all failed SMS.
        
    Returns:
        Dict with refund statistics
    """
    from .models import SMSLog
    from core.models import Profile
    
    stats = {
        'checked': 0,
        'refunded': 0,
        'total_refund_amount': 0,
        'errors': []
    }
    
    # Build query
    query = SMSLog.objects.filter(status='FAILED', balance_deducted=True)
    if log_id:
        query = query.filter(id=log_id)
    
    for log in query:
        stats['checked'] += 1
        
        try:
            with transaction.atomic():
                # Lock log and profile
                locked_log = SMSLog.objects.select_for_update().get(pk=log.pk)
                profile = Profile.objects.select_for_update().get(user=log.user)
                
                if locked_log.balance_deducted and locked_log.deducted_amount > 0:
                    # Perform refund
                    refund_amount = locked_log.deducted_amount
                    profile.balance += refund_amount
                    profile.save(update_fields=['balance'])
                    
                    locked_log.balance_deducted = False
                    locked_log.deducted_amount = 0
                    locked_log.save(update_fields=['balance_deducted', 'deducted_amount'])
                    
                    stats['refunded'] += 1
                    stats['total_refund_amount'] += float(refund_amount)
                    
                    logger.info(f"Manual refund: SMS {log.id}, Amount: {refund_amount} BDT")
                    
        except Exception as e:
            error_msg = f"Error refunding SMS {log.id}: {str(e)}"
            logger.error(error_msg)
            stats['errors'].append(error_msg)
    
    return stats
