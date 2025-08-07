# phonebridge/services/phonebridge_service.py

import requests
import json
import logging
import time
from datetime import datetime
from typing import Dict, Optional, List
from django.conf import settings
from django.utils import timezone

from ..models import ZohoToken, PopupLog

logger = logging.getLogger('phonebridge')

class PhoneBridgeService:
    """
    Service for interacting with Zoho PhoneBridge API for popup management
    """
    
    def __init__(self):
        self.config = settings.PHONEBRIDGE_SETTINGS
        self.api_base = self.config.get('ZOHO_API_BASE', 'https://www.zohoapis.com')
        self.phonebridge_base = f"{self.api_base}/phonebridge/v3"
        
        # Popup specific settings
        self.popup_timeout = self.config.get('POPUP_TIMEOUT_SECONDS', 10)
        self.max_retries = self.config.get('MAX_POPUP_RETRIES', 3)
        
        logger.info(f"PhoneBridgeService initialized - API Base: {self.phonebridge_base}")
    
    def send_popup(self, popup_data: Dict, popup_log: PopupLog) -> bool:
        """
        Send popup to Zoho PhoneBridge API
        
        Args:
            popup_data: Popup data to send
            popup_log: PopupLog instance to track the attempt
            
        Returns:
            Boolean indicating success
        """
        start_time = time.time()
        
        try:
            # Get access token for the user
            access_token = self._get_access_token_for_user(popup_data['userId'])
            if not access_token:
                popup_log.status = 'failed'
                popup_log.error_message = 'No valid access token available'
                popup_log.save()
                return False
            
            # Prepare API request
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            # Enhanced popup payload for Zoho PhoneBridge
            zoho_popup_payload = self._prepare_zoho_popup_payload(popup_data)
            
            # Send popup request
            url = f"{self.phonebridge_base}/calls/popup"
            
            logger.info(f"Sending popup to {url} for call {popup_data['callId']}")
            logger.debug(f"Popup payload: {json.dumps(zoho_popup_payload, indent=2)}")
            
            response = requests.post(
                url,
                headers=headers,
                json=zoho_popup_payload,
                timeout=self.popup_timeout
            )
            
            # Calculate response time
            response_time_ms = int((time.time() - start_time) * 1000)
            popup_log.response_time_ms = response_time_ms
            
            # Handle response
            popup_log.zoho_response = response.text
            
            if response.status_code in [200, 201, 202]:
                popup_log.status = 'sent'
                logger.info(f"Popup sent successfully for call {popup_data['callId']} (Response time: {response_time_ms}ms)")
                
                # Store response data if available
                try:
                    response_data = response.json()
                    popup_log.popup_response = json.dumps(response_data)
                except:
                    popup_log.popup_response = response.text
                
                popup_log.save()
                return True
            
            else:
                popup_log.status = 'failed'
                popup_log.error_message = f"HTTP {response.status_code}: {response.text}"
                
                logger.error(f"Popup failed for call {popup_data['callId']}: {popup_log.error_message}")
                
                # Check if we should retry
                if response.status_code in [429, 500, 502, 503, 504] and popup_log.retry_count < self.max_retries:
                    popup_log.status = 'retry'
                    popup_log.retry_count += 1
                    logger.info(f"Marking popup for retry (attempt {popup_log.retry_count})")
                
                popup_log.save()
                return False
        
        except requests.exceptions.Timeout:
            popup_log.status = 'failed'
            popup_log.error_message = f'Request timeout after {self.popup_timeout} seconds'
            popup_log.response_time_ms = int((time.time() - start_time) * 1000)
            popup_log.save()
            logger.error(f"Popup timeout for call {popup_data['callId']}")
            return False
        
        except requests.exceptions.RequestException as e:
            popup_log.status = 'failed'
            popup_log.error_message = f'Request error: {str(e)}'
            popup_log.response_time_ms = int((time.time() - start_time) * 1000)
            popup_log.save()
            logger.error(f"Popup request error for call {popup_data['callId']}: {str(e)}")
            return False
        
        except Exception as e:
            popup_log.status = 'failed'
            popup_log.error_message = f'Unexpected error: {str(e)}'
            popup_log.response_time_ms = int((time.time() - start_time) * 1000)
            popup_log.save()
            logger.error(f"Unexpected error sending popup for call {popup_data['callId']}: {str(e)}")
            return False
    
    def close_popup(self, call_id: str, zoho_user_id: str) -> bool:
        """
        Close/dismiss popup when call ends
        
        Args:
            call_id: VitalPBX call ID
            zoho_user_id: Zoho user ID
            
        Returns:
            Boolean indicating success
        """
        try:
            access_token = self._get_access_token_for_user(zoho_user_id)
            if not access_token:
                logger.warning(f"No access token available to close popup for call {call_id}")
                return False
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            url = f"{self.phonebridge_base}/calls/{call_id}/close"
            
            response = requests.delete(url, headers=headers, timeout=self.popup_timeout)
            
            if response.status_code in [200, 204, 404]:  # 404 is OK, popup might already be closed
                logger.info(f"Popup closed for call {call_id}")
                return True
            else:
                logger.warning(f"Failed to close popup for call {call_id}: HTTP {response.status_code}")
                return False
        
        except Exception as e:
            logger.error(f"Error closing popup for call {call_id}: {str(e)}")
            return False
    
    def update_popup(self, call_id: str, zoho_user_id: str, update_data: Dict) -> bool:
        """
        Update existing popup with new information
        
        Args:
            call_id: VitalPBX call ID
            zoho_user_id: Zoho user ID
            update_data: Data to update in popup
            
        Returns:
            Boolean indicating success
        """
        try:
            access_token = self._get_access_token_for_user(zoho_user_id)
            if not access_token:
                return False
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            url = f"{self.phonebridge_base}/calls/{call_id}"
            
            response = requests.patch(url, headers=headers, json=update_data, timeout=self.popup_timeout)
            
            if response.status_code in [200, 202]:
                logger.info(f"Popup updated for call {call_id}")
                return True
            else:
                logger.warning(f"Failed to update popup for call {call_id}: HTTP {response.status_code}")
                return False
        
        except Exception as e:
            logger.error(f"Error updating popup for call {call_id}: {str(e)}")
            return False
    
    def _prepare_zoho_popup_payload(self, popup_data: Dict) -> Dict:
        """
        Prepare popup payload in Zoho PhoneBridge API format
        """
        contact_info = popup_data.get('contactInfo', {})
        
        # Build the Zoho-compatible popup payload
        zoho_payload = {
            'call': {
                'id': popup_data['callId'],
                'from': popup_data['fromNumber'],
                'to': popup_data['toNumber'],
                'direction': popup_data['direction'],
                'startTime': popup_data['timestamp'],
                'status': 'ringing'
            },
            'contact': {
                'name': contact_info.get('name', 'Unknown Caller'),
                'phone': contact_info.get('phone', ''),
                'email': contact_info.get('email', ''),
                'company': contact_info.get('company', ''),
                'type': contact_info.get('type', 'unknown')
            },
            'metadata': {
                'callHistory': {
                    'totalCalls': contact_info.get('call_count', 0),
                    'recentActivity': contact_info.get('recent_activity', '')
                },
                'source': 'VitalPBX',
                'integration': 'PhoneBridge'
            },
            'user': {
                'id': popup_data['userId']
            },
            'actions': self._get_popup_actions(popup_data['direction'])
        }
        
        return zoho_payload
    
    def _get_popup_actions(self, call_direction: str) -> List[Dict]:
        """
        Get appropriate actions for popup based on call direction
        """
        if call_direction == 'inbound':
            return [
                {
                    'id': 'answer',
                    'label': 'Answer',
                    'type': 'primary',
                    'action': 'answer_call'
                },
                {
                    'id': 'decline',
                    'label': 'Decline',
                    'type': 'secondary',
                    'action': 'decline_call'
                },
                {
                    'id': 'record',
                    'label': 'Record',
                    'type': 'toggle',
                    'action': 'toggle_recording'
                }
            ]
        else:  # outbound
            return [
                {
                    'id': 'hangup',
                    'label': 'Hangup',
                    'type': 'danger',
                    'action': 'hangup_call'
                },
                {
                    'id': 'record',
                    'label': 'Record',
                    'type': 'toggle',
                    'action': 'toggle_recording'
                }
            ]
    
    def _get_access_token_for_user(self, zoho_user_id: str) -> Optional[str]:
        """
        Get valid access token for specific Zoho user
        """
        try:
            # Find token by Zoho user ID
            zoho_token = ZohoToken.objects.filter(
                zoho_user_id=zoho_user_id,
                expires_at__gt=timezone.now()
            ).first()
            
            if not zoho_token:
                # Fallback: get any valid token
                zoho_token = ZohoToken.objects.filter(
                    expires_at__gt=timezone.now()
                ).first()
            
            if not zoho_token:
                logger.warning("No valid Zoho tokens available")
                return None
            
            # Check if token needs refresh
            if zoho_token.is_expired():
                from .zoho_service import ZohoService
                zoho_service = ZohoService()
                
                try:
                    refresh_result = zoho_service.refresh_access_token(zoho_token.refresh_token)
                    zoho_token.access_token = refresh_result['access_token']
                    zoho_token.expires_at = refresh_result['expires_at']
                    if 'refresh_token' in refresh_result:
                        zoho_token.refresh_token = refresh_result['refresh_token']
                    zoho_token.save()
                    
                    logger.info("Access token refreshed successfully")
                except Exception as e:
                    logger.error(f"Failed to refresh access token: {str(e)}")
                    return None
            
            return zoho_token.access_token
            
        except Exception as e:
            logger.error(f"Error getting access token for user {zoho_user_id}: {str(e)}")
            return None
    
    def retry_failed_popups(self) -> Dict[str, int]:
        """
        Retry popups that failed and are marked for retry
        
        Returns:
            Dict with retry statistics
        """
        stats = {
            'attempted': 0,
            'succeeded': 0,
            'failed': 0
        }
        
        try:
            # Get popups that need retry
            retry_popups = PopupLog.objects.filter(
                status='retry',
                retry_count__lt=self.max_retries
            ).order_by('popup_sent_at')[:10]  # Limit to 10 at a time
            
            for popup_log in retry_popups:
                stats['attempted'] += 1
                
                logger.info(f"Retrying popup for call {popup_log.call_id} (attempt {popup_log.retry_count + 1})")
                
                success = self.send_popup(popup_log.popup_data, popup_log)
                
                if success:
                    stats['succeeded'] += 1
                else:
                    stats['failed'] += 1
            
            logger.info(f"Popup retry complete: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Error during popup retry: {str(e)}")
            return stats
    
    def get_popup_statistics(self, hours: int = 24) -> Dict[str, any]:
        """
        Get popup statistics for the specified time period
        
        Args:
            hours: Number of hours to look back
            
        Returns:
            Dict with popup statistics
        """
        try:
            from django.utils import timezone
            from datetime import timedelta
            
            cutoff_time = timezone.now() - timedelta(hours=hours)
            
            popups = PopupLog.objects.filter(popup_sent_at__gte=cutoff_time)
            
            stats = {
                'total_popups': popups.count(),
                'successful': popups.filter(status='sent').count(),
                'failed': popups.filter(status='failed').count(),
                'pending': popups.filter(status='pending').count(),
                'retry': popups.filter(status='retry').count(),
                'duplicate_prevented': popups.filter(status='duplicate').count(),
                'average_response_time_ms': 0,
                'success_rate': 0
            }
            
            # Calculate average response time
            response_times = list(popups.filter(
                response_time_ms__isnull=False
            ).values_list('response_time_ms', flat=True))
            
            if response_times:
                stats['average_response_time_ms'] = sum(response_times) / len(response_times)
            
            # Calculate success rate
            if stats['total_popups'] > 0:
                stats['success_rate'] = (stats['successful'] / stats['total_popups']) * 100
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting popup statistics: {str(e)}")
            return {}
    
    def test_popup_connectivity(self) -> Dict[str, any]:
        """
        Test connectivity to Zoho PhoneBridge API
        
        Returns:
            Dict with test results
        """
        test_results = {
            'api_accessible': False,
            'authentication_valid': False,
            'popup_endpoint_available': False,
            'response_time_ms': 0,
            'error': None
        }
        
        try:
            start_time = time.time()
            
            # Get a test access token
            access_token = self._get_access_token_for_user('')
            if not access_token:
                test_results['error'] = 'No valid access token available'
                return test_results
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            # Test basic API connectivity
            response = requests.get(
                f"{self.phonebridge_base}/status",
                headers=headers,
                timeout=self.popup_timeout
            )
            
            test_results['response_time_ms'] = int((time.time() - start_time) * 1000)
            
            if response.status_code in [200, 404]:  # 404 means endpoint exists but method not allowed
                test_results['api_accessible'] = True
                test_results['authentication_valid'] = True
                
                # Test popup endpoint specifically
                test_popup_data = {
                    'call': {
                        'id': 'test_call_12345',
                        'from': '+254700000000',
                        'to': '100',
                        'direction': 'inbound',
                        'startTime': datetime.now().isoformat(),
                        'status': 'ringing'
                    },
                    'contact': {
                        'name': 'Test Contact',
                        'phone': '+254700000000'
                    },
                    'user': {
                        'id': 'test_user'
                    }
                }
                
                popup_response = requests.post(
                    f"{self.phonebridge_base}/calls/popup",
                    headers=headers,
                    json=test_popup_data,
                    timeout=self.popup_timeout
                )
                
                if popup_response.status_code in [200, 201, 400]:  # 400 might be validation error, but endpoint exists
                    test_results['popup_endpoint_available'] = True
            
            elif response.status_code == 401:
                test_results['api_accessible'] = True
                test_results['authentication_valid'] = False
                test_results['error'] = 'Authentication failed'
            
            else:
                test_results['error'] = f'HTTP {response.status_code}: {response.text}'
            
        except requests.exceptions.Timeout:
            test_results['error'] = 'Request timeout'
        except requests.exceptions.RequestException as e:
            test_results['error'] = f'Request error: {str(e)}'
        except Exception as e:
            test_results['error'] = f'Unexpected error: {str(e)}'
        
        return test_results


# Utility class for popup management
class PopupManager:
    """
    High-level popup management utilities
    """
    
    def __init__(self):
        self.service = PhoneBridgeService()
    
    def create_popup_for_extension(self, call_data: Dict, extension: str) -> List[Dict]:
        """
        Create popups for all users mapped to an extension
        
        Args:
            call_data: Call information
            extension: Extension number
            
        Returns:
            List of popup creation results
        """
        from ..models import ExtensionMapping
        
        results = []
        
        try:
            mappings = ExtensionMapping.objects.filter(
                extension=extension,
                is_active=True
            )
            
            for mapping in mappings:
                if mapping.zoho_user_id:
                    # Create popup data
                    popup_data = {
                        'callId': call_data['call_id'],
                        'fromNumber': call_data['caller_number'],
                        'toNumber': call_data['called_number'],
                        'direction': call_data['direction'],
                        'userId': mapping.zoho_user_id,
                        'timestamp': call_data.get('start_time', datetime.now()).isoformat(),
                        'contactInfo': call_data.get('contact_info', {})
                    }
                    
                    # Create popup log
                    popup_log = PopupLog.objects.create(
                        call_log_id=call_data.get('call_log_id'),
                        call_id=call_data['call_id'],
                        zoho_user_id=mapping.zoho_user_id,
                        extension=extension,
                        popup_data=popup_data,
                        status='pending'
                    )
                    
                    # Send popup
                    success = self.service.send_popup(popup_data, popup_log)
                    
                    results.append({
                        'user_id': mapping.zoho_user_id,
                        'user_email': mapping.user.email,
                        'success': success,
                        'popup_log_id': popup_log.id
                    })
                    
                else:
                    results.append({
                        'user_id': None,
                        'user_email': mapping.user.email,
                        'success': False,
                        'error': 'No Zoho user ID configured'
                    })
            
            return results
            
        except Exception as e:
            logger.error(f"Error creating popups for extension {extension}: {str(e)}")
            return [{'error': str(e), 'success': False}]
    
    def cleanup_old_popups(self, days: int = 30) -> int:
        """
        Clean up old popup logs
        
        Args:
            days: Number of days to keep
            
        Returns:
            Number of records deleted
        """
        try:
            from datetime import timedelta
            
            cutoff_date = timezone.now() - timedelta(days=days)
            
            deleted_count = PopupLog.objects.filter(
                popup_sent_at__lt=cutoff_date
            ).delete()[0]
            
            logger.info(f"Cleaned up {deleted_count} old popup logs")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning up old popups: {str(e)}")
            return 0
    
    def get_popup_health_report(self) -> Dict[str, any]:
        """
        Generate comprehensive popup system health report
        
        Returns:
            Dict with health metrics
        """
        try:
            # Get statistics for different time periods
            last_hour = self.service.get_popup_statistics(1)
            last_24_hours = self.service.get_popup_statistics(24)
            last_week = self.service.get_popup_statistics(168)  # 7 * 24
            
            # Test connectivity
            connectivity = self.service.test_popup_connectivity()
            
            # Get active configurations
            from ..models import ExtensionMapping, ZohoToken
            
            active_mappings = ExtensionMapping.objects.filter(is_active=True).count()
            active_tokens = ZohoToken.objects.filter(expires_at__gt=timezone.now()).count()
            
            # Get pending/failed popups
            pending_popups = PopupLog.objects.filter(status='pending').count()
            failed_popups = PopupLog.objects.filter(status='failed').count()
            retry_popups = PopupLog.objects.filter(status='retry').count()
            
            report = {
                'timestamp': timezone.now().isoformat(),
                'system_health': {
                    'api_accessible': connectivity['api_accessible'],
                    'authentication_valid': connectivity['authentication_valid'],
                    'popup_endpoint_available': connectivity['popup_endpoint_available'],
                    'response_time_ms': connectivity['response_time_ms']
                },
                'configuration': {
                    'active_extension_mappings': active_mappings,
                    'active_zoho_tokens': active_tokens,
                    'popup_enabled': self.service.config.get('POPUP_ENABLED', True)
                },
                'statistics': {
                    'last_hour': last_hour,
                    'last_24_hours': last_24_hours,
                    'last_week': last_week
                },
                'queue_status': {
                    'pending_popups': pending_popups,
                    'failed_popups': failed_popups,
                    'retry_popups': retry_popups
                },
                'recommendations': []
            }
            
            # Add recommendations based on health metrics
            if not connectivity['api_accessible']:
                report['recommendations'].append("Zoho PhoneBridge API is not accessible - check network connectivity")
            
            if not connectivity['authentication_valid']:
                report['recommendations'].append("Authentication failed - check Zoho tokens")
            
            if active_tokens == 0:
                report['recommendations'].append("No active Zoho tokens - users need to re-authorize")
            
            if active_mappings == 0:
                report['recommendations'].append("No active extension mappings - configure user extensions")
            
            if last_24_hours.get('success_rate', 0) < 80:
                report['recommendations'].append("Low popup success rate - investigate API issues")
            
            if retry_popups > 10:
                report['recommendations'].append("High number of popups pending retry - check API rate limits")
            
            if connectivity['response_time_ms'] > 5000:
                report['recommendations'].append("High API response times - monitor network performance")
            
            return report
            
        except Exception as e:
            logger.error(f"Error generating popup health report: {str(e)}")
            return {
                'error': str(e),
                'timestamp': timezone.now().isoformat()
            }


# Background task utilities (for future Celery integration)
class PopupTaskManager:
    """
    Manager for background popup tasks
    """
    
    @staticmethod
    def schedule_popup_retry():
        """
        Schedule retry of failed popups (to be called by cron/celery)
        """
        try:
            service = PhoneBridgeService()
            stats = service.retry_failed_popups()
            
            logger.info(f"Popup retry task completed: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Error in popup retry task: {str(e)}")
            return {'error': str(e)}
    
    @staticmethod
    def schedule_popup_cleanup(days: int = 30):
        """
        Schedule cleanup of old popup logs
        """
        try:
            manager = PopupManager()
            deleted_count = manager.cleanup_old_popups(days)
            
            logger.info(f"Popup cleanup task completed: {deleted_count} records deleted")
            return {'deleted_count': deleted_count}
            
        except Exception as e:
            logger.error(f"Error in popup cleanup task: {str(e)}")
            return {'error': str(e)}
    
    @staticmethod
    def generate_daily_report():
        """
        Generate daily popup health report
        """
        try:
            manager = PopupManager()
            report = manager.get_popup_health_report()
            
            # Log important metrics
            stats_24h = report.get('statistics', {}).get('last_24_hours', {})
            logger.info(f"Daily popup report - Total: {stats_24h.get('total_popups', 0)}, "
                       f"Success rate: {stats_24h.get('success_rate', 0):.1f}%")
            
            return report
            
        except Exception as e:
            logger.error(f"Error generating daily popup report: {str(e)}")
            return {'error': str(e)}


# Example usage and testing
if __name__ == "__main__":
    # Test PhoneBridge service
    service = PhoneBridgeService()
    
    # Test connectivity
    print("Testing PhoneBridge connectivity...")
    connectivity_result = service.test_popup_connectivity()
    print(f"Connectivity test: {connectivity_result}")
    
    # Test popup statistics
    print("\nGetting popup statistics...")
    stats = service.get_popup_statistics(24)
    print(f"24h popup stats: {stats}")
    
    # Test popup manager
    print("\nTesting popup manager...")
    manager = PopupManager()
    health_report = manager.get_popup_health_report()
    print(f"Health report generated: {health_report.get('timestamp')}")
    print(f"System health: {health_report.get('system_health')}")
    print(f"Recommendations: {health_report.get('recommendations')}")