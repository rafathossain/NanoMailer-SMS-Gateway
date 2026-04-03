import re
from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


def validate_bd_mobile_number(value):
    """
    Validate Bangladeshi mobile number.
    Must be 11 digits starting with 01 (e.g., 01712345678)
    """
    pattern = r'^01[3-9]\d{8}$'
    if not re.match(pattern, value):
        raise ValidationError(
            'Enter a valid 11-digit Bangladeshi mobile number starting with 01 (e.g., 01712345678)'
        )


def user_profile_photo_path(instance, filename):
    """Upload profile photos to users/{username}/profile/ directory"""
    ext = filename.split('.')[-1]
    return f'users/{instance.user.username}/profile/photo.{ext}'


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    mobile_number = models.CharField(
        max_length=11,
        validators=[validate_bd_mobile_number],
        help_text='11-digit Bangladeshi mobile number (e.g., 01712345678)'
    )
    photo = models.ImageField(
        upload_to=user_profile_photo_path,
        blank=True,
        null=True,
        default='images/administrator.jpg',
        help_text='Profile photo'
    )
    balance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=5.00,
        help_text='Account balance in BDT'
    )
    
    # User-specific SMS rates (optional, falls back to provider rates if not set)
    masking_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text='Custom masking SMS rate (per SMS). Leave empty to use provider default.'
    )
    non_masking_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text='Custom non-masking SMS rate (per SMS). Leave empty to use provider default.'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_profiles'
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return f"{self.user.email} - {self.mobile_number}"

    def deposit(self, amount):
        """Add amount to balance"""
        self.balance += amount
        self.save()

    def deduct(self, amount):
        """Deduct amount from balance if sufficient"""
        if self.balance >= amount:
            self.balance -= amount
            self.save()
            return True
        return False
    
    def get_masking_rate(self):
        """Get masking rate (custom or provider default)"""
        if self.masking_rate is not None:
            return self.masking_rate
        # Fall back to provider default
        provider = SMSProvider.get_default_provider()
        return provider.masking_rate if provider else 0.35
    
    def get_non_masking_rate(self):
        """Get non-masking rate (custom or provider default)"""
        if self.non_masking_rate is not None:
            return self.non_masking_rate
        # Fall back to provider default
        provider = SMSProvider.get_default_provider()
        return provider.non_masking_rate if provider else 0.25


class SMSProvider(models.Model):
    """SMS Provider configuration model"""
    PROVIDER_CHOICES = [
        ('REVESMS', 'ReveSMS'),
    ]
    
    name = models.CharField(max_length=100, help_text='Provider name (e.g., ReveSMS Primary)')
    provider_class = models.CharField(
        max_length=50,
        choices=PROVIDER_CHOICES,
        default='REVESMS',
        help_text='Provider class to use for sending SMS'
    )
    credentials = models.JSONField(
        default=dict,
        help_text='Provider credentials in JSON format',
        blank=True
    )
    masking_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.35,
        help_text='Rate per SMS for masking (in BDT)'
    )
    non_masking_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.25,
        help_text='Rate per SMS for non-masking (in BDT)'
    )
    is_active = models.BooleanField(default=True, help_text='Is this provider active?')
    is_default = models.BooleanField(default=False, help_text='Set as default provider')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sms_providers'
        verbose_name = 'SMS Provider'
        verbose_name_plural = 'SMS Providers'
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        return f"{self.name} ({self.provider_class})"

    def save(self, *args, **kwargs):
        # If this provider is set as default, unset others
        if self.is_default:
            SMSProvider.objects.filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_default_provider(cls):
        """Get the default active provider"""
        return cls.objects.filter(is_active=True, is_default=True).first()

    @classmethod
    def get_active_providers(cls):
        """Get all active providers"""
        return cls.objects.filter(is_active=True)


class SenderID(models.Model):
    """Sender ID configuration for SMS providers"""
    provider = models.ForeignKey(
        SMSProvider,
        on_delete=models.CASCADE,
        related_name='sender_ids',
        help_text='Associated SMS Provider'
    )
    sender_id = models.CharField(
        max_length=20,
        help_text='Sender ID (e.g., SMS-GW, MyBrand)'
    )
    is_active = models.BooleanField(default=True, help_text='Is this sender ID active?')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sender_ids'
        verbose_name = 'Sender ID'
        verbose_name_plural = 'Sender IDs'
        ordering = ['-is_active', '-created_at']
        unique_together = ['provider', 'sender_id']

    def __str__(self):
        return f"{self.sender_id} ({self.provider.name})"

    @classmethod
    def get_active_sender_ids(cls, provider=None):
        """Get all active sender IDs, optionally filtered by provider"""
        queryset = cls.objects.filter(is_active=True)
        if provider:
            queryset = queryset.filter(provider=provider)
        return queryset


class PaymentGateway(models.Model):
    """Payment Gateway configuration model"""
    GATEWAY_CHOICES = [
        ('SSLCOMMERZ', 'SSLCommerz'),
        ('BKASH', 'bKash'),
    ]
    
    name = models.CharField(max_length=100, help_text='Gateway name (e.g., SSLCommerz Primary)')
    gateway_class = models.CharField(
        max_length=50,
        choices=GATEWAY_CHOICES,
        default='SSLCOMMERZ',
        help_text='Payment gateway class to use'
    )
    credentials = models.JSONField(
        default=dict,
        help_text='Gateway credentials in JSON format (store_id, store_pass, etc.)',
        blank=True
    )
    tdr = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        help_text='Transaction Discount Rate (TDR) in percentage'
    )
    is_active = models.BooleanField(default=True, help_text='Is this gateway active?')
    is_default = models.BooleanField(default=False, help_text='Set as default gateway')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payment_gateways'
        verbose_name = 'Payment Gateway'
        verbose_name_plural = 'Payment Gateways'
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        return f"{self.name} ({self.gateway_class})"

    def save(self, *args, **kwargs):
        # If this gateway is set as default, unset others
        if self.is_default:
            PaymentGateway.objects.filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_default_gateway(cls):
        """Get the default active gateway"""
        return cls.objects.filter(is_active=True, is_default=True).first()

    @classmethod
    def get_active_gateways(cls):
        """Get all active gateways"""
        return cls.objects.filter(is_active=True)


class DefaultRate(models.Model):
    """Store default SMS rates for masking and non-masking"""
    masking_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.35,
        help_text='Default rate per SMS for masking (in BDT)'
    )
    non_masking_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.25,
        help_text='Default rate per SMS for non-masking (in BDT)'
    )
    # Operator-specific rates stored as JSON
    credentials = models.JSONField(
        default=dict,
        blank=True,
        help_text='Operator-specific SMS rates (JSON format)'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'default_rates'
        verbose_name = 'Default Rate'
        verbose_name_plural = 'Default Rates'

    def __str__(self):
        return f"Masking: ৳{self.masking_rate}, Non-Masking: ৳{self.non_masking_rate}"

    @classmethod
    def get_instance(cls):
        """Get or create the singleton instance"""
        instance, created = cls.objects.get_or_create(pk=1)
        return instance

    @classmethod
    def get_masking_rate(cls):
        """Get current masking rate"""
        return cls.get_instance().masking_rate

    @classmethod
    def get_non_masking_rate(cls):
        """Get current non-masking rate"""
        return cls.get_instance().non_masking_rate
