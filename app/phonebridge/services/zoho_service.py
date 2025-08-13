import requests
import json
import logging
import secrets
import time
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from urllib.parse import urlencode
from typing import Dict, Optional, Tuple

logger = logging.getLogger('phonebridge')

class ZohoLocationService:
    """Service for handling Zoho location-based OAuth"""
    
    LOCATION_MAPPING = {
        'us': 'https://accounts.zoho.com',
        'eu': 'https://accounts.zoho.eu', 
        'in': 'https://accounts.zoho.in',
        'au': 'https://accounts.zoho.com.au',
        'jp': 'https://accounts.zoho.jp',
        'sa': 'https://accounts.zoho.sa',
        'ca': 'https://accounts.zohocloud.ca'
    }
    
    @classmethod
    def get_server_info(cls, timeout: int = 30) -> Dict:
        """Get server information for all Zoho locations"""
        try:
            logger.info("Fetching Zoho server info for location mapping")
            response = requests.get(
                'https://accounts.zoho.com/oauth/serverinfo',
                timeout=timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("Successfully retrieved Zoho server info")
                return {
                    'success': True,
                    'locations': data.get('locations', {}),
                    'result': data.get('result')
                }
            else:
                logger.warning(f"Server info request failed: {response.status_code}")
                return {
                    'success': False,
                    'error': f'HTTP {response.status_code}: {response.text}',
                    'fallback_locations': cls.LOCATION_MAPPING
                }
        except Exception as e:
            logger.error(f"Error fetching server info: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'fallback_locations': cls.LOCATION_MAPPING
            }
    
    @classmethod
    def get_oauth_domain_for_location(cls, location: str, server_info: Optional[Dict] = None) -> str:
        """Get OAuth domain for specific location"""
        if server_info and server_info.get('success') and 'locations' in server_info:
            locations = server_info['locations']
            if location in locations:
                return locations[location]
        
        # Fallback to hardcoded mapping
        return cls.LOCATION_MAPPING.get(location, cls.LOCATION_MAPPING['us'])


class ZohoService:
    """Enhanced service for Zoho APIs with HTTP development mode support"""
    
    def __init__(self):
        self.config = settings.PHONEBRIDGE_SETTINGS
        self.client_id = self.config['ZOHO_CLIENT_ID']
        self.client_secret = self.config['ZOHO_CLIENT_SECRET']
        
        # UPDATED: Use the redirect URI from settings/environment
        self.redirect_uri = self.config.get('ZOHO_REDIRECT_URI')
        
        # UPDATED: Use simpler scopes for PhoneBridge as per documentation
        self.scopes = self.config.get('ZOHO_SCOPES', 'PhoneBridge.call.log,PhoneBridge.zohoone.search')
        
        # Default domains (will be overridden by location-specific ones)
        self.default_auth_url = 'https://accounts.zoho.com/oauth/v2/auth'
        self.default_token_url = 'https://accounts.zoho.com/oauth/v2/token'
        self.default_api_base = 'https://www.zohoapis.com'
        
        self.location_service = ZohoLocationService()
        
        # UPDATED: HTTP development mode support
        self.http_mode = self.config.get('HTTP_DEVELOPMENT_MODE', settings.DEBUG)
        self.skip_ssl_verification = self.config.get('SKIP_SSL_VERIFICATION', False)
        
        logger.info(f"Enhanced Zoho Service initialized for HTTP development mode")
        logger.info(f"Client ID: {self.client_id[:20]}... (truncated)")
        logger.info(f"Redirect URI: {self.redirect_uri}")
        logger.info(f"Scopes: {self.scopes}")
        logger.info(f"HTTP Mode: {self.http_mode}")
    
    def validate_configuration(self) -> Dict:
        """Validate Zoho configuration with new requirements"""
        issues = []
        warnings = []
        
        if not self.client_id:
            issues.append("ZOHO_CLIENT_ID is not set")
        elif not self.client_id.startswith('1000.'):
            issues.append("ZOHO_CLIENT_ID should start with '1000.'")
        
        if not self.client_secret:
            issues.append("ZOHO_CLIENT_SECRET is not set")
        elif len(self.client_secret) < 32:
            warnings.append(f"Client secret length is {len(self.client_secret)}, verify if correct")
        
        if not self.redirect_uri:
            issues.append("Redirect URI is not configured")
        elif not self.redirect_uri.startswith(('http://', 'https://')):
            issues.append("Redirect URI must be a valid URL")
        
        # UPDATED: Check for HTTP in production
        if self.redirect_uri and self.redirect_uri.startswith('http://') and not settings.DEBUG:
            warnings.append("Using HTTP redirect URI in production mode - consider HTTPS")
        
        # UPDATED: Validate new simpler scopes for PhoneBridge
        required_scopes = ['PhoneBridge.call.log', 'PhoneBridge.zohoone.search']
        current_scopes = self.scopes.split(',')
        missing_scopes = [scope for scope in required_scopes if scope not in current_scopes]
        
        if missing_scopes:
            warnings.append(f"Missing PhoneBridge scopes: {', '.join(missing_scopes)}")
        
        # Test server info connectivity
        server_info = self.location_service.get_server_info(timeout=10)
        if not server_info.get('success'):
            warnings.append("Could not fetch Zoho server info - will use fallback locations")
        
        # UPDATED: Check redirect URI format for new server
        expected_path = '/phonebridge/zoho/callback/'
        if self.redirect_uri and expected_path not in self.redirect_uri:
            warnings.append(f"Redirect URI should contain '{expected_path}' path")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings,
            'config': {
                'client_id': self.client_id[:15] + '...' if self.client_id else None,
                'has_client_secret': bool(self.client_secret),
                'redirect_uri': self.redirect_uri,
                'scopes': self.scopes,
                'server_info_accessible': server_info.get('success', False),
                'available_locations': list(server_info.get('locations', {}).keys()) if server_info.get('success') else list(self.location_service.LOCATION_MAPPING.keys()),
                'http_mode': self.http_mode,
                'skip_ssl_verification': self.skip_ssl_verification
            }
        }
    
    def get_auth_url(self, state: Optional[str] = None) -> Dict:
        """Generate location-aware OAuth authorization URL"""
        if not state:
            state = secrets.token_urlsafe(32)
        
        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': self.redirect_uri,
            'scope': self.scopes,
            'access_type': 'offline',
            'state': state,
            'prompt': 'consent'  # Force consent to ensure we get refresh token
        }
        
        # Use default auth URL (Zoho will handle location routing)
        auth_url = f"{self.default_auth_url}?{urlencode(params)}"
        
        logger.info(f"Generated PhoneBridge auth URL with state: {state[:10]}...")
        logger.info(f"Scopes requested: {self.scopes}")
        logger.info(f"Redirect URI: {self.redirect_uri}")
        
        return {
            'auth_url': auth_url,
            'state': state,
            'params': params,
            'scopes': self.scopes
        }
    
    def handle_oauth_callback(self, code: str, location: Optional[str] = None, 
                            expected_state: Optional[str] = None, 
                            received_state: Optional[str] = None) -> Dict:
        """Handle OAuth callback with location parameter"""
        logger.info(f"Handling OAuth callback with location: {location}")
        logger.info(f"Redirect URI used: {self.redirect_uri}")
        
        # Validate state parameter
        if expected_state and received_state:
            if expected_state != received_state:
                logger.error("State parameter mismatch - possible CSRF attack")
                raise Exception("Invalid state parameter")
        
        # Step 1: Get server info if location is provided
        oauth_domain = self.default_token_url.replace('/oauth/v2/token', '')
        api_domain = self.default_api_base
        
        if location:
            logger.info(f"Getting domain info for location: {location}")
            server_info = self.location_service.get_server_info()
            
            if server_info.get('success'):
                oauth_domain = self.location_service.get_oauth_domain_for_location(location, server_info)
                # UPDATED: Determine API domain based on location
                if location == 'eu':
                    api_domain = 'https://www.zohoapis.eu'
                elif location == 'in':
                    api_domain = 'https://www.zohoapis.in'
                elif location == 'au':
                    api_domain = 'https://www.zohoapis.com.au'
                elif location == 'jp':
                    api_domain = 'https://www.zohoapis.jp'
                elif location == 'sa':
                    api_domain = 'https://www.zohoapis.sa'
                elif location == 'ca':
                    api_domain = 'https://www.zohoapis.ca'
                # Default to .com for US and others
                
                logger.info(f"Using OAuth domain: {oauth_domain}")
                logger.info(f"Using API domain: {api_domain}")
            else:
                logger.warning(f"Server info failed, using fallback for location {location}")
                oauth_domain = self.location_service.get_oauth_domain_for_location(location)
        
        # Step 2: Exchange code for tokens
        return self._exchange_code_for_tokens(
            code=code,
            oauth_domain=oauth_domain,
            location=location,
            api_domain=api_domain
        )
    
    def _exchange_code_for_tokens(self, code: str, oauth_domain: str, 
                                location: Optional[str] = None,
                                api_domain: Optional[str] = None) -> Dict:
        """Exchange authorization code for access and refresh tokens"""
        token_url = f"{oauth_domain.rstrip('/')}/oauth/v2/token"
        
        data = {
            'code': code,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': self.redirect_uri,
            'grant_type': 'authorization_code'
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }
        
        try:
            logger.info(f"Exchanging code for tokens at: {token_url}")
            logger.info(f"Using redirect_uri: {self.redirect_uri}")
            
            # UPDATED: Handle SSL verification for HTTP development mode
            verify_ssl = not self.skip_ssl_verification
            
            response = requests.post(
                token_url, 
                data=data, 
                headers=headers, 
                timeout=30,
                verify=verify_ssl
            )
            
            logger.info(f"Token exchange response: {response.status_code}")
            
            if response.status_code == 200:
                token_data = response.json()
                logger.info("Token exchange successful")
                
                # Extract API domain from response (preferred) or use parameter
                response_api_domain = token_data.get('api_domain', api_domain or self.default_api_base)
                
                # Calculate expiry time
                expires_in = token_data.get('expires_in', 3600)
                expires_at = timezone.now() + timedelta(seconds=expires_in)
                
                result = {
                    'access_token': token_data.get('access_token'),
                    'refresh_token': token_data.get('refresh_token'),
                    'expires_in': expires_in,
                    'expires_at': expires_at,
                    'token_type': token_data.get('token_type', 'Bearer'),
                    'scope': token_data.get('scope'),
                    'api_domain': response_api_domain,
                    'oauth_domain': oauth_domain,
                    'location': location or 'us',
                    'oauth_version': 'v3',
                    'raw_response': token_data
                }
                
                logger.info(f"Token details - Location: {result['location']}, API Domain: {result['api_domain']}")
                return result
            else:
                logger.error(f"Token exchange failed: {response.status_code}")
                logger.error(f"Response: {response.text}")
                
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error_description', 
                                             error_data.get('error', response.text))
                except:
                    error_msg = response.text
                
                raise Exception(f"Token exchange failed: {error_msg}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Token exchange request failed: {str(e)}")
            raise Exception(f"Network error during token exchange: {str(e)}")
    
    def refresh_access_token(self, refresh_token: str, oauth_domain: str, 
                           api_domain: Optional[str] = None) -> Dict:
        """Refresh access token using location-specific domain"""
        token_url = f"{oauth_domain.rstrip('/')}/oauth/v2/token"
        
        logger.info(f"Refreshing token at: {token_url}")
        
        data = {
            'refresh_token': refresh_token,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'refresh_token'
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }
        
        try:
            # UPDATED: Handle SSL verification for HTTP development mode
            verify_ssl = not self.skip_ssl_verification
            
            response = requests.post(
                token_url, 
                data=data, 
                headers=headers, 
                timeout=30,
                verify=verify_ssl
            )
            
            logger.info(f"Token refresh response: {response.status_code}")
            
            if response.status_code == 200:
                token_data = response.json()
                logger.info("Token refresh successful")
                
                expires_in = token_data.get('expires_in', 3600)
                expires_at = timezone.now() + timedelta(seconds=expires_in)
                
                return {
                    'access_token': token_data.get('access_token'),
                    'refresh_token': token_data.get('refresh_token', refresh_token),
                    'expires_in': expires_in,
                    'expires_at': expires_at,
                    'token_type': token_data.get('token_type', 'Bearer'),
                    'scope': token_data.get('scope'),
                    'api_domain': token_data.get('api_domain', api_domain),
                    'raw_response': token_data
                }
            else:
                logger.error(f"Token refresh failed: {response.status_code}")
                logger.error(f"Response: {response.text}")
                raise Exception(f"Token refresh failed: {response.text}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Token refresh request failed: {str(e)}")
            raise Exception(f"Network error during token refresh: {str(e)}")
    
    def get_user_info(self, access_token: str, api_domain: Optional[str] = None) -> Dict:
        """Get user information using location-specific API domain"""
        base_domain = api_domain or self.default_api_base
        
        logger.info(f"Fetching user info from: {base_domain}")
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        # Try multiple endpoints for PhoneBridge
        endpoints = [
            f"{base_domain}/phonebridge/v3/users/me",
            f"{base_domain}/crm/v2/users?type=CurrentUser",
            f"{base_domain}/crm/v2/org"
        ]
        
        # UPDATED: Handle SSL verification
        verify_ssl = not self.skip_ssl_verification
        
        for endpoint in endpoints:
            try:
                logger.info(f"Trying user info endpoint: {endpoint}")
                response = requests.get(
                    endpoint, 
                    headers=headers, 
                    timeout=30,
                    verify=verify_ssl
                )
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"User info retrieved from: {endpoint}")
                    
                    # Handle different response structures
                    if 'users' in data and data['users']:
                        user_data = data['users'][0]
                    elif 'data' in data and isinstance(data['data'], list) and data['data']:
                        user_data = data['data'][0]
                    elif 'data' in data:
                        user_data = data['data']
                    else:
                        user_data = data
                    
                    return {
                        'success': True,
                        'user_data': user_data,
                        'endpoint_used': endpoint,
                        'api_domain': base_domain,
                        'raw_response': data
                    }
                else:
                    logger.warning(f"User info failed for {endpoint}: {response.status_code}")
                    
            except Exception as e:
                logger.warning(f"Failed to get user info from {endpoint}: {str(e)}")
                continue
        
        logger.error("Failed to get user info from all endpoints")
        return {
            'success': False,
            'error': 'Failed to retrieve user information from all available endpoints',
            'api_domain': base_domain
        }
    
    def test_connection(self, access_token: str, api_domain: Optional[str] = None) -> Dict:
        """Test connection to both CRM and PhoneBridge APIs"""
        base_domain = api_domain or self.default_api_base
        
        logger.info(f"Testing Zoho API connection to: {base_domain}")
        
        test_results = {
            'overall_success': False,
            'api_domain': base_domain,
            'tests': {}
        }
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        # UPDATED: Handle SSL verification
        verify_ssl = not self.skip_ssl_verification
        
        # Test 1: PhoneBridge API connectivity (primary)
        try:
            phonebridge_response = requests.get(
                f"{base_domain}/phonebridge/v3/calls",
                headers=headers,
                timeout=30,
                verify=verify_ssl
            )
            
            test_results['tests']['phonebridge_api'] = {
                'success': phonebridge_response.status_code in [200, 404, 405],
                'status_code': phonebridge_response.status_code,
                'endpoint': f"{base_domain}/phonebridge/v3/calls",
                'available': phonebridge_response.status_code == 200,
                'response_sample': phonebridge_response.text[:200] if phonebridge_response.text else 'Empty response'
            }
            
        except Exception as e:
            test_results['tests']['phonebridge_api'] = {
                'success': False,
                'error': str(e)
            }
        
        # Test 2: CRM API connectivity (fallback)
        try:
            crm_response = requests.get(
                f"{base_domain}/crm/v2/org",
                headers=headers,
                timeout=30,
                verify=verify_ssl
            )
            
            test_results['tests']['crm_api'] = {
                'success': crm_response.status_code == 200,
                'status_code': crm_response.status_code,
                'endpoint': f"{base_domain}/crm/v2/org",
                'response_sample': crm_response.text[:200] if crm_response.text else 'Empty response'
            }
            
        except Exception as e:
            test_results['tests']['crm_api'] = {
                'success': False,
                'error': str(e)
            }
        
        # Test 3: User information
        user_info_result = self.get_user_info(access_token, base_domain)
        test_results['tests']['user_info'] = user_info_result
        
        # Determine overall success
        phonebridge_success = test_results['tests'].get('phonebridge_api', {}).get('success', False)
        crm_success = test_results['tests'].get('crm_api', {}).get('success', False)
        user_success = test_results['tests'].get('user_info', {}).get('success', False)
        
        test_results['overall_success'] = phonebridge_success or crm_success or user_success
        test_results['phonebridge_available'] = phonebridge_success
        
        if test_results['overall_success']:
            message = 'Zoho connection successful'
            if test_results['phonebridge_available']:
                message += ' with PhoneBridge access'
            return {
                'success': True,
                'message': message,
                'details': test_results
            }
        else:
            return {
                'success': False,
                'message': 'Zoho connection failed',
                'details': test_results
            }
    
    def validate_phonebridge_scopes(self, access_token: str, api_domain: Optional[str] = None) -> Dict:
        """Validate that token has necessary PhoneBridge scopes"""
        base_domain = api_domain or self.default_api_base
        
        logger.info("Validating PhoneBridge scopes")
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        # UPDATED: Test PhoneBridge specific endpoints
        scope_tests = {
            'call_log_access': f"{base_domain}/phonebridge/v3/calls",
            'search_access': f"{base_domain}/phonebridge/v3/search"
        }
        
        results = {}
        verify_ssl = not self.skip_ssl_verification
        
        for scope_name, endpoint in scope_tests.items():
            try:
                response = requests.get(
                    endpoint, 
                    headers=headers, 
                    timeout=15,
                    verify=verify_ssl
                )
                
                results[scope_name] = {
                    'available': response.status_code not in [401, 403],
                    'status_code': response.status_code,
                    'endpoint': endpoint
                }
                
                logger.debug(f"Scope test {scope_name}: {response.status_code}")
                
            except Exception as e:
                results[scope_name] = {
                    'available': False,
                    'error': str(e),
                    'endpoint': endpoint
                }
        
        # Determine overall scope validity
        available_scopes = sum(1 for result in results.values() if result.get('available', False))
        total_scopes = len(scope_tests)
        
        return {
            'valid': available_scopes > 0,
            'available_scopes': available_scopes,
            'total_scopes': total_scopes,
            'scope_percentage': (available_scopes / total_scopes) * 100,
            'details': results,
            'recommendations': self._get_scope_recommendations(results)
        }
    
    def _get_scope_recommendations(self, scope_results: Dict) -> list:
        """Get recommendations based on scope test results"""
        recommendations = []
        
        if not scope_results.get('call_log_access', {}).get('available', False):
            recommendations.append("PhoneBridge call log access not available - check PhoneBridge.call.log scope")
        
        if not scope_results.get('search_access', {}).get('available', False):
            recommendations.append("PhoneBridge search access not available - check PhoneBridge.zohoone.search scope")
        
        if not recommendations:
            recommendations.append("All PhoneBridge scopes appear to be working correctly")
        
        return recommendations


class ZohoTokenManager:
    """Manager for handling Zoho token operations with migration support"""
    
    def __init__(self, zoho_service: ZohoService):
        self.zoho_service = zoho_service
    
    def save_token_data(self, user, token_data: Dict) -> 'ZohoToken':
        """Save token data to database with new OAuth v3 fields"""
        from ..models import ZohoToken
        
        zoho_token, created = ZohoToken.objects.update_or_create(
            user=user,
            defaults={
                'access_token': token_data['access_token'],
                'refresh_token': token_data.get('refresh_token', ''),
                'expires_at': token_data['expires_at'],
                'location': token_data.get('location', 'us'),
                'oauth_domain': token_data.get('oauth_domain', ''),
                'api_domain': token_data.get('api_domain', ''),
                'oauth_version': token_data.get('oauth_version', 'v3'),
                'scopes_granted': token_data.get('scope', ''),
                'token_type': token_data.get('token_type', 'Bearer'),
                'last_refreshed_at': timezone.now() if not created else None
            }
        )
        
        logger.info(f"{'Created' if created else 'Updated'} Zoho token for {user.email}")
        return zoho_token
    
    def refresh_token_if_needed(self, zoho_token: 'ZohoToken') -> bool:
        """Refresh token if expired, using location-specific domain"""
        if not zoho_token.is_expired():
            return True
        
        try:
            logger.info(f"Refreshing expired token for {zoho_token.user.email}")
            
            refresh_result = self.zoho_service.refresh_access_token(
                refresh_token=zoho_token.refresh_token,
                oauth_domain=zoho_token.oauth_domain or 'https://accounts.zoho.com',
                api_domain=zoho_token.api_domain
            )
            
            # Update token
            zoho_token.access_token = refresh_result['access_token']
            zoho_token.expires_at = refresh_result['expires_at']
            zoho_token.last_refreshed_at = timezone.now()
            
            if 'refresh_token' in refresh_result:
                zoho_token.refresh_token = refresh_result['refresh_token']
            
            if 'api_domain' in refresh_result:
                zoho_token.api_domain = refresh_result['api_domain']
            
            zoho_token.save()
            
            logger.info(f"Token refreshed successfully for {zoho_token.user.email}")
            return True
            
        except Exception as e:
            logger.error(f"Token refresh failed for {zoho_token.user.email}: {str(e)}")
            return False
    
    def get_valid_token_for_user(self, user) -> Optional['ZohoToken']:
        """Get valid token for user, refreshing if necessary"""
        from ..models import ZohoToken
        
        try:
            zoho_token = ZohoToken.objects.get(user=user)
            
            if self.refresh_token_if_needed(zoho_token):
                return zoho_token
            else:
                logger.warning(f"Could not refresh token for {user.email}")
                return None
                
        except ZohoToken.DoesNotExist:
            logger.warning(f"No token found for {user.email}")
            return None
    
    def validate_token_migration_needed(self, zoho_token: 'ZohoToken') -> Dict:
        """Check if token needs migration to new OAuth flow"""
        needs_migration = zoho_token.needs_migration()
        
        issues = []
        if not zoho_token.location:
            issues.append("Missing location information")
        if not zoho_token.api_domain:
            issues.append("Missing API domain information")
        if zoho_token.oauth_version != 'v3':
            issues.append("Using old OAuth version")
        if not zoho_token.is_phonebridge_enabled():
            issues.append("PhoneBridge scopes not detected")
        
        return {
            'needs_migration': needs_migration,
            'issues': issues,
            'token_age_days': (timezone.now() - zoho_token.created_at).days,
            'last_refresh': zoho_token.last_refreshed_at
        }