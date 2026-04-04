"""
API URL Configuration

This module contains all REST API endpoints for the SMS Gateway.

Authentication: API Key required in header:
    X-API-Key: your_api_key_here
    or
    Authorization: ApiKey your_api_key_here
"""
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from . import views

app_name = 'api'

urlpatterns = [
    # Swagger/OpenAPI documentation
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/swagger/', SpectacularSwaggerView.as_view(url_name='api:schema'), name='swagger-ui'),
    path('docs/redoc/', SpectacularRedocView.as_view(url_name='api:schema'), name='redoc'),
    
    # SMS endpoints
    path('send-sms', views.send_sms_api, name='send_sms'),
    path('sms-logs', views.list_sms_logs_api, name='sms_logs'),
    path('sms-logs/<int:log_id>', views.get_sms_log_detail_api, name='sms_log_detail'),
    path('sender-ids', views.get_sender_ids_api, name='sender_ids'),
    
    # Balance endpoints
    path('balance', views.get_balance_api, name='balance'),
]
