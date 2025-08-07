# phonebridge/main_views.py - Updated OAuth callback handling

import json
import logging
from datetime import datetime, timedelta
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView
from django.http import JsonResponse, HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import models, transaction
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import ZohoToken, ExtensionMapping, CallLog, ZohoWebhookLog, VitalPBXWebhookLog, OAuthMigrationLog
from .serializers import ExtensionMappingSerializer, CallLogSerializer
from .services.vitalpbx_service import VitalPBXService
from .services.zoho_service import ZohoService, ZohoTokenManager

logger = logging.getLogger('phonebridge')

class PhoneBridgeHomeView(LoginRequiredMixin, TemplateView):
    """Main dashboard for PhoneBridge with migration status"""
    template_name = 'phonebridge/home.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Check Zoho connection status with migration info
        try:
            zoho_token = ZohoToken.objects.get(user=self.request.user)
            context['zoho_connected'] = not zoho_token.is_expired()
            context['zoho_phonebridge_enabled'] = zoho_token.is_phonebridge_enabled()
            context['token_needs_migration'] = zoho_token.needs_migration()
            context['token_location'] = zoho_token.location
            context['oauth_version'] = zoho_token.oauth_version
        except ZohoToken.DoesNotExist:
            context['zoho_connected'] = False
            context['zoho_phonebridge_enabled'] = False
            context['token_needs_migration'] = False
        
        # Get migration status if exists
        try:
            migration_log = OAuthMigrationLog.objects.filter(
                user=self.request.user
            ).latest('migration_started_at')
            context['migration_status'] = migration_log.migration_status
            context['migration_notes'] = migration_log.notes
        except OAuthMigrationLog.DoesNotExist:
            context['migration_status'] = None
        
        # Get user's extension mappings
        context['extensions'] = ExtensionMapping.objects.filter(
            user=self.request.user, 
            is_active=True
        )
        
        # Get recent call logs
        context['recent_calls'] = CallLog.objects.filter(
            user=self.request.user
        )[:10]
        
        return context

class SetupView(LoginRequiredMixin, TemplateView):
    """Setup and configuration page with OAuth migration info"""
    template_name = 'phonebridge/setup.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['phonebridge_settings'] = settings.PHONEBRIDGE_SETTINGS
        
        # Add OAuth flow information
        zoho_service = ZohoService()
        context['oauth_validation'] = zoho_service.validate_configuration()
        
        return context

class ExtensionMappingView(LoginRequiredMixin, TemplateView):
    """Manage extension mappings"""
    template_name = 'phonebridge/extensions.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['extensions'] = ExtensionMapping.objects.filter(user=self.request.user)
        return context

class ZohoConnectView(LoginRequiredMixin, View):
    """Initiate Zoho OAuth flow with new PhoneBridge scopes"""
    
    def get(self, request):
        try:
            zoho_service = ZohoService()
            
            # Validate configuration first
            validation = zoho_service.validate_configuration()
            if not validation['valid']:
                error_msg = f"OAuth configuration invalid: {', '.join(validation['issues'])}"
                logger.error(error_msg)
                messages.error(request, error_msg)
                return redirect('phonebridge:setup')
            
            # Generate auth URL with new scopes
            auth_url_data = zoho_service.get_auth_url()
            
            # Store state in session for validation
            request.session['zoho_oauth_state'] = auth_url_data['state']
            request.session['oauth_scopes'] = auth_url_data['scopes']
            
            logger.info(f"Redirecting user {request.user.email} to Zoho OAuth (PhoneBridge)")
            logger.info(f"Scopes: {auth_url_data['scopes']}")
            
            return redirect(auth_url_data['auth_url'])
            
        except Exception as e:
            logger.error(f"Zoho connect error for {request.user.email}: {str(e)}")
            messages.error(request, f"Failed to initiate Zoho connection: {str(e)}")
            return redirect('phonebridge:setup')


class ZohoCallbackView(LoginRequiredMixin, View):
    """Handle Zoho OAuth callback with location parameter support"""
    
    def get(self, request):
        code = request.GET.get('code')
        error = request.GET.get('error')
        received_state = request.GET.get('state')
        location = request.GET.get('location')  # NEW: Location parameter
        
        logger.info(f"OAuth callback for {request.user.email} - Location: {location}, State: {received_state[:10] if received_state else None}...")
        
        if error:
            logger.error(f"Zoho authorization failed for {request.user.email}: {error}")
            messages.error(request, f"Zoho authorization failed: {error}")
            return redirect('phonebridge:setup')
        
        if not code:
            logger.error(f"No authorization code received for {request.user.email}")
            messages.error(request, "No authorization code received from Zoho")
            return redirect('phonebridge:setup')
        
        # Validate state parameter
        expected_state = request.session.get('zoho_oauth_state')
        if expected_state and received_state != expected_state:
            logger.error(f"State parameter mismatch for {request.user.email}")
            messages.error(request, "Invalid state parameter - possible security issue")
            return redirect('phonebridge:setup')
        
        try:
            with transaction.atomic():
                zoho_service = ZohoService()
                token_manager = ZohoTokenManager(zoho_service)
                
                # Handle OAuth callback with location support
                tokens = zoho_service.handle_oauth_callback(
                    code=code,
                    location=location,
                    expected_state=expected_state,
                    received_state=received_state
                )
                
                logger.info(f"Token exchange successful for {request.user.email}")
                logger.info(f"Location: {tokens.get('location')}, API Domain: {tokens.get('api_domain')}")
                
                # Save token with new OAuth v3 fields
                zoho_token = token_manager.save_token_data(request.user, tokens)
                
                # Get Zoho user info to populate user ID
                user_info_result = zoho_service.get_user_info(
                    tokens['access_token'], 
                    tokens.get('api_domain')
                )
                
                if user_info_result.get('success') and user_info_result.get('user_data'):
                    user_data = user_info_result['user_data']
                    zoho_token.zoho_user_id = user_data.get('id', '')
                    zoho_token.save()
                    
                    logger.info(f"Zoho user ID updated: {zoho_token.zoho_user_id}")
                
                # Validate PhoneBridge scopes
                scope_validation = zoho_service.validate_phonebridge_scopes(
                    tokens['access_token'],
                    tokens.get('api_domain')
                )
                
                if scope_validation.get('valid'):
                    logger.info(f"PhoneBridge scopes validated successfully for {request.user.email}")
                    messages.success(
                        request, 
                        f"Successfully connected to Zoho PhoneBridge! Location: {tokens.get('location', 'us').upper()}"
                    )
                else:
                    logger.warning(f"PhoneBridge scope validation issues for {request.user.email}")
                    messages.warning(
                        request,
                        f"Connected to Zoho, but some PhoneBridge features may be limited. "
                        f"Available scopes: {scope_validation.get('available_scopes', 0)}/{scope_validation.get('total_scopes', 0)}"
                    )
                
                # Clean up session
                request.session.pop('zoho_oauth_state', None)
                request.session.pop('oauth_scopes', None)
                
                # Record successful migration if this was a migration
                try:
                    migration_log = OAuthMigrationLog.objects.filter(
                        user=request.user,
                        migration_status='in_progress'
                    ).latest('migration_started_at')
                    
                    migration_log.migration_status = 'completed'
                    migration_log.migration_completed_at = timezone.now()
                    migration_log.notes += f' - OAuth v3 connection successful with location: {tokens.get("location")}'
                    migration_log.save()
                    
                    logger.info(f"Migration marked as completed for {request.user.email}")
                    
                except OAuthMigrationLog.DoesNotExist:
                    # Not a migration, just a new connection
                    pass
                
        except Exception as e:
            logger.error(f"Zoho connection failed for {request.user.email}: {str(e)}")
            messages.error(request, f"Failed to connect to Zoho: {str(e)}")
            
            # Record failed migration if applicable
            try:
                migration_log = OAuthMigrationLog.objects.filter(
                    user=request.user,
                    migration_status='in_progress'
                ).latest('migration_started_at')
                
                migration_log.migration_status = 'failed'
                migration_log.error_message = str(e)
                migration_log.save()
                
            except OAuthMigrationLog.DoesNotExist:
                pass
        
        return redirect('phonebridge:home')


class ZohoDisconnectView(LoginRequiredMixin, View):
    """Disconnect from Zoho with migration log"""
    
    def post(self, request):
        try:
            with transaction.atomic():
                # Get token info before deletion
                try:
                    zoho_token = ZohoToken.objects.get(user=request.user)
                    token_info = {
                        'location': zoho_token.location,
                        'oauth_version': zoho_token.oauth_version,
                        'phonebridge_enabled': zoho_token.is_phonebridge_enabled(),
                        'api_domain': zoho_token.api_domain
                    }
                except ZohoToken.DoesNotExist:
                    token_info = None
                
                # Delete token
                deleted_count, _ = ZohoToken.objects.filter(user=request.user).delete()
                
                # Log disconnection
                if token_info:
                    OAuthMigrationLog.objects.create(
                        user=request.user,
                        old_token_data=token_info,
                        migration_status='completed',
                        migration_completed_at=timezone.now(),
                        notes=f'User manually disconnected from Zoho. Token info: {json.dumps(token_info)}'
                    )
                
                if deleted_count > 0:
                    messages.success(request, "Successfully disconnected from Zoho")
                    logger.info(f"User {request.user.email} disconnected from Zoho")
                else:
                    messages.info(request, "No Zoho connection found to disconnect")
                    
        except Exception as e:
            logger.error(f"Zoho disconnection failed for {request.user.email}: {str(e)}")
            messages.error(request, f"Error disconnecting from Zoho: {str(e)}")
        
        return redirect('phonebridge:home')

class ZohoStatusView(LoginRequiredMixin, View):
    """Check Zoho connection status with enhanced info"""
    
    def get(self, request):
        try:
            zoho_token = ZohoToken.objects.get(user=request.user)
            
            # Check if token needs refresh
            token_manager = ZohoTokenManager(ZohoService())
            token_refreshed = token_manager.refresh_token_if_needed(zoho_token)
            
            # Get migration status
            migration_info = token_manager.validate_token_migration_needed(zoho_token)
            
            response_data = {
                'connected': not zoho_token.is_expired(),
                'zoho_user_id': zoho_token.zoho_user_id,
                'location': zoho_token.location,
                'api_domain': zoho_token.api_domain,
                'oauth_version': zoho_token.oauth_version,
                'phonebridge_enabled': zoho_token.is_phonebridge_enabled(),
                'scopes_granted': zoho_token.scopes_granted,
                'expires_at': zoho_token.expires_at.isoformat(),
                'created_at': zoho_token.created_at.isoformat(),
                'last_refreshed_at': zoho_token.last_refreshed_at.isoformat() if zoho_token.last_refreshed_at else None,
                'token_refreshed': token_refreshed,
                'migration_info': migration_info
            }
            
            return JsonResponse(response_data)
            
        except ZohoToken.DoesNotExist:
            return JsonResponse({
                'connected': False,
                'error': 'No Zoho token found',
                'needs_authorization': True,
                'auth_url': '/phonebridge/zoho/connect/'
            })
        except Exception as e:
            logger.error(f"Error checking Zoho status for {request.user.email}: {str(e)}")
            return JsonResponse({
                'connected': False,
                'error': str(e)
            })

class ClickToCallView(LoginRequiredMixin, View):
    """Handle click-to-call requests with enhanced token management"""
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            destination_number = data.get('destination_number')
            caller_id = data.get('caller_id', '')
            
            if not destination_number:
                return JsonResponse({
                    'error': 'destination_number is required'
                }, status=400)
            
            # Get user's extension mapping
            try:
                extension_mapping = ExtensionMapping.objects.get(
                    user=request.user, 
                    is_active=True
                )
                extension = extension_mapping.extension
            except ExtensionMapping.DoesNotExist:
                return JsonResponse({
                    'error': 'No active extension mapped for this user'
                }, status=400)
            
            # Check Zoho token status
            token_manager = ZohoTokenManager(ZohoService())
            zoho_token = token_manager.get_valid_token_for_user(request.user)
            
            if not zoho_token:
                return JsonResponse({
                    'error': 'Zoho authorization required',
                    'auth_url': '/phonebridge/zoho/connect/'
                }, status=401)
            
            # Initiate call via VitalPBX
            vitalpbx_service = VitalPBXService()
            call_result = vitalpbx_service.originate_call(
                extension=extension,
                destination=destination_number,
                caller_id=caller_id
            )
            
            if call_result.get('success'):
                # Log the call with enhanced info
                call_log = CallLog.objects.create(
                    call_id=call_result.get('call_id', ''),
                    user=request.user,
                    extension=extension,
                    direction='outbound',
                    caller_number=extension,
                    called_number=destination_number,
                    status='initiated',
                    start_time=datetime.now()
                )
                
                logger.info(f"Click-to-call initiated: {extension} -> {destination_number} (Call ID: {call_log.call_id})")
                
                return JsonResponse({
                    'success': True,
                    'call_id': call_result.get('call_id'),
                    'message': 'Call initiated successfully',
                    'zoho_connected': True,
                    'phonebridge_enabled': zoho_token.is_phonebridge_enabled()
                })
            else:
                return JsonResponse({
                    'error': call_result.get('error', 'Failed to initiate call'),
                    'details': call_result.get('details', {})
                }, status=500)
                
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"Click-to-call error for {request.user.email}: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class VitalPBXWebhookView(View):
    """Handle webhooks from VitalPBX with enhanced processing"""
    
    def post(self, request):
        try:
            # Log the webhook
            payload = json.loads(request.body)
            webhook_log = VitalPBXWebhookLog.objects.create(
                event_type=payload.get('Event', 'unknown'),
                payload=payload
            )
            
            logger.info(f"Received VitalPBX webhook: {webhook_log.event_type} (ID: {webhook_log.id})")
            
            # Process the webhook
            self.process_vitalpbx_event(payload, webhook_log)
            
            return JsonResponse({'status': 'received', 'webhook_id': webhook_log.id})
            
        except json.JSONDecodeError:
            logger.error("Invalid JSON in VitalPBX webhook")
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"VitalPBX webhook error: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    
    def process_vitalpbx_event(self, payload, webhook_log):
        """Process different types of VitalPBX events using enhanced processor"""
        try:
            from .services.webhook_processor import WebhookProcessor
            
            processor = WebhookProcessor()
            success = processor.process_webhook(payload, webhook_log)
            
            if success:
                webhook_log.processed = True
                logger.info(f"Successfully processed {payload.get('Event', 'unknown')} event (ID: {webhook_log.id})")
            else:
                webhook_log.error_message = "Processing failed - see logs for details"
                logger.warning(f"Failed to process {payload.get('Event', 'unknown')} event (ID: {webhook_log.id})")
            
            webhook_log.save()
            
        except ImportError as e:
            # Fallback to basic processing if enhanced processor not available
            logger.warning(f"Enhanced processor not available, using basic processing: {str(e)}")
            self._process_vitalpbx_event_basic(payload, webhook_log)
            
        except Exception as e:
            webhook_log.error_message = str(e)
            webhook_log.save()
            logger.error(f"Error in enhanced webhook processing: {str(e)}")

    def _process_vitalpbx_event_basic(self, payload, webhook_log):
        """Basic webhook processing fallback"""
        event_type = payload.get('Event')
        
        try:
            if event_type == 'Dial':
                self.handle_dial_event_basic(payload)
            elif event_type == 'Hangup':
                self.handle_hangup_event_basic(payload)
            elif event_type == 'Bridge':
                self.handle_bridge_event_basic(payload)
            elif event_type == 'Newchannel':
                self.handle_new_channel_event_basic(payload)
            
            webhook_log.processed = True
            webhook_log.save()
            
        except Exception as e:
            webhook_log.error_message = str(e)
            webhook_log.save()
            logger.error(f"Error processing VitalPBX event {event_type}: {str(e)}")
    
    def handle_dial_event_basic(self, payload):
        """Handle dial events - when a call is connected"""
        call_id = payload.get('Uniqueid')
        extension = payload.get('DestinationExt') or payload.get('CallerIDNum')
        
        if call_id and extension:
            try:
                call_log = CallLog.objects.get(call_id=call_id)
                call_log.status = 'connected'
                call_log.call_state = 'connected'
                call_log.save()
                logger.info(f"Call {call_id} marked as connected")
            except CallLog.DoesNotExist:
                # Create new call log for inbound calls
                CallLog.objects.create(
                    call_id=call_id,
                    extension=extension,
                    direction='inbound',
                    caller_number=payload.get('CallerIDNum', ''),
                    called_number=payload.get('DestinationExt', ''),
                    status='connected',
                    call_state='connected',
                    start_time=datetime.now()
                )
                logger.info(f"Created new call log for {call_id}")
    
    def handle_hangup_event_basic(self, payload):
        """Handle hangup events - when a call ends"""
        call_id = payload.get('Uniqueid')
        
        if call_id:
            try:
                call_log = CallLog.objects.get(call_id=call_id)
                call_log.status = 'completed'
                call_log.call_state = 'completed'
                call_log.end_time = datetime.now()
                
                # Calculate duration
                if call_log.start_time:
                    duration = call_log.end_time - call_log.start_time
                    call_log.duration_seconds = int(duration.total_seconds())
                
                call_log.save()
                logger.info(f"Call {call_id} completed - Duration: {call_log.duration_seconds}s")
                
            except CallLog.DoesNotExist:
                logger.warning(f"Hangup event for unknown call: {call_id}")
    
    def handle_bridge_event_basic(self, payload):
        """Handle bridge events - when calls are connected"""
        call_id = payload.get('Uniqueid')
        
        if call_id:
            try:
                call_log = CallLog.objects.get(call_id=call_id)
                call_log.status = 'connected'
                call_log.call_state = 'connected'
                call_log.save()
                logger.info(f"Call {call_id} bridged")
            except CallLog.DoesNotExist:
                logger.warning(f"Bridge event for unknown call: {call_id}")
    
    def handle_new_channel_event_basic(self, payload):
        """Handle new channel events"""
        # Basic implementation - log the event
        call_id = payload.get('Uniqueid')
        channel = payload.get('Channel')
        logger.info(f"New channel created: {channel} (Call ID: {call_id})")

@method_decorator(csrf_exempt, name='dispatch')
class ZohoWebhookView(View):
    """Handle webhooks from Zoho"""
    
    def post(self, request):
        try:
            # Log the webhook
            payload = json.loads(request.body)
            webhook_log = ZohoWebhookLog.objects.create(
                event_type=payload.get('event_type', 'unknown'),
                payload=payload
            )
            
            logger.info(f"Received Zoho webhook: {webhook_log.event_type} (ID: {webhook_log.id})")
            
            # Process the webhook
            self.process_zoho_event(payload, webhook_log)
            
            return JsonResponse({'status': 'received', 'webhook_id': webhook_log.id})
            
        except json.JSONDecodeError:
            logger.error("Invalid JSON in Zoho webhook")
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"Zoho webhook error: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    
    def process_zoho_event(self, payload, webhook_log):
        """Process different types of Zoho events"""
        try:
            # Basic Zoho webhook processing
            event_type = payload.get('event_type', 'unknown')
            
            # Log the event for now - can be enhanced later
            logger.info(f"Processing Zoho webhook event: {event_type}")
            
            webhook_log.processed = True
            webhook_log.save()
            
        except Exception as e:
            webhook_log.error_message = str(e)
            webhook_log.save()
            logger.error(f"Error processing Zoho event: {str(e)}")

class TestVitalPBXView(LoginRequiredMixin, View):
    """Enhanced test view for VitalPBX connectivity"""
    
    def get(self, request):
        logger.info(f"VitalPBX test initiated by user: {request.user.email}")
        
        try:
            vitalpbx_service = VitalPBXService()
            
            # Validate configuration first
            config_validation = vitalpbx_service.validate_configuration()
            
            if not config_validation['valid']:
                return JsonResponse({
                    'vitalpbx_connected': False,
                    'message': 'Configuration validation failed',
                    'details': config_validation,
                    'recommendations': [
                        'Check environment variables are set correctly',
                        'Verify VITALPBX_API_BASE includes protocol (https://)',
                        'Ensure VITALPBX_API_KEY is correct'
                    ]
                })
            
            # Test connection
            result = vitalpbx_service.test_connection()
            
            return JsonResponse({
                'vitalpbx_connected': result.get('success', False),
                'message': result.get('message', ''),
                'details': result.get('details', {}),
                'configuration': config_validation,
                'timestamp': datetime.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"VitalPBX test error: {str(e)}")
            return JsonResponse({
                'vitalpbx_connected': False,
                'message': f'Test failed with error: {str(e)}',
                'details': {'error': str(e)},
                'timestamp': datetime.now().isoformat()
            })

class TestZohoView(LoginRequiredMixin, View):
    """Enhanced test view for Zoho connectivity with PhoneBridge validation"""
    
    def get(self, request):
        logger.info(f"Zoho test initiated by user: {request.user.email}")
        
        try:
            zoho_service = ZohoService()
            token_manager = ZohoTokenManager(zoho_service)
            
            # Validate configuration first
            config_validation = zoho_service.validate_configuration()
            
            if not config_validation['valid']:
                return JsonResponse({
                    'zoho_connected': False,
                    'message': 'Configuration validation failed',
                    'details': config_validation,
                    'recommendations': [
                        'Set ZOHO_CLIENT_ID in environment variables',
                        'Set ZOHO_CLIENT_SECRET in environment variables',
                        'Complete OAuth flow by visiting /phonebridge/zoho/connect/'
                    ]
                })
            
            # Check for token
            zoho_token = token_manager.get_valid_token_for_user(request.user)
            
            if not zoho_token:
                auth_url_data = zoho_service.get_auth_url()
                return JsonResponse({
                    'zoho_connected': False,
                    'message': 'No valid Zoho token found - OAuth authorization required',
                    'auth_url': auth_url_data['auth_url'],
                    'instructions': 'Visit the auth_url to complete OAuth authorization',
                    'details': config_validation,
                    'oauth_version': 'v3',
                    'scopes': auth_url_data['scopes']
                })
            
            # Test API connection
            test_result = zoho_service.test_connection(
                zoho_token.access_token, 
                zoho_token.api_domain
            )
            
            # Test PhoneBridge scopes specifically
            scope_validation = zoho_service.validate_phonebridge_scopes(
                zoho_token.access_token,
                zoho_token.api_domain
            )
            
            return JsonResponse({
                'zoho_connected': test_result.get('success', False),
                'message': test_result.get('message', ''),
                'details': test_result.get('details', {}),
                'token_info': {
                    'location': zoho_token.location,
                    'api_domain': zoho_token.api_domain,
                    'oauth_version': zoho_token.oauth_version,
                    'expires_at': zoho_token.expires_at.isoformat(),
                    'zoho_user_id': zoho_token.zoho_user_id,
                    'phonebridge_enabled': zoho_token.is_phonebridge_enabled(),
                    'scopes_granted': zoho_token.scopes_granted
                },
                'phonebridge_validation': scope_validation,
                'migration_info': token_manager.validate_token_migration_needed(zoho_token),
                'timestamp': datetime.now().isoformat()
            })
                
        except Exception as e:
            logger.error(f"Zoho test error: {str(e)}")
            return JsonResponse({
                'zoho_connected': False,
                'message': f'Test failed with error: {str(e)}',
                'details': {'error': str(e)},
                'timestamp': datetime.now().isoformat()
            })

class SystemDiagnosticsView(LoginRequiredMixin, View):
    """Enhanced comprehensive system diagnostics"""
    
    def get(self, request):
        from django.db import connection
        import requests
        
        diagnostics = {
            'timestamp': datetime.now().isoformat(),
            'user': request.user.email,
            'environment': {},
            'database': {},
            'external_services': {},
            'phonebridge_status': {},
            'oauth_migration': {}
        }
        
        # Check environment variables
        phonebridge_settings = settings.PHONEBRIDGE_SETTINGS
        diagnostics['environment'] = {
            'debug_mode': settings.DEBUG,
            'phonebridge_app_installed': 'phonebridge' in settings.INSTALLED_APPS,
            'oauth_version': 'v3',
            'required_settings': {
                'zoho_client_id_set': bool(phonebridge_settings.get('ZOHO_CLIENT_ID')),
                'zoho_client_secret_set': bool(phonebridge_settings.get('ZOHO_CLIENT_SECRET')),
                'vitalpbx_api_base_set': bool(phonebridge_settings.get('VITALPBX_API_BASE')),
                'vitalpbx_api_key_set': bool(phonebridge_settings.get('VITALPBX_API_KEY')),
                'popup_enabled': phonebridge_settings.get('POPUP_ENABLED', True),
                'oauth_migration_enabled': phonebridge_settings.get('OAUTH_MIGRATION_ENABLED', True)
            },
            'oauth_settings': {
                'redirect_uri': phonebridge_settings.get('ZOHO_REDIRECT_URI'),
                'scopes': phonebridge_settings.get('ZOHO_SCOPES'),
                'fallback_to_us': phonebridge_settings.get('OAUTH_FALLBACK_TO_US', True)
            }
        }
        
        # Check database
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            
            diagnostics['database'] = {
                'connection': 'OK',
                'zoho_tokens': ZohoToken.objects.count(),
                'extension_mappings': ExtensionMapping.objects.count(),
                'call_logs': CallLog.objects.count(),
                'oauth_migration_logs': OAuthMigrationLog.objects.count(),
                'v3_tokens': ZohoToken.objects.filter(oauth_version='v3').count(),
                'phonebridge_enabled_tokens': ZohoToken.objects.filter(
                    scopes_granted__icontains='PhoneBridge'
                ).count()
            }
        except Exception as e:
            diagnostics['database'] = {
                'connection': 'FAILED',
                'error': str(e)
            }
        
        # Check external services with location awareness
        try:
            # Test Zoho server info endpoint
            server_info_response = requests.get('https://accounts.zoho.com/oauth/serverinfo', timeout=10)
            diagnostics['external_services']['zoho_server_info'] = {
                'status': 'OK' if server_info_response.status_code == 200 else 'FAILED',
                'status_code': server_info_response.status_code,
                'locations_available': list(server_info_response.json().get('locations', {}).keys()) if server_info_response.status_code == 200 else []
            }
        except Exception as e:
            diagnostics['external_services']['zoho_server_info'] = {
                'status': 'FAILED',
                'error': str(e)
            }
        
        # Test VitalPBX connectivity
        vitalpbx_url = phonebridge_settings.get('VITALPBX_API_BASE')
        if vitalpbx_url:
            try:
                vitalpbx_response = requests.get(f"{vitalpbx_url}/v2/tenants", timeout=10, verify=False, headers={
                    'app-key': phonebridge_settings.get('VITALPBX_API_KEY', '')
                })
                diagnostics['external_services']['vitalpbx'] = {
                    'status': 'OK' if vitalpbx_response.status_code in [200, 401, 403] else 'FAILED',
                    'status_code': vitalpbx_response.status_code,
                    'api_key_auth': vitalpbx_response.status_code != 401
                }
            except Exception as e:
                diagnostics['external_services']['vitalpbx'] = {
                    'status': 'FAILED',
                    'error': str(e)
                }
        
        # PhoneBridge specific status for current user
        try:
            zoho_token = ZohoToken.objects.get(user=request.user)
            token_manager = ZohoTokenManager(ZohoService())
            migration_info = token_manager.validate_token_migration_needed(zoho_token)
            
            diagnostics['phonebridge_status']['user_token'] = {
                'exists': True,
                'expired': zoho_token.is_expired(),
                'expires_at': zoho_token.expires_at.isoformat(),
                'location': zoho_token.location,
                'oauth_version': zoho_token.oauth_version,
                'phonebridge_enabled': zoho_token.is_phonebridge_enabled(),
                'api_domain': zoho_token.api_domain,
                'needs_migration': migration_info['needs_migration'],
                'migration_issues': migration_info['issues']
            }
        except ZohoToken.DoesNotExist:
            diagnostics['phonebridge_status']['user_token'] = {
                'exists': False,
                'needs_authorization': True
            }
        
        # Extension mappings for current user
        user_extensions = ExtensionMapping.objects.filter(user=request.user, is_active=True)
        diagnostics['phonebridge_status']['extensions'] = {
            'count': user_extensions.count(),
            'extensions': [ext.extension for ext in user_extensions]
        }
        
        # OAuth migration summary
        migration_logs = OAuthMigrationLog.objects.filter(user=request.user)
        diagnostics['oauth_migration'] = {
            'migration_attempts': migration_logs.count(),
            'latest_migration': migration_logs.latest('migration_started_at').migration_status if migration_logs.exists() else None,
            'completed_migrations': migration_logs.filter(migration_status='completed').count(),
            'failed_migrations': migration_logs.filter(migration_status='failed').count()
        }
        
        return JsonResponse(diagnostics)

# API ViewSets for REST endpoints (keep existing implementation)
class ExtensionMappingViewSet(viewsets.ModelViewSet):
    """API for managing extension mappings"""
    serializer_class = ExtensionMappingSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return ExtensionMapping.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """Create multiple extension mappings at once"""
        mappings_data = request.data.get('mappings', [])
        created_mappings = []
        
        for mapping_data in mappings_data:
            mapping_data['user'] = request.user.id
            serializer = self.get_serializer(data=mapping_data)
            if serializer.is_valid():
                serializer.save(user=request.user)
                created_mappings.append(serializer.data)
        
        return Response({
            'created': len(created_mappings),
            'mappings': created_mappings
        })

class CallLogViewSet(viewsets.ReadOnlyModelViewSet):
    """API for viewing call logs"""
    serializer_class = CallLogSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return CallLog.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get call statistics with enhanced metrics"""
        queryset = self.get_queryset()
        
        # Calculate stats
        total_calls = queryset.count()
        inbound_calls = queryset.filter(direction='inbound').count()
        outbound_calls = queryset.filter(direction='outbound').count()
        completed_calls = queryset.filter(status='completed').count()
        
        # Average call duration
        completed_queryset = queryset.filter(
            status='completed',
            duration_seconds__isnull=False
        )
        avg_duration = completed_queryset.aggregate(
            avg_duration=models.Avg('duration_seconds')
        )['avg_duration'] or 0
        
        # PhoneBridge specific stats
        popup_sent_calls = queryset.filter(popup_sent=True).count()
        phonebridge_calls = queryset.filter(
            popup_sent=True,
            contact_id__isnull=False
        ).count()
        
        return Response({
            'total_calls': total_calls,
            'inbound_calls': inbound_calls,
            'outbound_calls': outbound_calls,
            'completed_calls': completed_calls,
            'success_rate': (completed_calls / total_calls * 100) if total_calls > 0 else 0,
            'average_duration_seconds': round(avg_duration, 2),
            'average_duration_minutes': round(avg_duration / 60, 2),
            'popup_sent_calls': popup_sent_calls,
            'phonebridge_integrated_calls': phonebridge_calls,
            'phonebridge_integration_rate': (phonebridge_calls / total_calls * 100) if total_calls > 0 else 0
        })