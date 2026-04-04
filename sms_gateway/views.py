"""
SMS Gateway Views - API endpoints for SMS operations

Note: The web UI for sending SMS is handled by core.views.send_sms_view.
This module provides API endpoints and utility views.
"""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .services import calculate_sms_cost
from .utils import check_balance


@login_required
def check_balance_view(request):
    """AJAX endpoint to check SMS provider balance"""
    result = check_balance()
    return JsonResponse(result)


@login_required
def calculate_cost_view(request):
    """AJAX endpoint to calculate SMS cost"""
    message = request.GET.get('message', '')
    sender_id = request.GET.get('sender_id')
    # Use new service for more accurate cost calculation
    cost_info = calculate_sms_cost(
        message=message,
        user=request.user,
        sender_id=sender_id
    )
    return JsonResponse({
        'success': True,
        'message_length': cost_info['message_length'],
        'is_unicode': cost_info['is_unicode'],
        'segments': cost_info['segments'],
        'message_type': cost_info['message_type'],
        'rate_per_sms': str(cost_info['rate_per_sms']),
        'total_cost': str(cost_info['total_cost']),
        'currency': cost_info['currency']
    })


@login_required
@require_http_methods(["GET"])
def sms_log_detail_view(request, log_id):
    """
    AJAX endpoint to get SMS log details
    
    Args:
        log_id: SMSLog ID
        
    Returns:
        JSON response with SMS details
    """
    from .models import SMSLog
    
    try:
        # Get the SMS log belonging to the current user
        log = SMSLog.objects.get(id=log_id, user=request.user)
        
        # Calculate rate per SMS
        rate_per_sms = log.cost / log.segments if log.segments > 0 else log.cost
        
        return JsonResponse({
            'success': True,
            'id': log.id,
            'recipient': log.recipient,
            'sender_id': log.sender_id,
            'message': log.message,
            'status': log.status,
            'cost': str(log.cost),
            'segments': log.segments,
            'rate_per_sms': str(round(rate_per_sms, 2)),
            'operator': log.operator,
            'balance_deducted': log.balance_deducted,
            'deducted_amount': str(log.deducted_amount) if log.deducted_amount else '0',
            'created_at': log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'message_id': log.message_id,
            'error_message': log.error_message,
            'message_type': log.message_type
        })
    except SMSLog.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'SMS log not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)
