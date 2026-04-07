"""
Views for payment gateway integration
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from .utils import initiate_payment, validate_payment, get_user_transactions
from .models import Transaction
from core.models import PaymentGateway


@login_required
def add_fund_view(request):
    """View for adding funds - payment initiation"""
    # Get all active payment gateways
    active_gateways = PaymentGateway.objects.filter(is_active=True).order_by('name')
    
    if not active_gateways.exists():
        messages.error(request, 'No active payment gateway available. Please contact support.')
        return redirect('dashboard')
    
    # Default to first gateway
    default_gateway = active_gateways.first()
    
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', '0'))
            gateway_id = request.POST.get('gateway_id')
            
            if amount <= 0:
                messages.error(request, 'Please enter a valid amount')
                return redirect('payment_gateway:add_fund')
            
            if amount < 100:
                messages.error(request, 'Minimum recharge amount is 100 BDT')
                return redirect('payment_gateway:add_fund')
            
            # Get selected gateway
            if gateway_id:
                try:
                    gateway = PaymentGateway.objects.get(id=gateway_id, is_active=True)
                except PaymentGateway.DoesNotExist:
                    gateway = default_gateway
            else:
                gateway = default_gateway
            
            # Build callback URLs
            success_url = request.build_absolute_uri(reverse('payment_gateway:payment_success'))
            fail_url = request.build_absolute_uri(reverse('payment_gateway:payment_fail'))
            cancel_url = request.build_absolute_uri(reverse('payment_gateway:payment_cancel'))
            
            # Customer info
            customer_info = {
                'name': request.user.get_full_name() or request.user.username,
                'email': request.user.email or f'user{request.user.id}@example.com',
                'phone': request.user.profile.mobile_number if hasattr(request.user, 'profile') else '01700000000',
                'user_id': request.user.id
            }
            
            # Initiate payment
            result = initiate_payment(
                user=request.user,
                amount=amount,
                customer_info=customer_info,
                success_url=success_url,
                fail_url=fail_url,
                cancel_url=cancel_url
            )
            
            if result.get('success'):
                # Redirect to gateway URL
                return redirect(result['gateway_url'])
            else:
                messages.error(request, result.get('message', 'Failed to initiate payment'))
                return redirect('payment_gateway:add_fund')
                
        except (InvalidOperation, ValueError):
            messages.error(request, 'Invalid amount entered')
            return redirect('payment_gateway:add_fund')
    
    context = {
        'gateways': active_gateways,
        'default_gateway': default_gateway,
        'transactions': get_user_transactions(request.user, limit=5)
    }
    return render(request, 'payment_gateway/add_fund.html', context)


@login_required
def transactions_view(request):
    """View for transaction history - shows only successful transactions by default"""
    from django.db.models import Sum, Count, Q
    
    # Show only completed transactions by default
    transactions = Transaction.objects.filter(user=request.user, status='COMPLETED').order_by('-created_at')
    
    # Allow filtering by status if explicitly provided
    status_filter = request.GET.get('status')
    if status_filter:
        if status_filter.upper() == 'ALL':
            transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')
        else:
            transactions = Transaction.objects.filter(user=request.user, status=status_filter.upper()).order_by('-created_at')
    
    # Calculate summary stats
    total_recharge = Transaction.objects.filter(
        user=request.user
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    total_completed = Transaction.objects.filter(
        user=request.user,
        status='COMPLETED'
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    total_pending = Transaction.objects.filter(
        user=request.user,
        status__in=['PENDING', 'INITIATED']
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    total_count = Transaction.objects.filter(user=request.user).count()
    
    context = {
        'transactions': transactions,
        'total_recharge': total_recharge,
        'total_completed': total_completed,
        'total_pending': total_pending,
        'total_count': total_count,
    }
    return render(request, 'payment_gateway/transactions.html', context)


@csrf_exempt
def payment_success_view(request):
    """Handle successful payment callback"""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"payment_success_view called: method={request.method}")
    
    # Check both GET and POST for the data
    data = request.POST if request.POST else request.GET
    
    logger.info(f"Data received: {data}")
    
    val_id = data.get('val_id')
    tran_id = data.get('tran_id') or data.get('mer_txnid')
    amount = data.get('amount')
    status = data.get('status') or data.get('pay_status')
    
    logger.info(f"Extracted: val_id={val_id}, tran_id={tran_id}, amount={amount}, status={status}")
    
    if not tran_id:
        logger.error("No transaction ID found in callback data")
        messages.error(request, 'Invalid callback: Transaction ID missing')
        return redirect('payment_gateway:add_fund')
    
    # Try to find the transaction to determine which gateway was used
    gateway_class = 'SSLCOMMERZ'  # Default to SSLCommerz for backward compatibility
    try:
        transaction = Transaction.objects.get(transaction_id=tran_id)
        if transaction.gateway:
            gateway_class = transaction.gateway.gateway_class
            logger.info(f"Found transaction with gateway: {gateway_class}")
    except Transaction.DoesNotExist:
        logger.warning(f"Transaction not found: {tran_id}")
    
    # Check if this is a valid success callback
    # SSLCommerz uses 'VALID' status, aamarPay uses 'SUCCESSFUL' or 'Successful'
    is_valid_status = (
        status in ['VALID', 'SUCCESSFUL', 'Successful'] or 
        (gateway_class == 'AAMARPAY' and data.get('pay_status') in ['SUCCESSFUL', 'Successful'])
    )
    
    if is_valid_status:
        # Prepare validation data based on gateway
        if gateway_class == 'AAMARPAY':
            validation_data = {
                'mer_txnid': tran_id,
                'pay_txnid': data.get('pay_txnid'),
                'amount': amount,
                'pay_status': data.get('pay_status'),
                'pg_txnid': data.get('pg_txnid'),
            }
        else:  # SSLCOMMERZ
            validation_data = {
                'tran_id': tran_id,
                'val_id': val_id,
                'amount': amount,
                'status': status
            }
        
        logger.info(f"Calling validate_payment for {gateway_class} with: {validation_data}")
        result = validate_payment(gateway_class, validation_data)
        logger.info(f"validate_payment result: {result}")
        
        if result.get('success'):
            messages.success(request, f'Payment of {amount} BDT was successful!')
            logger.info(f"Payment success message shown to user")
        else:
            messages.warning(request, 'Payment initiated but validation pending. Balance will be updated shortly.')
            logger.warning(f"Payment validation failed: {result.get('message')}")
    else:
        logger.error(f"Invalid callback: tran_id={tran_id}, status={status}")
        messages.error(request, 'Payment failed or was cancelled')
    
    return redirect('payment_gateway:add_fund')


@csrf_exempt
def payment_fail_view(request):
    """Handle failed payment callback"""
    data = request.POST if request.POST else request.GET
    tran_id = data.get('tran_id')
    
    if tran_id:
        # Update transaction status
        Transaction.objects.filter(transaction_id=tran_id).update(status='FAILED')
    
    messages.error(request, 'Payment failed. Please try again.')
    return redirect('payment_gateway:add_fund')


@csrf_exempt
def payment_cancel_view(request):
    """Handle cancelled payment callback"""
    data = request.POST if request.POST else request.GET
    tran_id = data.get('tran_id')
    
    if tran_id:
        # Update transaction status
        Transaction.objects.filter(transaction_id=tran_id).update(status='CANCELLED')
    
    messages.warning(request, 'Payment was cancelled.')
    return redirect('payment_gateway:add_fund')


@login_required
def transaction_detail_view(request, transaction_id):
    """View for transaction details"""
    transaction = get_object_or_404(Transaction, transaction_id=transaction_id, user=request.user)
    context = {
        'transaction': transaction
    }
    return render(request, 'payment_gateway/transaction_detail.html', context)


# API Endpoints
@login_required
def api_check_transaction_status(request, transaction_id):
    """AJAX endpoint to check transaction status"""
    try:
        transaction = Transaction.objects.get(transaction_id=transaction_id, user=request.user)
        return JsonResponse({
            'success': True,
            'status': transaction.status,
            'amount': str(transaction.amount),
            'total_amount': str(transaction.total_amount),
            'created_at': transaction.created_at.isoformat(),
            'completed_at': transaction.completed_at.isoformat() if transaction.completed_at else None
        })
    except Transaction.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Transaction not found'
        }, status=404)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def manual_add_fund_view(request):
    """View for superuser to manually add funds to a user account"""
    from django.contrib.auth.models import User
    from core.models import PaymentGateway
    
    # Get all users for dropdown
    users = User.objects.select_related('profile').all().order_by('email')
    
    # Get active gateways for reference
    gateways = PaymentGateway.objects.filter(is_active=True)
    
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        amount = request.POST.get('amount', '0').strip()
        payment_method = request.POST.get('payment_method', '').strip()
        transaction_id = request.POST.get('transaction_id', '').strip()
        notes = request.POST.get('notes', '').strip()
        
        # Validation
        errors = []
        
        if not user_id:
            errors.append('Please select a user')
        
        try:
            amount_decimal = Decimal(amount)
            if amount_decimal <= 0:
                errors.append('Amount must be greater than 0')
        except (InvalidOperation, ValueError):
            errors.append('Invalid amount entered')
        
        if not payment_method:
            errors.append('Payment method is required')
        
        if not transaction_id:
            errors.append('Transaction ID is required')
        
        # Check if transaction ID already exists
        if transaction_id and Transaction.objects.filter(transaction_id=transaction_id).exists():
            errors.append(f'Transaction ID "{transaction_id}" already exists')
        
        if errors:
            for error in errors:
                messages.error(request, error)
            context = {
                'users': users,
                'gateways': gateways,
                'form_data': {
                    'user_id': user_id,
                    'amount': amount,
                    'payment_method': payment_method,
                    'transaction_id': transaction_id,
                    'notes': notes,
                }
            }
            return render(request, 'payment_gateway/manual_add_fund.html', context)
        
        # Get the user
        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            messages.error(request, 'User not found')
            return redirect('payment_gateway:manual_add_fund')
        
        # Get or create a default gateway for this transaction
        gateway = PaymentGateway.objects.filter(is_active=True).first()
        
        # Create completed transaction
        transaction = Transaction.objects.create(
            user=target_user,
            gateway=gateway,
            transaction_id=transaction_id,
            gateway_transaction_id=transaction_id,
            amount=amount_decimal,
            tdr_amount=Decimal('0.00'),
            total_amount=amount_decimal,
            status='COMPLETED',
            gateway_response={
                'manual_entry': True,
                'added_by': request.user.email,
                'payment_method': payment_method,
                'notes': notes,
            },
            validation_response={
                'manual_entry': True,
                'added_by': request.user.email,
                'added_at': timezone.now().isoformat(),
            },
            completed_at=timezone.now()
        )
        
        # Add balance to user profile
        if hasattr(target_user, 'profile'):
            target_user.profile.deposit(amount_decimal)
        
        messages.success(
            request, 
            f'Successfully added ৳{amount_decimal} to {target_user.email}\'s account. '
            f'Transaction ID: {transaction_id}'
        )
        return redirect('payment_gateway:manual_add_fund')
    
    context = {
        'users': users,
        'gateways': gateways,
    }
    return render(request, 'payment_gateway/manual_add_fund.html', context)
