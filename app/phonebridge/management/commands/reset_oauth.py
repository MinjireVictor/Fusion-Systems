# phonebridge/management/commands/reset_oauth.py

import json
import logging
import os
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
from django.conf import settings

from phonebridge.models import (
    ZohoToken, ExtensionMapping, CallLog, OAuthMigrationLog, 
    PopupLog, ZohoWebhookLog, VitalPBXWebhookLog
)
from phonebridge.services.zoho_service import ZohoService, ZohoTokenManager
from phonebridge.services.vitalpbx_service import VitalPBXService

User = get_user_model()
logger = logging.getLogger('phonebridge')

class Command(BaseCommand):
    """
    Clean slate OAuth reset and testing command for new server setup
    
    Usage:
        python manage.py reset_oauth --clean-slate    # Remove all OAuth data
        python manage.py reset_oauth --test-config    # Test configuration only
        python manage.py reset_oauth --test-oauth     # Test OAuth flow
        python manage.py reset_oauth --status         # Show current status
        python manage.py reset_oauth --test-vitalpbx  # Test VitalPBX connectivity
        python manage.py reset_oauth --create-test-user email@example.com
    """
    
    help = 'Reset OAuth configuration for new server deployment with simple redirect URI'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--clean-slate',
            action='store_true',
            help='Remove all OAuth tokens and related data',
        )
        parser.add_argument(
            '--test-config',
            action='store_true',
            help='Test OAuth configuration without making changes',
        )
        parser.add_argument(
            '--test-oauth',
            action='store_true',
            help='Test OAuth flow with new configuration',
        )
        parser.add_argument(
            '--status',
            action='store_true',
            help='Show current OAuth status',
        )
        parser.add_argument(
            '--test-vitalpbx',
            action='store_true',
            help='Test VitalPBX connectivity',
        )
        parser.add_argument(
            '--create-test-user',
            type=str,
            help='Create test user with email',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompts',
        )
    
    def handle(self, *args, **options):
        """Main command handler"""
        self.stdout.write(
            self.style.SUCCESS('🚀 PhoneBridge OAuth Reset & Test Tool')
        )
        self.stdout.write('=' * 60)
        self.stdout.write(f'🖥️ Server: zoho.fusionsystems.co.ke:8000')
        self.stdout.write(f'🔗 Simple Redirect: http://zoho.fusionsystems.co.ke:8000')
        self.stdout.write('=' * 60)
        
        try:
            if options['status']:
                self.show_status()
            elif options['clean_slate']:
                self.clean_slate_reset(options['force'])
            elif options['test_config']:
                self.test_configuration()
            elif options['test_oauth']:
                self.test_oauth_flow()
            elif options['test_vitalpbx']:
                self.test_vitalpbx()
            elif options['create_test_user']:
                self.create_test_user(options['create_test_user'])
            else:
                self.show_help()
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Command failed: {str(e)}')
            )
            raise CommandError(str(e))
    
    def show_status(self):
        """Show current OAuth and system status"""
        self.stdout.write('\n📊 CURRENT STATUS')
        self.stdout.write('-' * 30)
        
        # Database counts
        token_count = ZohoToken.objects.count()
        extension_count = ExtensionMapping.objects.count()
        call_count = CallLog.objects.count()
        user_count = User.objects.count()
        
        self.stdout.write(f'👥 Users: {user_count}')
        self.stdout.write(f'🔑 OAuth Tokens: {token_count}')
        self.stdout.write(f'📞 Extension Mappings: {extension_count}')
        self.stdout.write(f'📋 Call Logs: {call_count}')
        
        # Configuration status
        self.stdout.write('\n⚙️ CONFIGURATION')
        self.stdout.write('-' * 20)
        
        phonebridge_settings = settings.PHONEBRIDGE_SETTINGS
        client_id = phonebridge_settings.get("ZOHO_CLIENT_ID", "NOT SET")
        redirect_uri = phonebridge_settings.get("ZOHO_REDIRECT_URI", "NOT SET")
        
        self.stdout.write(f'Client ID: {client_id[:20]}...' if client_id != "NOT SET" else 'Client ID: NOT SET')
        self.stdout.write(f'Redirect URI: {redirect_uri}')
        self.stdout.write(f'Scopes: {phonebridge_settings.get("ZOHO_SCOPES", "NOT SET")}')
        self.stdout.write(f'Debug Mode: {settings.DEBUG}')
        
        # Check if redirect URI is correct
        expected_redirect = 'http://zoho.fusionsystems.co.ke:8000'
        if redirect_uri == expected_redirect:
            self.stdout.write('✅ Redirect URI correctly configured for simple redirect')
        else:
            self.stdout.write(f'⚠️  Expected redirect URI: {expected_redirect}')
        
        # Recent activity
        if token_count > 0:
            self.stdout.write('\n🔄 RECENT TOKENS')
            self.stdout.write('-' * 20)
            
            recent_tokens = ZohoToken.objects.select_related('user').order_by('-created_at')[:5]
            for token in recent_tokens:
                status = '✅ Valid' if not token.is_expired() else '⏰ Expired'
                location = token.location or 'Unknown'
                oauth_version = token.oauth_version or 'v2'
                self.stdout.write(f'{status} {token.user.email} - {location} ({oauth_version}) - {token.created_at.strftime("%Y-%m-%d %H:%M")}')
        
        # Extension mappings
        if extension_count > 0:
            self.stdout.write('\n📞 EXTENSION MAPPINGS')
            self.stdout.write('-' * 25)
            
            extensions = ExtensionMapping.objects.select_related('user').filter(is_active=True)[:5]
            for ext in extensions:
                zoho_status = '✅ Set' if ext.zoho_user_id else '❌ Missing'
                self.stdout.write(f'📱 {ext.extension} -> {ext.user.email} ({zoho_status})')
    
    def clean_slate_reset(self, force=False):
        """Remove all OAuth data for fresh start"""
        self.stdout.write('\n🧹 CLEAN SLATE RESET')
        self.stdout.write('-' * 25)
        
        # Show what will be deleted
        counts = {
            'OAuth tokens': ZohoToken.objects.count(),
            'Extension mappings': ExtensionMapping.objects.count(),
            'Call logs': CallLog.objects.count(),
            'Migration logs': OAuthMigrationLog.objects.count(),
            'Popup logs': PopupLog.objects.count(),
            'Zoho webhook logs': ZohoWebhookLog.objects.count(),
            'VitalPBX webhook logs': VitalPBXWebhookLog.objects.count(),
        }
        
        self.stdout.write('📋 Data to be deleted:')
        for item, count in counts.items():
            if count > 0:
                self.stdout.write(f'  • {item}: {count}')
        
        total_records = sum(counts.values())
        
        if total_records == 0:
            self.stdout.write('✅ Database is already clean!')
            return
        
        if not force:
            self.stdout.write(f'\n⚠️  This will delete {total_records} records for fresh OAuth setup.')
            self.stdout.write('This is safe since you have no production users yet.')
            confirm = input('Continue? (yes/no): ')
            if confirm.lower() != 'yes':
                self.stdout.write('❌ Reset cancelled')
                return
        
        # Perform clean slate reset
        try:
            with transaction.atomic():
                deleted_counts = {}
                
                # Delete in order to avoid foreign key issues
                deleted_counts['popup_logs'] = PopupLog.objects.all().delete()[0]
                deleted_counts['call_logs'] = CallLog.objects.all().delete()[0]
                deleted_counts['extension_mappings'] = ExtensionMapping.objects.all().delete()[0]
                deleted_counts['oauth_tokens'] = ZohoToken.objects.all().delete()[0]
                deleted_counts['migration_logs'] = OAuthMigrationLog.objects.all().delete()[0]
                deleted_counts['zoho_webhooks'] = ZohoWebhookLog.objects.all().delete()[0]
                deleted_counts['vitalpbx_webhooks'] = VitalPBXWebhookLog.objects.all().delete()[0]
                
                self.stdout.write('\n✅ Clean slate reset completed!')
                self.stdout.write('📊 Deleted records:')
                for item, count in deleted_counts.items():
                    if count > 0:
                        self.stdout.write(f'  • {item}: {count}')
                
                self.stdout.write('\n🔄 Next steps:')
                self.stdout.write('1. Test configuration: python manage.py reset_oauth --test-config')
                self.stdout.write('2. Test OAuth flow: python manage.py reset_oauth --test-oauth')
                self.stdout.write('3. Visit: http://zoho.fusionsystems.co.ke:8000/phonebridge/zoho/connect/')
                self.stdout.write('4. ✅ Simple redirect URI: http://zoho.fusionsystems.co.ke:8000')
                
        except Exception as e:
            self.stdout.write(f'❌ Reset failed: {str(e)}')
            raise
    
    def test_configuration(self):
        """Test OAuth configuration"""
        self.stdout.write('\n🔧 TESTING CONFIGURATION')
        self.stdout.write('-' * 30)
        
        try:
            # Test 1: Basic configuration validation
            self.stdout.write('1️⃣ Validating OAuth configuration...')
            zoho_service = ZohoService()
            validation = zoho_service.validate_configuration()
            
            if validation['valid']:
                self.stdout.write('   ✅ Configuration valid')
                
                config = validation['config']
                self.stdout.write('\n📋 Configuration Details:')
                self.stdout.write(f'   • Client ID: {config["client_id"]}')
                self.stdout.write(f'   • Redirect URI: {config["redirect_uri"]}')
                self.stdout.write(f'   • Scopes: {config["scopes"]}')
                self.stdout.write(f'   • Server info accessible: {config["server_info_accessible"]}')
                self.stdout.write(f'   • Available locations: {", ".join(config["available_locations"])}')
                self.stdout.write(f'   • HTTP mode: {config.get("http_mode", "Not specified")}')
                
                # Check redirect URI specifically
                expected_redirect = 'http://zoho.fusionsystems.co.ke:8000'
                actual_redirect = config["redirect_uri"]
                
                if actual_redirect == expected_redirect:
                    self.stdout.write('\n✅ Simple redirect URI correctly configured!')
                else:
                    self.stdout.write(f'\n⚠️  Redirect URI mismatch:')
                    self.stdout.write(f'   Expected: {expected_redirect}')
                    self.stdout.write(f'   Actual: {actual_redirect}')
                
                if validation['warnings']:
                    self.stdout.write('\n⚠️  Warnings:')
                    for warning in validation['warnings']:
                        self.stdout.write(f'   • {warning}')
                
            else:
                self.stdout.write('   ❌ Configuration invalid')
                self.stdout.write('\n🚨 Issues:')
                for issue in validation['issues']:
                    self.stdout.write(f'   • {issue}')
                
                if validation['warnings']:
                    self.stdout.write('\n⚠️  Warnings:')
                    for warning in validation['warnings']:
                        self.stdout.write(f'   • {warning}')
                
                return
            
            # Test 2: Environment variables
            self.stdout.write('\n2️⃣ Checking environment variables...')
            required_vars = {
                'ZOHO_CLIENT_ID': os.environ.get('ZOHO_CLIENT_ID'),
                'ZOHO_CLIENT_SECRET': os.environ.get('ZOHO_CLIENT_SECRET'),
                'ZOHO_REDIRECT_URI': os.environ.get('ZOHO_REDIRECT_URI'),
                'VITALPBX_API_BASE': os.environ.get('VITALPBX_API_BASE'),
                'VITALPBX_API_KEY': os.environ.get('VITALPBX_API_KEY'),
            }
            
            all_set = True
            for var, value in required_vars.items():
                if value:
                    if 'SECRET' in var or 'KEY' in var:
                        display_value = f"***{value[-4:]}" if len(value) > 4 else "***"
                    else:
                        display_value = value
                    self.stdout.write(f'   ✅ {var}: {display_value}')
                else:
                    self.stdout.write(f'   ❌ {var}: NOT SET')
                    all_set = False
            
            if all_set:
                self.stdout.write('   ✅ All required environment variables set')
            else:
                self.stdout.write('   ⚠️  Some environment variables missing')
            
        except Exception as e:
            self.stdout.write(f'❌ Configuration test failed: {str(e)}')
    
    def test_oauth_flow(self):
        """Test OAuth flow without browser"""
        self.stdout.write('\n🔐 TESTING OAUTH FLOW')
        self.stdout.write('-' * 25)
        
        try:
            zoho_service = ZohoService()
            
            # Test 1: Generate auth URL
            self.stdout.write('1️⃣ Testing auth URL generation...')
            auth_data = zoho_service.get_auth_url()
            
            if auth_data.get('auth_url'):
                self.stdout.write('   ✅ Auth URL generated successfully')
                self.stdout.write(f'   📋 State: {auth_data["state"][:10]}...')
                self.stdout.write(f'   🎯 Scopes: {auth_data["scopes"]}')
                self.stdout.write(f'   🔗 Simple redirect: http://zoho.fusionsystems.co.ke:8000')
                
                # Display the URL for manual testing
                self.stdout.write('\n🔗 OAuth Authorization URL:')
                self.stdout.write('=' * 60)
                self.stdout.write(auth_data['auth_url'])
                self.stdout.write('=' * 60)
                
                self.stdout.write('\n📝 Manual Testing Steps:')
                self.stdout.write('1. Copy the URL above')
                self.stdout.write('2. Open it in your browser')
                self.stdout.write('3. Log in to Zoho and authorize')
                self.stdout.write('4. ✅ Will redirect to: http://zoho.fusionsystems.co.ke:8000')
                self.stdout.write('5. System handles OAuth at root level automatically')
                
            else:
                self.stdout.write('   ❌ Auth URL generation failed')
                return
            
            # Test 2: Server info connectivity
            self.stdout.write('\n2️⃣ Testing Zoho server info...')
            from phonebridge.services.zoho_service import ZohoLocationService
            location_service = ZohoLocationService()
            server_info = location_service.get_server_info()
            
            if server_info.get('success'):
                self.stdout.write('   ✅ Server info retrieved successfully')
                locations = server_info.get('locations', {})
                self.stdout.write(f'   🌍 Available locations: {", ".join(locations.keys())}')
            else:
                self.stdout.write('   ⚠️  Server info failed - will use fallback')
                self.stdout.write(f'   🔄 Fallback locations: {", ".join(location_service.LOCATION_MAPPING.keys())}')
            
        except Exception as e:
            self.stdout.write(f'❌ OAuth flow test failed: {str(e)}')
    
    def test_vitalpbx(self):
        """Test VitalPBX connectivity"""
        self.stdout.write('\n📞 TESTING VITALPBX')
        self.stdout.write('-' * 20)
        
        try:
            vitalpbx_service = VitalPBXService()
            
            # Test 1: Configuration validation
            self.stdout.write('1️⃣ Testing VitalPBX configuration...')
            config_validation = vitalpbx_service.validate_configuration()
            
            if config_validation['valid']:
                self.stdout.write('   ✅ Configuration valid')
                config = config_validation['config']
                self.stdout.write(f'   📋 API Base: {config["api_base"]}')
                self.stdout.write(f'   🔑 API Key: {config["api_key_sample"]}')
                self.stdout.write(f'   🏢 Tenant: {config["tenant"]}')
            else:
                self.stdout.write('   ❌ Configuration invalid')
                for issue in config_validation['issues']:
                    self.stdout.write(f'      • {issue}')
                return
            
            # Test 2: Connection test
            self.stdout.write('\n2️⃣ Testing VitalPBX connection...')
            connection_result = vitalpbx_service.test_connection()
            
            if connection_result.get('success'):
                self.stdout.write('   ✅ Connection successful')
                self.stdout.write(f'   🔗 Working endpoint: {connection_result.get("working_endpoint")}')
                self.stdout.write(f'   🔐 Auth method: {connection_result.get("auth_method")}')
            else:
                self.stdout.write('   ❌ Connection failed')
                self.stdout.write(f'   💬 Message: {connection_result.get("message")}')
                
                if connection_result.get('auth_issue'):
                    self.stdout.write('   🔧 Suggestions:')
                    suggestions = connection_result.get('details', {}).get('suggestions', [])
                    for suggestion in suggestions:
                        self.stdout.write(f'      • {suggestion}')
            
        except Exception as e:
            self.stdout.write(f'❌ VitalPBX test failed: {str(e)}')
    
    def create_test_user(self, email):
        """Create a test user for OAuth testing"""
        self.stdout.write(f'\n👤 CREATING TEST USER: {email}')
        self.stdout.write('-' * 30)
        
        try:
            # Check if user already exists
            if User.objects.filter(email=email).exists():
                self.stdout.write(f'⚠️  User {email} already exists')
                user = User.objects.get(email=email)
            else:
                # Create new user
                user = User.objects.create_user(
                    email=email,
                    password='testpass123',
                    name=f'Test User for {email.split("@")[0]}'
                )
                self.stdout.write(f'✅ Created user: {email}')
                self.stdout.write(f'🔑 Password: testpass123')
            
            # Create extension mapping
            extension_number = input('\n📱 Enter extension number for this user (e.g., 101): ')
            if extension_number:
                try:
                    extension, created = ExtensionMapping.objects.get_or_create(
                        extension=extension_number,
                        defaults={
                            'user': user,
                            'is_active': True
                        }
                    )
                    
                    if created:
                        self.stdout.write(f'✅ Created extension mapping: {extension_number} -> {email}')
                    else:
                        self.stdout.write(f'⚠️  Extension {extension_number} already mapped to {extension.user.email}')
                        
                except Exception as e:
                    self.stdout.write(f'❌ Failed to create extension mapping: {str(e)}')
            
            # Display next steps
            self.stdout.write('\n🔄 Next steps:')
            self.stdout.write(f'1. Login at: http://zoho.fusionsystems.co.ke:8000/accounts/login/')
            self.stdout.write(f'   Email: {email}')
            self.stdout.write(f'   Password: testpass123')
            self.stdout.write(f'2. Visit: http://zoho.fusionsystems.co.ke:8000/phonebridge/')
            self.stdout.write(f'3. Test OAuth: http://zoho.fusionsystems.co.ke:8000/phonebridge/zoho/connect/')
            self.stdout.write(f'4. ✅ Simple redirect: http://zoho.fusionsystems.co.ke:8000/')
            
        except Exception as e:
            self.stdout.write(f'❌ Failed to create test user: {str(e)}')
    
    def show_help(self):
        """Show command usage help"""
        self.stdout.write('\n📖 COMMAND USAGE')
        self.stdout.write('-' * 20)
        
        self.stdout.write('Available commands:')
        self.stdout.write('')
        self.stdout.write('🔍 Status and Testing:')
        self.stdout.write('  --status              Show current OAuth status')
        self.stdout.write('  --test-config         Test OAuth configuration')
        self.stdout.write('  --test-oauth          Test OAuth flow')
        self.stdout.write('  --test-vitalpbx       Test VitalPBX connectivity')
        self.stdout.write('')
        self.stdout.write('🧹 Data Management:')
        self.stdout.write('  --clean-slate         Remove all OAuth data')
        self.stdout.write('  --force               Skip confirmation prompts')
        self.stdout.write('')
        self.stdout.write('👤 User Management:')
        self.stdout.write('  --create-test-user EMAIL  Create test user')
        self.stdout.write('')
        self.stdout.write('🔗 Useful URLs:')
        self.stdout.write('  Root/OAuth: http://zoho.fusionsystems.co.ke:8000/')
        self.stdout.write('  Admin: http://zoho.fusionsystems.co.ke:8000/admin/')
        self.stdout.write('  PhoneBridge: http://zoho.fusionsystems.co.ke:8000/phonebridge/')
        self.stdout.write('  OAuth Test: http://zoho.fusionsystems.co.ke:8000/phonebridge/zoho/connect/')
        self.stdout.write('')
        self.stdout.write('📝 Examples:')
        self.stdout.write('  python manage.py reset_oauth --status')
        self.stdout.write('  python manage.py reset_oauth --clean-slate --force')
        self.stdout.write('  python manage.py reset_oauth --test-config')
        self.stdout.write('  python manage.py reset_oauth --create-test-user test@fusionsystems.co.ke')
        
        # Show current configuration
        self.stdout.write('\n⚙️ CURRENT CONFIGURATION')
        self.stdout.write('-' * 30)
        
        phonebridge_settings = settings.PHONEBRIDGE_SETTINGS
        self.stdout.write(f'🔑 Client ID: {phonebridge_settings.get("ZOHO_CLIENT_ID", "NOT SET")[:20]}...')
        self.stdout.write(f'🔗 Redirect URI: {phonebridge_settings.get("ZOHO_REDIRECT_URI", "NOT SET")}')
        self.stdout.write(f'🎯 Scopes: {phonebridge_settings.get("ZOHO_SCOPES", "NOT SET")}')
        self.stdout.write(f'🐛 Debug Mode: {settings.DEBUG}')
        self.stdout.write(f'📞 VitalPBX: {phonebridge_settings.get("VITALPBX_API_BASE", "NOT SET")}')
        
        # Important reminders
        self.stdout.write('\n⚠️  IMPORTANT REMINDERS')
        self.stdout.write('-' * 25)
        self.stdout.write('1. ✅ SIMPLE REDIRECT URI CONFIGURED:')
        self.stdout.write('   http://zoho.fusionsystems.co.ke:8000')
        self.stdout.write('   (Partnership with Zoho - no console changes needed)')
        self.stdout.write('')
        self.stdout.write('2. Root-level OAuth callback handling implemented')
        self.stdout.write('')
        self.stdout.write('3. Test OAuth flow after running --clean-slate')
        self.stdout.write('')
        self.stdout.write('4. 🎉 Simple redirect = cleaner OAuth flow!')


# Utility classes for enhanced functionality
class ConfigurationValidator:
    """Helper class for validating PhoneBridge configuration"""
    
    @staticmethod
    def validate_redirect_uri():
        """Validate redirect URI configuration"""
        expected_redirect = 'http://zoho.fusionsystems.co.ke:8000'
        current_redirect = settings.PHONEBRIDGE_SETTINGS.get('ZOHO_REDIRECT_URI', '')
        
        return {
            'expected': expected_redirect,
            'current': current_redirect,
            'matches': current_redirect == expected_redirect,
            'is_simple': not '/' in current_redirect.replace('http://', '').replace('https://', ''),
            'protocol_correct': current_redirect.startswith('http://'),
            'domain_correct': 'zoho.fusionsystems.co.ke' in current_redirect,
            'port_included': ':8000' in current_redirect
        }
    
    @staticmethod
    def validate_environment():
        """Validate environment configuration"""
        required_vars = [
            'ZOHO_CLIENT_ID',
            'ZOHO_CLIENT_SECRET',
            'ZOHO_REDIRECT_URI',
            'VITALPBX_API_BASE',
            'VITALPBX_API_KEY'
        ]
        
        missing_vars = []
        present_vars = []
        
        for var in required_vars:
            if os.environ.get(var):
                present_vars.append(var)
            else:
                missing_vars.append(var)
        
        return {
            'all_set': len(missing_vars) == 0,
            'missing_vars': missing_vars,
            'present_vars': present_vars,
            'total_required': len(required_vars),
            'completion_percentage': (len(present_vars) / len(required_vars)) * 100
        }


class DatabaseManager:
    """Helper class for database operations"""
    
    @staticmethod
    def backup_data():
        """Create backup of important data before cleanup"""
        backup_data = {
            'timestamp': timezone.now().isoformat(),
            'users': [],
            'extensions': [],
            'tokens_summary': []
        }
        
        # Backup users with extensions
        for user in User.objects.all():
            user_data = {
                'email': user.email,
                'name': user.name,
                'is_staff': user.is_staff,
                'extensions': []
            }
            
            extensions = ExtensionMapping.objects.filter(user=user, is_active=True)
            for ext in extensions:
                user_data['extensions'].append({
                    'extension': ext.extension,
                    'zoho_user_id': ext.zoho_user_id,
                })
            
            backup_data['users'].append(user_data)
        
        # Backup token summaries (without sensitive data)
        for token in ZohoToken.objects.all():
            backup_data['tokens_summary'].append({
                'user_email': token.user.email,
                'location': token.location,
                'oauth_version': token.oauth_version,
                'phonebridge_enabled': token.is_phonebridge_enabled(),
                'expires_at': token.expires_at.isoformat()
            })
        
        return backup_data
    
    @staticmethod
    def get_system_stats():
        """Get comprehensive system statistics"""
        stats = {
            'database': {
                'users': User.objects.count(),
                'tokens': ZohoToken.objects.count(),
                'extensions': ExtensionMapping.objects.count(),
                'call_logs': CallLog.objects.count(),
                'popup_logs': PopupLog.objects.count()
            },
            'oauth': {
                'v3_tokens': ZohoToken.objects.filter(oauth_version='v3').count(),
                'phonebridge_enabled': ZohoToken.objects.filter(
                    scopes_granted__icontains='PhoneBridge'
                ).count(),
                'expired_tokens': ZohoToken.objects.filter(
                    expires_at__lt=timezone.now()
                ).count()
            },
            'extensions': {
                'active': ExtensionMapping.objects.filter(is_active=True).count(),
                'with_zoho_id': ExtensionMapping.objects.exclude(zoho_user_id='').count()
            }
        }
        
        return stats