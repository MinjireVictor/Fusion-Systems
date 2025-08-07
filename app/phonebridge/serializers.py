from rest_framework import serializers
from .models import ExtensionMapping, CallLog, ZohoToken

class ExtensionMappingSerializer(serializers.ModelSerializer):
    """Serializer for extension mappings"""
    user_email = serializers.EmailField(source='user.email', read_only=True)
    
    class Meta:
        model = ExtensionMapping
        fields = [
            'id', 
            'extension', 
            'zoho_user_id', 
            'is_active', 
            'user_email',
            'created_at', 
            'updated_at'
        ]
        read_only_fields = ['id', 'user_email', 'created_at', 'updated_at']
    
    def validate_extension(self, value):
        """Validate extension format"""
        if not value.isdigit():
            raise serializers.ValidationError("Extension must contain only digits")
        if len(value) < 2 or len(value) > 10:
            raise serializers.ValidationError("Extension must be between 2 and 10 digits")
        return value

class CallLogSerializer(serializers.ModelSerializer):
    """Serializer for call logs"""
    user_email = serializers.EmailField(source='user.email', read_only=True)
    duration_formatted = serializers.SerializerMethodField()
    
    class Meta:
        model = CallLog
        fields = [
            'id',
            'call_id',
            'user_email',
            'extension',
            'direction',
            'caller_number',
            'called_number',
            'status',
            'start_time',
            'end_time',
            'duration_seconds',
            'duration_formatted',
            'recording_url',
            'zoho_call_id',
            'notes',
            'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'id', 
            'user_email', 
            'duration_formatted',
            'created_at', 
            'updated_at'
        ]
    
    def get_duration_formatted(self, obj):
        """Format duration in human-readable format"""
        if not obj.duration_seconds:
            return None
        
        minutes, seconds = divmod(obj.duration_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"

class ZohoTokenSerializer(serializers.ModelSerializer):
    """Serializer for Zoho tokens (for admin/debug purposes)"""
    is_expired = serializers.SerializerMethodField()
    
    class Meta:
        model = ZohoToken
        fields = [
            'id',
            'zoho_user_id',
            'expires_at',
            'is_expired',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'is_expired', 'created_at', 'updated_at']
    
    def get_is_expired(self, obj):
        return obj.is_expired()