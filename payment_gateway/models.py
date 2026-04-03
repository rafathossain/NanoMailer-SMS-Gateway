import uuid
from django.db import models
from django.contrib.auth.models import User
from core.models import PaymentGateway as GatewayConfig


class Transaction(models.Model):
    """Payment transaction model"""
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('INITIATED', 'Initiated'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('CANCELLED', 'Cancelled'),
        ('VALIDATED', 'Validated'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payment_transactions')
    gateway = models.ForeignKey(GatewayConfig, on_delete=models.SET_NULL, null=True, related_name='transactions')
    
    # Transaction details
    transaction_id = models.CharField(max_length=100, unique=True, help_text='Unique transaction ID')
    gateway_transaction_id = models.CharField(max_length=100, blank=True, null=True, help_text='Gateway transaction ID')
    
    # Amount details
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text='Base amount')
    tdr_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text='TDR amount')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, help_text='Total amount with TDR')
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    # Response data
    gateway_response = models.JSONField(default=dict, blank=True, help_text='Raw gateway response')
    validation_response = models.JSONField(default=dict, blank=True, help_text='Validation response')
    
    # Session data for tracking
    session_key = models.CharField(max_length=255, blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'payment_transactions'
        verbose_name = 'Payment Transaction'
        verbose_name_plural = 'Payment Transactions'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction_id} - {self.user.email} - ৳{self.amount}"

    @classmethod
    def generate_transaction_id(cls):
        """Generate unique transaction ID"""
        return f"TXN{uuid.uuid4().hex[:12].upper()}"

    def mark_success(self, gateway_response=None):
        """Mark transaction as successful"""
        self.status = 'COMPLETED'
        if gateway_response:
            self.gateway_response = gateway_response
        from django.utils import timezone
        self.completed_at = timezone.now()
        self.save()
        
        # Add balance to user profile
        if hasattr(self.user, 'profile'):
            self.user.profile.deposit(self.amount)

    def mark_failed(self, reason=None):
        """Mark transaction as failed"""
        self.status = 'FAILED'
        if reason:
            self.gateway_response['failure_reason'] = reason
        self.save()

    def mark_cancelled(self):
        """Mark transaction as cancelled"""
        self.status = 'CANCELLED'
        self.save()
