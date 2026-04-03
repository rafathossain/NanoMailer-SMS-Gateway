from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
import json
from .models import DefaultRate, SMSProvider, SenderID, PaymentGateway


@login_required
def dashboard_view(request):
    return render(request, 'core/dashboard.html')


@login_required
def sms_rates_view(request):
    # Get or create the default rate instance
    default_rate = DefaultRate.get_instance()
    
    if request.method == 'POST':
        try:
            # Update default rates
            default_masking = request.POST.get('default_masking_rate', '').strip()
            default_non_masking = request.POST.get('default_non_masking_rate', '').strip()
            
            if default_masking and default_non_masking:
                default_rate.masking_rate = float(default_masking)
                default_rate.non_masking_rate = float(default_non_masking)
                default_rate.save()
            
            # Update operator-specific rates (stored in credentials JSON)
            operators = ['gp', 'bl', 'robi', 'airtel', 'teletalk']
            operator_rates = {}
            
            for op in operators:
                masking_key = f'{op}_masking_rate'
                non_masking_key = f'{op}_non_masking_rate'
                masking_val = request.POST.get(masking_key, '').strip()
                non_masking_val = request.POST.get(non_masking_key, '').strip()
                
                if masking_val:
                    operator_rates[f'{op}_masking'] = float(masking_val)
                if non_masking_val:
                    operator_rates[f'{op}_non_masking'] = float(non_masking_val)
            
            # Save operator rates to default_rate credentials
            default_rate.credentials = operator_rates
            default_rate.save()
            
            messages.success(request, 'SMS rates updated successfully!')
            return redirect('sms_rates')
            
        except ValueError:
            messages.error(request, 'Invalid rate values. Please enter valid numbers.')
    
    # Prepare context with all rates
    credentials = default_rate.credentials or {}
    
    context = {
        'default_masking_rate': default_rate.masking_rate,
        'default_non_masking_rate': default_rate.non_masking_rate,
        # Operator rates from credentials
        'gp_masking_rate': credentials.get('gp_masking', default_rate.masking_rate),
        'gp_non_masking_rate': credentials.get('gp_non_masking', default_rate.non_masking_rate),
        'bl_masking_rate': credentials.get('bl_masking', default_rate.masking_rate),
        'bl_non_masking_rate': credentials.get('bl_non_masking', default_rate.non_masking_rate),
        'robi_masking_rate': credentials.get('robi_masking', default_rate.masking_rate),
        'robi_non_masking_rate': credentials.get('robi_non_masking', default_rate.non_masking_rate),
        'airtel_masking_rate': credentials.get('airtel_masking', default_rate.masking_rate),
        'airtel_non_masking_rate': credentials.get('airtel_non_masking', default_rate.non_masking_rate),
        'teletalk_masking_rate': credentials.get('teletalk_masking', default_rate.masking_rate),
        'teletalk_non_masking_rate': credentials.get('teletalk_non_masking', default_rate.non_masking_rate),
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
            is_default = request.POST.get('is_default') == 'on'
            
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
                    non_masking_rate=non_masking_rate_val,
                    is_default=is_default
                )
                messages.success(request, f'Provider "{name}" added successfully!')
            else:
                messages.error(request, 'Please provide all required fields.')
                
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
                
                # Send test SMS using sms_gateway
                from sms_gateway.utils import send_sms
                
                result = send_sms(
                    recipient=mobile_number,
                    message=message,
                    sender_id=sender_id if sender_id else None,
                    provider=provider,
                    user=request.user if request.user.is_authenticated else None
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
    
    providers = SMSProvider.objects.all().order_by('-is_default', '-created_at')
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
            is_active = request.POST.get('is_active') == 'on'
            
            if provider_id and sender_id_text:
                try:
                    provider = SMSProvider.objects.get(id=provider_id)
                    # Check if sender ID already exists for this provider
                    if SenderID.objects.filter(provider=provider, sender_id=sender_id_text).exists():
                        messages.error(request, f'Sender ID "{sender_id_text}" already exists for this provider.')
                    else:
                        SenderID.objects.create(
                            provider=provider,
                            sender_id=sender_id_text,
                            is_active=is_active
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
    
    sender_ids = SenderID.objects.all().select_related('provider').order_by('-is_active', '-created_at')
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
            is_default = request.POST.get('is_default') == 'on'
            
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
                
                PaymentGateway.objects.create(
                    name=name,
                    gateway_class=gateway_class,
                    credentials=credentials,
                    tdr=tdr_val,
                    is_default=is_default
                )
                messages.success(request, f'Payment gateway "{name}" added successfully!')
            else:
                messages.error(request, 'Please provide all required fields.')
                
        elif action == 'delete':
            gateway_id = request.POST.get('gateway_id')
            try:
                gateway = PaymentGateway.objects.get(id=gateway_id)
                gateway.delete()
                messages.success(request, 'Payment gateway deleted successfully!')
            except PaymentGateway.DoesNotExist:
                messages.error(request, 'Payment gateway not found.')
    
    gateways = PaymentGateway.objects.all().order_by('-is_default', '-created_at')
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
    return render(request, 'core/profile.html')


@login_required
def change_password_view(request):
    return render(request, 'core/change_password.html')


@login_required
def users_view(request):
    from django.contrib.auth.models import User
    
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
