"""
URL patterns for SMS Gateway
"""
from django.urls import path
from . import views

app_name = 'sms_gateway'

urlpatterns = [
    path('send', views.send_sms_view, name='send_sms'),
    path('api/check-balance', views.check_balance_view, name='check_balance'),
    path('api/calculate-cost', views.calculate_cost_view, name='calculate_cost'),
]
