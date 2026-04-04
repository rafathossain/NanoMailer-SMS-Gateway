"""
URL patterns for SMS Gateway - Web AJAX endpoints only

Note: The REST API endpoints are in the 'api' app.
The web UI for sending SMS is in core.urls
"""
from django.urls import path
from . import views

app_name = 'sms_gateway'

urlpatterns = [
    # Web AJAX endpoints (for dashboard UI)
    path('api/check-balance', views.check_balance_view, name='check_balance'),
    path('api/calculate-cost', views.calculate_cost_view, name='calculate_cost'),
    path('api/sms-log/<int:log_id>/', views.sms_log_detail_view, name='sms_log_detail'),
]
