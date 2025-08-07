import requests
import json
import logging
import secrets
from datetime import datetime, timedelta
from django.conf import settings
from urllib.parse import urlencode

logger = logging.getLogger('phonebridge')

class VitalPBXService:
    """Enhanced VitalPBX service with API Key authentication"""
    
    def __init__(self):
        self.config = settings.PHONEBRIDGE_SETTINGS
        self.api_base = self.config['VITALPBX_API_BASE'].rstrip('/')
        self.api_key = self.config.get('VITALPBX_API_KEY', '')
        self.username = self.config.get('VITALPBX_USERNAME', '')
        self.password = self.config.get('VITALPBX_PASSWORD', '')
        self.tenant = self.config.get('VITALPBX_TENANT', '')
        self.timeout = self.config['CALL_TIMEOUT_SECONDS']
        
        logger.info(f"VitalPBX Service initialized with base URL: {self.api_base}")
        logger.info(f"API Key: {'***' + self.api_key[-4:] if self.api_key else 'NOT SET'}")
        logger.info(f"Tenant: {self.tenant or 'Default'}")
        logger.info(f"Timeout: {self.timeout}s")
    
    def _make_request(self, endpoint, method='GET', data=None, params=None, use_api_key=True):
        """Make authenticated request to VitalPBX API with API Key authentication"""
        # Clean up endpoint
        endpoint = endpoint.lstrip('/')
        url = f"{self.api_base}/v2/{endpoint}"  # Using v2 as shown in documentation
        
        # Set up headers for API Key authentication
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'PhoneBridge/1.0'
        }
        
        # Add API Key authentication (primary method)
        if use_api_key and self.api_key:
            headers['app-key'] = self.api_key
            logger.debug(f"Using API Key authentication: ***{self.api_key[-4:]}")
        
        # Add tenant parameter if specified
        if not params:
            params = {}
        if self.tenant:
            params['tenant'] = self.tenant
            logger.debug(f"Using tenant: {self.tenant}")
        
        # Add query parameters if provided
        if params:
            url += '?' + urlencode(params)
        
        logger.info(f"Making {method} request to: {url}")
        logger.debug(f"Headers: {dict(headers)}")
        
        try:
            # Prepare auth for fallback (if API key fails)
            auth = None
            if not use_api_key and self.username and self.password:
                auth = (self.username, self.password)
                logger.debug("Using Basic Auth as fallback")
            
            if method.upper() == 'GET':
                response = requests.get(
                    url,
                    auth=auth,
                    headers=headers,
                    timeout=self.timeout,
                    verify=False  # For self-signed certificates
                )
            elif method.upper() == 'POST':
                response = requests.post(
                    url,
                    auth=auth,
                    headers=headers,
                    json=data,
                    timeout=self.timeout,
                    verify=False
                )
            elif method.upper() == 'PUT':
                response = requests.put(
                    url,
                    auth=auth,
                    headers=headers,
                    json=data,
                    timeout=self.timeout,
                    verify=False
                )
            elif method.upper() == 'DELETE':
                response = requests.delete(
                    url,
                    auth=auth,
                    headers=headers,
                    timeout=self.timeout,
                    verify=False
                )
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            logger.info(f"Response status: {response.status_code}")
            logger.debug(f"Response headers: {dict(response.headers)}")
            
            if response.content:
                logger.debug(f"Response content: {response.text[:500]}...")
            
            return response
            
        except requests.exceptions.Timeout:
            logger.error(f"VitalPBX API timeout for {endpoint} (timeout: {self.timeout}s)")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"VitalPBX API connection error for {endpoint}: {str(e)}")
            return None
        except requests.exceptions.SSLError as e:
            logger.error(f"VitalPBX API SSL error for {endpoint}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"VitalPBX API unexpected error for {endpoint}: {str(e)}")
            return None
    
    def test_connection(self):
        """Test VitalPBX API connection with comprehensive authentication testing"""
        logger.info("Testing VitalPBX API connection with API Key authentication")
        
        # Test endpoints based on documentation
        test_endpoints = [
            'tenants',         # Test tenant access
            'account_codes',   # Test basic API access
            'auth_codes',      # Test authorization codes
            'extensions',      # Test extensions (important for our use case)
            'calls',          # Test call management
        ]
        
        connection_results = []
        
        # First, test with API Key authentication
        logger.info("=== Testing API Key Authentication ===")
        for endpoint in test_endpoints:
            logger.info(f"Testing endpoint: /{endpoint} with API Key")
            response = self._make_request(endpoint, use_api_key=True)
            
            result = {
                'endpoint': f"/v2/{endpoint}",
                'auth_method': 'API Key',
                'success': False,
                'status_code': None,
                'error': None,
                'response_data': None
            }
            
            if response is not None:
                result['status_code'] = response.status_code
                
                # Consider 200, 201, 202 as success
                if response.status_code in [200, 201, 202]:
                    result['success'] = True
                    try:
                        if response.content:
                            result['response_data'] = response.json()
                        else:
                            result['response_data'] = {'message': 'Empty response but successful'}
                    except json.JSONDecodeError:
                        result['response_data'] = {'raw_response': response.text[:200]}
                elif response.status_code == 401:
                    result['error'] = f"Authentication failed - API key may be invalid"
                    result['response_data'] = {'auth_failed': True}
                elif response.status_code == 403:
                    result['error'] = f"Access forbidden - API key may lack permissions"
                    result['response_data'] = {'permission_denied': True}
                elif response.status_code == 422:
                    result['error'] = f"Unprocessable content - may need additional parameters"
                    result['response_data'] = {'parameter_issue': True}
                else:
                    result['error'] = f"HTTP {response.status_code}: {response.text[:200]}"
            else:
                result['error'] = 'No response received'
            
            connection_results.append(result)
            
            # If we found a working endpoint, note it
            if result['success']:
                logger.info(f"✅ SUCCESS: {endpoint} endpoint working with API Key!")
                break
        
        # If API Key didn't work, try Basic Auth as fallback
        if not any(r['success'] for r in connection_results):
            logger.info("=== API Key failed, testing Basic Auth fallback ===")
            
            if self.username and self.password:
                for endpoint in test_endpoints[:3]:  # Test fewer endpoints for fallback
                    logger.info(f"Testing endpoint: /{endpoint} with Basic Auth")
                    response = self._make_request(endpoint, use_api_key=False)
                    
                    result = {
                        'endpoint': f"/v2/{endpoint}",
                        'auth_method': 'Basic Auth',
                        'success': False,
                        'status_code': None,
                        'error': None,
                        'response_data': None
                    }
                    
                    if response and response.status_code in [200, 201, 202]:
                        result['success'] = True
                        result['status_code'] = response.status_code
                        try:
                            result['response_data'] = response.json()
                        except:
                            result['response_data'] = {'message': 'Basic auth worked'}
                        
                        connection_results.append(result)
                        logger.info(f"✅ SUCCESS: {endpoint} endpoint working with Basic Auth!")
                        break
                    elif response:
                        result['status_code'] = response.status_code
                        result['error'] = f"Basic Auth failed: HTTP {response.status_code}"
                        connection_results.append(result)
            else:
                logger.warning("No Basic Auth credentials available for fallback")
        
        # Determine overall connection status
        any_success = any(r['success'] for r in connection_results)
        auth_issues = any(r['status_code'] == 401 for r in connection_results)
        permission_issues = any(r['status_code'] == 403 for r in connection_results)
        
        if any_success:
            working_result = next(r for r in connection_results if r['success'])
            return {
                'success': True,
                'message': f'VitalPBX connection successful!',
                'working_endpoint': working_result['endpoint'],
                'auth_method': working_result['auth_method'],
                'details': {
                    'test_results': connection_results,
                    'api_base': self.api_base,
                    'api_key_provided': bool(self.api_key),
                    'tenant': self.tenant or 'default',
                    'timeout': self.timeout
                }
            }
        elif auth_issues:
            return {
                'success': False,
                'message': 'VitalPBX authentication failed',
                'auth_issue': True,
                'details': {
                    'test_results': connection_results,
                    'api_base': self.api_base,
                    'api_key_provided': bool(self.api_key),
                    'suggestions': [
                        'Verify API key is correct: 36e6b22faea32d0069b1a7bd1da9de82',
                        'Check if API key has required permissions',
                        'Confirm tenant access is properly configured',
                        'Contact Eric to verify API key status'
                    ]
                }
            }
        elif permission_issues:
            return {
                'success': False,
                'message': 'VitalPBX access forbidden - permission issue',
                'details': {
                    'test_results': connection_results,
                    'suggestions': [
                        'API key may need additional permissions',
                        'Contact Eric to expand API key access',
                        'Check tenant-specific permissions'
                    ]
                }
            }
        else:
            return {
                'success': False,
                'message': 'VitalPBX connection failed - no working endpoints found',
                'details': {
                    'test_results': connection_results,
                    'api_base': self.api_base,
                    'api_key_provided': bool(self.api_key),
                    'common_issues': [
                        'API key may be invalid or expired',
                        'VitalPBX API may still be under construction',
                        'Network connectivity issues',
                        'API endpoints may have changed'
                    ]
                }
            }
    
    def get_tenants(self):
        """Get list of available tenants"""
        logger.info("Fetching tenants list")
        response = self._make_request('tenants')
        
        if response and response.status_code == 200:
            try:
                tenants = response.json()
                logger.info(f"Retrieved {len(tenants.get('data', []))} tenants")
                return {
                    'success': True,
                    'tenants': tenants.get('data', []),
                    'raw_response': tenants
                }
            except json.JSONDecodeError:
                logger.error("Invalid JSON response from tenants endpoint")
                return {'success': False, 'error': 'Invalid JSON response'}
        else:
            error_msg = f"Failed to get tenants: {response.status_code if response else 'No response'}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def originate_call(self, extension, destination, caller_id=None):
        """Originate a call using VitalPBX API"""
        # Generate unique action ID for tracking
        action_id = f"call_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        # Prepare call data based on VitalPBX documentation
        call_data = {
            'Channel': f'PJSIP/{extension}',
            'Context': 'from-internal',
            'Exten': destination,
            'Priority': 1,
            'Timeout': self.timeout * 1000,  # VitalPBX expects milliseconds
            'CallerID': caller_id or extension,
            'Async': True,
            'ActionID': action_id
        }
        
        logger.info(f"Originating call: {extension} -> {destination}")
        logger.debug(f"Call payload: {call_data}")
        
        # Try originate endpoint
        response = self._make_request('originate', method='POST', data=call_data)
        
        if response and response.status_code in [200, 201, 202]:
            try:
                result = response.json()
                call_id = result.get('ActionID', action_id)
                
                logger.info(f"Call initiated successfully: {call_id}")
                return {
                    'success': True,
                    'call_id': call_id,
                    'message': 'Call initiated successfully',
                    'details': result
                }
            except (json.JSONDecodeError, KeyError):
                # Even if JSON parsing fails, call might have been initiated
                logger.warning("Call initiated but response parsing failed")
                return {
                    'success': True,
                    'call_id': action_id,
                    'message': 'Call initiated (response parsing failed)',
                    'details': {'raw_response': response.text}
                }
        else:
            error_msg = f'Call origination failed: HTTP {response.status_code if response else "No response"}'
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'details': {
                    'call_data': call_data,
                    'response': response.text if response else None
                }
            }
    
    def get_extensions(self):
        """Get list of all extensions"""
        logger.info("Fetching extensions list")
        response = self._make_request('extensions')
        
        if response and response.status_code == 200:
            try:
                extensions = response.json()
                logger.info(f"Retrieved extensions successfully")
                return {
                    'success': True,
                    'extensions': extensions.get('data', []),
                    'raw_response': extensions
                }
            except json.JSONDecodeError:
                logger.error("Invalid JSON response from extensions endpoint")
                return {'success': False, 'error': 'Invalid JSON response'}
        else:
            error_msg = f"Failed to get extensions: {response.status_code if response else 'No response'}"
            logger.warning(error_msg)
            return {'success': False, 'error': error_msg}
    
    def get_call_status(self, call_id):
        """Get status of a specific call"""
        logger.info(f"Getting call status for: {call_id}")
        response = self._make_request(f'calls/{call_id}')
        
        if response and response.status_code == 200:
            try:
                status = response.json()
                logger.info(f"Call status retrieved successfully")
                return {
                    'success': True,
                    'status': status,
                    'raw_response': status
                }
            except json.JSONDecodeError:
                logger.error("Invalid JSON response from call status endpoint")
                return {'success': False, 'error': 'Invalid JSON response'}
        else:
            error_msg = f"Failed to get call status: {response.status_code if response else 'No response'}"
            logger.warning(error_msg)
            return {'success': False, 'error': error_msg}
    
    def hangup_call(self, call_id):
        """Hangup a specific call"""
        logger.info(f"Hanging up call: {call_id}")
        response = self._make_request(f'calls/{call_id}/hangup', method='POST')
        
        if response and response.status_code in [200, 204]:
            logger.info(f"Call {call_id} hangup initiated successfully")
            return {
                'success': True,
                'message': 'Call hangup initiated',
                'call_id': call_id
            }
        else:
            error_msg = f'Failed to hangup call: HTTP {response.status_code if response else "No response"}'
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'call_id': call_id
            }
    
    def discover_api_endpoints(self):
        """Discover available API endpoints for debugging"""
        logger.info("Discovering VitalPBX API endpoints")
        
        # Common endpoint patterns to test
        endpoints_to_test = [
            # Documentation endpoints
            'tenants', 'account_codes', 'auth_codes', 'extensions', 'calls',
            # Call management
            'originate', 'hangup', 'channels', 'status',
            # User management  
            'users', 'roles', 'devices',
            # System
            'system', 'health', 'version'
        ]
        
        discovered_endpoints = []
        
        for endpoint in endpoints_to_test:
            logger.debug(f"Testing endpoint: {endpoint}")
            response = self._make_request(endpoint)
            
            endpoint_info = {
                'endpoint': endpoint,
                'url': f"{self.api_base}/v2/{endpoint}",
                'accessible': False,
                'status_code': None,
                'auth_required': False,
                'data_available': False
            }
            
            if response:
                endpoint_info['status_code'] = response.status_code
                endpoint_info['accessible'] = response.status_code not in [404, 500]
                endpoint_info['auth_required'] = response.status_code in [401, 403]
                endpoint_info['data_available'] = response.status_code == 200
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        endpoint_info['sample_data'] = str(data)[:100] + '...' if len(str(data)) > 100 else str(data)
                    except:
                        endpoint_info['sample_data'] = 'Non-JSON response'
            
            discovered_endpoints.append(endpoint_info)
        
        # Summary
        accessible = len([e for e in discovered_endpoints if e['accessible']])
        working = len([e for e in discovered_endpoints if e['data_available']])
        auth_required = len([e for e in discovered_endpoints if e['auth_required']])
        
        logger.info(f"Discovery complete: {accessible} accessible, {working} working, {auth_required} auth required")
        
        return {
            'total_tested': len(endpoints_to_test),
            'accessible_endpoints': accessible,
            'working_endpoints': working,
            'auth_required_endpoints': auth_required,
            'endpoints': discovered_endpoints,
            'summary': {
                'api_key_working': working > 0,
                'auth_configured': auth_required == 0 or working > 0,
                'api_available': accessible > 0
            }
        }
    
    def validate_configuration(self):
        """Validate VitalPBX configuration"""
        issues = []
        warnings = []
        
        if not self.api_base:
            issues.append("VITALPBX_API_BASE is not set")
        elif not self.api_base.startswith(('http://', 'https://')):
            issues.append("VITALPBX_API_BASE must include protocol (http:// or https://)")
        
        if not self.api_key:
            issues.append("VITALPBX_API_KEY is not set - this is required for authentication")
        elif len(self.api_key) != 32:
            warnings.append(f"API key length is {len(self.api_key)}, expected 32 characters")
        
        if not self.username or not self.password:
            warnings.append("VITALPBX_USERNAME/PASSWORD not set - only API key auth available")
        
        if self.timeout <= 0:
            issues.append("CALL_TIMEOUT must be greater than 0")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings,
            'config': {
                'api_base': self.api_base,
                'has_api_key': bool(self.api_key),
                'api_key_sample': f"***{self.api_key[-4:]}" if self.api_key else None,
                'has_basic_auth': bool(self.username and self.password),
                'tenant': self.tenant or 'default',
                'timeout': self.timeout
            }
        }