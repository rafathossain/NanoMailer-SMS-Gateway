from django.urls import path
from . import views

urlpatterns = [
    path('dashboard', views.dashboard_view, name='dashboard'),
    path('settings/sms-rates', views.sms_rates_view, name='sms_rates'),
    path('settings/provider', views.provider_view, name='provider'),
    path('settings/sender-id', views.sender_id_view, name='sender_id'),
    path('settings/payment-gateway', views.payment_gateway_view, name='payment_gateway'),
    path('sms/send', views.send_sms_view, name='send_sms'),
    path('sms/log', views.sms_log_view, name='sms_log'),
    path('billing/transactions', views.transactions_view, name='transactions_core'),
    path('billing/add-fund', views.add_fund_view, name='add_fund_core'),
    path('developer/api-key', views.api_key_view, name='api_key'),
    path('account/profile', views.profile_view, name='profile'),
    path('account/change-password', views.change_password_view, name='change_password'),
    path('users', views.users_view, name='users'),
    path('users/<int:user_id>/sms-rates', views.user_sms_rates_view, name='user_sms_rates'),
    path('admin/sms-log', views.admin_sms_log_view, name='admin_sms_log'),
]
