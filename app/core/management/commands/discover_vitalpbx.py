# phonebridge/management/commands/discover_vitalpbx.py
"""
Django management command to discover VitalPBX API configuration
Usage: python manage.py discover_vitalpbx
"""

from django.core.management.base import BaseCommand
from django.conf import settings
import requests
import json
import warnings
from datetime import datetime

# Suppress SSL warnings
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

class Command(BaseCommand):
    help = 'Discover VitalPBX API authentication and endpoints'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--save-config',
            action='store_true',
            help='Save working configuration to environment variables',
        )
        parser.add_argument(
            '--test-calls',
            action='store_true',
            help='Test call origination endpoints (safe test)',
        )
        parser.add_argument(
            '--output',
            type=str,
            help='Output file for results (JSON format)',
        )
    
    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting VitalPBX API Discovery...')
        )
        
        # Get configuration from Django settings
        try:
            config = settings.PHONEBRIDGE_SETTINGS
            api_base = config['VITALPBX_API_BASE']
            username = config['VITALPBX_USERNAME']
            password = config['VITALPBX_PASSWORD']
            timeout = config.get('CALL_TIMEOUT_SECONDS', 30)
        except KeyError as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Missing configuration: {e}')
            )
            return
        
        self.stdout.write(f"📍 Target: {api_base}")
        self.stdout.write(f"👤 Username: {username}")
        self.stdout.write("=" * 60)
        
        # Run discovery
        discovery = VitalPBXDiscoveryDjango(
            api_base, username, password, timeout, self.stdout, self.style
        )
        
        results = discovery.run_discovery(
            test_calls=options['test_calls']
        )
        
        # Save results if requested
        if options['output']:
            try:
                with open(options['output'], 'w') as f:
                    json.dump(results, f, indent=2)
                self.stdout.write(
                    self.style.SUCCESS(f'💾 Results saved to: {options["output"]}')
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Failed to save results: {e}')
                )
        
        # Generate Django configuration if working method found
        if options['save_config'] and results['working_methods']:
            self.generate_django_config(results)
    
    def generate_django_config(self, results):
        """Generate Django service configuration based on discovery"""
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(
            self.style.SUCCESS('🔧 DJANGO CONFIGURATION RECOMMENDATIONS')
        )
        self.stdout.write("=" * 60)
        
        working_method = results['working_methods'][0]
        auth_config = results['discovery_results'][working_method]
        
        self.stdout.write(f"Recommended authentication: {working_method}")
        
        if working_method == 'basic_auth':
            self.stdout.write("\n📝 Your current Django service should work!")
            self.stdout.write("The basic authentication is working correctly.")
            
        elif 'api_key' in working_method:
            headers = auth_config.get('headers_used', {})
            self.stdout.write(f"\n📝 Update Django service to use API key headers:")
            self.stdout.write(f"Headers needed: {headers}")
            
        # Recommend working endpoints
        if 'api_structure' in results:
            working_endpoints = [
                ep for ep, data in results['api_structure'].items() 
                if data.get('accessible')
            ]
            
            self.stdout.write(f"\n📋 Working endpoints: {working_endpoints}")
            
            # Specific recommendations
            if 'calls' in working_endpoints:
                self.stdout.write("✅ Use '/calls' for call operations")
            if 'originate' in working_endpoints:
                self.stdout.write("✅ Use '/originate' for call origination")
            if 'extensions' in working_endpoints:
                self.stdout.write("✅ Use '/extensions' for extension management")


class VitalPBXDiscoveryDjango:
    """Django-integrated VitalPBX discovery"""
    
    def __init__(self, api_base, username, password, timeout, stdout, style):
        self.api_base = api_base.rstrip('/')
        self.username = username
        self.password = password
        self.timeout = timeout
        self.stdout = stdout
        self.style = style
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'api_base': api_base,
            'username': username,
            'discovery_results': {},
            'working_methods': [],
            'recommendations': []
        }
    
    def run_discovery(self, test_calls=False):
        """Run the discovery process"""
        # Test authentication methods
        self._test_authentication_methods()
        
        # Test API structure if auth works
        if self.results['working_methods']:
            self._discover_api_structure()
            
            if test_calls:
                self._test_call_origination()
        
        # Generate recommendations
        self._generate_recommendations()
        
        return self.results
    
    def _test_authentication_methods(self):
        """Test different authentication methods"""
        self.stdout.write("\n🔐 Testing Authentication Methods...")
        self.stdout.write("-" * 40)
        
        auth_methods = {
            'basic_auth': self._test_basic_auth,
            'api_key_bearer': self._test_api_key_bearer,
            'api_key_header': self._test_api_key_header,
        }
        
        for method_name, test_func in auth_methods.items():
            self.stdout.write(f"🧪 Testing {method_name}...")
            
            try:
                result = test_func()
                self.results['discovery_results'][method_name] = result
                
                if result.get('success'):
                    self.stdout.write(
                        self.style.SUCCESS(f"   ✅ {method_name}: WORKING")
                    )
                    self.results['working_methods'].append(method_name)
                else:
                    self.stdout.write(
                        self.style.WARNING(f"   ❌ {method_name}: {result.get('error', 'Failed')}")
                    )
                    
            except Exception as e:
                error_result = {'success': False, 'error': str(e)}
                self.results['discovery_results'][method_name] = error_result
                self.stdout.write(
                    self.style.ERROR(f"   💥 {method_name}: Exception - {str(e)}")
                )
    
    def _test_basic_auth(self):
        """Test HTTP Basic Authentication (current method)"""
        test_endpoints = ['status', 'calls', 'extensions', 'health', '']
        
        for endpoint in test_endpoints:
            try:
                url = f"{self.api_base}/{endpoint}" if endpoint else self.api_base
                
                response = requests.get(
                    url,
                    auth=(self.username, self.password),
                    headers={'Accept': 'application/json'},
                    timeout=self.timeout,
                    verify=False
                )
                
                if response.status_code in [200, 201, 202]:
                    return {
                        'success': True,
                        'method': 'basic_auth',
                        'endpoint': endpoint,
                        'status_code': response.status_code,
                        'response': self._safe_json_parse(response)
                    }
                    
            except Exception:
                continue
        
        return {
            'success': False,
            'error': 'Basic auth failed on all test endpoints'
        }
    
    def _test_api_key_bearer(self):
        """Test Bearer token authentication"""
        api_key = self.password  # Try password as API key
        
        test_endpoints = ['status', 'calls', 'extensions']
        
        for endpoint in test_endpoints:
            try:
                url = f"{self.api_base}/{endpoint}"
                
                response = requests.get(
                    url,
                    headers={
                        'Authorization': f'Bearer {api_key}',
                        'Accept': 'application/json'
                    },
                    timeout=self.timeout,
                    verify=False
                )
                
                if response.status_code in [200, 201, 202]:
                    return {
                        'success': True,
                        'method': 'api_key_bearer',
                        'endpoint': endpoint,
                        'status_code': response.status_code,
                        'headers_used': {'Authorization': f'Bearer {api_key}'}
                    }
                    
            except Exception:
                continue
        
        return {
            'success': False,
            'error': 'Bearer token auth failed'
        }
    
    def _test_api_key_header(self):
        """Test API key in custom headers"""
        api_key = self.password
        
        header_variations = [
            {'X-API-Key': api_key},
            {'API-Key': api_key},
            {'X-Auth-Token': api_key}
        ]
        
        test_endpoints = ['status', 'calls']
        
        for headers in header_variations:
            for endpoint in test_endpoints:
                try:
                    url = f"{self.api_base}/{endpoint}"
                    
                    response = requests.get(
                        url,
                        headers={**headers, 'Accept': 'application/json'},
                        timeout=self.timeout,
                        verify=False
                    )
                    
                    if response.status_code in [200, 201, 202]:
                        return {
                            'success': True,
                            'method': 'api_key_header',
                            'endpoint': endpoint,
                            'status_code': response.status_code,
                            'headers_used': headers
                        }
                        
                except Exception:
                    continue
        
        return {
            'success': False,
            'error': 'API key headers failed'
        }
    
    def _discover_api_structure(self):
        """Discover available API endpoints"""
        self.stdout.write("\n🗂️  Discovering API Structure...")
        self.stdout.write("-" * 40)
        
        working_method = self.results['working_methods'][0]
        
        endpoints_to_test = [
            'status', 'health', 'calls', 'originate', 
            'extensions', 'channels', 'system'
        ]
        
        structure_results = {}
        
        for endpoint in endpoints_to_test:
            result = self._test_endpoint_with_auth(endpoint, working_method)
            if result:
                structure_results[endpoint] = result
                status = "✅" if result.get('accessible') else "❌"
                self.stdout.write(f"   {status} /{endpoint}: {result.get('status_code', 'N/A')}")
        
        self.results['api_structure'] = structure_results
    
    def _test_endpoint_with_auth(self, endpoint, auth_method):
        """Test endpoint with discovered authentication"""
        try:
            url = f"{self.api_base}/{endpoint}"
            auth_config = self.results['discovery_results'][auth_method]
            
            if auth_method == 'basic_auth':
                response = requests.get(
                    url,
                    auth=(self.username, self.password),
                    headers={'Accept': 'application/json'},
                    timeout=10,
                    verify=False
                )
            else:
                headers = auth_config.get('headers_used', {})
                response = requests.get(
                    url,
                    headers={**headers, 'Accept': 'application/json'},
                    timeout=10,
                    verify=False
                )
            
            return {
                'accessible': response.status_code in [200, 201, 202],
                'status_code': response.status_code,
                'content_type': response.headers.get('Content-Type', ''),
                'response_size': len(response.content)
            }
            
        except Exception as e:
            return {
                'accessible': False,
                'error': str(e)
            }
    
    def _test_call_origination(self):
        """Test call origination endpoints (safe test)"""
        self.stdout.write("\n📞 Testing Call Origination Endpoints...")
        self.stdout.write("-" * 40)
        self.stdout.write("⚠️  Using safe test payload (won't make actual calls)")
        
        # Safe test payload that shouldn't actually originate a call
        test_payload = {
            'Channel': 'PJSIP/test',
            'Context': 'test-context',
            'Exten': 'test',
            'Priority': 1,
            'Timeout': 1000,
            'CallerID': 'test',
            'Async': True,
            'ActionID': 'discovery_test'
        }
        
        originate_endpoints = ['calls', 'originate', 'ami/originate']
        working_method = self.results['working_methods'][0]
        
        for endpoint in originate_endpoints:
            result = self._test_safe_originate(endpoint, test_payload, working_method)
            
            if result.get('endpoint_exists'):
                self.stdout.write(
                    self.style.SUCCESS(f"   ✅ /{endpoint}: Endpoint accessible")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"   ❌ /{endpoint}: {result.get('error', 'Failed')}")
                )
    
    def _test_safe_originate(self, endpoint, payload, auth_method):
        """Safely test originate endpoint without making actual calls"""
        try:
            url = f"{self.api_base}/{endpoint}"
            auth_config = self.results['discovery_results'][auth_method]
            
            if auth_method == 'basic_auth':
                response = requests.post(
                    url,
                    json=payload,
                    auth=(self.username, self.password),
                    headers={'Content-Type': 'application/json'},
                    timeout=5,
                    verify=False
                )
            else:
                headers = auth_config.get('headers_used', {})
                response = requests.post(
                    url,
                    json=payload,
                    headers={**headers, 'Content-Type': 'application/json'},
                    timeout=5,
                    verify=False
                )
            
            # Any response (even error) means endpoint exists
            return {
                'endpoint_exists': True,
                'status_code': response.status_code,
                'response': response.text[:100]
            }
            
        except Exception as e:
            return {
                'endpoint_exists': False,
                'error': str(e)
            }
    
    def _generate_recommendations(self):
        """Generate recommendations"""
        self.stdout.write("\n💡 Recommendations...")
        self.stdout.write("-" * 40)
        
        if self.results['working_methods']:
            working_method = self.results['working_methods'][0]
            self.stdout.write(
                self.style.SUCCESS(f"✅ Use {working_method} authentication")
            )
            
            if working_method == 'basic_auth':
                self.stdout.write("📝 Your current Django service should work!")
                self.stdout.write("   The HTTP Basic Authentication is working correctly.")
                self.stdout.write("   Check for other issues like endpoint paths or payload format.")
            else:
                auth_config = self.results['discovery_results'][working_method]
                headers = auth_config.get('headers_used', {})
                self.stdout.write(f"📝 Update Django service to use: {headers}")
        else:
            self.stdout.write(
                self.style.ERROR("❌ No working authentication methods found")
            )
            self.stdout.write("🔍 Check VitalPBX API module installation")
            self.stdout.write("🔐 Verify user has API permissions")
    
    def _safe_json_parse(self, response):
        """Safely parse JSON response"""
        try:
            return response.json()
        except:
            return {'raw_response': response.text[:200]}