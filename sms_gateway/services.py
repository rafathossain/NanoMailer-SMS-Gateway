"""
SMS Gateway Service - Handles the complete SMS sending flow

This service provides reusable functions for sending SMS that can be used
from views, API endpoints, Celery tasks, or management commands.

Flow:
1. Get user's assigned SMS provider (from profile or system default)
2. Validate sender_id belongs to the user
3. Create SMS log entry
4. Identify operator from recipient number
5. Calculate SMS count and cost
6. Deduct balance from user (with tracking to prevent double deduction)
7. Queue SMS to Celery for async processing
"""
import logging
import re
import time
from decimal import Decimal
from typing import Optional, Dict, Any, Tuple
from django.contrib.auth.models import User
from django.db import transaction
from core.models import SMSProvider, SenderID, UserSenderID, Profile
from .models import SMSLog, UserSMSRate

logger = logging.getLogger(__name__)


# Operator prefixes mapping for Bangladesh
OPERATOR_PREFIXES = {
    'grameenphone': ['013', '017'],
    'banglalink': ['014', '019'],
    'robi': ['018'],
    'airtel': ['016'],
    'teletalk': ['015'],
}


def identify_operator(phone_number: str) -> str:
    """
    Identify mobile operator from Bangladesh phone number.
    
    Args:
        phone_number: Phone number (e.g., 01712345678 or 8801712345678)
        
    Returns:
        Operator code (grameenphone, banglalink, robi, airtel, teletalk, unknown)
    """
    # Clean the number - keep only digits
    number = ''.join(filter(str.isdigit, phone_number))
    
    # Remove country code if present
    if number.startswith('88') and len(number) == 13:
        number = number[2:]  # Remove '88' to get 11 digit number
    
    # Check if it's a valid Bangladesh number (11 digits starting with 01)
    if len(number) != 11 or not number.startswith('01'):
        return 'unknown'
    
    # Get the prefix (first 3 digits)
    prefix = number[:3]
    
    # Match prefix to operator
    for operator, prefixes in OPERATOR_PREFIXES.items():
        if prefix in prefixes:
            return operator
    
    return 'unknown'


def calculate_sms_segments(message: str, is_unicode: Optional[bool] = None) -> int:
    """
    Calculate number of SMS segments needed for a message.
    
    Args:
        message: SMS message content
        is_unicode: Whether message is Unicode (auto-detected if not provided)
        
    Returns:
        Number of SMS segments
    """
    # Auto-detect Unicode
    if is_unicode is None:
        try:
            message.encode('ascii')
            is_unicode = False
        except UnicodeEncodeError:
            is_unicode = True
    
    # SMS character limits
    if is_unicode:
        max_chars = 70  # Unicode SMS limit
    else:
        max_chars = 160  # Standard SMS limit
    
    message_length = len(message)
    segments = (message_length + max_chars - 1) // max_chars  # Ceiling division
    
    return max(segments, 1)


def is_unicode_message(message: str) -> bool:
    """
    Check if message contains Unicode characters.
    
    Args:
        message: SMS message content
        
    Returns:
        True if message is Unicode, False otherwise
    """
    try:
        message.encode('ascii')
        return False
    except UnicodeEncodeError:
        return True


def detect_sms_type_from_sender_id(sender_id: str) -> str:
    """
    Detect SMS type (masking/non_masking) from sender_id.
    
    Rules:
    - If sender_id contains only digits (numeric) → non_masking
    - If sender_id contains letters → masking
    
    Args:
        sender_id: Sender ID string (e.g., '017XXXXXXXX' or 'MyBrand')
        
    Returns:
        'masking' or 'non_masking'
    """
    if not sender_id:
        return 'masking'  # Default fallback
    
    # Check if sender_id contains only digits (numeric)
    # Remove any whitespace for checking
    clean_sender_id = sender_id.strip()
    if clean_sender_id.isdigit():
        return 'non_masking'
    
    return 'masking'


def get_message_type(message: str) -> str:
    """
    Get message type (masking/non_masking) based on content.
    In Bangladesh context, masking typically means branded sender ID messages.
    For simplicity, we consider all messages as masking if sender_id is custom.
    
    Args:
        message: SMS message content
        
    Returns:
        'masking' or 'non_masking'
    """
    # For now, determine based on whether message is Unicode
    # This can be customized based on business logic
    if is_unicode_message(message):
        return 'masking'
    return 'non_masking'


def get_sms_rate(
    user: User, 
    operator: str, 
    message_type: str,
    provider: Optional[SMSProvider] = None
) -> Decimal:
    """
    Get SMS rate for a user based on operator and message type.
    Checks user-specific rates first, then falls back to provider defaults.
    
    Args:
        user: User instance
        operator: Operator code
        message_type: 'masking' or 'non_masking'
        provider: SMSProvider instance (optional)
        
    Returns:
        Rate per SMS as Decimal
    """
    # Try to get user-specific rate first
    user_rate = UserSMSRate.get_user_rate(user, operator, message_type)
    if user_rate is not None:
        return Decimal(str(user_rate))
    
    # Fall back to provider default rates
    if not provider:
        provider = SMSProvider.get_default_provider()
    
    if provider:
        if message_type == 'masking':
            return Decimal(str(provider.masking_rate))
        else:
            return Decimal(str(provider.non_masking_rate))
    
    # Ultimate fallback
    return Decimal('0.35') if message_type == 'masking' else Decimal('0.25')


def get_user_only_rate(
    user: User, 
    operator: str, 
    message_type: str
) -> Optional[Decimal]:
    """
    Get SMS rate for a user based on operator and message type.
    ONLY returns user-specific rates, never falls back to provider defaults.
    Used for user-facing cost calculations to avoid exposing provider costs.
    
    Args:
        user: User instance
        operator: Operator code
        message_type: 'masking' or 'non_masking'
        
    Returns:
        Rate per SMS as Decimal, or None if no user rate exists
    """
    user_rate = UserSMSRate.get_user_rate(user, operator, message_type)
    if user_rate is not None:
        return Decimal(str(user_rate))
    return None


def get_default_operator_rate(operator: str, message_type: str) -> Decimal:
    """
    Get default rate for an operator from DefaultRate settings.
    This is used as fallback when user has no custom rate set.
    
    Args:
        operator: Operator code (grameenphone, banglalink, robi, airtel, teletalk)
        message_type: 'masking' or 'non_masking'
        
    Returns:
        Rate per SMS as Decimal
    """
    from core.models import DefaultRate
    
    # Map operator codes to frontend codes
    operator_mapping = {
        'grameenphone': 'gp',
        'banglalink': 'bl',
        'robi': 'robi',
        'airtel': 'airtel',
        'teletalk': 'teletalk',
    }
    
    op_code = operator_mapping.get(operator, operator)
    
    try:
        default_rate = DefaultRate.get_instance()
        op_rates = default_rate.operator_rates.get(op_code, {})
        rate = op_rates.get(message_type, None)
        if rate is not None:
            return Decimal(str(rate))
    except Exception:
        pass
    
    # Ultimate fallback
    return Decimal('0.35') if message_type == 'masking' else Decimal('0.25')


def get_user_provider(user: User) -> Optional[SMSProvider]:
    """
    Get the SMS provider assigned to the user.
    Uses user's default_provider if set, otherwise falls back to system default.
    
    Args:
        user: User instance
        
    Returns:
        SMSProvider instance or None
    """
    # Check if user has a default provider set in their profile
    if hasattr(user, 'profile') and user.profile.default_provider:
        return user.profile.default_provider
    
    # Fall back to system default provider
    return SMSProvider.get_default_provider()


def validate_user_sender_id(sender_id: str, user: User) -> bool:
    """
    Validate that the sender_id belongs to the user.
    
    Args:
        sender_id: Sender ID string (e.g., 'MyBrand')
        user: User instance
        
    Returns:
        True if sender_id is valid for the user, False otherwise
    """
    if not sender_id:
        return False
    
    # Check if sender_id is assigned to the user
    return UserSenderID.objects.filter(
        user=user,
        sender_id__sender_id=sender_id,
        is_active=True
    ).exists()


def calculate_sms_cost(
    message: str,
    user: User,
    operator: Optional[str] = None,
    provider: Optional[SMSProvider] = None,
    user_only: bool = False,
    sender_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculate total cost for sending an SMS.
    
    Args:
        message: SMS message content
        user: User instance
        operator: Operator code (optional, will be auto-detected if not provided)
        provider: SMSProvider instance (optional)
        user_only: If True, only use user-specific rates (no provider fallback)
        sender_id: Sender ID (optional) - used to determine message type
        
    Returns:
        Dict with cost breakdown
    """
    # Calculate segments
    unicode_msg = is_unicode_message(message)
    segments = calculate_sms_segments(message, unicode_msg)
    
    # Determine message type from sender_id
    # Numeric sender_id = non-masking, Alphabetic = masking
    if sender_id:
        message_type = detect_sms_type_from_sender_id(sender_id)
    else:
        message_type = 'masking'  # Default fallback
    
    # Get rate
    if user_only:
        rate = get_user_only_rate(user, operator or 'unknown', message_type)
        if rate is None:
            # Fall back to default operator rate (not provider rate)
            rate = get_default_operator_rate(operator or 'unknown', message_type)
    else:
        rate = get_sms_rate(user, operator or 'unknown', message_type, provider)
    
    # Calculate total cost
    total_cost = rate * segments
    
    return {
        'message_length': len(message),
        'is_unicode': unicode_msg,
        'segments': segments,
        'message_type': message_type,
        'operator': operator or 'unknown',
        'rate_per_sms': rate,
        'total_cost': total_cost,
        'currency': 'BDT'
    }


@transaction.atomic
def deduct_sms_balance(log: SMSLog, amount: Decimal) -> bool:
    """
    Deduct SMS cost from user balance and update log.
    Uses atomic transaction to prevent race conditions.
    Checks balance_deducted flag to prevent double deduction.
    
    Args:
        log: SMSLog instance
        amount: Amount to deduct
        
    Returns:
        True if deduction successful, False otherwise
    """
    # Lock the log row to prevent concurrent updates
    log = SMSLog.objects.select_for_update().get(pk=log.pk)
    
    # Check if already deducted
    if log.balance_deducted:
        logger.info(f"Balance already deducted for SMS log {log.id}")
        return True
    
    # Get user profile with lock
    try:
        profile = Profile.objects.select_for_update().get(user=log.user)
    except Profile.DoesNotExist:
        logger.error(f"Profile not found for user {log.user.id}")
        return False
    
    # Check sufficient balance
    if profile.balance < amount:
        logger.warning(
            f"Insufficient balance for user {log.user.id}. "
            f"Required: {amount}, Available: {profile.balance}"
        )
        return False
    
    # Deduct balance
    profile.balance -= amount
    profile.save(update_fields=['balance'])
    
    # Update log
    log.balance_deducted = True
    log.deducted_amount = amount
    log.save(update_fields=['balance_deducted', 'deducted_amount'])
    
    logger.info(
        f"Balance deducted for SMS log {log.id}: {amount} BDT. "
        f"New balance: {profile.balance} BDT"
    )
    
    return True


@transaction.atomic
def refund_sms_balance(log: SMSLog) -> bool:
    """
    Refund SMS cost to user balance (e.g., if SMS failed permanently).
    Checks balance_deducted flag to prevent double refund.
    
    Args:
        log: SMSLog instance
        
    Returns:
        True if refund successful, False otherwise
    """
    # Lock the log row to prevent concurrent updates
    log = SMSLog.objects.select_for_update().get(pk=log.pk)
    
    # Check if balance was deducted
    if not log.balance_deducted:
        logger.info(f"No balance to refund for SMS log {log.id}")
        return True
    
    # Get user profile with lock
    try:
        profile = Profile.objects.select_for_update().get(user=log.user)
    except Profile.DoesNotExist:
        logger.error(f"Profile not found for user {log.user.id}")
        return False
    
    # Refund balance
    profile.balance += log.deducted_amount
    profile.save(update_fields=['balance'])
    
    # Update log
    log.balance_deducted = False
    log.deducted_amount = 0
    log.save(update_fields=['balance_deducted', 'deducted_amount'])
    
    logger.info(
        f"Balance refunded for SMS log {log.id}: {log.deducted_amount} BDT. "
        f"New balance: {profile.balance} BDT"
    )
    
    return True


def create_sms_log(
    user: User,
    recipient: str,
    message: str,
    sender_id: Optional[str] = None,
    provider: Optional[SMSProvider] = None
) -> SMSLog:
    """
    Create a new SMS log entry.
    
    Args:
        user: User instance
        recipient: Phone number
        message: SMS message
        sender_id: Sender ID (optional)
        provider: SMSProvider instance (optional)
        
    Returns:
        Created SMSLog instance
    """
    # Identify operator
    operator = identify_operator(recipient)
    
    # Calculate segments
    segments = calculate_sms_segments(message)
    
    # Detect message type from sender_id
    final_sender_id = sender_id or 'NanoMailer'
    message_type = detect_sms_type_from_sender_id(final_sender_id)
    
    log = SMSLog.objects.create(
        user=user,
        recipient=recipient,
        message=message,
        sender_id=final_sender_id,
        message_type=message_type,
        provider=provider,
        operator=operator,
        segments=segments,
        status='PENDING'
    )
    
    logger.info(f"SMS log created: {log.id} for user {user.id} (type: {message_type})")
    return log


def parse_recipients(recipients_str: str) -> list:
    """
    Parse comma-separated recipient string into list of cleaned phone numbers.
    
    Args:
        recipients_str: Comma-separated phone numbers (e.g., "01712345678, 01787654321")
        
    Returns:
        List of cleaned phone numbers
    """
    if not recipients_str:
        return []
    
    recipients = []
    for num in recipients_str.split(','):
        cleaned = num.strip()
        if cleaned:
            recipients.append(cleaned)
    
    return recipients


@transaction.atomic
def process_sms_request(
    user: User,
    recipient: str,
    message: str,
    sender_id: Optional[str] = None,
    skip_queue: bool = False
) -> Dict[str, Any]:
    """
    Process an SMS request with full flow:
    1. Parse multiple recipients from comma-separated string
    2. Get user's assigned provider
    3. Validate sender_id belongs to the user
    4. Calculate total cost for ALL recipients
    5. Check if user has sufficient balance for ALL SMS
    6. If insufficient balance, mark ALL as FAILED
    7. If sufficient balance, create log for each, deduct balance, and queue
    
    This is the main entry point for sending SMS. Can be used from:
    - Web views
    - API endpoints
    - Celery tasks
    - Management commands
    
    Args:
        user: User instance
        recipient: Phone number(s) - comma-separated for multiple
        message: SMS message content
        sender_id: Sender ID (optional)
        skip_queue: If True, skip Celery queuing (for testing/direct sending)
        
    Returns:
        Dict with result information:
        {
            'success': bool,
            'log_ids': list[int],
            'message': str,
            'total_cost': Decimal,
            'total_recipients': int,
            'successful': int,
            'failed': int,
            'balance_deducted': bool,
        }
    """
    # Step 1: Parse recipients
    recipients = parse_recipients(recipient)
    if not recipients:
        return {
            'success': False,
            'log_ids': [],
            'message': 'No valid recipients provided',
            'total_cost': Decimal('0'),
            'total_recipients': 0,
            'successful': 0,
            'failed': 0,
            'balance_deducted': False
        }
    
    total_recipients = len(recipients)
    
    # Step 2: Get user's assigned provider
    provider = get_user_provider(user)
    
    if not provider:
        logger.error(f"No SMS provider available for user {user.id}")
        # Create failed logs for all recipients
        log_ids = []
        for rec in recipients:
            log = SMSLog.objects.create(
                user=user,
                recipient=rec,
                message=message,
                sender_id=sender_id or 'NanoMailer',
                provider=None,
                operator=identify_operator(rec),
                segments=calculate_sms_segments(message),
                status='FAILED',
                error_message='No SMS provider configured'
            )
            log_ids.append(log.id)
        
        return {
            'success': False,
            'log_ids': log_ids,
            'message': 'No SMS provider configured',
            'total_cost': Decimal('0'),
            'total_recipients': total_recipients,
            'successful': 0,
            'failed': total_recipients,
            'balance_deducted': False
        }
    
    # Step 3: Validate sender_id belongs to the user
    if sender_id and not validate_user_sender_id(sender_id, user):
        logger.warning(f"User {user.id} attempted to use unauthorized sender_id: {sender_id}")
        # Create failed logs for all recipients
        log_ids = []
        for rec in recipients:
            log = SMSLog.objects.create(
                user=user,
                recipient=rec,
                message=message,
                sender_id=sender_id,
                provider=provider,
                operator=identify_operator(rec),
                segments=calculate_sms_segments(message),
                status='FAILED',
                error_message=f'Sender ID "{sender_id}" is not assigned to your account'
            )
            log_ids.append(log.id)
        
        return {
            'success': False,
            'log_ids': log_ids,
            'message': f'Sender ID "{sender_id}" is not assigned to your account',
            'total_cost': Decimal('0'),
            'total_recipients': total_recipients,
            'successful': 0,
            'failed': total_recipients,
            'balance_deducted': False
        }
    
    # Step 4: Check user profile
    if not hasattr(user, 'profile'):
        logger.error(f"User {user.id} has no profile")
        # Create failed logs for all recipients
        log_ids = []
        for rec in recipients:
            log = SMSLog.objects.create(
                user=user,
                recipient=rec,
                message=message,
                sender_id=sender_id or 'NanoMailer',
                provider=provider,
                operator=identify_operator(rec),
                segments=calculate_sms_segments(message),
                status='FAILED',
                error_message='User profile not found'
            )
            log_ids.append(log.id)
        
        return {
            'success': False,
            'log_ids': log_ids,
            'message': 'User profile not found',
            'total_cost': Decimal('0'),
            'total_recipients': total_recipients,
            'successful': 0,
            'failed': total_recipients,
            'balance_deducted': False
        }
    
    # Step 5: Validate all recipients have valid operators and calculate cost
    # Calculate cost for each recipient based on their operator
    total_cost = Decimal('0')
    segments_per_sms = 1
    recipient_costs = []  # Store cost info for each recipient
    
    for rec in recipients:
        operator = identify_operator(rec)
        
        # Check if operator is valid
        if operator == 'unknown':
            logger.warning(f"User {user.id} attempted to send SMS to invalid number: {rec}")
            # Create failed logs for all recipients
            log_ids = []
            for r in recipients:
                op = identify_operator(r)
                # Calculate what the cost would have been (for display purposes - use user-only rate)
                cost_info = calculate_sms_cost(
                    message=message,
                    user=user,
                    operator='grameenphone',  # Use a valid operator for cost estimate
                    provider=provider,
                    user_only=True,
                    sender_id=sender_id
                )
                log = SMSLog.objects.create(
                    user=user,
                    recipient=r,
                    message=message,
                    sender_id=sender_id or 'NanoMailer',
                    provider=provider,
                    operator=op,
                    segments=cost_info['segments'],
                    cost=cost_info['total_cost'],
                    status='FAILED',
                    error_message=f'Invalid phone number format: {rec}' if r == rec else 'Batch failed due to invalid number in request'
                )
                log_ids.append(log.id)
            
            # Calculate total cost for display (using user-only rate)
            display_cost_info = calculate_sms_cost(
                message=message,
                user=user,
                operator='grameenphone',
                provider=provider,
                user_only=True,
                sender_id=sender_id
            )
            
            return {
                'success': False,
                'log_ids': log_ids,
                'message': f'Invalid phone number: {rec}. Please provide valid Bangladeshi mobile numbers.',
                'total_cost': display_cost_info['total_cost'] * total_recipients,
                'total_recipients': total_recipients,
                'successful': 0,
                'failed': total_recipients,
                'balance_deducted': False
            }
        
        cost_info = calculate_sms_cost(
            message=message,
            user=user,
            operator=operator,
            provider=provider,
            user_only=True,
            sender_id=sender_id
        )
        total_cost += cost_info['total_cost']
        segments_per_sms = cost_info['segments']
        recipient_costs.append({'recipient': rec, 'operator': operator, 'cost_info': cost_info})
    
    # Step 6: Check if user has sufficient balance for ALL recipients
    if user.profile.balance < total_cost:
        logger.warning(
            f"Insufficient balance for user {user.id}. "
            f"Required: {total_cost} BDT, Available: {user.profile.balance} BDT"
        )
        # Create failed logs for all recipients with insufficient balance error
        log_ids = []
        for rc in recipient_costs:
            log = SMSLog.objects.create(
                user=user,
                recipient=rc['recipient'],
                message=message,
                sender_id=sender_id or 'NanoMailer',
                provider=provider,
                operator=rc['operator'],
                segments=rc['cost_info']['segments'],
                cost=rc['cost_info']['total_cost'],
                status='FAILED',
                error_message=f'Insufficient balance. Required: {total_cost} BDT for {total_recipients} SMS, Available: {user.profile.balance} BDT'
            )
            log_ids.append(log.id)
        
        return {
            'success': False,
            'log_ids': log_ids,
            'message': f'Insufficient balance. Required: {total_cost} BDT for {total_recipients} SMS',
            'total_cost': total_cost,
            'total_recipients': total_recipients,
            'successful': 0,
            'failed': total_recipients,
            'balance_deducted': False
        }
    
    # Step 7: Process each recipient - create logs, deduct balance, queue
    log_ids = []
    successful = 0
    failed = 0
    
    try:
        for rc in recipient_costs:
            rec = rc['recipient']
            rec_cost_info = rc['cost_info']
            
            # Create SMS log
            log = create_sms_log(
                user=user,
                recipient=rec,
                message=message,
                sender_id=sender_id,
                provider=provider
            )
            
            # Calculate internal cost (with provider fallback) for actual deduction
            # This ensures we charge the correct amount even if user has no custom rate
            internal_cost_info = calculate_sms_cost(
                message=message,
                user=user,
                operator=rc['operator'],
                provider=provider,
                user_only=False,  # Allow provider fallback for internal calculation
                sender_id=sender_id
            )
            internal_cost = internal_cost_info['total_cost']
            
            # Update log with user-facing cost (shows user's rate, not provider rate)
            log.cost = rec_cost_info['total_cost']
            log.save(update_fields=['cost'])
            
            # Deduct balance using internal cost (actual charge amount)
            deduction_success = deduct_sms_balance(log, internal_cost)
            
            if not deduction_success:
                # This shouldn't happen since we checked balance beforehand, but handle it
                log.status = 'FAILED'
                log.error_message = 'Failed to deduct balance'
                log.save(update_fields=['status', 'error_message'])
                failed += 1
            else:
                # Check if TEST_MODE is enabled
                from django.conf import settings
                test_mode = getattr(settings, 'TEST_MODE', False)
                
                if test_mode:
                    # TEST_MODE: Simulate success without actually sending
                    log.status = 'DELIVERED'
                    log.message_id = f'TEST_{log.id}_{int(time.time())}'
                    log.save(update_fields=['status', 'message_id'])
                    logger.info(f"SMS {log.id} simulated (TEST_MODE enabled) - marked as DELIVERED")
                elif skip_queue:
                    # Send immediately (skip Celery queue)
                    from .utils import send_sms_via_provider
                    send_sms_via_provider(
                        log_id=log.id,
                        recipient=rec,
                        message=message,
                        sender_id=sender_id or 'NanoMailer',
                        provider=provider
                    )
                else:
                    # Update status to QUEUED
                    log.status = 'QUEUED'
                    log.save(update_fields=['status'])
                    
                    # Queue to Celery for background processing
                    from .tasks import send_sms_task
                    send_sms_task.delay(log_id=log.id)
                    logger.info(f"SMS {log.id} queued to Celery for processing")
                
                successful += 1
            
            log_ids.append(log.id)
        
        logger.info(
            f"SMS batch processed for user {user.id}: "
            f"{successful} successful, {failed} failed, "
            f"total cost: {total_cost} BDT"
        )
        
        return {
            'success': successful > 0,
            'log_ids': log_ids,
            'message': f'{successful} of {total_recipients} SMS queued successfully. Cost: ৳{total_cost}',
            'total_cost': total_cost,
            'total_recipients': total_recipients,
            'successful': successful,
            'failed': failed,
            'balance_deducted': successful > 0
        }
        
    except Exception as e:
        logger.exception(f"Error processing SMS batch: {str(e)}")
        
        # Refund any deducted balances for logs in this batch
        for log_id in log_ids:
            try:
                log = SMSLog.objects.get(id=log_id)
                if log.balance_deducted:
                    refund_sms_balance(log)
                    log.status = 'FAILED'
                    log.error_message = f'Batch processing error: {str(e)}'
                    log.save(update_fields=['status', 'error_message'])
            except SMSLog.DoesNotExist:
                pass
        
        return {
            'success': False,
            'log_ids': log_ids,
            'message': f'Error processing SMS: {str(e)}',
            'total_cost': total_cost,
            'total_recipients': total_recipients,
            'successful': 0,
            'failed': total_recipients,
            'balance_deducted': False
        }


# Alias for backward compatibility and cleaner API
send_sms = process_sms_request
