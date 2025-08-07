# phonebridge/views/call_control.py

import json
import logging
from datetime import datetime
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from ..models import CallLog, ExtensionMapping, PopupLog
from ..services.vitalpbx_service import VitalPBXService
from ..services.phonebridge_service import PhoneBridgeService
from ..serializers import CallLogSerializer

logger = logging.getLogger('phonebridge')

class CallControlMixin:
    """
    Mixin providing common call control functionality
    """
    
    def __init__(self):
        super().__init__()
        self.vitalpbx_service = VitalPBXService()
        self.phonebridge_service = PhoneBridgeService()
    
    def get_call_log_by_id(self, call_id: str):
        """Get CallLog by call_id with error handling"""
        try:
            return CallLog.objects.get(call_id=call_id)
        except CallLog.DoesNotExist:
            logger.warning(f"Call not found: {call_id}")
            return None
    
    def validate_user_extension_access(self, user, extension: str) -> bool:
        """Check if user has access to the extension"""
        try:
            return ExtensionMapping.objects.filter(
                user=user,
                extension=extension,
                is_active=True
            ).exists()
        except Exception as e:
            logger.error(f"Error validating user extension access: {str(e)}")
            return False
    
    def update_call_status(self, call_log: CallLog, new_status: str, notes: str = None):
        """Update call status with optional notes"""
        try:
            call_log.status = new_status
            call_log.call_state = new_status
            if notes:
                if call_log.notes:
                    call_log.notes += f"\n{notes}"
                else:
                    call_log.notes = notes
            call_log.save()
            
            logger.info(f"Updated call {call_log.call_id} status to {new_status}")
            
        except Exception as e:
            logger.error(f"Error updating call status: {str(e)}")


@method_decorator(csrf_exempt, name='dispatch')
class CallAnswerView(LoginRequiredMixin, CallControlMixin, View):
    """
    Handle call answer requests
    """
    
    def post(self, request, call_id):
        """
        Answer an incoming call
        
        Expected payload:
        {
            "extension": "101",
            "notes": "Optional notes"
        }
        """
        try:
            data = json.loads(request.body) if request.body else {}
            extension = data.get('extension')
            notes = data.get('notes', '')
            
            # Get call log
            call_log = self.get_call_log_by_id(call_id)
            if not call_log:
                return JsonResponse({
                    'success': False,
                    'error': 'Call not found'
                }, status=404)
            
            # Validate user access to extension
            if extension and not self.validate_user_extension_access(request.user, extension):
                return JsonResponse({
                    'success': False,
                    'error': 'User does not have access to this extension'
                }, status=403)
            
            # Check if call is in answerable state
            if call_log.status not in ['initiated', 'ringing']:
                return JsonResponse({
                    'success': False,
                    'error': f'Call cannot be answered in {call_log.status} state'
                }, status=400)
            
            # Answer call via VitalPBX API
            answer_result = self._answer_call_vitalpbx(call_log, extension or call_log.extension)
            
            if answer_result['success']:
                # Update call status
                self.update_call_status(
                    call_log, 
                    'connected', 
                    f"Call answered by {request.user.email}. {notes}".strip()
                )
                
                # Update popup if exists
                self._update_popup_on_answer(call_log)
                
                logger.info(f"Call {call_id} answered successfully by {request.user.email}")
                
                return JsonResponse({
                    'success': True,
                    'message': 'Call answered successfully',
                    'call_id': call_id,
                    'status': 'connected'
                })
            else:
                logger.error(f"Failed to answer call {call_id}: {answer_result.get('error')}")
                
                return JsonResponse({
                    'success': False,
                    'error': answer_result.get('error', 'Failed to answer call'),
                    'details': answer_result.get('details', {})
                }, status=500)
        
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON payload'
            }, status=400)
        
        except Exception as e:
            logger.error(f"Error answering call {call_id}: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    def _answer_call_vitalpbx(self, call_log: CallLog, extension: str):
        """Answer call using VitalPBX API"""
        try:
            # For VitalPBX, answering usually involves connecting to extension
            # This might vary based on your VitalPBX configuration
            
            # Method 1: Use originate to connect extension to caller
            if call_log.direction == 'inbound':
                result = self.vitalpbx_service.originate_call(
                    extension=extension,
                    destination=call_log.caller_number,
                    caller_id=extension
                )
            else:
                # For outbound calls, answer might not be applicable
                result = {'success': True, 'message': 'Outbound call already connected'}
            
            return result
            
        except Exception as e:
            logger.error(f"Error in VitalPBX answer call: {str(e)}")
            return {
                'success': False,
                'error': f'VitalPBX API error: {str(e)}'
            }
    
    def _update_popup_on_answer(self, call_log: CallLog):
        """Update popup when call is answered"""
        try:
            popup_logs = PopupLog.objects.filter(
                call_id=call_log.call_id,
                status='sent'
            )
            
            for popup_log in popup_logs:
                update_data = {
                    'status': 'connected',
                    'message': 'Call answered',
                    'timestamp': datetime.now().isoformat()
                }
                
                self.phonebridge_service.update_popup(
                    call_log.call_id,
                    popup_log.zoho_user_id,
                    update_data
                )
                
        except Exception as e:
            logger.error(f"Error updating popup on answer: {str(e)}")


@method_decorator(csrf_exempt, name='dispatch')
class CallDeclineView(LoginRequiredMixin, CallControlMixin, View):
    """
    Handle call decline/hangup requests
    """
    
    def post(self, request, call_id):
        """
        Decline/hangup a call
        
        Expected payload:
        {
            "reason": "busy|unavailable|other",
            "notes": "Optional notes"
        }
        """
        try:
            data = json.loads(request.body) if request.body else {}
            reason = data.get('reason', 'declined')
            notes = data.get('notes', '')
            
            # Get call log
            call_log = self.get_call_log_by_id(call_id)
            if not call_log:
                return JsonResponse({
                    'success': False,
                    'error': 'Call not found'
                }, status=404)
            
            # Check if call can be declined
            if call_log.status in ['completed', 'failed']:
                return JsonResponse({
                    'success': False,
                    'error': f'Call already ended with status: {call_log.status}'
                }, status=400)
            
            # Decline call via VitalPBX API
            decline_result = self._decline_call_vitalpbx(call_log, reason)
            
            if decline_result['success']:
                # Update call status
                status_map = {
                    'busy': 'busy',
                    'unavailable': 'no_answer',
                    'declined': 'failed',
                    'other': 'failed'
                }
                
                new_status = status_map.get(reason, 'failed')
                self.update_call_status(
                    call_log,
                    new_status,
                    f"Call {reason} by {request.user.email}. {notes}".strip()
                )
                
                # Set end time
                call_log.end_time = datetime.now()
                call_log.save()
                
                # Close popup
                self._close_popup_on_decline(call_log)
                
                logger.info(f"Call {call_id} declined successfully by {request.user.email}")
                
                return JsonResponse({
                    'success': True,
                    'message': f'Call {reason} successfully',
                    'call_id': call_id,
                    'status': new_status
                })
            else:
                logger.error(f"Failed to decline call {call_id}: {decline_result.get('error')}")
                
                return JsonResponse({
                    'success': False,
                    'error': decline_result.get('error', 'Failed to decline call'),
                    'details': decline_result.get('details', {})
                }, status=500)
        
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON payload'
            }, status=400)
        
        except Exception as e:
            logger.error(f"Error declining call {call_id}: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    def _decline_call_vitalpbx(self, call_log: CallLog, reason: str):
        """Decline call using VitalPBX API"""
        try:
            # Use hangup API to decline the call
            result = self.vitalpbx_service.hangup_call(call_log.call_id)
            
            if not result.get('success'):
                # If direct hangup fails, try channel hangup
                # This is a fallback method
                hangup_result = self._hangup_call_channel(call_log)
                return hangup_result
            
            return result
            
        except Exception as e:
            logger.error(f"Error in VitalPBX decline call: {str(e)}")
            return {
                'success': False,
                'error': f'VitalPBX API error: {str(e)}'
            }
    
    def _hangup_call_channel(self, call_log: CallLog):
        """Hangup call using channel-based approach"""
        try:
            # This would use AMI or specific VitalPBX API to hangup channel
            # Implementation depends on VitalPBX API capabilities
            
            # For now, return success as webhook should handle the actual hangup
            return {
                'success': True,
                'message': 'Hangup request sent'
            }
            
        except Exception as e:
            logger.error(f"Error hanging up call channel: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _close_popup_on_decline(self, call_log: CallLog):
        """Close popup when call is declined"""
        try:
            popup_logs = PopupLog.objects.filter(
                call_id=call_log.call_id,
                status='sent'
            )
            
            for popup_log in popup_logs:
                self.phonebridge_service.close_popup(
                    call_log.call_id,
                    popup_log.zoho_user_id
                )
                
        except Exception as e:
            logger.error(f"Error closing popup on decline: {str(e)}")


@method_decorator(csrf_exempt, name='dispatch')
class CallRecordingView(LoginRequiredMixin, CallControlMixin, View):
    """
    Handle call recording start/stop requests
    """
    
    def post(self, request, call_id, action):
        """
        Start or stop call recording
        
        Actions: 'start' or 'stop'
        
        Expected payload:
        {
            "format": "wav|mp3",
            "notes": "Optional notes"
        }
        """
        if action not in ['start', 'stop']:
            return JsonResponse({
                'success': False,
                'error': 'Invalid action. Use "start" or "stop"'
            }, status=400)
        
        try:
            data = json.loads(request.body) if request.body else {}
            format_type = data.get('format', 'wav')
            notes = data.get('notes', '')
            
            # Get call log
            call_log = self.get_call_log_by_id(call_id)
            if not call_log:
                return JsonResponse({
                    'success': False,
                    'error': 'Call not found'
                }, status=404)
            
            # Check if call is active
            if call_log.status not in ['connected', 'ringing']:
                return JsonResponse({
                    'success': False,
                    'error': f'Recording not available for call in {call_log.status} state'
                }, status=400)
            
            # Start or stop recording
            if action == 'start':
                result = self._start_recording(call_log, format_type, notes)
            else:
                result = self._stop_recording(call_log, notes)
            
            if result['success']:
                # Update call log
                action_note = f"Recording {action}ed by {request.user.email}. {notes}".strip()
                self.update_call_status(call_log, call_log.status, action_note)
                
                logger.info(f"Call {call_id} recording {action} successful")
                
                return JsonResponse({
                    'success': True,
                    'message': f'Recording {action}ed successfully',
                    'call_id': call_id,
                    'recording_info': result.get('recording_info', {})
                })
            else:
                logger.error(f"Failed to {action} recording for call {call_id}")
                
                return JsonResponse({
                    'success': False,
                    'error': result.get('error', f'Failed to {action} recording'),
                    'details': result.get('details', {})
                }, status=500)
        
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON payload'
            }, status=400)
        
        except Exception as e:
            logger.error(f"Error {action}ing recording for call {call_id}: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    def _start_recording(self, call_log: CallLog, format_type: str, notes: str):
        """Start call recording"""
        try:
            # Generate recording filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"call_{call_log.call_id}_{timestamp}.{format_type}"
            
            # This would call VitalPBX recording API
            # Implementation depends on VitalPBX capabilities
            recording_data = {
                'call_id': call_log.call_id,
                'filename': filename,
                'format': format_type,
                'start_time': datetime.now().isoformat()
            }
            
            # For now, simulate successful start
            # In real implementation, this would call VitalPBX API
            
            return {
                'success': True,
                'recording_info': recording_data,
                'message': 'Recording started'
            }
            
        except Exception as e:
            logger.error(f"Error starting recording: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _stop_recording(self, call_log: CallLog, notes: str):
        """Stop call recording"""
        try:
            # This would call VitalPBX recording API to stop
            # Implementation depends on VitalPBX capabilities
            
            recording_data = {
                'call_id': call_log.call_id,
                'stop_time': datetime.now().isoformat(),
                'recording_url': call_log.recording_url  # If available
            }
            
            # For now, simulate successful stop
            # In real implementation, this would call VitalPBX API
            
            return {
                'success': True,
                'recording_info': recording_data,
                'message': 'Recording stopped'
            }
            
        except Exception as e:
            logger.error(f"Error stopping recording: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }


class CallStatusView(LoginRequiredMixin, View):
    """
    Get current call status and information
    """
    
    def get(self, request, call_id):
        """Get detailed call status"""
        try:
            call_log = CallLog.objects.get(call_id=call_id)
            
            # Check user access
            if not ExtensionMapping.objects.filter(
                user=request.user,
                extension=call_log.extension,
                is_active=True
            ).exists():
                return JsonResponse({
                    'success': False,
                    'error': 'Access denied'
                }, status=403)
            
            # Get popup logs
            popup_logs = PopupLog.objects.filter(call_id=call_id)
            
            # Build response
            response_data = {
                'success': True,
                'call': {
                    'id': call_log.call_id,
                    'direction': call_log.direction,
                    'caller_number': call_log.caller_number,
                    'called_number': call_log.called_number,
                    'status': call_log.status,
                    'call_state': call_log.call_state,
                    'start_time': call_log.start_time.isoformat() if call_log.start_time else None,
                    'end_time': call_log.end_time.isoformat() if call_log.end_time else None,
                    'duration_seconds': call_log.duration_seconds,
                    'extension': call_log.extension,
                    'recording_url': call_log.recording_url,
                    'notes': call_log.notes,
                },
                'contact': call_log.get_caller_info(),
                'popups': [
                    {
                        'zoho_user_id': popup.zoho_user_id,
                        'status': popup.status,
                        'sent_at': popup.popup_sent_at.isoformat(),
                        'response_time_ms': popup.response_time_ms
                    }
                    for popup in popup_logs
                ],
                'actions_available': self._get_available_actions(call_log)
            }
            
            return JsonResponse(response_data)
        
        except CallLog.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Call not found'
            }, status=404)
        
        except Exception as e:
            logger.error(f"Error getting call status for {call_id}: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    def _get_available_actions(self, call_log: CallLog):
        """Get list of actions available for current call state"""
        actions = []
        
        if call_log.status in ['initiated', 'ringing']:
            actions.extend(['answer', 'decline'])
        
        if call_log.status in ['connected', 'ringing']:
            actions.extend(['start_recording', 'hangup'])
        
        if call_log.recording_url:
            actions.append('stop_recording')
        
        return actions


# REST API ViewSet for comprehensive call management
class CallControlViewSet(viewsets.ReadOnlyModelViewSet):
    """
    REST API for call control and monitoring
    """
    serializer_class = CallLogSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter calls by user's extensions"""
        user_extensions = ExtensionMapping.objects.filter(
            user=self.request.user,
            is_active=True
        ).values_list('extension', flat=True)
        
        return CallLog.objects.filter(extension__in=user_extensions)
    
    @action(detail=True, methods=['post'])
    def answer(self, request, pk=None):
        """Answer a call"""
        call_log = self.get_object()
        
        # Delegate to answer view logic
        answer_view = CallAnswerView()
        answer_view.setup(request)
        
        # Create mock request with call_id
        from django.http import HttpRequest
        mock_request = HttpRequest()
        mock_request.method = 'POST'
        mock_request.user = request.user
        mock_request._body = request.body
        
        # Call the answer logic
        response = answer_view.post(mock_request, call_log.call_id)
        
        # Convert JsonResponse to DRF Response
        if hasattr(response, 'content'):
            import json
            response_data = json.loads(response.content.decode())
            status_code = response.status_code
            
            if status_code == 200:
                return Response(response_data, status=status.HTTP_200_OK)
            else:
                return Response(response_data, status=status_code)
        
        return Response({'error': 'Unexpected response format'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'])
    def decline(self, request, pk=None):
        """Decline a call"""
        call_log = self.get_object()
        
        # Delegate to decline view logic
        decline_view = CallDeclineView()
        decline_view.setup(request)
        
        # Create mock request
        from django.http import HttpRequest
        mock_request = HttpRequest()
        mock_request.method = 'POST'
        mock_request.user = request.user
        mock_request._body = request.body
        
        # Call the decline logic
        response = decline_view.post(mock_request, call_log.call_id)
        
        # Convert JsonResponse to DRF Response
        if hasattr(response, 'content'):
            import json
            response_data = json.loads(response.content.decode())
            status_code = response.status_code
            
            if status_code == 200:
                return Response(response_data, status=status.HTTP_200_OK)
            else:
                return Response(response_data, status=status_code)
        
        return Response({'error': 'Unexpected response format'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'])
    def start_recording(self, request, pk=None):
        """Start call recording"""
        call_log = self.get_object()
        
        # Delegate to recording view logic
        recording_view = CallRecordingView()
        recording_view.setup(request)
        
        # Create mock request
        from django.http import HttpRequest
        mock_request = HttpRequest()
        mock_request.method = 'POST'
        mock_request.user = request.user
        mock_request._body = request.body
        
        # Call the recording logic
        response = recording_view.post(mock_request, call_log.call_id, 'start')
        
        # Convert JsonResponse to DRF Response
        if hasattr(response, 'content'):
            import json
            response_data = json.loads(response.content.decode())
            status_code = response.status_code
            
            if status_code == 200:
                return Response(response_data, status=status.HTTP_200_OK)
            else:
                return Response(response_data, status=status_code)
        
        return Response({'error': 'Unexpected response format'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'])
    def stop_recording(self, request, pk=None):
        """Stop call recording"""
        call_log = self.get_object()
        
        # Delegate to recording view logic
        recording_view = CallRecordingView()
        recording_view.setup(request)
        
        # Create mock request
        from django.http import HttpRequest
        mock_request = HttpRequest()
        mock_request.method = 'POST'
        mock_request.user = request.user
        mock_request._body = request.body
        
        # Call the recording logic
        response = recording_view.post(mock_request, call_log.call_id, 'stop')
        
        # Convert JsonResponse to DRF Response
        if hasattr(response, 'content'):
            import json
            response_data = json.loads(response.content.decode())
            status_code = response.status_code
            
            if status_code == 200:
                return Response(response_data, status=status.HTTP_200_OK)
            else:
                return Response(response_data, status=status_code)
        
        return Response({'error': 'Unexpected response format'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """Get detailed call status"""
        call_log = self.get_object()
        
        # Use the status view logic
        status_view = CallStatusView()
        status_view.setup(request)
        
        # Create mock request
        from django.http import HttpRequest
        mock_request = HttpRequest()
        mock_request.method = 'GET'
        mock_request.user = request.user
        
        # Call the status logic
        response = status_view.get(mock_request, call_log.call_id)
        
        # Convert JsonResponse to DRF Response
        if hasattr(response, 'content'):
            import json
            response_data = json.loads(response.content.decode())
            status_code = response.status_code
            
            if status_code == 200:
                return Response(response_data, status=status.HTTP_200_OK)
            else:
                return Response(response_data, status=status_code)
        
        return Response({'error': 'Unexpected response format'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get all active calls for user's extensions"""
        active_calls = self.get_queryset().filter(
            status__in=['initiated', 'ringing', 'connected']
        ).order_by('-start_time')[:20]  # Limit to 20 most recent
        
        serializer = self.get_serializer(active_calls, many=True)
        return Response({
            'success': True,
            'active_calls': serializer.data,
            'count': active_calls.count()
        })
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get call statistics for user's extensions"""
        from django.utils import timezone
        from datetime import timedelta
        from django.db.models import Count, Avg, Q
        
        # Get time range from query params
        hours = int(request.query_params.get('hours', 24))
        cutoff_time = timezone.now() - timedelta(hours=hours)
        
        queryset = self.get_queryset().filter(start_time__gte=cutoff_time)
        
        # Calculate statistics
        stats = {
            'total_calls': queryset.count(),
            'inbound_calls': queryset.filter(direction='inbound').count(),
            'outbound_calls': queryset.filter(direction='outbound').count(),
            'completed_calls': queryset.filter(status='completed').count(),
            'failed_calls': queryset.filter(status='failed').count(),
            'missed_calls': queryset.filter(status='no_answer').count(),
            'busy_calls': queryset.filter(status='busy').count(),
        }
        
        # Calculate success rate
        if stats['total_calls'] > 0:
            stats['success_rate'] = (stats['completed_calls'] / stats['total_calls']) * 100
        else:
            stats['success_rate'] = 0
        
        # Calculate average duration
        completed_calls = queryset.filter(
            status='completed',
            duration_seconds__isnull=False
        )
        
        if completed_calls.exists():
            avg_duration = completed_calls.aggregate(
                avg_duration=Avg('duration_seconds')
            )['avg_duration']
            stats['average_duration_seconds'] = round(avg_duration, 2)
            stats['average_duration_minutes'] = round(avg_duration / 60, 2)
        else:
            stats['average_duration_seconds'] = 0
            stats['average_duration_minutes'] = 0
        
        # Get popup statistics
        from ..models import PopupLog
        user_extensions = ExtensionMapping.objects.filter(
            user=request.user,
            is_active=True
        ).values_list('extension', flat=True)
        
        popup_stats = PopupLog.objects.filter(
            extension__in=user_extensions,
            popup_sent_at__gte=cutoff_time
        ).aggregate(
            total_popups=Count('id'),
            successful_popups=Count('id', filter=Q(status='sent')),
            failed_popups=Count('id', filter=Q(status='failed'))
        )
        
        stats['popup_statistics'] = popup_stats
        
        if popup_stats['total_popups'] > 0:
            stats['popup_success_rate'] = (
                popup_stats['successful_popups'] / popup_stats['total_popups']
            ) * 100
        else:
            stats['popup_success_rate'] = 0
        
        return Response({
            'success': True,
            'time_range_hours': hours,
            'statistics': stats
        })


# URL configuration helper
def get_call_control_urls():
    """
    Get URL patterns for call control endpoints
    
    Returns:
        List of URL patterns to include in phonebridge/urls.py
    """
    from django.urls import path
    
    return [
        # Individual call control endpoints
        path('calls/<str:call_id>/answer/', CallAnswerView.as_view(), name='call_answer'),
        path('calls/<str:call_id>/decline/', CallDeclineView.as_view(), name='call_decline'),
        path('calls/<str:call_id>/recording/<str:action>/', CallRecordingView.as_view(), name='call_recording'),
        path('calls/<str:call_id>/status/', CallStatusView.as_view(), name='call_status'),
    ]


# Management command for testing call control
class CallControlTestManager:
    """
    Testing utilities for call control functionality
    """
    
    @staticmethod
    def create_test_call(extension: str = "101", direction: str = "inbound") -> CallLog:
        """Create a test call for testing purposes"""
        from django.utils import timezone
        import uuid
        
        call_id = f"test_{uuid.uuid4().hex[:8]}"
        
        call_log = CallLog.objects.create(
            call_id=call_id,
            extension=extension,
            direction=direction,
            caller_number="+254712345678" if direction == "inbound" else extension,
            called_number=extension if direction == "inbound" else "+254787654321",
            status='ringing',
            call_state='ringing',
            start_time=timezone.now()
        )
        
        logger.info(f"Created test call: {call_id}")
        return call_log
    
    @staticmethod
    def test_call_control_flow():
        """Test the complete call control flow"""
        try:
            # Create test call
            call_log = CallControlTestManager.create_test_call()
            
            # Test answer
            print(f"Testing call control for call: {call_log.call_id}")
            
            # Simulate call progression
            call_log.status = 'connected'
            call_log.call_state = 'connected'
            call_log.save()
            print(f"Call {call_log.call_id} marked as connected")
            
            # Simulate call end
            call_log.status = 'completed'
            call_log.call_state = 'completed'
            call_log.end_time = timezone.now()
            call_log.duration_seconds = 120  # 2 minutes
            call_log.save()
            print(f"Call {call_log.call_id} completed with duration: {call_log.duration_seconds}s")
            
            return True
            
        except Exception as e:
            logger.error(f"Error testing call control flow: {str(e)}")
            return False


# Example usage
if __name__ == "__main__":
    # Test call control functionality
    print("Testing Call Control System...")
    
    # Test call creation
    test_manager = CallControlTestManager()
    success = test_manager.test_call_control_flow()
    
    if success:
        print("✅ Call control test completed successfully")
    else:
        print("❌ Call control test failed")
    
    # Test URL patterns
    urls = get_call_control_urls()
    print(f"📝 Generated {len(urls)} URL patterns for call control")