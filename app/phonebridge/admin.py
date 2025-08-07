from django.contrib import admin
from .models import ZohoToken, ExtensionMapping, CallLog, ZohoWebhookLog, VitalPBXWebhookLog

@admin.register(ZohoToken)
class ZohoTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'zoho_user_id', 'expires_at', 'is_expired', 'created_at']
    list_filter = ['expires_at', 'created_at']
    search_fields = ['user__email', 'zoho_user_id']
    readonly_fields = ['created_at', 'updated_at']
    
    def is_expired(self, obj):
        return obj.is_expired()
    is_expired.boolean = True
    is_expired.short_description = 'Expired'

@admin.register(ExtensionMapping)
class ExtensionMappingAdmin(admin.ModelAdmin):
    list_display = ['user', 'extension', 'zoho_user_id', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['user__email', 'extension', 'zoho_user_id']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(CallLog)
class CallLogAdmin(admin.ModelAdmin):
    list_display = [
        'call_id', 'user', 'direction', 'caller_number', 
        'called_number', 'status', 'start_time', 'duration_formatted'
    ]
    list_filter = ['direction', 'status', 'start_time', 'created_at']
    search_fields = ['call_id', 'caller_number', 'called_number', 'user__email']
    readonly_fields = ['created_at', 'updated_at', 'duration_formatted']
    date_hierarchy = 'start_time'
    
    def duration_formatted(self, obj):
        if not obj.duration_seconds:
            return '-'
        
        minutes, seconds = divmod(obj.duration_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"
    
    duration_formatted.short_description = 'Duration'

@admin.register(ZohoWebhookLog)
class ZohoWebhookLogAdmin(admin.ModelAdmin):
    list_display = ['event_type', 'processed', 'created_at', 'error_message_short']
    list_filter = ['event_type', 'processed', 'created_at']
    search_fields = ['event_type', 'error_message']
    readonly_fields = ['created_at']
    
    def error_message_short(self, obj):
        if obj.error_message:
            return obj.error_message[:50] + '...' if len(obj.error_message) > 50 else obj.error_message
        return '-'
    error_message_short.short_description = 'Error'

@admin.register(VitalPBXWebhookLog)
class VitalPBXWebhookLogAdmin(admin.ModelAdmin):
    list_display = ['event_type', 'processed', 'created_at', 'error_message_short']
    list_filter = ['event_type', 'processed', 'created_at']
    search_fields = ['event_type', 'error_message']
    readonly_fields = ['created_at']
    
    def error_message_short(self, obj):
        if obj.error_message:
            return obj.error_message[:50] + '...' if len(obj.error_message) > 50 else obj.error_message
        return '-'
    error_message_short.short_description = 'Error'