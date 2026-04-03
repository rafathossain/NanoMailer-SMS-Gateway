"""
SMS Gateway utilities - integrates with core SMSProvider model
"""
import logging
from decimal import Decimal
from django.contrib.auth.models import User
from core.models import SMSProvider
from .revesms import ReveSMSProvider

logger = logging.getLogger(__name__)


def get_sms_provider(provider_instance=None):
    """
    Get SMS provider instance based on provider configuration
    
    Args:
        provider_instance: SMSProvider model instance (optional, uses default if not provided)
        
    Returns:
        Provider instance (ReveSMSProvider, etc.)
    """
    if not provider_instance:
        provider_instance = SMSProvider.get_default_provider()
    
    if not provider_instance:
        raise ValueError("No SMS provider configured")
    
    if provider_instance.provider_class == 'REVESMS':
        return ReveSMSProvider(provider_instance.credentials)
    else:
        raise ValueError(f"Unsupported provider class: {provider_instance.provider_class}")


def send_sms(recipient, message, sender_id=None, provider=None, user=None):
    """
    Send SMS using configured provider
    
    Args:
        recipient: Phone number (e.g., 01XXXXXXXXX)
        message: SMS message content
        sender_id: Sender ID (optional)
        provider: SMSProvider instance (optional, uses default if not provided)
        user: User instance for logging (optional)
        
    Returns:
        Dict with success status and response data
    """
    try:
        # Get provider instance
        sms_provider = get_sms_provider(provider)
        
        # If sender_id not provided, get from provider default
        if not sender_id and provider:
            sender_id = provider.credentials.get('sender_id')
        
        # Send SMS
        result = sms_provider.send_sms(
            recipient=recipient,
            message=message,
            sender_id=sender_id
        )
        
        # Log the SMS (if user provided)
        if user:
            from .models import SMSLog
            SMSLog.objects.create(
                user=user,
                recipient=recipient,
                message=message,
                sender_id=sender_id or 'Default',
                provider=provider or SMSProvider.get_default_provider(),
                status='SENT' if result.get('success') else 'FAILED',
                message_id=result.get('message_id'),
                response_data=result.get('response'),
                error_message=None if result.get('success') else result.get('message')
            )
        
        return result
        
    except Exception as e:
        logger.error(f"Error sending SMS: {str(e)}")
        
        # Log failed SMS
        if user:
            from .models import SMSLog
            SMSLog.objects.create(
                user=user,
                recipient=recipient,
                message=message,
                sender_id=sender_id or 'Default',
                provider=provider or SMSProvider.get_default_provider(),
                status='FAILED',
                error_message=str(e)
            )
        
        return {
            'success': False,
            'message': str(e),
            'response': None
        }


def check_balance(provider=None):
    """
    Check SMS provider balance
    
    Args:
        provider: SMSProvider instance (optional, uses default if not provided)
        
    Returns:
        Dict with balance info
    """
    try:
        sms_provider = get_sms_provider(provider)
        return sms_provider.check_balance()
    except Exception as e:
        logger.error(f"Error checking balance: {str(e)}")
        return {
            'success': False,
            'message': str(e),
            'response': None
        }


def send_bulk_sms(recipients, message, sender_id=None, provider=None, user=None):
    """
    Send SMS to multiple recipients
    
    Args:
        recipients: List of phone numbers
        message: SMS message content
        sender_id: Sender ID (optional)
        provider: SMSProvider instance (optional)
        user: User instance for logging (optional)
        
    Returns:
        Dict with success count and failed count
    """
    results = {
        'total': len(recipients),
        'success': 0,
        'failed': 0,
        'details': []
    }
    
    for recipient in recipients:
        result = send_sms(
            recipient=recipient,
            message=message,
            sender_id=sender_id,
            provider=provider,
            user=user
        )
        
        if result.get('success'):
            results['success'] += 1
        else:
            results['failed'] += 1
        
        results['details'].append({
            'recipient': recipient,
            'success': result.get('success'),
            'message': result.get('message')
        })
    
    return results


def get_sms_cost(message, is_unicode=False, provider=None, user=None):
    """
    Calculate SMS cost based on message length and type
    
    Args:
        message: SMS message
        is_unicode: Whether message is Unicode (auto-detected if not provided)
        provider: SMSProvider instance for rates (optional)
        user: User instance to check for custom rates (optional)
        
    Returns:
        Dict with cost info
    """
    from .models import UserSMSRate
    
    if not provider:
        provider = SMSProvider.get_default_provider()
    
    # Auto-detect Unicode
    if is_unicode is None:
        try:
            message.encode('ascii')
            is_unicode = False
        except UnicodeEncodeError:
            is_unicode = True
    
    # Get rates - check user custom rates first, then provider defaults
    message_type = 'masking' if is_unicode else 'non_masking'
    
    if is_unicode:
        max_chars = 70  # Unicode SMS limit
    else:
        max_chars = 160  # Standard SMS limit
    
    # Get effective rate using UserSMSRate model
    if user:
        rate = UserSMSRate.get_effective_rate(user, operator='default', message_type=message_type)
    else:
        if message_type == 'masking':
            rate = provider.masking_rate if provider else Decimal('0.35')
        else:
            rate = provider.non_masking_rate if provider else Decimal('0.25')
    
    message_length = len(message)
    segments = (message_length + max_chars - 1) // max_chars  # Ceiling division
    
    total_cost = Decimal(str(rate)) * segments
    
    return {
        'message_length': message_length,
        'is_unicode': is_unicode,
        'segments': segments,
        'rate_per_sms': rate,
        'total_cost': total_cost,
        'currency': 'BDT'
    }
