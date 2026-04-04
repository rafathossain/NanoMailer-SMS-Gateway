"""
Utility functions for payment gateway integration
Connects core PaymentGateway model with actual gateway implementations
"""
from decimal import Decimal
from core.models import PaymentGateway as GatewayConfig
from .factory import GatewayFactory
from .models import Transaction


def get_active_gateway():
    """Get the default active gateway configuration"""
    return GatewayConfig.get_default_gateway()


def initiate_payment(user, amount, customer_info, success_url, fail_url, cancel_url, **kwargs):
    """
    Initiate a payment using the configured gateway
    
    Args:
        user: User instance making the payment
        amount: Payment amount
        customer_info: Dict with customer details
        success_url: URL to redirect on success
        fail_url: URL to redirect on failure
        cancel_url: URL to redirect on cancellation
        **kwargs: Additional parameters
        
    Returns:
        Dict with payment URL or error message
    """
    # Get default gateway
    gateway_config = get_active_gateway()
    
    if not gateway_config:
        return {
            'success': False,
            'message': 'No active payment gateway configured'
        }
    
    # Check if gateway is active
    if not gateway_config.is_active:
        return {
            'success': False,
            'message': 'Payment gateway is currently inactive'
        }
    
    # Get gateway instance
    try:
        gateway = GatewayFactory.get_gateway(
            gateway_config.gateway_class,
            gateway_config.credentials
        )
    except ValueError as e:
        return {
            'success': False,
            'message': str(e)
        }
    
    # Calculate amounts using formula: X = A / (1 - r)
    # Where A = desired amount (what user wants to receive), r = fee rate
    # This ensures user receives exactly the amount they entered after fee deduction
    tdr = gateway_config.tdr or Decimal('0.00')
    tdr_rate = tdr / 100  # Convert percentage to decimal
    
    if tdr_rate < 1:
        total_amount = Decimal(str(amount)) / (1 - tdr_rate)
        tdr_amount = total_amount - Decimal(str(amount))
    else:
        # Fallback if TDR is 100% or more (shouldn't happen)
        total_amount = Decimal(str(amount))
        tdr_amount = Decimal('0.00')
    
    # Generate transaction ID
    transaction_id = Transaction.generate_transaction_id()
    
    # Create transaction record
    transaction = Transaction.objects.create(
        user=user,
        gateway=gateway_config,
        transaction_id=transaction_id,
        amount=amount,
        tdr_amount=tdr_amount,
        total_amount=total_amount,
        status='PENDING'
    )
    
    # Initiate payment with gateway (pass base amount, gateway will calculate total with TDR)
    result = gateway.initiate_payment(
        transaction_id=transaction_id,
        amount=amount,
        customer_info=customer_info,
        tdr=tdr,
        success_url=success_url,
        fail_url=fail_url,
        cancel_url=cancel_url,
        product_name='SMS Credit Recharge',
        product_category='Recharge',
        **kwargs
    )
    
    if result.get('success'):
        # Update transaction
        transaction.status = 'INITIATED'
        transaction.session_key = result.get('session_key')
        transaction.gateway_response = result
        transaction.save()
        
        return {
            'success': True,
            'gateway_url': result.get('gateway_url'),
            'transaction_id': transaction_id,
            'amount': amount,
            'tdr_amount': tdr_amount,
            'total_amount': total_amount
        }
    else:
        # Mark transaction as failed
        transaction.status = 'FAILED'
        transaction.gateway_response = result
        transaction.save()
        
        return {
            'success': False,
            'message': result.get('message', 'Failed to initiate payment'),
            'transaction_id': transaction_id
        }


def validate_payment(gateway_class, validation_data):
    """
    Validate a payment callback
    
    Args:
        gateway_class: String identifier for the gateway class
        validation_data: Data from gateway callback
        
    Returns:
        Dict with validation result
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"validate_payment called: gateway_class={gateway_class}, data={validation_data}")
    
    # Get gateway configuration
    try:
        gateway_config = GatewayConfig.objects.get(gateway_class=gateway_class, is_active=True)
        logger.info(f"Found gateway config: {gateway_config.name}")
    except GatewayConfig.DoesNotExist:
        logger.error(f"Gateway configuration not found for: {gateway_class}")
        return {
            'success': False,
            'message': 'Gateway configuration not found'
        }
    
    # Get gateway instance
    try:
        gateway = GatewayFactory.get_gateway(
            gateway_class,
            gateway_config.credentials
        )
        logger.info("Gateway instance created")
    except ValueError as e:
        logger.error(f"Failed to create gateway: {str(e)}")
        return {
            'success': False,
            'message': str(e)
        }
    
    # Validate payment
    result = gateway.validate_payment(validation_data)
    logger.info(f"Gateway validation result: {result}")
    
    # Update transaction if found
    transaction_id = result.get('transaction_id')
    logger.info(f"Transaction ID from result: {transaction_id}")
    
    if transaction_id:
        try:
            transaction = Transaction.objects.get(transaction_id=transaction_id)
            logger.info(f"Found transaction: {transaction}")
            transaction.validation_response = result
            
            if result.get('success'):
                logger.info(f"Marking transaction {transaction_id} as successful")
                transaction.mark_success(gateway_response=result)
                logger.info(f"Transaction {transaction_id} marked as successful, balance updated")
            else:
                logger.warning(f"Marking transaction {transaction_id} as failed: {result.get('message')}")
                transaction.mark_failed(reason=result.get('message'))
                
        except Transaction.DoesNotExist:
            logger.error(f"Transaction not found: {transaction_id}")
    else:
        logger.error("No transaction_id in validation result")
    
    return result


def get_transaction_status(transaction_id):
    """Get the status of a transaction"""
    try:
        transaction = Transaction.objects.get(transaction_id=transaction_id)
        return {
            'success': True,
            'transaction_id': transaction.transaction_id,
            'status': transaction.status,
            'amount': str(transaction.amount),
            'total_amount': str(transaction.total_amount),
            'created_at': transaction.created_at,
            'completed_at': transaction.completed_at
        }
    except Transaction.DoesNotExist:
        return {
            'success': False,
            'message': 'Transaction not found'
        }


def get_user_transactions(user, limit=10):
    """Get recent transactions for a user"""
    transactions = Transaction.objects.filter(user=user).order_by('-created_at')[:limit]
    return transactions
