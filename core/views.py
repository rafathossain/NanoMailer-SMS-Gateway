from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from decimal import Decimal
import json
import logging
from .models import DefaultRate, SMSProvider, SenderID, PaymentGateway, Profile, UserSenderID

# Logger
general_logger = logging.getLogger('general')


@login_required
def dashboard_view(request):
    """Dashboard view with user-specific statistics"""
    from sms_gateway.models import SMSLog
    from django.db.models import Sum, Count, Q
    from datetime import datetime, timedelta
    
    user = request.user
    
    # Get user's wallet balance
    wallet_balance = user.profile.balance if hasattr(user, 'profile') else Decimal('0.00')
    
    # Get SMS statistics
    sms_logs = SMSLog.objects.filter(user=user)
    
    # Total SMS sent (SENT + DELIVERED status)
    total_sms_sent = sms_logs.filter(
        status__in=['SENT', 'DELIVERED']
    ).count()
    
    # Masking SMS count
    masking_sms_count = sms_logs.filter(
        message_type='masking',
        status__in=['SENT', 'DELIVERED']
    ).count()
    
    # Non-Masking SMS count
    non_masking_sms_count = sms_logs.filter(
        message_type='non_masking',
        status__in=['SENT', 'DELIVERED']
    ).count()
    
    # SMS data for chart (last 30 days)
    today = datetime.now().date()
    thirty_days_ago = today - timedelta(days=30)
    
    # Check if user has any SMS data
    has_sms_data = sms_logs.filter(
        status__in=['SENT', 'DELIVERED'],
        created_at__date__gte=thirty_days_ago
    ).exists()
    
    # Prepare chart data - daily SMS count for last 30 days
    chart_data = []
    chart_labels = []
    
    for i in range(30, -1, -1):
        date = today - timedelta(days=i)
        chart_labels.append(date.strftime('%d %b'))
        
        daily_count = sms_logs.filter(
            status__in=['SENT', 'DELIVERED'],
            created_at__date=date
        ).count()
        chart_data.append(daily_count)
    
    context = {
        'wallet_balance': wallet_balance,
        'total_sms_sent': total_sms_sent,
        'masking_sms_count': masking_sms_count,
        'non_masking_sms_count': non_masking_sms_count,
        'has_sms_data': has_sms_data,
        'chart_labels': chart_labels,
        'chart_data': chart_data,
    }
    
    return render(request, 'core/dashboard.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def sms_rates_view(request):
    """View for managing SMS rates for all operators."""
    default_rate = DefaultRate.get_instance()
    
    # Define operators
    operators = {
        'gp': 'Grameenphone',
        'bl': 'Banglalink',
        'robi': 'Robi',
        'airtel': 'Airtel',
        'teletalk': 'Teletalk',
    }
    
    if request.method == 'POST':
        try:
            # Update operator-specific rates (stored in nested JSON)
            # Format: {"gp": {"masking": 0.30, "non_masking": 0.25}, ...}
            operator_rates = {}
            
            for op_code in operators.keys():
                masking_key = f'{op_code}_masking'
                non_masking_key = f'{op_code}_non_masking'
                masking_val = request.POST.get(masking_key, '').strip()
                non_masking_val = request.POST.get(non_masking_key, '').strip()
                
                op_rate = {}
                if masking_val:
                    op_rate['masking'] = float(masking_val)
                if non_masking_val:
                    op_rate['non_masking'] = float(non_masking_val)
                
                if op_rate:
                    operator_rates[op_code] = op_rate
            
            default_rate.operator_rates = operator_rates
            default_rate.save()
            
            messages.success(request, 'SMS rates updated successfully!')
            return redirect('sms_rates')
            
        except ValueError:
            messages.error(request, 'Invalid rate values. Please enter valid numbers.')
    
    # Build operators list with their rates for the template
    operators_list = []
    for code, name in operators.items():
        op_data = default_rate.operator_rates.get(code, {})
        operators_list.append({
            'code': code,
            'name': name,
            'masking_rate': op_data.get('masking'),
            'non_masking_rate': op_data.get('non_masking'),
        })
    
    # Get sender IDs for display
    sender_ids = SenderID.objects.select_related('provider').all().order_by('-created_at')
    
    context = {
        'operators': operators_list,
        'sender_ids': sender_ids,
    }
    return render(request, 'core/sms_rates.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def provider_view(request):
    if request.method == 'POST':
        action = request.POST.get('action', '')
        
        if action == 'add':
            name = request.POST.get('name', '').strip()
            provider_class = request.POST.get('provider_class', '').strip()
            credentials_json = request.POST.get('credentials_json', '').strip()
            masking_rate = request.POST.get('masking_rate', '').strip()
            non_masking_rate = request.POST.get('non_masking_rate', '').strip()
            
            if name and provider_class:
                # Parse credentials JSON
                try:
                    credentials = json.loads(credentials_json) if credentials_json else {}
                except json.JSONDecodeError:
                    messages.error(request, 'Invalid JSON format for credentials.')
                    return redirect('provider')
                
                # Parse rates
                try:
                    masking_rate_val = float(masking_rate) if masking_rate else 0.35
                    non_masking_rate_val = float(non_masking_rate) if non_masking_rate else 0.25
                except ValueError:
                    messages.error(request, 'Invalid rate values.')
                    return redirect('provider')
                
                provider = SMSProvider.objects.create(
                    name=name,
                    provider_class=provider_class,
                    credentials=credentials,
                    masking_rate=masking_rate_val,
                    non_masking_rate=non_masking_rate_val
                )
                messages.success(request, f'Provider "{name}" added successfully!')
            else:
                messages.error(request, 'Please provide all required fields.')
                
        elif action == 'edit':
            provider_id = request.POST.get('provider_id')
            name = request.POST.get('name', '').strip()
            provider_class = request.POST.get('provider_class', '').strip()
            credentials_json = request.POST.get('credentials_json', '').strip()
            masking_rate = request.POST.get('masking_rate', '').strip()
            non_masking_rate = request.POST.get('non_masking_rate', '').strip()
            
            if not name or not provider_class:
                messages.error(request, 'Provider name and class are required.')
                return redirect('provider')
            
            try:
                provider = SMSProvider.objects.get(id=provider_id)
                
                # Parse credentials JSON
                try:
                    credentials = json.loads(credentials_json) if credentials_json else {}
                except json.JSONDecodeError:
                    messages.error(request, 'Invalid JSON format for credentials.')
                    return redirect('provider')
                
                # Parse rates
                try:
                    masking_rate_val = float(masking_rate) if masking_rate else 0.35
                    non_masking_rate_val = float(non_masking_rate) if non_masking_rate else 0.25
                except ValueError:
                    messages.error(request, 'Invalid rate values.')
                    return redirect('provider')
                
                provider.name = name
                provider.provider_class = provider_class
                provider.credentials = credentials
                provider.masking_rate = masking_rate_val
                provider.non_masking_rate = non_masking_rate_val
                provider.save()
                
                messages.success(request, f'Provider "{name}" updated successfully!')
            except SMSProvider.DoesNotExist:
                messages.error(request, 'Provider not found.')
                
        elif action == 'delete':
            provider_id = request.POST.get('provider_id')
            try:
                provider = SMSProvider.objects.get(id=provider_id)
                provider.delete()
                messages.success(request, 'Provider deleted successfully!')
            except SMSProvider.DoesNotExist:
                messages.error(request, 'Provider not found.')
        
        elif action == 'send_test_sms':
            provider_id = request.POST.get('provider_id')
            mobile_number = request.POST.get('mobile_number', '').strip()
            message = request.POST.get('message', '').strip()
            sender_id = request.POST.get('sender_id', '').strip()
            
            if not mobile_number or not message:
                messages.error(request, 'Mobile number and message are required.')
                return redirect('provider')
            
            try:
                provider = SMSProvider.objects.get(id=provider_id)
                
                # Send test SMS directly without logging
                from sms_gateway.revesms import ReveSMSProvider
                
                sms_provider = ReveSMSProvider(provider.credentials)
                result = sms_provider.send_sms(
                    recipient=mobile_number,
                    message=message,
                    sender_id=sender_id if sender_id else None
                )
                
                if result.get('success'):
                    messages.success(
                        request, 
                        f'Test SMS sent successfully! Message ID: {result.get("message_id", "N/A")}'
                    )
                else:
                    messages.error(
                        request, 
                        f'Failed to send test SMS: {result.get("message", "Unknown error")}'
                    )
                    
            except SMSProvider.DoesNotExist:
                messages.error(request, 'Provider not found.')
            except Exception as e:
                messages.error(request, f'Error sending test SMS: {str(e)}')
            
            return redirect('provider')
        
        elif action == 'sync_balance':
            provider_id = request.POST.get('provider_id')
            
            try:
                provider = SMSProvider.objects.get(id=provider_id)
                
                # Check balance using the provider
                from sms_gateway.revesms import ReveSMSProvider
                
                sms_provider = ReveSMSProvider(provider.credentials)
                result = sms_provider.check_balance()
                
                if result.get('success'):
                    provider.balance = result.get('balance', 0)
                    provider.balance_last_updated = timezone.now()
                    provider.save()
                    messages.success(
                        request, 
                        f'Balance synced successfully! Current balance: ঳{provider.balance}'
                    )
                else:
                    messages.error(
                        request, 
                        f'Failed to sync balance: {result.get("message", "Unknown error")}'
                    )
                    
            except SMSProvider.DoesNotExist:
                messages.error(request, 'Provider not found.')
            except Exception as e:
                messages.error(request, f'Error syncing balance: {str(e)}')
            
            return redirect('provider')
        
        elif action == 'set_default':
            provider_id = request.POST.get('provider_id')
            
            try:
                provider = SMSProvider.objects.get(id=provider_id)
                provider.is_default = True
                provider.save()
                messages.success(request, f'"{provider.name}" is now the default provider.')
            except SMSProvider.DoesNotExist:
                messages.error(request, 'Provider not found.')
            
            return redirect('provider')
    
    providers = SMSProvider.objects.all().order_by('-is_default', '-created_at')
    context = {
        'providers': providers,
        'provider_choices': SMSProvider.PROVIDER_CHOICES,
    }
    return render(request, 'core/provider.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def sender_id_view(request):
    if request.method == 'POST':
        action = request.POST.get('action', '')
        
        if action == 'add':
            provider_id = request.POST.get('provider', '').strip()
            sender_id_text = request.POST.get('sender_id', '').strip()
            
            if provider_id and sender_id_text:
                try:
                    provider = SMSProvider.objects.get(id=provider_id)
                    # Check if sender ID already exists for this provider
                    if SenderID.objects.filter(provider=provider, sender_id=sender_id_text).exists():
                        messages.error(request, f'Sender ID "{sender_id_text}" already exists for this provider.')
                    else:
                        SenderID.objects.create(
                            provider=provider,
                            sender_id=sender_id_text
                        )
                        messages.success(request, f'Sender ID "{sender_id_text}" added successfully!')
                except SMSProvider.DoesNotExist:
                    messages.error(request, 'Selected provider not found.')
            else:
                messages.error(request, 'Please provide all required fields.')
                
        elif action == 'delete':
            sender_id_id = request.POST.get('sender_id_id')
            try:
                sender_id = SenderID.objects.get(id=sender_id_id)
                sender_id.delete()
                messages.success(request, 'Sender ID deleted successfully!')
            except SenderID.DoesNotExist:
                messages.error(request, 'Sender ID not found.')
    
    sender_ids = SenderID.objects.all().select_related('provider').order_by('-created_at')
    providers = SMSProvider.objects.filter(is_active=True)
    context = {
        'sender_ids': sender_ids,
        'providers': providers,
    }
    return render(request, 'core/sender_id.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def payment_gateway_view(request):
    if request.method == 'POST':
        action = request.POST.get('action', '')
        
        if action == 'add':
            name = request.POST.get('name', '').strip()
            gateway_class = request.POST.get('gateway_class', '').strip()
            credentials_json = request.POST.get('credentials_json', '').strip()
            tdr = request.POST.get('tdr', '').strip()
            logo = request.FILES.get('logo')
            
            if name and gateway_class:
                # Parse credentials JSON
                try:
                    credentials = json.loads(credentials_json) if credentials_json else {}
                except json.JSONDecodeError:
                    messages.error(request, 'Invalid JSON format for credentials.')
                    return redirect('payment_gateway')
                
                # Parse TDR
                try:
                    tdr_val = float(tdr) if tdr else 0.00
                except ValueError:
                    messages.error(request, 'Invalid TDR value.')
                    return redirect('payment_gateway')
                
                gateway = PaymentGateway.objects.create(
                    name=name,
                    gateway_class=gateway_class,
                    credentials=credentials,
                    tdr=tdr_val
                )
                
                # Save logo if provided
                if logo:
                    gateway.logo = logo
                    gateway.save()
                
                messages.success(request, f'Payment gateway "{name}" added successfully!')
            else:
                messages.error(request, 'Please provide all required fields.')
                
        elif action == 'edit':
            gateway_id = request.POST.get('gateway_id')
            name = request.POST.get('name', '').strip()
            gateway_class = request.POST.get('gateway_class', '').strip()
            credentials_json = request.POST.get('credentials_json', '').strip()
            tdr = request.POST.get('tdr', '').strip()
            logo = request.FILES.get('logo')
            clear_logo = request.POST.get('clear_logo') == 'on'
            
            try:
                gateway = PaymentGateway.objects.get(id=gateway_id)
                if name and gateway_class:
                    # Parse credentials JSON
                    try:
                        credentials = json.loads(credentials_json) if credentials_json else {}
                    except json.JSONDecodeError:
                        messages.error(request, 'Invalid JSON format for credentials.')
                        return redirect('payment_gateway')
                    
                    # Parse TDR
                    try:
                        tdr_val = float(tdr) if tdr else 0.00
                    except ValueError:
                        messages.error(request, 'Invalid TDR value.')
                        return redirect('payment_gateway')
                    
                    gateway.name = name
                    gateway.gateway_class = gateway_class
                    gateway.credentials = credentials
                    gateway.tdr = tdr_val
                    
                    # Handle logo update
                    if clear_logo:
                        gateway.logo.delete(save=False)
                        gateway.logo = None
                    elif logo:
                        gateway.logo = logo
                    
                    gateway.save()
                    messages.success(request, f'Payment gateway "{name}" updated successfully!')
                else:
                    messages.error(request, 'Please provide all required fields.')
            except PaymentGateway.DoesNotExist:
                messages.error(request, 'Payment gateway not found.')
                
        elif action == 'toggle_status':
            gateway_id = request.POST.get('gateway_id')
            try:
                gateway = PaymentGateway.objects.get(id=gateway_id)
                gateway.is_active = not gateway.is_active
                gateway.save()
                status = 'activated' if gateway.is_active else 'deactivated'
                messages.success(request, f'Payment gateway "{gateway.name}" {status} successfully!')
            except PaymentGateway.DoesNotExist:
                messages.error(request, 'Payment gateway not found.')
                
        elif action == 'delete':
            gateway_id = request.POST.get('gateway_id')
            try:
                gateway = PaymentGateway.objects.get(id=gateway_id)
                gateway.delete()
                messages.success(request, 'Payment gateway deleted successfully!')
            except PaymentGateway.DoesNotExist:
                messages.error(request, 'Payment gateway not found.')
    
    gateways = PaymentGateway.objects.all().order_by('-created_at')
    context = {
        'gateways': gateways,
        'gateway_choices': PaymentGateway.GATEWAY_CHOICES,
    }
    return render(request, 'core/payment_gateway.html', context)


@login_required
@login_required
def send_sms_view(request):
    """Send SMS view with user's assigned sender IDs and rates"""
    from sms_gateway.models import UserSMSRate
    from sms_gateway.services import process_sms_request
    
    # Handle POST request - send SMS
    if request.method == 'POST':
        recipient = request.POST.get('recipient', '').strip()
        message = request.POST.get('message', '').strip()
        sender_id = request.POST.get('sender_id', '').strip()
        
        general_logger.info(f"SMS send request - User: {request.user}, Recipient: {recipient}, SenderID: {sender_id}")
        
        if not recipient or not message:
            messages.error(request, 'Recipient and message are required')
            general_logger.warning(f"SMS send failed - missing recipient or message")
            return redirect('send_sms')
        
        try:
            # Process SMS request using the service
            result = process_sms_request(
                user=request.user,
                recipient=recipient,
                message=message,
                sender_id=sender_id if sender_id else None,
                skip_queue=False  # Will queue to Celery
            )
            
            general_logger.info(f"SMS send result: {result}")
            
            if result.get('success'):
                total_recipients = result.get('total_recipients', 1)
                if total_recipients > 1:
                    messages.success(
                        request, 
                        f"{result.get('successful', 0)} of {total_recipients} SMS queued successfully. "
                        f"Cost: ৳{result.get('total_cost', 0)}."
                    )
                else:
                    messages.success(
                        request, 
                        f"SMS queued successfully! Cost: ৳{result.get('total_cost', 0)}."
                    )
            else:
                total_recipients = result.get('total_recipients', 1)
                if total_recipients > 1:
                    messages.error(
                        request, 
                        f"Failed to send {total_recipients} SMS: {result.get('message')}"
                    )
                else:
                    messages.error(request, f'Failed to send SMS: {result.get("message")}')
        except Exception as e:
            general_logger.exception(f"Error processing SMS send request: {str(e)}")
            messages.error(request, f'An error occurred: {str(e)}')
        
        return redirect('send_sms')
    
    # GET request - render form
    # Get user's assigned sender IDs
    user_sender_ids = UserSenderID.objects.select_related('sender_id', 'sender_id__provider').filter(
        user=request.user, 
        is_active=True
    ).order_by('-created_at')
    
    # Get default rates
    default_rate = DefaultRate.get_instance()
    
    # Operators
    operators = {
        'gp': 'Grameenphone',
        'bl': 'Banglalink',
        'robi': 'Robi',
        'airtel': 'Airtel',
        'teletalk': 'Teletalk',
    }
    
    # Build user rates
    user_rates = []
    for op_code, op_name in operators.items():
        user_op_code = op_code if op_code in ['robi', 'airtel', 'teletalk'] else ('grameenphone' if op_code == 'gp' else 'banglalink')
        
        # Get default rates
        default_op_rates = default_rate.operator_rates.get(op_code, {})
        default_masking = default_op_rates.get('masking', 0.35)
        default_non_masking = default_op_rates.get('non_masking', 0.25)
        
        # Get user rates
        try:
            user_masking = UserSMSRate.objects.get(user=request.user, operator=user_op_code, message_type='masking', is_active=True).rate
        except UserSMSRate.DoesNotExist:
            user_masking = default_masking
        
        try:
            user_non_masking = UserSMSRate.objects.get(user=request.user, operator=user_op_code, message_type='non_masking', is_active=True).rate
        except UserSMSRate.DoesNotExist:
            user_non_masking = default_non_masking
        
        user_rates.append({
            'name': op_name,
            'masking': user_masking,
            'non_masking': user_non_masking,
        })
    
    context = {
        'user_sender_ids': user_sender_ids,
        'user_rates': user_rates,
    }
    return render(request, 'core/send_sms.html', context)


@login_required
def sms_log_view(request):
    """SMS Log view showing user's SMS history"""
    from sms_gateway.models import SMSLog
    
    # Get user's SMS logs
    sms_logs = SMSLog.objects.filter(user=request.user).order_by('-created_at')
    
    # Calculate stats
    total_sms = sms_logs.count()
    delivered_count = sms_logs.filter(status__in=['DELIVERED', 'SENT']).count()
    pending_count = sms_logs.filter(status__in=['PENDING', 'QUEUED']).count()
    failed_count = sms_logs.filter(status='FAILED').count()
    
    context = {
        'sms_logs': sms_logs,
        'total_sms': total_sms,
        'delivered_count': delivered_count,
        'pending_count': pending_count,
        'failed_count': failed_count,
    }
    return render(request, 'core/sms_log.html', context)


@login_required
def transactions_view(request):
    """Redirect to payment_gateway transactions"""
    return redirect('payment_gateway:transactions')


@login_required
def add_fund_view(request):
    """Redirect to payment_gateway add_fund"""
    return redirect('payment_gateway:add_fund')


@login_required
def api_key_view(request):
    """API Key management view"""
    from sms_gateway.models import APIKey
    from sms_gateway.authentication import APIKeyManager
    
    # Handle key rotation
    if request.method == 'POST' and request.POST.get('action') == 'rotate':
        # Revoke existing active keys
        APIKey.objects.filter(user=request.user, is_active=True).update(
            is_active=False,
            revoked_at=timezone.now()
        )
        
        # Create new key
        api_key = APIKeyManager.create_api_key(
            user=request.user,
            name='Default'
        )
        
        messages.success(request, 'API key rotated successfully. Your old key is now invalid.')
        return redirect('api_key')
    
    # Get or create API key
    api_key = APIKey.objects.filter(user=request.user, is_active=True).first()
    
    if not api_key:
        # Create a new API key for the user
        api_key = APIKeyManager.create_api_key(
            user=request.user,
            name='Default'
        )
    
    context = {
        'api_key': api_key.key,
        'api_key_created_at': api_key.created_at,
        'api_key_last_used': api_key.last_used_at,
    }
    return render(request, 'core/api_key.html', context)


@login_required
def profile_view(request):
    """Profile view with real user data"""
    from django.contrib.auth.models import User
    from sms_gateway.models import SMSLog
    from payment_gateway.models import Transaction
    from django.utils import timezone
    from datetime import timedelta
    
    user = request.user
    
    # Get or create user profile
    profile, created = Profile.objects.get_or_create(
        user=user,
        defaults={
            'mobile_number': '01' + str(user.id).zfill(9),
            'balance': 5.00
        }
    )
    
    # Get real statistics
    sms_sent = SMSLog.objects.filter(user=user).count()
    recharges = Transaction.objects.filter(user=user, status='COMPLETED').count()
    
    # Calculate years since joined
    days_since_joined = (timezone.now() - user.date_joined).days
    years_member = max(1, days_since_joined // 365)
    
    # Get last login formatted (convert to local timezone)
    last_login = user.last_login
    if last_login:
        # Convert to local timezone
        last_login_local = last_login.astimezone()
        # Check if last login was today
        if last_login_local.date() == timezone.now().date():
            last_login_str = f"Today, {last_login_local.strftime('%I:%M %p')}"
        else:
            last_login_str = last_login_local.strftime('%b %d, %Y %I:%M %p')
    else:
        last_login_str = "Never"
    
    # Format date joined (convert to local timezone)
    date_joined_local = user.date_joined.astimezone()
    date_joined_str = date_joined_local.strftime('%b %d, %Y')
    
    # Handle profile update
    if request.method == 'POST':
        action = request.POST.get('action', '')
        
        if action == 'update_profile':
            # Update user info
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            
            user.first_name = first_name
            user.last_name = last_name
            user.save()
            
            # Update profile info
            address = request.POST.get('address', '').strip()
            
            profile.address = address
            profile.save()
            
            messages.success(request, 'Profile updated successfully!')
            return redirect('profile')
        
        elif action == 'update_password':
            current_password = request.POST.get('current_password', '')
            new_password = request.POST.get('new_password', '')
            confirm_password = request.POST.get('confirm_password', '')
            
            # Validate
            if not user.check_password(current_password):
                messages.error(request, 'Current password is incorrect.')
            elif new_password != confirm_password:
                messages.error(request, 'New password and confirm password do not match.')
            elif len(new_password) < 8:
                messages.error(request, 'Password must be at least 8 characters long.')
            else:
                user.set_password(new_password)
                user.save()
                from django.contrib.auth import update_session_auth_hash
                update_session_auth_hash(request, user)
                messages.success(request, 'Password updated successfully!')
            return redirect('profile')
        
        elif action == 'update_photo':
            if request.FILES.get('photo'):
                from django.core.files.storage import default_storage
                # Delete old photo if it exists and is not the default
                default_photo = 'images/administrator.jpg'
                if profile.photo and profile.photo.name != default_photo:
                    try:
                        if default_storage.exists(profile.photo.name):
                            default_storage.delete(profile.photo.name)
                    except Exception:
                        pass  # Ignore errors if file doesn't exist
                
                profile.photo = request.FILES['photo']
                profile.save()
                messages.success(request, 'Profile photo updated successfully!')
            else:
                messages.error(request, 'Please select a photo to upload.')
            return redirect('profile')
    
    context = {
        'profile': profile,
        'sms_sent': sms_sent,
        'recharges': recharges,
        'years_member': years_member,
        'last_login_str': last_login_str,
        'date_joined_str': date_joined_str,
    }
    return render(request, 'core/profile.html', context)


@login_required
def change_password_view(request):
    if request.method == 'POST':
        old_password = request.POST.get('old_password', '')
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')
        
        # Validate inputs
        if not old_password or not new_password or not confirm_password:
            messages.error(request, 'All fields are required.')
            return render(request, 'core/change_password.html')
        
        # Check if new passwords match
        if new_password != confirm_password:
            messages.error(request, 'New password and confirm password do not match.')
            return render(request, 'core/change_password.html')
        
        # Check if old password is correct
        if not request.user.check_password(old_password):
            messages.error(request, 'Current password is incorrect.')
            return render(request, 'core/change_password.html')
        
        # Check password length
        if len(new_password) < 8:
            messages.error(request, 'New password must be at least 8 characters long.')
            return render(request, 'core/change_password.html')
        
        # Change password
        request.user.set_password(new_password)
        request.user.save()
        
        # Update session to prevent logout
        from django.contrib.auth import update_session_auth_hash
        update_session_auth_hash(request, request.user)
        
        # Log password change with IP and timestamp
        user_ip = request.META.get('REMOTE_ADDR', 'unknown')
        general_logger.info(f"User '{request.user.username}' changed password from IP: {user_ip}")
        
        messages.success(request, 'Your password has been changed successfully.')
        return redirect('change_password')
    
    return render(request, 'core/change_password.html')


@login_required
@user_passes_test(lambda u: u.is_superuser)
def users_view(request):
    from django.contrib.auth.models import User
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'toggle_status':
            user_id = request.POST.get('user_id')
            try:
                user = User.objects.get(id=user_id)
                user.is_active = not user.is_active
                user.save()
                status = 'activated' if user.is_active else 'deactivated'
                messages.success(request, f'User "{user.get_full_name() or user.username}" {status} successfully.')
            except User.DoesNotExist:
                messages.error(request, 'User not found.')
            return redirect('users')
    
    users = User.objects.select_related('profile').all().order_by('-date_joined')
    context = {
        'users': users,
    }
    return render(request, 'core/users.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def user_sms_rates_view(request, user_id):
    """View for configuring user-specific SMS rates per operator"""
    from django.contrib.auth.models import User
    from sms_gateway.models import UserSMSRate
    
    try:
        user = User.objects.select_related('profile').get(id=user_id)
    except User.DoesNotExist:
        messages.error(request, 'User not found')
        return redirect('users')
    
    # Get default rates from DefaultRate model
    default_rate = DefaultRate.get_instance()
    
    # Operator mapping: code -> name
    operators = {
        'gp': 'Grameenphone',
        'bl': 'Banglalink', 
        'robi': 'Robi',
        'airtel': 'Airtel',
        'teletalk': 'Teletalk',
    }
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'update_rates':
            for op_code, op_name in operators.items():
                masking_key = f'{op_code}_masking'
                non_masking_key = f'{op_code}_non_masking'
                
                masking_val = request.POST.get(masking_key, '').strip()
                non_masking_val = request.POST.get(non_masking_key, '').strip()
                
                user_op_code = op_code if op_code in ['robi', 'airtel', 'teletalk'] else ('grameenphone' if op_code == 'gp' else 'banglalink')
                
                if masking_val:
                    UserSMSRate.objects.update_or_create(
                        user=user,
                        operator=user_op_code,
                        message_type='masking',
                        defaults={'rate': float(masking_val), 'is_active': True}
                    )
                
                if non_masking_val:
                    UserSMSRate.objects.update_or_create(
                        user=user,
                        operator=user_op_code,
                        message_type='non_masking',
                        defaults={'rate': float(non_masking_val), 'is_active': True}
                    )
            
            messages.success(request, f'SMS rates updated for {user.get_full_name() or user.username}')
            return redirect('user_sms_rates', user_id=user.id)
        
        elif action == 'assign_sender_id':
            sender_id_id = request.POST.get('sender_id_id')
            try:
                sender_id = SenderID.objects.get(id=sender_id_id)
                # Check if already assigned
                if not UserSenderID.objects.filter(user=user, sender_id=sender_id).exists():
                    UserSenderID.objects.create(user=user, sender_id=sender_id, is_active=True)
                    messages.success(request, f'Sender ID "{sender_id.sender_id}" assigned to user.')
                else:
                    messages.warning(request, f'Sender ID "{sender_id.sender_id}" is already assigned to this user.')
            except SenderID.DoesNotExist:
                messages.error(request, 'Sender ID not found.')
            return redirect('user_sms_rates', user_id=user.id)
        
        elif action == 'remove_sender_id':
            user_sender_id_id = request.POST.get('user_sender_id_id')
            try:
                user_sender_id = UserSenderID.objects.get(id=user_sender_id_id, user=user)
                sender_id_name = user_sender_id.sender_id.sender_id
                user_sender_id.delete()
                messages.success(request, f'Sender ID "{sender_id_name}" removed from user.')
            except UserSenderID.DoesNotExist:
                messages.error(request, 'Assignment not found.')
            return redirect('user_sms_rates', user_id=user.id)
        
        elif action == 'assign_provider':
            provider_id = request.POST.get('provider_id')
            try:
                provider = SMSProvider.objects.get(id=provider_id)
                user.profile.default_provider = provider
                user.profile.save()
                messages.success(request, f'Provider "{provider.name}" assigned to user.')
            except SMSProvider.DoesNotExist:
                messages.error(request, 'Provider not found.')
            return redirect('user_sms_rates', user_id=user.id)
        
        elif action == 'remove_provider':
            if user.profile.default_provider:
                provider_name = user.profile.default_provider.name
                user.profile.default_provider = None
                user.profile.save()
                messages.success(request, f'Provider "{provider_name}" removed from user.')
            else:
                messages.warning(request, 'No provider assigned to this user.')
            return redirect('user_sms_rates', user_id=user.id)
    
    # Build rates for template
    rates = []
    for op_code, op_name in operators.items():
        user_op_code = op_code if op_code in ['robi', 'airtel', 'teletalk'] else ('grameenphone' if op_code == 'gp' else 'banglalink')
        
        default_op_rates = default_rate.operator_rates.get(op_code, {})
        default_masking = default_op_rates.get('masking', 0.35)
        default_non_masking = default_op_rates.get('non_masking', 0.25)
        
        try:
            user_masking = UserSMSRate.objects.get(user=user, operator=user_op_code, message_type='masking', is_active=True).rate
        except UserSMSRate.DoesNotExist:
            user_masking = None
        
        try:
            user_non_masking = UserSMSRate.objects.get(user=user, operator=user_op_code, message_type='non_masking', is_active=True).rate
        except UserSMSRate.DoesNotExist:
            user_non_masking = None
        
        rates.append({
            'code': op_code,
            'name': op_name,
            'masking': user_masking if user_masking is not None else default_masking,
            'non_masking': user_non_masking if user_non_masking is not None else default_non_masking,
        })
    
    # Get all available sender IDs
    all_sender_ids = SenderID.objects.select_related('provider').all().order_by('-created_at')
    
    # Get user's assigned sender IDs
    user_sender_ids = UserSenderID.objects.select_related('sender_id', 'sender_id__provider').filter(user=user, is_active=True).order_by('-created_at')
    
    # Get IDs of already assigned sender IDs to exclude from modal
    assigned_sender_id_ids = list(user_sender_ids.values_list('sender_id_id', flat=True))
    
    # Get all providers for provider assignment
    all_providers = SMSProvider.objects.all().order_by('-created_at')
    
    # Get user's assigned provider
    user_provider = user.profile.default_provider
    
    context = {
        'target_user': user,
        'rates': rates,
        'all_sender_ids': all_sender_ids,
        'user_sender_ids': user_sender_ids,
        'assigned_sender_id_ids': assigned_sender_id_ids,
        'all_providers': all_providers,
        'user_provider': user_provider,
    }
    return render(request, 'core/user_sms_rates.html', context)
