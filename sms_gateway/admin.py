"""
SMS Gateway Admin configuration
"""
from django.contrib import admin
from .models import SMSLog, SMSQueue, UserSMSRate


@admin.register(SMSLog)
class SMSLogAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'sender_id', 'status', 'created_at', 'user')
    list_filter = ('status', 'provider', 'created_at')
    search_fields = ('recipient', 'message', 'message_id')
    readonly_fields = ('created_at', 'updated_at', 'delivered_at')
    date_hierarchy = 'created_at'


@admin.register(SMSQueue)
class SMSQueueAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'total_recipients', 'success_count', 'failed_count', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('name', 'message')
    readonly_fields = ('created_at', 'started_at', 'completed_at')


@admin.register(UserSMSRate)
class UserSMSRateAdmin(admin.ModelAdmin):
    list_display = ('user', 'operator', 'message_type', 'rate', 'is_active', 'updated_at')
    list_filter = ('operator', 'message_type', 'is_active', 'updated_at')
    search_fields = ('user__username', 'user__email')
    list_editable = ('rate', 'is_active')
