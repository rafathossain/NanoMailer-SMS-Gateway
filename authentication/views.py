from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.conf import settings
from core.models import Profile, validate_bd_mobile_number, DefaultRate, SMSProvider, SenderID, UserSenderID
from sms_gateway.models import UserSMSRate
import requests
import re


def verify_turnstile_token(token, remote_ip=None):
    """Verify Cloudflare Turnstile token."""
    if not settings.TURNSTILE_SECRET_KEY:
        return True  # Skip verification if secret key is not configured
    
    if not token:
        return False
    
    data = {
        'secret': settings.TURNSTILE_SECRET_KEY,
        'response': token,
    }
    if remote_ip:
        data['remoteip'] = remote_ip
    
    try:
        response = requests.post(settings.TURNSTILE_VERIFY_URL, data=data, timeout=5)
        result = response.json()
        return result.get('success', False)
    except requests.RequestException:
        return False


def signin_view(request):
    if request.method == 'POST':
        # Verify Turnstile token
        turnstile_token = request.POST.get('cf-turnstile-response', '')
        if not verify_turnstile_token(turnstile_token, request.META.get('REMOTE_ADDR')):
            messages.error(request, 'CAPTCHA verification failed. Please try again.')
            return render(request, 'auth/signin.html')
        
        username_input = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        
        # Determine if input is mobile number or email
        # Mobile numbers start with 01 and are 11 digits
        if re.match(r'^01[3-9]\d{8}$', username_input):
            # Input is a mobile number, find user by profile
            try:
                profile = Profile.objects.get(mobile_number=username_input)
                username = profile.user.username
            except Profile.DoesNotExist:
                messages.error(request, 'Invalid mobile number or password.')
                return render(request, 'auth/signin.html')
        else:
            # Input is email/username
            username = username_input
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid email/mobile number or password.')
    
    context = {
        'turnstile_site_key': settings.TURNSTILE_SITE_KEY,
    }
    return render(request, 'auth/signin.html', context)


def signup_view(request):
    if request.method == 'POST':
        # Verify Turnstile token
        turnstile_token = request.POST.get('cf-turnstile-response', '')
        if not verify_turnstile_token(turnstile_token, request.META.get('REMOTE_ADDR')):
            messages.error(request, 'CAPTCHA verification failed. Please try again.')
            return render(request, 'auth/signup.html')
        
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        mobile = request.POST.get('mobile', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')

        if not name or not email or not mobile or not password:
            messages.error(request, 'All fields are required.')
        elif password != confirm_password:
            messages.error(request, 'Passwords do not match.')
        elif User.objects.filter(username=email).exists():
            messages.error(request, 'An account with this email already exists.')
        else:
            # Validate mobile number
            try:
                validate_bd_mobile_number(mobile)
            except ValidationError as e:
                messages.error(request, str(e))
                return render(request, 'auth/signup.html')

            # Check if mobile number already exists
            if Profile.objects.filter(mobile_number=mobile).exists():
                messages.error(request, 'This mobile number is already registered.')
                return render(request, 'auth/signup.html')

            user = User.objects.create_user(
                username=email,
                email=email,
                first_name=name,
                password=password,
            )
            user.is_active = True
            user.save()

            # Create user profile with default balance of 5 BDT
            profile = Profile.objects.create(
                user=user,
                mobile_number=mobile,
                balance=5.00
            )

            # Set up user with default rates, provider, and sender ID
            setup_new_user(user, profile)

            messages.success(request, 'Registration successful! Please log in to continue.')
            return redirect('signin')

    context = {
        'turnstile_site_key': settings.TURNSTILE_SITE_KEY,
    }
    return render(request, 'auth/signup.html', context)


def verify_otp_view(request):
    email = request.GET.get('email') or request.POST.get('email', '').strip()
    if not email:
        messages.error(request, 'Invalid request.')
        return redirect('signup')

    try:
        user = User.objects.get(username=email)
    except User.DoesNotExist:
        messages.error(request, 'User not found.')
        return redirect('signup')

    if request.method == 'POST':
        otp_code = request.POST.get('otp', '').strip()
        try:
            otp = OTP.objects.filter(user=user, is_used=False).latest('created_at')
        except OTP.DoesNotExist:
            messages.error(request, 'OTP not found. Please register again.')
            return redirect('signup')

        if otp.is_expired():
            messages.error(request, 'OTP has expired. Please register again.')
            otp.delete()
            user.delete()
            return redirect('signup')

        if otp.code == otp_code:
            otp.is_used = True
            otp.save()
            user.is_active = True
            user.save()
            messages.success(request, 'Your account has been verified. Please sign in.')
            return redirect('signin')
        else:
            messages.error(request, 'Invalid OTP. Please try again.')

    return render(request, 'auth/verify_otp.html', {'email': email})


def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('signin')


def setup_new_user(user, profile):
    """
    Set up a new user with default rates, provider, and sender ID.
    Called automatically after user registration.
    """
    # Get default rates
    default_rate = DefaultRate.get_instance()
    
    # Operator mapping: code -> database operator name
    operators = {
        'gp': 'grameenphone',
        'bl': 'banglalink',
        'robi': 'robi',
        'airtel': 'airtel',
        'teletalk': 'teletalk',
    }
    
    # Create user SMS rates from default rates
    if default_rate and default_rate.operator_rates:
        for op_code, db_op_name in operators.items():
            op_rates = default_rate.operator_rates.get(op_code, {})
            
            # Masking rate
            masking_rate = op_rates.get('masking')
            if masking_rate:
                UserSMSRate.objects.create(
                    user=user,
                    operator=db_op_name,
                    message_type='masking',
                    rate=float(masking_rate),
                    is_active=True
                )
            
            # Non-masking rate
            non_masking_rate = op_rates.get('non_masking')
            if non_masking_rate:
                UserSMSRate.objects.create(
                    user=user,
                    operator=db_op_name,
                    message_type='non_masking',
                    rate=float(non_masking_rate),
                    is_active=True
                )
    
    # Assign default provider to user
    default_provider = SMSProvider.get_default_provider()
    if default_provider:
        profile.default_provider = default_provider
        profile.save(update_fields=['default_provider'])
        
        # Assign first sender ID from default provider to user
        sender_id = SenderID.objects.filter(provider=default_provider).first()
        if sender_id:
            UserSenderID.objects.create(
                user=user,
                sender_id=sender_id,
                is_active=True
            )
