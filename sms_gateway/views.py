"""
SMS Gateway Views
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .utils import send_sms, check_balance, get_sms_cost


@login_required
def send_sms_view(request):
    """View for sending SMS"""
    if request.method == 'POST':
        recipient = request.POST.get('recipient', '').strip()
        message = request.POST.get('message', '').strip()
        sender_id = request.POST.get('sender_id', '').strip()
        
        if not recipient or not message:
            messages.error(request, 'Recipient and message are required')
            return redirect('sms_gateway:send_sms')
        
        # Check user balance
        if hasattr(request.user, 'profile'):
            cost_info = get_sms_cost(message, user=request.user)
            if request.user.profile.balance < cost_info['total_cost']:
                messages.error(request, f'Insufficient balance. Required: ৳{cost_info["total_cost"]}, Available: ৳{request.user.profile.balance}')
                return redirect('sms_gateway:send_sms')
        
        # Send SMS
        result = send_sms(
            recipient=recipient,
            message=message,
            sender_id=sender_id if sender_id else None,
            user=request.user
        )
        
        if result.get('success'):
            messages.success(request, f'SMS sent successfully! Message ID: {result.get("message_id")}')
            # Deduct balance
            if hasattr(request.user, 'profile'):
                cost_info = get_sms_cost(message, user=request.user)
                request.user.profile.deduct(cost_info['total_cost'])
        else:
            messages.error(request, f'Failed to send SMS: {result.get("message")}')
        
        return redirect('sms_gateway:send_sms')
    
    # Calculate cost preview
    context = {
        'user_balance': getattr(request.user.profile, 'balance', 0) if hasattr(request.user, 'profile') else 0
    }
    return render(request, 'sms_gateway/send_sms.html', context)


@login_required
def check_balance_view(request):
    """AJAX endpoint to check SMS provider balance"""
    result = check_balance()
    return JsonResponse(result)


@login_required
def calculate_cost_view(request):
    """AJAX endpoint to calculate SMS cost"""
    message = request.GET.get('message', '')
    cost_info = get_sms_cost(message, user=request.user)
    return JsonResponse({
        'success': True,
        'message_length': cost_info['message_length'],
        'is_unicode': cost_info['is_unicode'],
        'segments': cost_info['segments'],
        'rate_per_sms': str(cost_info['rate_per_sms']),
        'total_cost': str(cost_info['total_cost']),
        'currency': cost_info['currency']
    })
