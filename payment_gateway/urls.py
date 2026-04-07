"""
URL patterns for payment gateway
"""
from django.urls import path
from . import views

app_name = 'payment_gateway'

urlpatterns = [
    path('add-fund', views.add_fund_view, name='add_fund'),
    path('transactions', views.transactions_view, name='transactions'),
    path('success', views.payment_success_view, name='payment_success'),
    path('fail', views.payment_fail_view, name='payment_fail'),
    path('cancel', views.payment_cancel_view, name='payment_cancel'),
    path('transaction/<str:transaction_id>', views.transaction_detail_view, name='transaction_detail'),
    path('manual-add-fund', views.manual_add_fund_view, name='manual_add_fund'),
    
    # API endpoints
    path('api/transaction/<str:transaction_id>/status', views.api_check_transaction_status, name='api_transaction_status'),
]
