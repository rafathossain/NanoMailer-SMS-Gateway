"""
SMS Gateway models
"""
from django.db import models
from django.contrib.auth.models import User
from core.models import SMSProvider


class SMSLog(models.Model):
    """Log of sent SMS messages"""
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('SENT', 'Sent'),
        ('DELIVERED', 'Delivered'),
        ('FAILED', 'Failed'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sms_logs')
    provider = models.ForeignKey(SMSProvider, on_delete=models.SET_NULL, null=True, related_name='sms_logs')
    
    # SMS details
    recipient = models.CharField(max_length=20, help_text='Phone number')
    message = models.TextField()
    sender_id = models.CharField(max_length=20, default='NanoMailer')
    
    # Status tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    message_id = models.CharField(max_length=100, blank=True, null=True, help_text='Gateway message ID')
    
    # Response data
    response_data = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, null=True)
    
    # Cost tracking
    segments = models.PositiveIntegerField(default=1)
    cost = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'sms_logs'
        verbose_name = 'SMS Log'
        verbose_name_plural = 'SMS Logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"SMS to {self.recipient} - {self.status}"


class SMSQueue(models.Model):
    """Queue for bulk SMS sending"""
    STATUS_CHOICES = [
        ('QUEUED', 'Queued'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sms_queues')
    
    # Queue details
    name = models.CharField(max_length=100)
    message = models.TextField()
    sender_id = models.CharField(max_length=20, default='NanoMailer')
    
    # Recipients (JSON array of phone numbers)
    recipients = models.JSONField(default=list)
    total_recipients = models.PositiveIntegerField(default=0)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='QUEUED')
    processed_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    
    # Provider
    provider = models.ForeignKey(SMSProvider, on_delete=models.SET_NULL, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'sms_queues'
        verbose_name = 'SMS Queue'
        verbose_name_plural = 'SMS Queues'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.status} ({self.processed_count}/{self.total_recipients})"


class UserSMSRate(models.Model):
    """User-specific SMS rates per operator and message type"""
    MESSAGE_TYPE_CHOICES = [
        ('masking', 'Masking'),
        ('non_masking', 'Non-Masking'),
    ]
    
    # Common operators in Bangladesh
    OPERATOR_CHOICES = [
        ('grameenphone', 'Grameenphone'),
        ('banglalink', 'Banglalink'),
        ('robi', 'Robi'),
        ('airtel', 'Airtel'),
        ('teletalk', 'Teletalk'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sms_rates')
    operator = models.CharField(
        max_length=20, 
        choices=OPERATOR_CHOICES,
        default='grameenphone',
        help_text='Mobile operator'
    )
    message_type = models.CharField(
        max_length=20,
        choices=MESSAGE_TYPE_CHOICES,
        default='masking',
        help_text='Type of SMS'
    )
    rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text='Rate per SMS in BDT'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_sms_rates'
        verbose_name = 'User SMS Rate'
        verbose_name_plural = 'User SMS Rates'
        ordering = ['user', 'operator', 'message_type']
        unique_together = ['user', 'operator', 'message_type']

    def __str__(self):
        return f"{self.user.username} - {self.get_operator_display()} - {self.get_message_type_display()}: ৳{self.rate}"

    @classmethod
    def get_user_rate(cls, user, operator='default', message_type='masking'):
        """Get user's custom rate for specific operator and type"""
        try:
            rate_obj = cls.objects.get(user=user, operator=operator, message_type=message_type, is_active=True)
            return rate_obj.rate
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_effective_rate(cls, user, operator='default', message_type='masking'):
        """Get effective rate (user custom or provider default)"""
        # Try user-specific rate first
        user_rate = cls.get_user_rate(user, operator, message_type)
        if user_rate is not None:
            return user_rate
        
        # Fall back to provider default
        provider = SMSProvider.get_default_provider()
        if provider:
            if message_type == 'masking':
                return provider.masking_rate
            else:
                return provider.non_masking_rate
        
        # Ultimate fallback
        return 0.35 if message_type == 'masking' else 0.25
