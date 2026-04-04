from django.contrib import admin
from django.utils.html import format_html
from .models import Profile, DefaultRate, SMSProvider, SenderID, PaymentGateway


@admin.register(PaymentGateway)
class PaymentGatewayAdmin(admin.ModelAdmin):
    list_display = ['name', 'gateway_class', 'tdr', 'is_active', 'updated_at']
    list_filter = ['gateway_class', 'is_active']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(SenderID)
class SenderIDAdmin(admin.ModelAdmin):
    list_display = ['sender_id', 'provider', 'created_at']
    list_filter = ['provider']
    search_fields = ['sender_id', 'provider__name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(SMSProvider)
class SMSProviderAdmin(admin.ModelAdmin):
    list_display = ['name', 'provider_class', 'masking_rate', 'non_masking_rate', 'updated_at']
    list_filter = ['provider_class']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(DefaultRate)
class DefaultRateAdmin(admin.ModelAdmin):
    list_display = ['operator_rates_summary', 'updated_at']
    readonly_fields = ['updated_at']
    
    def operator_rates_summary(self, obj):
        """Display a summary of operator rates"""
        rates = obj.get_all_operators()
        parts = []
        for code, data in rates.items():
            masking = data.get('masking') or '-'
            non_masking = data.get('non_masking') or '-'
            parts.append(f"{code.upper()}: M={masking}, N={non_masking}")
        return '; '.join(parts) if parts else 'No rates set'
    operator_rates_summary.short_description = 'Operator Rates'
    
    def has_add_permission(self, request):
        """Prevent adding more than one instance"""
        return not DefaultRate.objects.exists()


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'photo_preview', 'mobile_number', 'balance', 'created_at', 'updated_at']
    list_filter = ['created_at', 'updated_at']
    search_fields = ['user__email', 'mobile_number']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'mobile_number')
        }),
        ('Profile Photo', {
            'fields': ('photo',)
        }),
        ('Account', {
            'fields': ('balance',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def photo_preview(self, obj):
        if obj.photo:
            return format_html('<img src="{}" style="width: 40px; height: 40px; border-radius: 50%;" />', obj.photo.url)
        return '-'
    photo_preview.short_description = 'Photo'
