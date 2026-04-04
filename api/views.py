"""
API Views - REST API endpoints for SMS Gateway

This module provides REST API endpoints for:
- Sending SMS
- Checking balance
- Viewing SMS logs
- Getting sender IDs

Authentication: API Key required in header:
    X-API-Key: your_api_key_here
    or
    Authorization: ApiKey your_api_key_here
"""
import logging
from decimal import Decimal
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import BasePermission
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes

from sms_gateway.authentication import APIKeyAuthentication
from sms_gateway.services import process_sms_request, calculate_sms_cost
from sms_gateway.models import SMSLog

logger = logging.getLogger(__name__)


class IsAuthenticatedWithAPIKey(BasePermission):
    """
    Permission class to check if user is authenticated with API key.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated


@extend_schema(
    tags=['SMS'],
    summary='Send SMS',
    description='Send SMS to one or multiple recipients. For multiple recipients, provide comma-separated phone numbers.',
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'recipient': {'type': 'string', 'description': 'Single phone number or comma-separated numbers (e.g., "01712345678, 01887654321")'},
                'message': {'type': 'string', 'description': 'SMS message content'},
                'sender_id': {'type': 'string', 'description': 'Sender ID (optional, must be assigned to your account)'},
            },
            'required': ['recipient', 'message'],
            'example': {
                'recipient': '01712345678',
                'message': 'Hello World',
                'sender_id': 'MyBrand'
            }
        }
    },
    responses={
        200: {
            'description': 'SMS queued successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'message': 'SMS queued successfully! Cost: ৳0.40.',
                        'data': {
                            'log_ids': [1],
                            'total_recipients': 1,
                            'successful': 1,
                            'failed': 0,
                            'total_cost': '0.40',
                            'balance_deducted': True
                        }
                    }
                }
            }
        },
        400: {
            'description': 'Bad request - missing fields or insufficient balance',
            'content': {
                'application/json': {
                    'example': {
                        'success': False,
                        'message': 'Insufficient balance. Required: 0.40 BDT',
                        'data': {
                            'log_ids': [2],
                            'total_recipients': 1,
                            'successful': 0,
                            'failed': 1,
                            'total_cost': '0.40',
                            'balance_deducted': False
                        }
                    }
                }
            }
        }
    },
    auth=[{'ApiKeyAuth': []}],
)
@api_view(['POST'])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticatedWithAPIKey])
def send_sms_api(request):
    recipient = request.data.get('recipient', '').strip()
    message = request.data.get('message', '').strip()
    sender_id = request.data.get('sender_id', '').strip() or None
    
    # Validate required fields
    if not recipient:
        return Response({
            'success': False,
            'message': 'recipient is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if not message:
        return Response({
            'success': False,
            'message': 'message is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Process SMS request
        result = process_sms_request(
            user=request.user,
            recipient=recipient,
            message=message,
            sender_id=sender_id,
            skip_queue=False
        )
        
        if result.get('success'):
            return Response({
                'success': True,
                'message': result.get('message'),
                'data': {
                    'log_ids': result.get('log_ids', []),
                    'total_recipients': result.get('total_recipients', 0),
                    'successful': result.get('successful', 0),
                    'failed': result.get('failed', 0),
                    'total_cost': str(result.get('total_cost', '0')),
                    'balance_deducted': result.get('balance_deducted', False)
                }
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'message': result.get('message'),
                'data': {
                    'log_ids': result.get('log_ids', []),
                    'total_recipients': result.get('total_recipients', 0),
                    'successful': result.get('successful', 0),
                    'failed': result.get('failed', 0),
                    'total_cost': str(result.get('total_cost', '0')),
                    'balance_deducted': result.get('balance_deducted', False)
                }
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        logger.exception(f"API send SMS error: {str(e)}")
        return Response({
            'success': False,
            'message': f'Internal error: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    tags=['Balance'],
    summary='Get Balance',
    description='Get your current account balance in BDT.',
    responses={
        200: {
            'description': 'Balance retrieved successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'data': {
                            'balance': '125.50',
                            'currency': 'BDT'
                        }
                    }
                }
            }
        }
    },
    auth=[{'ApiKeyAuth': []}],
)
@api_view(['GET'])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticatedWithAPIKey])
def get_balance_api(request):
    try:
        if hasattr(request.user, 'profile'):
            balance = request.user.profile.balance
        else:
            balance = Decimal('0.00')
        
        return Response({
            'success': True,
            'data': {
                'balance': str(balance),
                'currency': 'BDT'
            }
        })
    except Exception as e:
        logger.exception(f"API get balance error: {str(e)}")
        return Response({
            'success': False,
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    tags=['SMS'],
    summary='List SMS Logs',
    description='Retrieve SMS history with pagination and optional status filtering.',
    parameters=[
        OpenApiParameter(
            name='status',
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description='Filter by status: PENDING, QUEUED, SENT, DELIVERED, FAILED',
            required=False
        ),
        OpenApiParameter(
            name='limit',
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description='Number of results per page (default: 20, max: 100)',
            required=False
        ),
        OpenApiParameter(
            name='offset',
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description='Offset for pagination (default: 0)',
            required=False
        ),
    ],
    responses={
        200: {
            'description': 'SMS logs retrieved successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'data': {
                            'total': 50,
                            'limit': 20,
                            'offset': 0,
                            'results': [
                                {
                                    'id': 1,
                                    'recipient': '01712345678',
                                    'sender_id': 'MyBrand',
                                    'message': 'Hello',
                                    'status': 'DELIVERED',
                                    'cost': '0.25',
                                    'segments': 1,
                                    'operator': 'grameenphone',
                                    'balance_deducted': True,
                                    'error_message': None,
                                    'created_at': '2026-04-04 10:30:00'
                                }
                            ]
                        }
                    }
                }
            }
        }
    },
    auth=[{'ApiKeyAuth': []}],
)
@api_view(['GET'])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticatedWithAPIKey])
def list_sms_logs_api(request):
    try:
        # Get query parameters
        status_filter = request.query_params.get('status')
        limit = int(request.query_params.get('limit', 20))
        offset = int(request.query_params.get('offset', 0))
        
        # Validate limit
        if limit > 100:
            limit = 100
        if limit < 1:
            limit = 20
        
        # Build queryset
        queryset = SMSLog.objects.filter(user=request.user)
        
        if status_filter:
            queryset = queryset.filter(status=status_filter.upper())
        
        total = queryset.count()
        
        # Paginate
        logs = queryset.order_by('-created_at')[offset:offset + limit]
        
        # Serialize
        results = []
        for log in logs:
            results.append({
                'id': log.id,
                'recipient': log.recipient,
                'sender_id': log.sender_id,
                'message': log.message,
                'status': log.status,
                'cost': str(log.cost),
                'segments': log.segments,
                'operator': log.operator,
                'balance_deducted': log.balance_deducted,
                'error_message': log.error_message,
                'created_at': log.created_at.strftime('%Y-%m-%d %H:%M:%S')
            })
        
        return Response({
            'success': True,
            'data': {
                'total': total,
                'limit': limit,
                'offset': offset,
                'results': results
            }
        })
    except Exception as e:
        logger.exception(f"API list SMS logs error: {str(e)}")
        return Response({
            'success': False,
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    tags=['SMS'],
    summary='Get SMS Log Detail',
    description='Retrieve detailed information about a specific SMS log by ID.',
    parameters=[
        OpenApiParameter(
            name='log_id',
            type=OpenApiTypes.INT,
            location=OpenApiParameter.PATH,
            description='SMS Log ID'
        ),
    ],
    responses={
        200: {
            'description': 'SMS log details retrieved successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'data': {
                            'id': 1,
                            'recipient': '01712345678',
                            'sender_id': 'MyBrand',
                            'message': 'Hello',
                            'status': 'DELIVERED',
                            'cost': '0.25',
                            'rate_per_sms': '0.25',
                            'segments': 1,
                            'operator': 'grameenphone',
                            'balance_deducted': True,
                            'deducted_amount': '0.25',
                            'message_id': 'msg_123',
                            'error_message': None,
                            'created_at': '2026-04-04 10:30:00',
                            'delivered_at': '2026-04-04 10:30:05'
                        }
                    }
                }
            }
        },
        404: {
            'description': 'SMS log not found',
            'content': {
                'application/json': {
                    'example': {
                        'success': False,
                        'message': 'SMS log not found'
                    }
                }
            }
        }
    },
    auth=[{'ApiKeyAuth': []}],
)
@api_view(['GET'])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticatedWithAPIKey])
def get_sms_log_detail_api(request, log_id):
    try:
        log = SMSLog.objects.get(id=log_id, user=request.user)
        
        # Calculate rate per SMS
        rate_per_sms = log.cost / log.segments if log.segments > 0 else log.cost
        
        return Response({
            'success': True,
            'data': {
                'id': log.id,
                'recipient': log.recipient,
                'sender_id': log.sender_id,
                'message': log.message,
                'status': log.status,
                'cost': str(log.cost),
                'rate_per_sms': str(round(rate_per_sms, 2)),
                'segments': log.segments,
                'operator': log.operator,
                'balance_deducted': log.balance_deducted,
                'deducted_amount': str(log.deducted_amount) if log.deducted_amount else '0',
                'message_id': log.message_id,
                'error_message': log.error_message,
                'created_at': log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'delivered_at': log.delivered_at.strftime('%Y-%m-%d %H:%M:%S') if log.delivered_at else None
            }
        })
    except SMSLog.DoesNotExist:
        return Response({
            'success': False,
            'message': 'SMS log not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception(f"API get SMS log detail error: {str(e)}")
        return Response({
            'success': False,
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    tags=['SMS'],
    summary='Get Sender IDs',
    description='Get all sender IDs assigned to your account. These can be used when sending SMS.',
    responses={
        200: {
            'description': 'Sender IDs retrieved successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'data': {
                            'sender_ids': [
                                {
                                    'sender_id': 'MyBrand',
                                    'is_active': True
                                },
                                {
                                    'sender_id': 'NanoMailer',
                                    'is_active': True
                                }
                            ],
                            'count': 2
                        }
                    }
                }
            }
        }
    },
    auth=[{'ApiKeyAuth': []}],
)
@api_view(['GET'])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticatedWithAPIKey])
def get_sender_ids_api(request):
    """
    Get all sender IDs assigned to the authenticated user.
    """
    try:
        from core.models import UserSenderID
        
        # Get user's assigned sender IDs
        user_sender_ids = UserSenderID.objects.select_related(
            'sender_id', 'sender_id__provider'
        ).filter(
            user=request.user,
            is_active=True
        ).order_by('-created_at')
        
        # Serialize
        sender_ids = []
        for user_sender_id in user_sender_ids:
            sender_ids.append({
                'sender_id': user_sender_id.sender_id.sender_id,
                'is_active': user_sender_id.is_active
            })
        
        return Response({
            'success': True,
            'data': {
                'sender_ids': sender_ids,
                'count': len(sender_ids)
            }
        })
    except Exception as e:
        logger.exception(f"API get sender IDs error: {str(e)}")
        return Response({
            'success': False,
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
