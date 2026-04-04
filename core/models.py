import json
import re
import uuid
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
    """Upload profile photos to users/{username}/profile/ directory with UUID filename"""
    ext = filename.split('.')[-1].lower()
    # Use UUID for filename to prevent security issues and overwriting
    unique_filename = f"{uuid.uuid4().hex}.{ext}"
    # Sanitize username by removing special characters (keep only alphanumeric and underscore)
    safe_username = re.sub(r'[^a-zA-Z0-9_]', '', instance.user.username)
    # Fallback to 'user' if username is empty after sanitization
    if not safe_username:
        safe_username = 'user'
    return f'users/{safe_username}/profile/{unique_filename}'


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
    
    # Additional profile fields
    company_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Company or organization name'
    )
    designation = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Job title or designation'
    )
    address = models.TextField(
        blank=True,
        null=True,
        help_text='Physical address'
    )
    bio = models.TextField(
        blank=True,
        null=True,
        help_text='Short biography or description'
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
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        help_text='Current provider balance (in BDT)'
    )
    balance_last_updated = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Last time balance was synced'
    )
    is_active = models.BooleanField(default=True, help_text='Is this provider active?')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sms_providers'
        verbose_name = 'SMS Provider'
        verbose_name_plural = 'SMS Providers'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.provider_class})"

    @property
    def credentials_json(self):
        """Return credentials as formatted JSON string"""
        if self.credentials:
            return json.dumps(self.credentials, indent=2)
        return ''

    @classmethod
    def get_default_provider(cls):
        """Get the first provider as default"""
        return cls.objects.first()

    @classmethod
    def get_active_providers(cls):
        """Get all providers"""
        return cls.objects.all()


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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sender_ids'
        verbose_name = 'Sender ID'
        verbose_name_plural = 'Sender IDs'
        ordering = ['-created_at']
        unique_together = ['provider', 'sender_id']

    def __str__(self):
        return f"{self.sender_id} ({self.provider.name})"


def gateway_logo_path(instance, filename):
    """Upload gateway logos to gateways/ directory with UUID filename"""
    ext = filename.split('.')[-1].lower()
    unique_filename = f"{uuid.uuid4().hex}.{ext}"
    return f'gateways/{unique_filename}'


class PaymentGateway(models.Model):
    """Payment Gateway configuration model"""
    GATEWAY_CHOICES = [
        ('SSLCOMMERZ', 'SSLCommerz'),
        ('BKASH', 'bKash'),
    ]
    
    name = models.CharField(max_length=100, help_text='Gateway name (e.g., SSLCommerz Primary)')
    logo = models.ImageField(
        upload_to=gateway_logo_path,
        blank=True,
        null=True,
        help_text='Gateway logo image (recommended size: 120x40px)'
    )
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payment_gateways'
        verbose_name = 'Payment Gateway'
        verbose_name_plural = 'Payment Gateways'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.gateway_class})"

    @classmethod
    def get_default_gateway(cls):
        """Get the first active gateway (for backward compatibility)"""
        return cls.objects.filter(is_active=True).first()

    @classmethod
    def get_active_gateways(cls):
        """Get all active gateways"""
        return cls.objects.filter(is_active=True)

    @property
    def credentials_json(self):
        """Return credentials as formatted JSON string for textarea display"""
        import json
        return json.dumps(self.credentials, indent=2)


class DefaultRate(models.Model):
    """
    Store SMS rates for operators.
    Each operator can have masking and non-masking rates stored in JSON.
    """
    # Operator-specific rates stored as nested JSON
    # Format: {"gp": {"masking": 0.30, "non_masking": 0.25}, "bl": {...}}
    operator_rates = models.JSONField(
        default=dict,
        blank=True,
        help_text='Operator-specific SMS rates. Format: {"gp": {"masking": 0.30, "non_masking": 0.25}, ...}'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'default_rates'
        verbose_name = 'Default Rate'
        verbose_name_plural = 'Default Rates'

    def __str__(self):
        return f"SMS Rates ({len(self.operator_rates)} operators)"

    @classmethod
    def get_instance(cls):
        """Get or create the singleton instance"""
        instance, created = cls.objects.get_or_create(pk=1)
        return instance

    @classmethod
    def get_masking_rate(cls, operator='gp'):
        """Get masking rate for an operator."""
        instance = cls.get_instance()
        op_rates = instance.operator_rates.get(operator, {})
        return op_rates.get('masking', 0.35)

    @classmethod
    def get_non_masking_rate(cls, operator='gp'):
        """Get non-masking rate for an operator."""
        instance = cls.get_instance()
        op_rates = instance.operator_rates.get(operator, {})
        return op_rates.get('non_masking', 0.25)

    def get_operator_rate(self, operator, message_type='masking'):
        """Get rate for a specific operator and message type."""
        op_rates = self.operator_rates.get(operator, {})
        return op_rates.get(message_type, 0.35 if message_type == 'masking' else 0.25)

    def set_operator_rate(self, operator, message_type, rate):
        """Set rate for a specific operator and message type."""
        if operator not in self.operator_rates:
            self.operator_rates[operator] = {}
        self.operator_rates[operator][message_type] = rate

    def get_all_operators(self):
        """Get list of all operators with their rates."""
        operators = {
            'gp': 'Grameenphone',
            'bl': 'Banglalink',
            'robi': 'Robi',
            'airtel': 'Airtel',
            'teletalk': 'Teletalk',
        }
        result = {}
        for code, name in operators.items():
            op_rates = self.operator_rates.get(code, {})
            result[code] = {
                'name': name,
                'masking': op_rates.get('masking'),
                'non_masking': op_rates.get('non_masking'),
            }
        return result
