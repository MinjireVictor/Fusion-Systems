# phonebridge/management/commands/test_phonebridge.py

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.conf import settings
import json
import time

from phonebridge.services.zoho_service import ZohoService, ZohoLocationService, ZohoTokenManager
from phonebridge.services.vitalpbx_service import VitalPBXService
from phonebridge.services.phonebridge_service import PhoneBridgeService
from phonebridge.models import ZohoToken, ExtensionMapping

User = get_user_model()

class Command(BaseCommand):
    """
    Comprehensive testing command for PhoneBridge integration
    
    Usage:
        python manage.py test_phonebridge --all
        python manage.py test_phonebridge --oauth-flow
        python manage.py test_phonebridge --vitalpbx
        python manage.py test_phonebridge --phonebridge
        python manage.py test_phonebridge --user=user@example.com
    """
    
    help = 'Test PhoneBridge integration components'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Run all tests',
        )
        parser.add_argument(
            '--oauth-flow',
            action='store_true',
            help='Test OAuth flow and location handling',
        )
        parser.add_argument(
            '--vitalpbx',
            action='store_true',
            help='Test VitalPBX connectivity and API',
        )
        parser.add_argument(
            '--phonebridge',
            action='store_true',
            help='Test PhoneBridge popup functionality',
        )
        parser.add_argument(
            '--user',
            type=str,
            help='Test with specific user token',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )
    
    def handle(self, *args, **options):
        """Main test handler"""
        self.verbose = options.get('verbose', False)
        
        self.stdout.write(
            self.style.SUCCESS('🧪 PhoneBridge Integration Test Suite')
        )
        self.stdout.write('=' * 60)
        
        test_results = {
            'oauth_flow': None,
            'vitalpbx': None,
            'phonebridge': None,
            'user_specific': None
        }
        
        try:
            if options['all'] or options['oauth_flow']:
                test_results['oauth_flow'] = self.test_oauth_flow()
            
            if options['all'] or options['vitalpbx']:
                test_results['vitalpbx'] = self.test_vitalpbx()
            
            if options['all'] or options['phonebridge']:
                test_results['phonebridge'] = self.test_phonebridge_service()
            
            if options['user']:
                test_results['user_specific'] = self.test_user_token(options['user'])
            
            # Display summary
            self.display_test_summary(test_results)
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Test suite failed: {str(e)}')
            )
            raise CommandError(str(e))
    
    def test_oauth_flow(self):
        """Test OAuth flow and location handling"""
        self.stdout.write('\n🔐 Testing OAuth Flow and Location Handling')
        self.stdout.write('-' * 50)
        
        results = {
            'config_validation': None,
            'location_service': None,
            'auth_url_generation': None,
            'server_info': None,
            'overall_success': False
        }
        
        try:
            # Test 1: Configuration validation
            self.stdout.write('1️⃣ Validating OAuth configuration...')
            zoho_service = ZohoService()
            config_validation = zoho_service.validate_configuration()
            
            results['config_validation'] = config_validation
            
            if config_validation['valid']:
                self.stdout.write('   ✅ Configuration valid')
                if self.verbose:
                    self.stdout.write(f"   📋 Client ID: {config_validation['config']['client_id']}")
                    self.stdout.write(f"   📋 Scopes: {config_validation['config']['scopes']}")
                    self.stdout.write(f"   📋 Available locations: {', '.join(config_validation['config']['available_locations'])}")
            else:
                self.stdout.write('   ❌ Configuration invalid')
                for issue in config_validation['issues']:
                    self.stdout.write(f'      - {issue}')
                return results
            
            # Test 2: Location service
            self.stdout.write('2️⃣ Testing location service...')
            location_service = ZohoLocationService()
            server_info = location_service.get_server_info()
            
            results['server_info'] = server_info
            
            if server_info.get('success'):
                self.stdout.write('   ✅ Server info retrieved successfully')
                locations = server_info.get('locations', {})
                self.stdout.write(f"   📍 Available locations: {', '.join(locations.keys())}")
                
                if self.verbose:
                    for location, domain in locations.items():
                        self.stdout.write(f"      {location}: {domain}")
            else:
                self.stdout.write('   ⚠️  Server info failed - using fallback')
                self.stdout.write(f"   🔄 Fallback locations: {', '.join(location_service.LOCATION_MAPPING.keys())}")
            
            results['location_service'] = server_info.get('success', False)
            
            # Test 3: Auth URL generation
            self.stdout.write('3️⃣ Testing auth URL generation...')
            auth_url_data = zoho_service.get_auth_url()
            
            results['auth_url_generation'] = {
                'success': bool(auth_url_data.get('auth_url')),
                'has_state': bool(auth_url_data.get('state')),
                'scopes': auth_url_data.get('scopes')
            }
            
            if auth_url_data.get('auth_url'):
                self.stdout.write('   ✅ Auth URL generated successfully')
                self.stdout.write(f"   🔗 URL length: {len(auth_url_data['auth_url'])} characters")
                self.stdout.write(f"   🎯 State parameter: {auth_url_data['state'][:10]}...")
                
                if self.verbose:
                    self.stdout.write(f"   🔗 Full URL: {auth_url_data['auth_url']}")
            else:
                self.stdout.write('   ❌ Auth URL generation failed')
                return results
            
            # Test 4: Location domain resolution
            self.stdout.write('4️⃣ Testing location domain resolution...')
            test_locations = ['us', 'eu', 'in', 'au']
            
            for location in test_locations:
                domain = location_service.get_oauth_domain_for_location(location, server_info)
                self.stdout.write(f"   📍 {location.upper()}: {domain}")
            
            results['overall_success'] = True
            self.stdout.write('✅ OAuth flow tests completed successfully')
            
        except Exception as e:
            self.stdout.write(f'❌ OAuth flow test failed: {str(e)}')
            results['error'] = str(e)
        
        return results
    
    def test_vitalpbx(self):
        """Test VitalPBX connectivity and API"""
        self.stdout.write('\n📞 Testing VitalPBX Integration')
        self.stdout.write('-' * 50)
        
        results = {
            'config_validation': None,
            'connection_test': None,
            'api_discovery': None,
            'overall_success': False
        }
        
        try:
            # Test 1: Configuration validation
            self.stdout.write('1️⃣ Validating VitalPBX configuration...')
            vitalpbx_service = VitalPBXService()
            config_validation = vitalpbx_service.validate_configuration()
            
            results['config_validation'] = config_validation
            
            if config_validation['valid']:
                self.stdout.write('   ✅ Configuration valid')
                config = config_validation['config']
                self.stdout.write(f"   📋 API Base: {config['api_base']}")
                self.stdout.write(f"   🔑 Has API Key: {config['has_api_key']}")
                if config['api_key_sample']:
                    self.stdout.write(f"   🔑 API Key: {config['api_key_sample']}")
                self.stdout.write(f"   🏢 Tenant: {config['tenant']}")
                self.stdout.write(f"   ⏰ Timeout: {config['timeout']}s")
                
                if config_validation['warnings']:
                    self.stdout.write('   ⚠️  Warnings:')
                    for warning in config_validation['warnings']:
                        self.stdout.write(f'      - {warning}')
            else:
                self.stdout.write('   ❌ Configuration invalid')
                for issue in config_validation['issues']:
                    self.stdout.write(f'      - {issue}')
                return results
            
            # Test 2: Connection test
            self.stdout.write('2️⃣ Testing VitalPBX connection...')
            connection_result = vitalpbx_service.test_connection()
            
            results['connection_test'] = connection_result
            
            if connection_result.get('success'):
                self.stdout.write('   ✅ Connection successful')
                self.stdout.write(f"   🔗 Working endpoint: {connection_result.get('working_endpoint')}")
                self.stdout.write(f"   🔐 Auth method: {connection_result.get('auth_method')}")
                
                if self.verbose:
                    details = connection_result.get('details', {})
                    test_results = details.get('test_results', [])
                    for test_result in test_results:
                        if test_result.get('success'):
                            self.stdout.write(f"      ✅ {test_result['endpoint']} - {test_result['auth_method']}")
            else:
                self.stdout.write('   ❌ Connection failed')
                self.stdout.write(f"   💬 Message: {connection_result.get('message')}")
                
                if connection_result.get('auth_issue'):
                    self.stdout.write('   🔐 Authentication issue detected')
                    suggestions = connection_result.get('details', {}).get('suggestions', [])
                    for suggestion in suggestions:
                        self.stdout.write(f'      - {suggestion}')
            
            # Test 3: API discovery
            if connection_result.get('success'):
                self.stdout.write('3️⃣ Discovering API endpoints...')
                discovery_result = vitalpbx_service.discover_api_endpoints()
                
                results['api_discovery'] = discovery_result
                
                summary = discovery_result.get('summary', {})
                self.stdout.write(f"   📊 Total tested: {discovery_result.get('total_tested', 0)}")
                self.stdout.write(f"   ✅ Accessible: {discovery_result.get('accessible_endpoints', 0)}")
                self.stdout.write(f"   🟢 Working: {discovery_result.get('working_endpoints', 0)}")
                self.stdout.write(f"   🔐 Auth required: {discovery_result.get('auth_required_endpoints', 0)}")
                
                if self.verbose:
                    endpoints = discovery_result.get('endpoints', [])
                    for endpoint in endpoints[:10]:  # Show first 10
                        status = '✅' if endpoint['accessible'] else '❌'
                        self.stdout.write(f"      {status} {endpoint['endpoint']} ({endpoint.get('status_code', 'N/A')})")
            
            results['overall_success'] = connection_result.get('success', False)
            
            if results['overall_success']:
                self.stdout.write('✅ VitalPBX tests completed successfully')
            else:
                self.stdout.write('❌ VitalPBX tests failed')
                
        except Exception as e:
            self.stdout.write(f'❌ VitalPBX test failed: {str(e)}')
            results['error'] = str(e)
        
        return results
    
    def test_phonebridge_service(self):
        """Test PhoneBridge popup service"""
        self.stdout.write('\n🔔 Testing PhoneBridge Service')
        self.stdout.write('-' * 50)
        
        results = {
            'service_initialization': None,
            'popup_connectivity': None,
            'popup_statistics': None,
            'overall_success': False
        }
        
        try:
            # Test 1: Service initialization
            self.stdout.write('1️⃣ Initializing PhoneBridge service...')
            try:
                phonebridge_service = PhoneBridgeService()
                results['service_initialization'] = True
                self.stdout.write('   ✅ Service initialized successfully')
                self.stdout.write(f"   📡 API Base: {phonebridge_service.phonebridge_base}")
                self.stdout.write(f"   ⏰ Timeout: {phonebridge_service.popup_timeout}s")
                self.stdout.write(f"   🔄 Max retries: {phonebridge_service.max_retries}")
            except Exception as e:
                results['service_initialization'] = False
                self.stdout.write(f'   ❌ Service initialization failed: {str(e)}')
                return results
            
            # Test 2: Popup connectivity test
            self.stdout.write('2️⃣ Testing popup connectivity...')
            connectivity_test = phonebridge_service.test_popup_connectivity()
            
            results['popup_connectivity'] = connectivity_test
            
            if connectivity_test.get('api_accessible'):
                self.stdout.write('   ✅ PhoneBridge API accessible')
                self.stdout.write(f"   ⏱️  Response time: {connectivity_test.get('response_time_ms', 0)}ms")
                
                if connectivity_test.get('authentication_valid'):
                    self.stdout.write('   🔐 Authentication valid')
                else:
                    self.stdout.write('   ❌ Authentication failed')
                
                if connectivity_test.get('popup_endpoint_available'):
                    self.stdout.write('   🔔 Popup endpoint available')
                else:
                    self.stdout.write('   ⚠️  Popup endpoint may not be available')
            else:
                self.stdout.write('   ❌ PhoneBridge API not accessible')
                self.stdout.write(f"   💬 Error: {connectivity_test.get('error', 'Unknown error')}")
            
            # Test 3: Popup statistics
            self.stdout.write('3️⃣ Getting popup statistics...')
            stats = phonebridge_service.get_popup_statistics(24)  # Last 24 hours
            
            results['popup_statistics'] = stats
            
            if stats:
                self.stdout.write(f"   📊 Total popups (24h): {stats.get('total_popups', 0)}")
                self.stdout.write(f"   ✅ Successful: {stats.get('successful', 0)}")
                self.stdout.write(f"   ❌ Failed: {stats.get('failed', 0)}")
                self.stdout.write(f"   📈 Success rate: {stats.get('success_rate', 0):.1f}%")
                self.stdout.write(f"   ⏱️  Avg response time: {stats.get('average_response_time_ms', 0):.0f}ms")
            else:
                self.stdout.write('   📊 No popup statistics available')
            
            results['overall_success'] = connectivity_test.get('api_accessible', False)
            
            if results['overall_success']:
                self.stdout.write('✅ PhoneBridge service tests completed')
            else:
                self.stdout.write('❌ PhoneBridge service tests failed')
                
        except Exception as e:
            self.stdout.write(f'❌ PhoneBridge service test failed: {str(e)}')
            results['error'] = str(e)
        
        return results
    
    def test_user_token(self, user_email):
        """Test specific user's token"""
        self.stdout.write(f'\n👤 Testing User Token: {user_email}')
        self.stdout.write('-' * 50)
        
        results = {
            'user_exists': False,
            'token_exists': False,
            'token_valid': False,
            'migration_status': None,
            'api_test': None,
            'overall_success': False
        }
        
        try:
            # Test 1: Check if user exists
            try:
                user = User.objects.get(email=user_email)
                results['user_exists'] = True
                self.stdout.write(f'   👤 User found: {user.email}')
            except User.DoesNotExist:
                self.stdout.write(f'   ❌ User not found: {user_email}')
                return results
            
            # Test 2: Check if token exists
            try:
                zoho_token = ZohoToken.objects.get(user=user)
                results['token_exists'] = True
                self.stdout.write('   🔑 Token found')
                self.stdout.write(f'      📅 Created: {zoho_token.created_at.strftime("%Y-%m-%d %H:%M")}')
                self.stdout.write(f'      ⏰ Expires: {zoho_token.expires_at.strftime("%Y-%m-%d %H:%M")}')
                self.stdout.write(f'      🌍 Location: {zoho_token.location or "Not set"}')
                self.stdout.write(f'      📋 OAuth Version: {zoho_token.oauth_version}')
                self.stdout.write(f'      🔔 PhoneBridge: {"Enabled" if zoho_token.is_phonebridge_enabled() else "Disabled"}')
            except ZohoToken.DoesNotExist:
                self.stdout.write('   ❌ No token found for user')
                self.stdout.write('   🔗 User needs to authorize at /phonebridge/zoho/connect/')
                return results
            
            # Test 3: Check token validity and refresh if needed
            zoho_service = ZohoService()
            token_manager = ZohoTokenManager(zoho_service)
            
            if zoho_token.is_expired():
                self.stdout.write('   ⏰ Token expired - attempting refresh...')
                refresh_success = token_manager.refresh_token_if_needed(zoho_token)
                if refresh_success:
                    self.stdout.write('   ✅ Token refreshed successfully')
                    results['token_valid'] = True
                else:
                    self.stdout.write('   ❌ Token refresh failed')
                    return results
            else:
                self.stdout.write('   ✅ Token is valid')
                results['token_valid'] = True
            
            # Test 4: Check migration status
            migration_info = token_manager.validate_token_migration_needed(zoho_token)
            results['migration_status'] = migration_info
            
            if migration_info['needs_migration']:
                self.stdout.write('   🔄 Token needs migration')
                self.stdout.write('   📋 Issues:')
                for issue in migration_info['issues']:
                    self.stdout.write(f'      - {issue}')
            else:
                self.stdout.write('   ✅ Token is up-to-date (OAuth v3)')
            
            # Test 5: API functionality test
            self.stdout.write('   🧪 Testing API functionality...')
            api_test = zoho_service.test_connection(
                zoho_token.access_token,
                zoho_token.api_domain
            )
            
            results['api_test'] = api_test
            
            if api_test.get('success'):
                self.stdout.write('   ✅ API test successful')
                
                # Test PhoneBridge scopes
                scope_test = zoho_service.validate_phonebridge_scopes(
                    zoho_token.access_token,
                    zoho_token.api_domain
                )
                
                if scope_test.get('valid'):
                    self.stdout.write('   🔔 PhoneBridge scopes valid')
                    self.stdout.write(f'      📊 Available scopes: {scope_test.get("available_scopes", 0)}/{scope_test.get("total_scopes", 0)}')
                else:
                    self.stdout.write('   ⚠️  PhoneBridge scopes limited')
                    for recommendation in scope_test.get('recommendations', []):
                        self.stdout.write(f'      - {recommendation}')
            else:
                self.stdout.write('   ❌ API test failed')
                self.stdout.write(f'   💬 Message: {api_test.get("message", "Unknown error")}')
            
            results['overall_success'] = api_test.get('success', False) and results['token_valid']
            
            if results['overall_success']:
                self.stdout.write('✅ User token tests completed successfully')
            else:
                self.stdout.write('❌ User token tests failed')
                
        except Exception as e:
            self.stdout.write(f'❌ User token test failed: {str(e)}')
            results['error'] = str(e)
        
        return results
    
    def display_test_summary(self, test_results):
        """Display comprehensive test summary"""
        self.stdout.write('\n📊 TEST SUMMARY')
        self.stdout.write('=' * 60)
        
        total_tests = 0
        passed_tests = 0
        
        for test_name, result in test_results.items():
            if result is None:
                continue
            
            total_tests += 1
            success = result.get('overall_success', False) if isinstance(result, dict) else bool(result)
            
            if success:
                passed_tests += 1
                status_emoji = '✅'
                status_text = 'PASSED'
            else:
                status_emoji = '❌'
                status_text = 'FAILED'
            
            test_display_name = test_name.replace('_', ' ').title()
            self.stdout.write(f'{status_emoji} {test_display_name}: {status_text}')
        
        # Calculate success rate
        if total_tests > 0:
            success_rate = (passed_tests / total_tests) * 100
            self.stdout.write(f'\n📈 Overall Success Rate: {success_rate:.1f}% ({passed_tests}/{total_tests})')
            
            if success_rate == 100:
                self.stdout.write(
                    self.style.SUCCESS('🎉 All tests passed! PhoneBridge is ready to use.')
                )
            elif success_rate >= 75:
                self.stdout.write(
                    self.style.WARNING('⚠️  Most tests passed, but some issues need attention.')
                )
            else:
                self.stdout.write(
                    self.style.ERROR('❌ Multiple tests failed. Please review configuration.')
                )
        else:
            self.stdout.write('ℹ️  No tests were executed')
        
        # Recommendations
        self.stdout.write('\n🎯 RECOMMENDATIONS')
        self.stdout.write('-' * 30)
        
        recommendations = []
        
        # OAuth flow recommendations
        oauth_result = test_results.get('oauth_flow')
        if oauth_result and not oauth_result.get('overall_success'):
            recommendations.append('Fix OAuth configuration issues before proceeding')
        
        # VitalPBX recommendations
        vitalpbx_result = test_results.get('vitalpbx')
        if vitalpbx_result and not vitalpbx_result.get('overall_success'):
            recommendations.append('Verify VitalPBX API key and network connectivity')
        
        # PhoneBridge recommendations
        phonebridge_result = test_results.get('phonebridge')
        if phonebridge_result and not phonebridge_result.get('overall_success'):
            recommendations.append('Check Zoho PhoneBridge API access and permissions')
        
        # User specific recommendations
        user_result = test_results.get('user_specific')
        if user_result and not user_result.get('overall_success'):
            recommendations.append('User token needs refresh or re-authorization')
        
        if not recommendations:
            recommendations.append('All systems appear to be functioning correctly')
        
        for i, recommendation in enumerate(recommendations, 1):
            self.stdout.write(f'{i}. {recommendation}')
        
        # Next steps
        self.stdout.write('\n🚀 NEXT STEPS')
        self.stdout.write('-' * 30)
        
        if passed_tests == total_tests:
            next_steps = [
                'Configure extension mappings for your users',
                'Test click-to-call functionality from Zoho CRM',
                'Set up VitalPBX webhooks for call events',
                'Monitor popup logs and call statistics'
            ]
        else:
            next_steps = [
                'Review failed test results and fix configuration issues',
                'Run migration command if OAuth issues detected',
                'Test individual components with specific flags',
                'Check logs for detailed error information'
            ]
        
        for i, step in enumerate(next_steps, 1):
            self.stdout.write(f'{i}. {step}')
        
        self.stdout.write(f'\n📅 Test completed at: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}')


class PhoneBridgeHealthCheck:
    """Health check utility for PhoneBridge system"""
    
    @staticmethod
    def run_health_check():
        """Run comprehensive health check"""
        health_status = {
            'timestamp': timezone.now().isoformat(),
            'overall_health': 'unknown',
            'components': {},
            'recommendations': []
        }
        
        # Check database
        try:
            token_count = ZohoToken.objects.count()
            extension_count = ExtensionMapping.objects.count()
            
            health_status['components']['database'] = {
                'status': 'healthy',
                'tokens': token_count,
                'extensions': extension_count
            }
        except Exception as e:
            health_status['components']['database'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
        
        # Check configuration
        try:
            zoho_service = ZohoService()
            config_validation = zoho_service.validate_configuration()
            
            health_status['components']['configuration'] = {
                'status': 'healthy' if config_validation['valid'] else 'unhealthy',
                'issues': config_validation.get('issues', []),
                'warnings': config_validation.get('warnings', [])
            }
        except Exception as e:
            health_status['components']['configuration'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
        
        # Check external services
        try:
            location_service = ZohoLocationService()
            server_info = location_service.get_server_info(timeout=5)
            
            health_status['components']['external_services'] = {
                'zoho_server_info': 'healthy' if server_info.get('success') else 'degraded'
            }
        except Exception as e:
            health_status['components']['external_services'] = {
                'zoho_server_info': 'unhealthy',
                'error': str(e)
            }
        
        # Determine overall health
        component_statuses = [comp.get('status', 'unhealthy') for comp in health_status['components'].values()]
        
        if all(status == 'healthy' for status in component_statuses):
            health_status['overall_health'] = 'healthy'
        elif any(status == 'unhealthy' for status in component_statuses):
            health_status['overall_health'] = 'unhealthy'
        else:
            health_status['overall_health'] = 'degraded'
        
        return health_status