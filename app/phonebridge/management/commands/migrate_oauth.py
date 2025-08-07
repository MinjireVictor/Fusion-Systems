# phonebridge/management/commands/migrate_oauth.py

import json
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction

from phonebridge.models import ZohoToken, OAuthMigrationLog
from phonebridge.services.zoho_service import ZohoService, ZohoTokenManager

User = get_user_model()

class Command(BaseCommand):
    """
    Management command to migrate users from old OAuth flow to new PhoneBridge OAuth flow
    
    Usage:
        python manage.py migrate_oauth --dry-run  # Preview changes
        python manage.py migrate_oauth --confirm  # Execute migration
        python manage.py migrate_oauth --user=user@example.com  # Migrate specific user
        python manage.py migrate_oauth --reset-all  # Clear all tokens (force re-auth)
    """
    
    help = 'Migrate Zoho OAuth tokens to new PhoneBridge-compatible flow'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be migrated without making changes',
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm migration execution',
        )
        parser.add_argument(
            '--user',
            type=str,
            help='Migrate specific user by email',
        )
        parser.add_argument(
            '--reset-all',
            action='store_true',
            help='Reset all tokens (users will need to re-authorize)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force migration even if tokens seem compatible',
        )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.zoho_service = ZohoService()
        self.token_manager = ZohoTokenManager(self.zoho_service)
    
    def handle(self, *args, **options):
        """Main command handler"""
        try:
            if options['reset_all']:
                self.handle_reset_all(options)
            elif options['user']:
                self.handle_user_migration(options['user'], options)
            else:
                self.handle_bulk_migration(options)
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Migration failed: {str(e)}')
            )
            raise CommandError(str(e))
    
    def handle_reset_all(self, options):
        """Reset all OAuth tokens"""
        if not options['confirm']:
            self.stdout.write(
                self.style.WARNING('⚠️  DRY RUN: Would delete all Zoho tokens')
            )
            
            token_count = ZohoToken.objects.count()
            user_emails = list(ZohoToken.objects.values_list('user__email', flat=True))
            
            self.stdout.write(f'Tokens to delete: {token_count}')
            self.stdout.write('Affected users:')
            for email in user_emails:
                self.stdout.write(f'  - {email}')
            
            self.stdout.write(
                self.style.WARNING('Run with --confirm to execute the reset')
            )
            return
        
        with transaction.atomic():
            deleted_count, _ = ZohoToken.objects.all().delete()
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ Deleted {deleted_count} OAuth tokens')
            )
            self.stdout.write(
                'Users will need to re-authorize at /phonebridge/zoho/connect/'
            )
    
    def handle_user_migration(self, user_email, options):
        """Migrate specific user"""
        try:
            user = User.objects.get(email=user_email)
        except User.DoesNotExist:
            raise CommandError(f'User not found: {user_email}')
        
        try:
            token = ZohoToken.objects.get(user=user)
        except ZohoToken.DoesNotExist:
            self.stdout.write(
                self.style.WARNING(f'No OAuth token found for {user_email}')
            )
            return
        
        migration_info = self.analyze_token_migration(token)
        
        self.stdout.write(f'\n👤 User: {user_email}')
        self.stdout.write('=' * 50)
        
        self.display_token_analysis(token, migration_info)
        
        if not migration_info['needs_migration'] and not options.get('force'):
            self.stdout.write(
                self.style.SUCCESS('✅ Token is already compatible with new OAuth flow')
            )
            return
        
        if options.get('dry_run'):
            self.stdout.write(
                self.style.WARNING('🔄 DRY RUN: Would migrate this token')
            )
        elif options.get('confirm'):
            self.migrate_user_token(user, token, migration_info)
        else:
            self.stdout.write(
                self.style.WARNING('Use --confirm to execute migration or --dry-run to preview')
            )
    
    def handle_bulk_migration(self, options):
        """Handle bulk migration of all tokens"""
        tokens = ZohoToken.objects.all()
        
        if not tokens.exists():
            self.stdout.write(
                self.style.WARNING('No OAuth tokens found to migrate')
            )
            return
        
        self.stdout.write(f'📊 Found {tokens.count()} OAuth tokens to analyze')
        self.stdout.write('=' * 60)
        
        migration_stats = {
            'total': 0,
            'needs_migration': 0,
            'already_compatible': 0,
            'expired': 0,
            'invalid': 0
        }
        
        tokens_to_migrate = []
        
        for token in tokens:
            migration_stats['total'] += 1
            migration_info = self.analyze_token_migration(token)
            
            self.stdout.write(f'\n👤 {token.user.email}:')
            
            if token.is_expired():
                migration_stats['expired'] += 1
                self.stdout.write('  ⏰ Token expired - needs re-authorization')
            elif not migration_info['needs_migration'] and not options.get('force'):
                migration_stats['already_compatible'] += 1
                self.stdout.write('  ✅ Already compatible')
            else:
                migration_stats['needs_migration'] += 1
                self.stdout.write('  🔄 Needs migration')
                tokens_to_migrate.append((token, migration_info))
        
        # Display summary
        self.stdout.write('\n📈 Migration Summary')
        self.stdout.write('=' * 30)
        self.stdout.write(f'Total tokens: {migration_stats["total"]}')
        self.stdout.write(f'Already compatible: {migration_stats["already_compatible"]}')
        self.stdout.write(f'Need migration: {migration_stats["needs_migration"]}')
        self.stdout.write(f'Expired (need re-auth): {migration_stats["expired"]}')
        
        if not tokens_to_migrate:
            self.stdout.write(
                self.style.SUCCESS('🎉 All tokens are already compatible!')
            )
            return
        
        if options.get('dry_run'):
            self.stdout.write(
                self.style.WARNING(f'\n🔍 DRY RUN: Would migrate {len(tokens_to_migrate)} tokens')
            )
            for token, migration_info in tokens_to_migrate:
                self.stdout.write(f'  - {token.user.email}: {", ".join(migration_info["issues"])}')
        elif options.get('confirm'):
            self.stdout.write(f'\n🚀 Migrating {len(tokens_to_migrate)} tokens...')
            self.execute_bulk_migration(tokens_to_migrate)
        else:
            self.stdout.write(
                self.style.WARNING('\nUse --confirm to execute migration or --dry-run to preview')
            )
    
    def analyze_token_migration(self, token):
        """Analyze if token needs migration"""
        return self.token_manager.validate_token_migration_needed(token)
    
    def display_token_analysis(self, token, migration_info):
        """Display detailed token analysis"""
        self.stdout.write(f'  📅 Created: {token.created_at.strftime("%Y-%m-%d %H:%M")}')
        self.stdout.write(f'  ⏰ Expires: {token.expires_at.strftime("%Y-%m-%d %H:%M")}')
        self.stdout.write(f'  🌍 Location: {token.location or "Not set"}')
        self.stdout.write(f'  🔗 API Domain: {token.api_domain or "Not set"}')
        self.stdout.write(f'  📋 OAuth Version: {token.oauth_version}')
        self.stdout.write(f'  🎯 PhoneBridge Enabled: {token.is_phonebridge_enabled()}')
        
        if migration_info['issues']:
            self.stdout.write('  ⚠️  Issues:')
            for issue in migration_info['issues']:
                self.stdout.write(f'    - {issue}')
    
    def migrate_user_token(self, user, token, migration_info):
        """Migrate a single user's token"""
        try:
            # Create migration log
            migration_log = OAuthMigrationLog.objects.create(
                user=user,
                old_token_data={
                    'access_token': token.access_token[:20] + '...',  # Truncated for security
                    'expires_at': token.expires_at.isoformat(),
                    'location': token.location,
                    'api_domain': token.api_domain,
                    'oauth_version': token.oauth_version,
                    'scopes_granted': token.scopes_granted,
                    'migration_issues': migration_info['issues']
                },
                migration_status='in_progress',
                notes=f'Automated migration - Issues: {", ".join(migration_info["issues"])}'
            )
            
            # Strategy 1: Try to enhance existing token with missing info
            if token.access_token and not token.is_expired():
                enhanced = self.enhance_existing_token(token)
                if enhanced:
                    migration_log.migration_status = 'completed'
                    migration_log.migration_completed_at = timezone.now()
                    migration_log.notes += ' - Enhanced existing token successfully'
                    migration_log.save()
                    
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ Enhanced token for {user.email}')
                    )
                    return
            
            # Strategy 2: Token needs re-authorization
            self.handle_token_reauthorization(user, token, migration_log)
            
        except Exception as e:
            migration_log.migration_status = 'failed'
            migration_log.error_message = str(e)
            migration_log.save()
            
            self.stdout.write(
                self.style.ERROR(f'❌ Migration failed for {user.email}: {str(e)}')
            )
    
    def enhance_existing_token(self, token):
        """Try to enhance existing token with missing information"""
        try:
            # Test current token and get user info to determine location/domain
            test_result = self.zoho_service.test_connection(
                token.access_token, 
                token.api_domain
            )
            
            if not test_result.get('success'):
                return False
            
            # Try to determine location and API domain from successful API calls
            user_info = self.zoho_service.get_user_info(token.access_token, token.api_domain)
            
            if user_info.get('success'):
                # Update token with inferred information
                if not token.location:
                    token.location = 'us'  # Default to US if we can't determine
                
                if not token.api_domain:
                    token.api_domain = user_info.get('api_domain', 'https://www.zohoapis.com')
                
                if not token.oauth_domain:
                    token.oauth_domain = 'https://accounts.zoho.com'  # Default for US
                
                if token.oauth_version != 'v3':
                    token.oauth_version = 'v3'
                
                # Update scopes if not set
                if not token.scopes_granted:
                    token.scopes_granted = self.zoho_service.scopes
                
                token.save()
                
                self.stdout.write(f'  🔄 Enhanced token with location: {token.location}, API domain: {token.api_domain}')
                return True
            
            return False
            
        except Exception as e:
            self.stdout.write(f'  ⚠️  Token enhancement failed: {str(e)}')
            return False
    
    def handle_token_reauthorization(self, user, token, migration_log):
        """Handle token that needs complete re-authorization"""
        # Delete old token to force re-authorization
        old_token_info = {
            'location': token.location,
            'api_domain': token.api_domain,
            'expired': token.is_expired(),
            'phonebridge_enabled': token.is_phonebridge_enabled()
        }
        
        token.delete()
        
        migration_log.migration_status = 'completed'
        migration_log.migration_completed_at = timezone.now()
        migration_log.notes += f' - Deleted old token, user needs re-authorization. Old token info: {json.dumps(old_token_info)}'
        migration_log.save()
        
        self.stdout.write(
            self.style.WARNING(f'🔑 Token deleted for {user.email} - user needs to re-authorize')
        )
        self.stdout.write(f'    Re-authorization URL: /phonebridge/zoho/connect/')
    
    def execute_bulk_migration(self, tokens_to_migrate):
        """Execute bulk migration of multiple tokens"""
        success_count = 0
        error_count = 0
        
        for token, migration_info in tokens_to_migrate:
            try:
                self.stdout.write(f'🔄 Migrating {token.user.email}...')
                self.migrate_user_token(token.user, token, migration_info)
                success_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Failed to migrate {token.user.email}: {str(e)}')
                )
                error_count += 1
        
        # Final summary
        self.stdout.write('\n📊 Migration Results')
        self.stdout.write('=' * 30)
        self.stdout.write(f'✅ Successful: {success_count}')
        self.stdout.write(f'❌ Failed: {error_count}')
        
        if error_count == 0:
            self.stdout.write(
                self.style.SUCCESS('🎉 All migrations completed successfully!')
            )
        else:
            self.stdout.write(
                self.style.WARNING('⚠️  Some migrations failed. Check logs for details.')
            )
    
    def validate_new_oauth_flow(self, options):
        """Validate that the new OAuth flow is properly configured"""
        self.stdout.write('🔍 Validating new OAuth flow configuration...')
        
        # Validate service configuration
        validation = self.zoho_service.validate_configuration()
        
        if not validation['valid']:
            self.stdout.write(
                self.style.ERROR('❌ OAuth configuration validation failed:')
            )
            for issue in validation['issues']:
                self.stdout.write(f'  - {issue}')
            
            if validation['warnings']:
                self.stdout.write('⚠️  Warnings:')
                for warning in validation['warnings']:
                    self.stdout.write(f'  - {warning}')
            
            return False
        
        self.stdout.write('✅ OAuth configuration is valid')
        
        # Display configuration details
        config = validation['config']
        self.stdout.write('\n📋 Configuration Details:')
        self.stdout.write(f'  Client ID: {config["client_id"]}')
        self.stdout.write(f'  Redirect URI: {config["redirect_uri"]}')
        self.stdout.write(f'  Scopes: {config["scopes"]}')
        self.stdout.write(f'  Server Info Accessible: {config["server_info_accessible"]}')
        self.stdout.write(f'  Available Locations: {", ".join(config["available_locations"])}')
        
        return True
    
    def show_migration_status(self):
        """Show current migration status for all users"""
        self.stdout.write('📊 Current OAuth Migration Status')
        self.stdout.write('=' * 50)
        
        # Get all users with tokens
        tokens = ZohoToken.objects.select_related('user').all()
        
        if not tokens.exists():
            self.stdout.write('No OAuth tokens found')
            return
        
        migration_logs = OAuthMigrationLog.objects.select_related('user').all()
        migration_log_map = {log.user_id: log for log in migration_logs}
        
        stats = {
            'total': 0,
            'v3_compatible': 0,
            'needs_migration': 0,
            'expired': 0,
            'phonebridge_enabled': 0
        }
        
        for token in tokens:
            stats['total'] += 1
            
            migration_info = self.analyze_token_migration(token)
            migration_log = migration_log_map.get(token.user_id)
            
            status_emoji = '✅' if not migration_info['needs_migration'] else '🔄'
            if token.is_expired():
                status_emoji = '⏰'
                stats['expired'] += 1
            elif not migration_info['needs_migration']:
                stats['v3_compatible'] += 1
            else:
                stats['needs_migration'] += 1
            
            if token.is_phonebridge_enabled():
                stats['phonebridge_enabled'] += 1
            
            self.stdout.write(f'{status_emoji} {token.user.email}')
            self.stdout.write(f'    Version: {token.oauth_version}, Location: {token.location or "N/A"}')
            
            if migration_log:
                self.stdout.write(f'    Migration: {migration_log.migration_status} ({migration_log.migration_started_at.strftime("%Y-%m-%d")})')
            
            if migration_info['issues']:
                self.stdout.write(f'    Issues: {", ".join(migration_info["issues"])}')
        
        # Summary
        self.stdout.write('\n📈 Summary:')
        self.stdout.write(f'  Total tokens: {stats["total"]}')
        self.stdout.write(f'  OAuth v3 compatible: {stats["v3_compatible"]}')
        self.stdout.write(f'  Need migration: {stats["needs_migration"]}')
        self.stdout.write(f'  Expired: {stats["expired"]}')
        self.stdout.write(f'  PhoneBridge enabled: {stats["phonebridge_enabled"]}')


class MigrationHelper:
    """Helper class for OAuth migration utilities"""
    
    @staticmethod
    def backup_token_data(token):
        """Create backup of token data before migration"""
        return {
            'user_email': token.user.email,
            'access_token_length': len(token.access_token) if token.access_token else 0,
            'refresh_token_length': len(token.refresh_token) if token.refresh_token else 0,
            'expires_at': token.expires_at.isoformat(),
            'location': token.location,
            'oauth_domain': token.oauth_domain,
            'api_domain': token.api_domain,
            'oauth_version': token.oauth_version,
            'scopes_granted': token.scopes_granted,
            'token_type': token.token_type,
            'created_at': token.created_at.isoformat(),
            'last_refreshed_at': token.last_refreshed_at.isoformat() if token.last_refreshed_at else None,
            'phonebridge_enabled': token.is_phonebridge_enabled()
        }
    
    @staticmethod
    def generate_migration_report():
        """Generate comprehensive migration report"""
        report = {
            'timestamp': timezone.now().isoformat(),
            'tokens': [],
            'migration_logs': [],
            'statistics': {}
        }
        
        # Get all tokens
        tokens = ZohoToken.objects.select_related('user').all()
        for token in tokens:
            report['tokens'].append(MigrationHelper.backup_token_data(token))
        
        # Get migration logs
        migration_logs = OAuthMigrationLog.objects.select_related('user').all()
        for log in migration_logs:
            report['migration_logs'].append({
                'user_email': log.user.email,
                'status': log.migration_status,
                'started_at': log.migration_started_at.isoformat(),
                'completed_at': log.migration_completed_at.isoformat() if log.migration_completed_at else None,
                'error_message': log.error_message,
                'notes': log.notes
            })
        
        # Calculate statistics
        report['statistics'] = {
            'total_tokens': len(report['tokens']),
            'migration_attempts': len(report['migration_logs']),
            'completed_migrations': len([log for log in report['migration_logs'] if log['status'] == 'completed']),
            'failed_migrations': len([log for log in report['migration_logs'] if log['status'] == 'failed'])
        }
        
        return report