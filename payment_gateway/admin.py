from django.contrib import admin
from .models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        'transaction_id', 'user', 'gateway', 'amount', 'tdr_amount', 
        'total_amount', 'status', 'created_at'
    ]
    list_filter = ['status', 'gateway', 'created_at']
    search_fields = ['transaction_id', 'user__email', 'user__username']
    readonly_fields = [
        'transaction_id', 'created_at', 'updated_at', 'completed_at',
        'gateway_response', 'validation_response'
    ]
    ordering = ['-created_at']
    
    fieldsets = (
        ('Transaction Info', {
            'fields': ('transaction_id', 'user', 'gateway', 'status')
        }),
        ('Amount Details', {
            'fields': ('amount', 'tdr_amount', 'total_amount')
        }),
        ('Gateway Data', {
            'fields': ('gateway_transaction_id', 'session_key', 'gateway_response', 'validation_response'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )
