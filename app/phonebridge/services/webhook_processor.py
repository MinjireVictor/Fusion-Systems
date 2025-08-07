# phonebridge/services/webhook_processor.py

import json
import logging
from datetime import datetime
from typing import Dict, Optional, List
from django.utils import timezone
from django.db import transaction
from django.conf import settings

from ..models import CallLog, ExtensionMapping, PopupLog, VitalPBXWebhookLog
from ..utils.phone_normalizer import PhoneNormalizer
from .zoho_service import ZohoService
from .phonebridge_service import PhoneBridgeService

logger = logging.getLogger('phonebridge')

class WebhookProcessor:
    """
    Enhanced webhook processor for VitalPBX events with popup integration
    """
    
    def __init__(self):
        self.phone_normalizer = PhoneNormalizer('kenya')
        self.zoho_service = ZohoService()
        self.phonebridge_service = PhoneBridgeService()
        
        # Get popup settings
        self.popup_settings = getattr(settings, 'PHONEBRIDGE_SETTINGS', {})
        self.popup_enabled = self.popup_settings.get('POPUP_ENABLED', True)
        self.include_call_history = self.popup_settings.get('INCLUDE_CALL_HISTORY', True)
        self.include_recent_notes = self.popup_settings.get('INCLUDE_RECENT_NOTES', True)
        
        logger.info(f"WebhookProcessor initialized - Popup enabled: {self.popup_enabled}")
    
    def process_webhook(self, payload: Dict, webhook_log: VitalPBXWebhookLog) -> bool:
        """
        Process VitalPBX webhook with enhanced call tracking and popup creation
        
        Args:
            payload: Webhook payload from VitalPBX
            webhook_log: Database record for this webhook
            
        Returns:
            Boolean indicating processing success
        """
        try:
            event_type = payload.get('Event', 'unknown')
            call_id = payload.get('Uniqueid', '')
            
            logger.info(f"Processing webhook: {event_type} for call {call_id}")
            
            # Route to specific event handlers
            if event_type == 'Newchannel':
                return self._handle_newchannel(payload, webhook_log)
            elif event_type == 'Dial':
                return self._handle_dial(payload, webhook_log)
            elif event_type == 'Bridge':
                return self._handle_bridge(payload, webhook_log)
            elif event_type == 'Hangup':
                return self._handle_hangup(payload, webhook_log)
            elif event_type in ['RecordStart', 'RecordStop']:
                return self._handle_recording(payload, webhook_log)
            else:
                logger.info(f"Unhandled event type: {event_type}")
                return True  # Not an error, just not processed
                
        except Exception as e:
            logger.error(f"Error processing webhook {event_type}: {str(e)}")
            webhook_log.error_message = str(e)
            webhook_log.save()
            return False
    
    def _handle_newchannel(self, payload: Dict, webhook_log: VitalPBXWebhookLog) -> bool:
        """
        Handle Newchannel event - Call initiated (earliest event)
        This is where we create the initial CallLog and potentially trigger popup
        """
        call_id = payload.get('Uniqueid', '')
        channel = payload.get('Channel', '')
        caller_number = payload.get('CallerIDNum', '')
        context = payload.get('Context', '')
        
        if not call_id:
            logger.warning("Newchannel event missing Uniqueid")
            return False
        
        # Determine call direction and extract extension
        direction, extension, called_number = self._analyze_call_direction(payload)
        
        if not extension:
            logger.info(f"No extension found for call {call_id}, skipping popup")
            return True
        
        logger.info(f"New call detected: {direction} on extension {extension}")
        
        try:
            with transaction.atomic():
                # Create or get CallLog
                call_log, created = CallLog.objects.get_or_create(
                    call_id=call_id,
                    defaults={
                        'extension': extension,
                        'direction': direction,
                        'caller_number': caller_number,
                        'called_number': called_number,
                        'call_state': 'initiated',
                        'start_time': timezone.now(),
                        'status': 'initiated'
                    }
                )
                
                if created:
                    logger.info(f"Created new CallLog for {call_id}")
                    
                    # Enhance call log with normalized phone and contact info
                    self._enrich_call_log(call_log)
                    
                    # Create popup if enabled
                    if self.popup_enabled:
                        self._create_popup_for_call(call_log)
                else:
                    logger.info(f"CallLog already exists for {call_id}")
                
                webhook_log.processed = True
                webhook_log.save()
                
                return True
                
        except Exception as e:
            logger.error(f"Error handling Newchannel for {call_id}: {str(e)}")
            return False
    
    def _handle_dial(self, payload: Dict, webhook_log: VitalPBXWebhookLog) -> bool:
        """
        Handle Dial event - Call is ringing/connecting
        """
        call_id = payload.get('Uniqueid', '')
        
        try:
            call_log = CallLog.objects.get(call_id=call_id)
            call_log.call_state = 'ringing'
            call_log.status = 'ringing'
            call_log.save()
            
            logger.info(f"Call {call_id} state updated to ringing")
            
            webhook_log.processed = True
            webhook_log.save()
            
            return True
            
        except CallLog.DoesNotExist:
            logger.warning(f"Dial event for unknown call {call_id}")
            return False
        except Exception as e:
            logger.error(f"Error handling Dial for {call_id}: {str(e)}")
            return False
    
    def _handle_bridge(self, payload: Dict, webhook_log: VitalPBXWebhookLog) -> bool:
        """
        Handle Bridge event - Call connected
        """
        call_id = payload.get('Uniqueid', '')
        
        try:
            call_log = CallLog.objects.get(call_id=call_id)
            call_log.call_state = 'connected'
            call_log.status = 'connected'
            call_log.save()
            
            logger.info(f"Call {call_id} state updated to connected")
            
            webhook_log.processed = True
            webhook_log.save()
            
            return True
            
        except CallLog.DoesNotExist:
            logger.warning(f"Bridge event for unknown call {call_id}")
            return False
        except Exception as e:
            logger.error(f"Error handling Bridge for {call_id}: {str(e)}")
            return False
    
    def _handle_hangup(self, payload: Dict, webhook_log: VitalPBXWebhookLog) -> bool:
        """
        Handle Hangup event - Call ended
        """
        call_id = payload.get('Uniqueid', '')
        hangup_cause = payload.get('HangupCause', '')
        
        try:
            call_log = CallLog.objects.get(call_id=call_id)
            call_log.call_state = 'completed'
            call_log.status = self._map_hangup_cause(hangup_cause)
            call_log.end_time = timezone.now()
            
            # Calculate duration
            if call_log.start_time:
                duration = call_log.end_time - call_log.start_time
                call_log.duration_seconds = int(duration.total_seconds())
            
            call_log.save()
            
            logger.info(f"Call {call_id} ended - Duration: {call_log.duration_seconds}s")
            
            # Close popup if it exists
            self._close_popup_for_call(call_log)
            
            webhook_log.processed = True
            webhook_log.save()
            
            return True
            
        except CallLog.DoesNotExist:
            logger.warning(f"Hangup event for unknown call {call_id}")
            return False
        except Exception as e:
            logger.error(f"Error handling Hangup for {call_id}: {str(e)}")
            return False
    
    def _handle_recording(self, payload: Dict, webhook_log: VitalPBXWebhookLog) -> bool:
        """
        Handle recording events - RecordStart/RecordStop
        """
        call_id = payload.get('Uniqueid', '')
        event_type = payload.get('Event', '')
        
        try:
            call_log = CallLog.objects.get(call_id=call_id)
            
            if event_type == 'RecordStart':
                recording_file = payload.get('RecordingFile', '')
                if recording_file:
                    # Store recording info (will be processed later)
                    call_log.notes += f"\nRecording started: {recording_file}"
                    call_log.save()
                    logger.info(f"Recording started for call {call_id}: {recording_file}")
            
            elif event_type == 'RecordStop':
                recording_file = payload.get('RecordingFile', '')
                if recording_file:
                    call_log.recording_url = recording_file  # Will be converted to URL later
                    call_log.save()
                    logger.info(f"Recording stopped for call {call_id}: {recording_file}")
            
            webhook_log.processed = True
            webhook_log.save()
            
            return True
            
        except CallLog.DoesNotExist:
            logger.warning(f"Recording event for unknown call {call_id}")
            return False
        except Exception as e:
            logger.error(f"Error handling recording event for {call_id}: {str(e)}")
            return False
    
    def _analyze_call_direction(self, payload: Dict) -> tuple:
        """
        Analyze webhook payload to determine call direction and extract extension
        
        Returns:
            Tuple of (direction, extension, called_number)
        """
        channel = payload.get('Channel', '')
        context = payload.get('Context', '')
        caller_id = payload.get('CallerIDNum', '')
        exten = payload.get('Exten', '')
        
        # Extract extension from channel (e.g., 'PJSIP/101-00000001' -> '101')
        extension_match = re.search(r'PJSIP/(\d+)', channel)
        extension = extension_match.group(1) if extension_match else None
        
        # Determine direction based on context and patterns
        if context in ['from-internal', 'from-zoho']:
            # Outbound call
            direction = 'outbound'
            called_number = exten or ''
        else:
            # Inbound call
            direction = 'inbound'
            called_number = extension or ''
        
        return direction, extension, called_number
    
    def _enrich_call_log(self, call_log: CallLog) -> None:
        """
        Enrich call log with normalized phone number and contact information
        """
        try:
            # Determine which number to lookup based on direction
            lookup_number = call_log.caller_number if call_log.direction == 'inbound' else call_log.called_number
            
            # Normalize phone number
            norm_result = self.phone_normalizer.normalize(lookup_number)
            call_log.normalized_phone = norm_result['normalized']
            
            # Lookup contact in Zoho CRM
            contact_info = self._lookup_contact_in_crm(norm_result)
            
            if contact_info:
                call_log.contact_id = contact_info.get('id', '')
                call_log.contact_name = contact_info.get('name', '')
                call_log.contact_type = contact_info.get('type', 'unknown')
                call_log.contact_company = contact_info.get('company', '')
                call_log.contact_email = contact_info.get('email', '')
                
                # Get call history if enabled
                if self.include_call_history:
                    call_log.call_history_count = self._get_call_history_count(call_log.normalized_phone)
                
                # Get recent activity if enabled
                if self.include_recent_notes:
                    call_log.recent_activity = self._get_recent_activity(contact_info.get('id', ''))
            
            call_log.save()
            logger.info(f"Enriched call log for {call_log.call_id} with contact: {call_log.contact_name}")
            
        except Exception as e:
            logger.error(f"Error enriching call log {call_log.call_id}: {str(e)}")
    
    def _lookup_contact_in_crm(self, norm_result: Dict) -> Optional[Dict]:
        """
        Lookup contact in Zoho CRM using normalized phone number
        """
        if not norm_result['valid']:
            return None
        
        try:
            # Get all possible phone formats for searching
            search_variants = norm_result['formats']
            
            # Try to get Zoho access token
            # This would need to be enhanced to get token from current user context
            # For now, we'll use a service account or first available token
            from ..models import ZohoToken
            zoho_token = ZohoToken.objects.filter(
                expires_at__gt=timezone.now()
            ).first()
            
            if not zoho_token:
                logger.warning("No valid Zoho token available for contact lookup")
                return None
            
            # Search for contact using all phone variants
            for phone_variant in search_variants:
                contacts = self.zoho_service.search_contact_by_phone(
                    zoho_token.access_token, 
                    phone_variant
                )
                
                if contacts:
                    # Return highest priority contact (Contact > Lead)
                    contact_priority = {'Contact': 1, 'Lead': 2, 'unknown': 3}
                    best_contact = min(contacts, key=lambda x: contact_priority.get(x['module'], 3))
                    
                    return {
                        'id': best_contact['id'],
                        'name': best_contact['name'],
                        'company': best_contact['company'],
                        'email': best_contact['email'],
                        'phone': best_contact['phone'],
                        'type': best_contact['module'].lower(),
                        'record': best_contact['record']
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Error looking up contact: {str(e)}")
            return None
    
    def _get_call_history_count(self, phone_number: str) -> int:
        """Get count of previous calls with this phone number"""
        try:
            return CallLog.objects.filter(
                normalized_phone=phone_number,
                status='completed'
            ).count()
        except Exception as e:
            logger.error(f"Error getting call history count: {str(e)}")
            return 0
    
    def _get_recent_activity(self, contact_id: str) -> str:
        """Get recent CRM activity for contact"""
        # This would integrate with Zoho CRM Activities API
        # For now, return placeholder
        try:
            # TODO: Implement Zoho CRM activity lookup
            return "Recent activity lookup not implemented yet"
        except Exception as e:
            logger.error(f"Error getting recent activity: {str(e)}")
            return ""
    
    def _create_popup_for_call(self, call_log: CallLog) -> None:
        """
        Create popup for all users mapped to the extension
        """
        try:
            # Get all users mapped to this extension
            extension_mappings = ExtensionMapping.objects.filter(
                extension=call_log.extension,
                is_active=True
            )
            
            if not extension_mappings.exists():
                logger.info(f"No users mapped to extension {call_log.extension}")
                return
            
            for mapping in extension_mappings:
                if mapping.zoho_user_id:
                    self._send_popup_to_user(call_log, mapping.zoho_user_id)
                else:
                    logger.warning(f"User {mapping.user.email} has no Zoho user ID")
                    
        except Exception as e:
            logger.error(f"Error creating popup for call {call_log.call_id}: {str(e)}")
    
    def _send_popup_to_user(self, call_log: CallLog, zoho_user_id: str) -> None:
        """
        Send popup to specific Zoho user
        """
        try:
            # Check for existing popup to prevent duplicates
            existing_popup = PopupLog.objects.filter(
                call_id=call_log.call_id,
                zoho_user_id=zoho_user_id
            ).first()
            
            if existing_popup:
                logger.info(f"Popup already exists for call {call_log.call_id} user {zoho_user_id}")
                return
            
            # Prepare popup data
            popup_data = {
                'callId': call_log.call_id,
                'fromNumber': call_log.caller_number,
                'toNumber': call_log.called_number,
                'direction': call_log.direction,
                'userId': zoho_user_id,
                'timestamp': call_log.start_time.isoformat(),
                'contactInfo': call_log.get_caller_info()
            }
            
            # Create popup log entry
            popup_log = PopupLog.objects.create(
                call_log=call_log,
                call_id=call_log.call_id,
                zoho_user_id=zoho_user_id,
                extension=call_log.extension,
                popup_data=popup_data,
                status='pending'
            )
            
            # Send popup via PhoneBridge service
            success = self.phonebridge_service.send_popup(popup_data, popup_log)
            
            if success:
                call_log.popup_sent = True
                call_log.save()
                logger.info(f"Popup sent successfully for call {call_log.call_id} to user {zoho_user_id}")
            else:
                logger.error(f"Failed to send popup for call {call_log.call_id} to user {zoho_user_id}")
                
        except Exception as e:
            logger.error(f"Error sending popup to user {zoho_user_id}: {str(e)}")
    
    def _close_popup_for_call(self, call_log: CallLog) -> None:
        """
        Close/dismiss popup when call ends
        """
        try:
            # Get all popup logs for this call
            popup_logs = PopupLog.objects.filter(
                call_id=call_log.call_id,
                status='sent'
            )
            
            for popup_log in popup_logs:
                self.phonebridge_service.close_popup(call_log.call_id, popup_log.zoho_user_id)
                
            logger.info(f"Closed popups for ended call {call_log.call_id}")
            
        except Exception as e:
            logger.error(f"Error closing popup for call {call_log.call_id}: {str(e)}")
    
    def _map_hangup_cause(self, hangup_cause: str) -> str:
        """
        Map VitalPBX hangup cause to our call status
        """
        cause_mapping = {
            '16': 'completed',     # Normal clearing
            '17': 'busy',          # User busy
            '18': 'no_answer',     # No user responding
            '19': 'no_answer',     # No answer
            '21': 'failed',        # Call rejected
            '34': 'failed',        # No circuit available
        }
        
        return cause_mapping.get(hangup_cause, 'completed')


# Import regex for extension extraction
import re


class EnhancedVitalPBXWebhookView:
    """
    Enhanced webhook view that integrates with WebhookProcessor
    """
    
    def __init__(self):
        self.processor = WebhookProcessor()
    
    def process_webhook_payload(self, payload: Dict) -> Dict[str, any]:
        """
        Process webhook payload using enhanced processor
        
        Args:
            payload: Raw webhook payload from VitalPBX
            
        Returns:
            Dict with processing results
        """
        try:
            # Log the webhook
            webhook_log = VitalPBXWebhookLog.objects.create(
                event_type=payload.get('Event', 'unknown'),
                payload=payload
            )
            
            # Process with enhanced processor
            success = self.processor.process_webhook(payload, webhook_log)
            
            return {
                'success': success,
                'webhook_log_id': webhook_log.id,
                'message': 'Webhook processed successfully' if success else 'Webhook processing failed'
            }
            
        except Exception as e:
            logger.error(f"Error in webhook processing: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'message': 'Webhook processing failed with exception'
            }


# Utility functions for call analysis
class CallAnalyzer:
    """
    Utility class for analyzing call patterns and extracting information
    """
    
    @staticmethod
    def extract_extension_from_channel(channel: str) -> Optional[str]:
        """
        Extract extension number from VitalPBX channel string
        
        Examples:
            'PJSIP/101-00000001' -> '101'
            'SIP/102-abc123' -> '102'
            'Local/103@from-internal' -> '103'
        """
        patterns = [
            r'PJSIP/(\d+)-',      # PJSIP channels
            r'SIP/(\d+)-',        # SIP channels
            r'Local/(\d+)@',      # Local channels
            r'DAHDI/(\d+)-',      # DAHDI channels
        ]
        
        for pattern in patterns:
            match = re.search(pattern, channel)
            if match:
                return match.group(1)
        
        return None
    
    @staticmethod
    def determine_call_direction(payload: Dict) -> str:
        """
        Determine call direction based on webhook payload
        """
        context = payload.get('Context', '')
        channel = payload.get('Channel', '')
        
        # Common patterns for call direction
        inbound_contexts = [
            'from-pstn', 'from-trunk', 'from-external', 
            'inbound', 'from-did'
        ]
        
        outbound_contexts = [
            'from-internal', 'from-zoho', 'outbound',
            'from-extensions'
        ]
        
        context_lower = context.lower()
        
        for ctx in inbound_contexts:
            if ctx in context_lower:
                return 'inbound'
        
        for ctx in outbound_contexts:
            if ctx in context_lower:
                return 'outbound'
        
        # Fallback: analyze channel
        if 'local' in channel.lower():
            return 'outbound'  # Local channels often indicate outbound
        
        return 'inbound'  # Default to inbound if uncertain
    
    @staticmethod
    def extract_numbers_from_payload(payload: Dict, direction: str) -> Dict[str, str]:
        """
        Extract caller and called numbers based on call direction
        """
        caller_id_num = payload.get('CallerIDNum', '')
        caller_id_name = payload.get('CallerIDName', '')
        exten = payload.get('Exten', '')
        channel = payload.get('Channel', '')
        
        if direction == 'inbound':
            # For inbound calls
            caller_number = caller_id_num
            called_number = CallAnalyzer.extract_extension_from_channel(channel) or exten
        else:
            # For outbound calls
            caller_number = CallAnalyzer.extract_extension_from_channel(channel) or caller_id_num
            called_number = exten or payload.get('DestinationExt', '')
        
        return {
            'caller_number': caller_number,
            'called_number': called_number,
            'caller_name': caller_id_name
        }


# Configuration validation
class WebhookConfiguration:
    """
    Validate and manage webhook configuration
    """
    
    @staticmethod
    def validate_popup_settings() -> Dict[str, any]:
        """
        Validate popup-related configuration settings
        """
        settings_obj = getattr(settings, 'PHONEBRIDGE_SETTINGS', {})
        
        required_settings = {
            'POPUP_ENABLED': bool,
            'POPUP_TIMEOUT_SECONDS': int,
            'CONTACT_LOOKUP_CACHE_TTL': int,
            'MAX_POPUP_RETRIES': int,
        }
        
        validation_result = {
            'valid': True,
            'warnings': [],
            'errors': []
        }
        
        for setting_name, expected_type in required_settings.items():
            value = settings_obj.get(setting_name)
            
            if value is None:
                validation_result['warnings'].append(f"{setting_name} not set, using default")
            elif not isinstance(value, expected_type):
                validation_result['errors'].append(f"{setting_name} should be {expected_type.__name__}")
                validation_result['valid'] = False
        
        # Check Zoho token availability
        from ..models import ZohoToken
        active_tokens = ZohoToken.objects.filter(expires_at__gt=timezone.now()).count()
        
        if active_tokens == 0:
            validation_result['warnings'].append("No active Zoho tokens available for CRM lookup")
        
        # Check extension mappings
        from ..models import ExtensionMapping
        active_mappings = ExtensionMapping.objects.filter(is_active=True).count()
        
        if active_mappings == 0:
            validation_result['warnings'].append("No active extension mappings configured")
        
        return validation_result
    
    @staticmethod
    def get_popup_settings() -> Dict[str, any]:
        """
        Get popup settings with defaults
        """
        settings_obj = getattr(settings, 'PHONEBRIDGE_SETTINGS', {})
        
        return {
            'popup_enabled': settings_obj.get('POPUP_ENABLED', True),
            'popup_timeout': settings_obj.get('POPUP_TIMEOUT_SECONDS', 10),
            'cache_ttl': settings_obj.get('CONTACT_LOOKUP_CACHE_TTL', 300),
            'max_retries': settings_obj.get('MAX_POPUP_RETRIES', 3),
            'include_history': settings_obj.get('INCLUDE_CALL_HISTORY', True),
            'include_notes': settings_obj.get('INCLUDE_RECENT_NOTES', True),
        }


# Example usage and testing
if __name__ == "__main__":
    # Test webhook processing
    sample_newchannel_payload = {
        "Event": "Newchannel",
        "Uniqueid": "1728123456.123",
        "Channel": "PJSIP/101-00000001",
        "CallerIDNum": "+254712345678",
        "CallerIDName": "John Doe",
        "Context": "from-pstn",
        "Exten": "101",
        "Timestamp": "2025-08-04T10:15:00Z"
    }
    
    # This would be called from the actual webhook view
    processor = WebhookProcessor()
    # processor.process_webhook(sample_newchannel_payload, webhook_log)
    
    print("WebhookProcessor initialized successfully")
    print("Configuration validation:")
    validation = WebhookConfiguration.validate_popup_settings()
    print(f"Valid: {validation['valid']}")
    print(f"Warnings: {validation['warnings']}")
    print(f"Errors: {validation['errors']}")