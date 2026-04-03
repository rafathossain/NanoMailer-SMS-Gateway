from django.contrib import admin
from django.utils.html import format_html
from .models import Profile, DefaultRate, SMSProvider, SenderID, PaymentGateway


@admin.register(PaymentGateway)
class PaymentGatewayAdmin(admin.ModelAdmin):
    list_display = ['name', 'gateway_class', 'tdr', 'is_active', 'is_default', 'updated_at']
    list_filter = ['gateway_class', 'is_active', 'is_default']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(SenderID)
class SenderIDAdmin(admin.ModelAdmin):
    list_display = ['sender_id', 'provider', 'is_active', 'created_at']
    list_filter = ['provider', 'is_active']
    search_fields = ['sender_id', 'provider__name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(SMSProvider)
class SMSProviderAdmin(admin.ModelAdmin):
    list_display = ['name', 'provider_class', 'masking_rate', 'non_masking_rate', 'is_active', 'is_default', 'updated_at']
    list_filter = ['provider_class', 'is_active', 'is_default']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(DefaultRate)
class DefaultRateAdmin(admin.ModelAdmin):
    list_display = ['masking_rate', 'non_masking_rate', 'updated_at']
    readonly_fields = ['updated_at']
    
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
