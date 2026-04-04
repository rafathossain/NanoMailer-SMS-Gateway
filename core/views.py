from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
import json
import logging
from .models import DefaultRate, SMSProvider, SenderID, PaymentGateway, Profile

# Logger
general_logger = logging.getLogger('general')


@login_required
def dashboard_view(request):
    return render(request, 'core/dashboard.html')


@login_required
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
    
    context = {
        'operators': operators_list,
    }
    return render(request, 'core/sms_rates.html', context)


@login_required
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
    
    providers = SMSProvider.objects.all().order_by('-created_at')
    context = {
        'providers': providers,
        'provider_choices': SMSProvider.PROVIDER_CHOICES,
    }
    return render(request, 'core/provider.html', context)


@login_required
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
def send_sms_view(request):
    return render(request, 'core/send_sms.html')


@login_required
def sms_log_view(request):
    return render(request, 'core/sms_log.html')


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
    return render(request, 'core/api_key.html')


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
    
    # Get last login formatted
    last_login = user.last_login
    if last_login:
        # Check if last login was today
        if last_login.date() == timezone.now().date():
            last_login_str = f"Today, {last_login.strftime('%I:%M %p')}"
        else:
            last_login_str = last_login.strftime('%b %d, %Y')
    else:
        last_login_str = "Never"
    
    # Format date joined
    date_joined_str = user.date_joined.strftime('%b %d, %Y')
    
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
def user_sms_rates_view(request, user_id):
    """View for configuring user-specific SMS rates per operator"""
    from django.contrib.auth.models import User
    from sms_gateway.models import UserSMSRate
    
    try:
        user = User.objects.select_related('profile').get(id=user_id)
    except User.DoesNotExist:
        messages.error(request, 'User not found')
        return redirect('users')
    
    # Get default provider rates for reference
    provider = SMSProvider.get_default_provider()
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'update_rates':
            # Update rates for all operators
            operators = ['default', 'grameenphone', 'banglalink', 'robi', 'airtel', 'teletalk']
            message_types = ['masking', 'non_masking']
            
            for operator in operators:
                for msg_type in message_types:
                    rate_key = f"rate_{operator}_{msg_type}"
                    rate_value = request.POST.get(rate_key, '').strip()
                    
                    if rate_value:
                        try:
                            rate_decimal = float(rate_value)
                            # Update or create rate
                            UserSMSRate.objects.update_or_create(
                                user=user,
                                operator=operator,
                                message_type=msg_type,
                                defaults={'rate': rate_decimal, 'is_active': True}
                            )
                        except ValueError:
                            messages.error(request, f'Invalid rate value for {operator} {msg_type}')
                    else:
                        # Deactivate this rate (use default)
                        UserSMSRate.objects.filter(
                            user=user,
                            operator=operator,
                            message_type=msg_type
                        ).update(is_active=False)
            
            messages.success(request, f'SMS rates updated for {user.get_full_name() or user.username}')
            return redirect('user_sms_rates', user_id=user.id)
    
    # Build rate data for template
    operators = [
        ('default', 'Default (All Operators)'),
        ('grameenphone', 'Grameenphone'),
        ('banglalink', 'Banglalink'),
        ('robi', 'Robi'),
        ('airtel', 'Airtel'),
        ('teletalk', 'Teletalk'),
    ]
    
    message_types = [
        ('masking', 'Masking'),
        ('non_masking', 'Non-Masking'),
    ]
    
    # Get user's rates
    user_rates = {}
    for rate in UserSMSRate.objects.filter(user=user, is_active=True):
        key = f"{rate.operator}_{rate.message_type}"
        user_rates[key] = rate.rate
    
    # Get default rates from provider
    default_masking_rate = provider.masking_rate if provider else 0.35
    default_non_masking_rate = provider.non_masking_rate if provider else 0.25
    
    context = {
        'target_user': user,
        'operators': operators,
        'message_types': message_types,
        'user_rates': user_rates,
        'default_masking_rate': default_masking_rate,
        'default_non_masking_rate': default_non_masking_rate,
        'provider': provider,
    }
    return render(request, 'core/user_sms_rates.html', context)
