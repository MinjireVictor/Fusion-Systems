from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import json

User = get_user_model()

class ZohoToken(models.Model):
    """Store Zoho OAuth tokens with location-aware PhoneBridge support"""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    access_token = models.TextField()
    refresh_token = models.TextField()
    expires_at = models.DateTimeField()
    zoho_user_id = models.CharField(max_length=100, blank=True)
    
    # NEW: Location-aware OAuth fields
    location = models.CharField(
        max_length=10, 
        blank=True,
        help_text='Zoho location (us, eu, in, au, jp, sa, ca)'
    )
    oauth_domain = models.URLField(
        blank=True,
        help_text='Location-specific OAuth domain (e.g., https://accounts.zoho.com)'
    )
    api_domain = models.URLField(
        blank=True,
        help_text='Location-specific API domain (e.g., https://www.zohoapis.com)'
    )
    oauth_version = models.CharField(
        max_length=10,
        default='v3',
        help_text='OAuth version used (v2 for legacy, v3 for new PhoneBridge)'
    )
    scopes_granted = models.TextField(
        blank=True,
        help_text='Comma-separated list of granted scopes'
    )
    token_type = models.CharField(
        max_length=20,
        default='Bearer',
        help_text='Token type from OAuth response'
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_refreshed_at = models.DateTimeField(null=True, blank=True)
    
    def is_expired(self):
        return timezone.now() >= self.expires_at
    
    def is_phonebridge_enabled(self):
        """Check if token has PhoneBridge scopes"""
        if not self.scopes_granted:
            return False
        scopes = self.scopes_granted.lower()
        return 'phonebridge' in scopes
    
    def get_phonebridge_api_base(self):
        """Get PhoneBridge API base URL"""
        if self.api_domain:
            return f"{self.api_domain.rstrip('/')}/phonebridge/v3"
        return "https://www.zohoapis.com/phonebridge/v3"  # fallback
    
    def get_crm_api_base(self):
        """Get CRM API base URL"""
        if self.api_domain:
            return f"{self.api_domain.rstrip('/')}/crm/v2"
        return "https://www.zohoapis.com/crm/v2"  # fallback
    
    def needs_migration(self):
        """Check if token needs migration to new OAuth flow"""
        return not self.location or not self.api_domain or self.oauth_version != 'v3'
    
    def __str__(self):
        location_info = f" ({self.location})" if self.location else ""
        return f"Zoho Token for {self.user.email}{location_info}"
    
    class Meta:
        indexes = [
            models.Index(fields=['expires_at']),
            models.Index(fields=['location']),
            models.Index(fields=['oauth_version']),
        ]

class ExtensionMapping(models.Model):
    """Map VitalPBX extensions to Django users and Zoho users"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    extension = models.CharField(max_length=20, unique=True)
    zoho_user_id = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user', 'extension']
    
    def __str__(self):
        return f"{self.user.email} -> Extension {self.extension}"

class CallLog(models.Model):
    """Log all call activities with enhanced popup support"""
    CALL_DIRECTIONS = [
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
    ]
    
    CALL_STATUSES = [
        ('initiated', 'Initiated'),
        ('ringing', 'Ringing'),
        ('connected', 'Connected'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('no_answer', 'No Answer'),
        ('busy', 'Busy'),
    ]
    
    CONTACT_TYPES = [
        ('contact', 'Contact'),
        ('lead', 'Lead'),
        ('unknown', 'Unknown'),
    ]
    
    # Original fields
    call_id = models.CharField(max_length=100, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    extension = models.CharField(max_length=20)
    direction = models.CharField(max_length=10, choices=CALL_DIRECTIONS)
    caller_number = models.CharField(max_length=50)
    called_number = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=CALL_STATUSES, default='initiated')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)
    recording_url = models.URLField(blank=True)
    zoho_call_id = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Enhanced fields for popup functionality
    contact_id = models.CharField(
        max_length=100, 
        blank=True, 
        help_text='Zoho CRM Contact/Lead ID'
    )
    contact_name = models.CharField(
        max_length=255, 
        blank=True, 
        help_text='Contact/Lead name from CRM'
    )
    contact_type = models.CharField(
        max_length=20, 
        choices=CONTACT_TYPES,
        blank=True,
        help_text='Type of CRM record found'
    )
    contact_company = models.CharField(
        max_length=255,
        blank=True,
        help_text='Company name from CRM'
    )
    contact_email = models.EmailField(
        blank=True,
        help_text='Email from CRM record'
    )
    normalized_phone = models.CharField(
        max_length=20, 
        blank=True, 
        help_text='Normalized phone number (+254 format)'
    )
    popup_sent = models.BooleanField(
        default=False, 
        help_text='Whether popup was sent to Zoho PhoneBridge'
    )
    popup_response = models.TextField(
        blank=True, 
        help_text='Response from Zoho PhoneBridge API'
    )
    call_state = models.CharField(
        max_length=20,
        choices=CALL_STATUSES,
        default='initiated',
        help_text='Current call state based on VitalPBX events'
    )
    call_history_count = models.IntegerField(
        default=0,
        help_text='Number of previous calls with this contact'
    )
    recent_activity = models.TextField(
        blank=True,
        help_text='Recent CRM activity/notes for popup display'
    )
    
    class Meta:
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['call_id']),
            models.Index(fields=['normalized_phone']),
            models.Index(fields=['contact_id']),
            models.Index(fields=['extension', 'start_time']),
        ]
    
    def __str__(self):
        return f"{self.direction.title()} call: {self.caller_number} -> {self.called_number}"
    
    def get_caller_info(self):
        """Get formatted caller information for popup display"""
        if self.contact_name:
            return {
                'name': self.contact_name,
                'company': self.contact_company or 'Unknown Company',
                'email': self.contact_email,
                'type': self.contact_type,
                'phone': self.normalized_phone or self.caller_number,
                'call_count': self.call_history_count,
                'recent_activity': self.recent_activity
            }
        return {
            'name': 'Unknown Caller',
            'company': '',
            'email': '',
            'type': 'unknown',
            'phone': self.normalized_phone or self.caller_number,
            'call_count': 0,
            'recent_activity': ''
        }

class PopupLog(models.Model):
    """Track all popup attempts and responses"""
    POPUP_STATUSES = [
        ('pending', 'Pending'),
        ('sent', 'Sent Successfully'),
        ('failed', 'Failed'),
        ('retry', 'Retry Required'),
        ('duplicate', 'Duplicate Prevented'),
    ]
    
    call_log = models.ForeignKey(
        CallLog, 
        on_delete=models.CASCADE, 
        related_name='popup_logs'
    )
    call_id = models.CharField(
        max_length=100, 
        help_text='VitalPBX call ID for quick lookup'
    )
    zoho_user_id = models.CharField(
        max_length=100, 
        help_text='Target Zoho user ID'
    )
    extension = models.CharField(
        max_length=20, 
        help_text='Extension that received/made the call'
    )
    popup_data = models.JSONField(
        help_text='Complete popup data sent to Zoho PhoneBridge API'
    )
    popup_sent_at = models.DateTimeField(auto_now_add=True)
    zoho_response = models.TextField(
        blank=True, 
        help_text='Raw response from Zoho PhoneBridge API'
    )
    status = models.CharField(
        max_length=20,
        choices=POPUP_STATUSES,
        default='pending'
    )
    error_message = models.TextField(
        blank=True, 
        help_text='Error details if popup failed'
    )
    response_time_ms = models.IntegerField(
        null=True, 
        blank=True,
        help_text='API response time in milliseconds'
    )
    retry_count = models.IntegerField(
        default=0,
        help_text='Number of retry attempts'
    )
    
    class Meta:
        ordering = ['-popup_sent_at']
        indexes = [
            models.Index(fields=['call_id']),
            models.Index(fields=['zoho_user_id']),
            models.Index(fields=['extension']),
            models.Index(fields=['status']),
        ]
        unique_together = [
            ['call_id', 'zoho_user_id'],  # Prevent duplicate popups for same call/user
        ]
    
    def __str__(self):
        return f"Popup for call {self.call_id} to user {self.zoho_user_id} - {self.status}"
    
    def is_successful(self):
        """Check if popup was sent successfully"""
        return self.status == 'sent'
    
    def needs_retry(self):
        """Check if popup needs retry"""
        return self.status in ['failed', 'retry'] and self.retry_count < 3

class ZohoWebhookLog(models.Model):
    """Log all webhook events from Zoho"""
    event_type = models.CharField(max_length=50)
    payload = models.JSONField()
    processed = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Zoho webhook: {self.event_type} at {self.created_at}"

class VitalPBXWebhookLog(models.Model):
    """Log all webhook events from VitalPBX"""
    event_type = models.CharField(max_length=50)
    payload = models.JSONField()
    processed = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"VitalPBX webhook: {self.event_type} at {self.created_at}"

class OAuthMigrationLog(models.Model):
    """Track OAuth migration attempts and results"""
    MIGRATION_STATUSES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    old_token_data = models.JSONField(
        null=True, 
        blank=True,
        help_text='Backup of old token data'
    )
    migration_status = models.CharField(
        max_length=20,
        choices=MIGRATION_STATUSES,
        default='pending'
    )
    migration_started_at = models.DateTimeField(auto_now_add=True)
    migration_completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    notes = models.TextField(
        blank=True,
        help_text='Migration notes and details'
    )
    
    class Meta:
        ordering = ['-migration_started_at']
    
    def __str__(self):
        return f"OAuth Migration for {self.user.email} - {self.migration_status}"