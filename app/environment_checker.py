#!/usr/bin/env python3
"""
Environment Configuration Checker for PhoneBridge
Run this script to validate your environment setup before starting the application
"""

import os
import sys
import requests
from urllib.parse import urlparse

def check_environment_variables():
    """Check if all required environment variables are set"""
    print("🔍 Checking Environment Variables...")
    print("=" * 50)
    
    required_vars = {
        'Database Configuration': [
            ('DB_HOST', 'Database host'),
            ('DB_NAME', 'Database name'),
            ('DB_USER', 'Database username'),
            ('DB_PASS', 'Database password'),
        ],
        'Django Configuration': [
            ('SECRET_KEY', 'Django secret key'),
            ('DEBUG', 'Debug mode'),
        ],
        'Zoho Configuration': [
            ('ZOHO_CLIENT_ID', 'Zoho OAuth Client ID'),
            ('ZOHO_CLIENT_SECRET', 'Zoho OAuth Client Secret'),
            ('ZOHO_REDIRECT_URI', 'Zoho OAuth Redirect URI'),
        ],
        'VitalPBX Configuration': [
            ('VITALPBX_API_BASE', 'VitalPBX API Base URL'),
            ('VITALPBX_USERNAME', 'VitalPBX Username'),
            ('VITALPBX_PASSWORD', 'VitalPBX Password'),
        ],
    }
    
    all_good = True
    
    for category, vars_list in required_vars.items():
        print(f"\n📋 {category}:")
        for var_name, description in vars_list:
            value = os.getenv(var_name)
            if value:
                # Mask sensitive values
                if any(sensitive in var_name.lower() for sensitive in ['password', 'secret', 'key']):
                    display_value = f"{'*' * min(len(value), 8)}... ({len(value)} chars)"
                else:
                    display_value = value[:30] + '...' if len(value) > 30 else value
                print(f"   ✅ {var_name}: {display_value}")
            else:
                print(f"   ❌ {var_name}: NOT SET - {description}")
                all_good = False
    
    return all_good

def validate_zoho_configuration():
    """Validate Zoho configuration"""
    print("\n🔍 Validating Zoho Configuration...")
    print("=" * 50)
    
    client_id = os.getenv('ZOHO_CLIENT_ID')
    client_secret = os.getenv('ZOHO_CLIENT_SECRET')
    redirect_uri = os.getenv('ZOHO_REDIRECT_URI')
    
    issues = []
    
    # Validate Client ID
    if not client_id:
        issues.append("ZOHO_CLIENT_ID is not set")
    elif not client_id.startswith('1000.'):
        issues.append("ZOHO_CLIENT_ID should start with '1000.'")
    else:
        print(f"✅ Client ID format: {client_id[:15]}...")
    
    # Validate Client Secret
    if not client_secret:
        issues.append("ZOHO_CLIENT_SECRET is not set")
    elif len(client_secret) < 32:
        issues.append("ZOHO_CLIENT_SECRET appears to be too short")
    else:
        print(f"✅ Client Secret length: {len(client_secret)} characters")
    
    # Validate Redirect URI
    if not redirect_uri:
        issues.append("ZOHO_REDIRECT_URI is not set")
    else:
        parsed = urlparse(redirect_uri)
        if not parsed.scheme or not parsed.netloc:
            issues.append("ZOHO_REDIRECT_URI must be a valid URL")
        elif not parsed.scheme in ['http', 'https']:
            issues.append("ZOHO_REDIRECT_URI must use http or https")
        else:
            print(f"✅ Redirect URI: {redirect_uri}")
    
    if issues:
        print("\n❌ Zoho Configuration Issues:")
        for issue in issues:
            print(f"   - {issue}")
        return False
    else:
        print("✅ Zoho configuration looks good!")
        return True

def validate_vitalpbx_configuration():
    """Validate VitalPBX configuration"""
    print("\n🔍 Validating VitalPBX Configuration...")
    print("=" * 50)
    
    api_base = os.getenv('VITALPBX_API_BASE')
    username = os.getenv('VITALPBX_USERNAME')
    password = os.getenv('VITALPBX_PASSWORD')
    
    issues = []
    
    # Validate API Base URL
    if not api_base:
        issues.append("VITALPBX_API_BASE is not set")
    else:
        parsed = urlparse(api_base)
        if not parsed.scheme or not parsed.netloc:
            issues.append("VITALPBX_API_BASE must be a valid URL")
        elif not parsed.scheme in ['http', 'https']:
            issues.append("VITALPBX_API_BASE must use http or https")
        else:
            print(f"✅ API Base URL: {api_base}")
    
    # Validate credentials
    if not username:
        issues.append("VITALPBX_USERNAME is not set")
    else:
        print(f"✅ Username: {username}")
    
    if not password:
        issues.append("VITALPBX_PASSWORD is not set")
    else:
        print(f"✅ Password: {'*' * min(len(password), 8)}... ({len(password)} chars)")
    
    if issues:
        print("\n❌ VitalPBX Configuration Issues:")
        for issue in issues:
            print(f"   - {issue}")
        return False
    else:
        print("✅ VitalPBX configuration looks good!")
        return True

def test_external_connectivity():
    """Test connectivity to external services"""
    print("\n🔍 Testing External Connectivity...")
    print("=" * 50)
    
    services = [
        ("Zoho Accounts", "https://accounts.zoho.com"),
        ("Zoho API", "https://www.zohoapis.com"),
        ("VitalPBX Server", os.getenv('VITALPBX_API_BASE'))
    ]
    
    all_good = True
    
    for service_name, url in services:
        if not url:
            print(f"❌ {service_name}: URL not configured")
            all_good = False
            continue
            
        try:
            print(f"🔄 Testing {service_name}...")
            response = requests.get(url, timeout=10, verify=False)
            
            if response.status_code in [200, 401, 403]:  # 401/403 means server is responding
                print(f"✅ {service_name}: Reachable (Status: {response.status_code})")
            else:
                print(f"⚠️  {service_name}: Unexpected status code {response.status_code}")
                all_good = False
                
        except requests.exceptions.Timeout:
            print(f"❌ {service_name}: Connection timeout")
            all_good = False
        except requests.exceptions.ConnectionError:
            print(f"❌ {service_name}: Connection failed")
            all_good = False
        except Exception as e:
            print(f"❌ {service_name}: Error - {str(e)}")
            all_good = False
    
    return all_good

def generate_django_env_file():
    """Generate a sample .env file for Django"""
    print("\n📝 Generating sample .env file...")
    print("=" * 50)
    
    env_content = """# Database Configuration
DB_HOST=db
DB_NAME=devdb
DB_USER=devuser
DB_PASS=changeme

# Django Configuration
DEBUG=true
SECRET_KEY=your-secret-key-here

# Zoho Configuration
ZOHO_CLIENT_ID=your_zoho_client_id
ZOHO_CLIENT_SECRET=your_zoho_client_secret
ZOHO_REDIRECT_URI=https://cc.fusionsystems.co.ke/phonebridge/zoho/callback

# VitalPBX Configuration
VITALPBX_API_BASE=https://cc.fusionsystems.co.ke/api
VITALPBX_USERNAME=your_vitalpbx_username
VITALPBX_PASSWORD=your_vitalpbx_password

# PhoneBridge Settings
CALL_TIMEOUT=30
PHONEBRIDGE_MAX_RETRIES=3

# Redis Configuration (optional)
REDIS_URL=redis://redis:6379/1
"""
    
    try:
        with open('.env.sample', 'w') as f:
            f.write(env_content)
        print("✅ Sample .env file created as '.env.sample'")
        print("   Copy this to '.env' and update with your actual values")
    except Exception as e:
        print(f"❌ Failed to create .env.sample: {str(e)}")

def print_next_steps():
    """Print next steps for setup"""
    print("\n🚀 Next Steps...")
    print("=" * 50)
    
    steps = [
        "1. Fix any configuration issues shown above",
        "2. Ensure Django migrations are run: python manage.py migrate",
        "3. Create a superuser: python manage.py createsuperuser",
        "4. Start the Django server: python manage.py runserver",
        "5. Visit http://localhost:8000/phonebridge/ to access the interface",
        "6. Go to http://localhost:8000/phonebridge/zoho/connect/ to authorize Zoho",
        "7. Configure extension mappings at http://localhost:8000/phonebridge/extensions/",
        "8. Test connections at http://localhost:8000/phonebridge/test/vitalpbx/ and /test/zoho/",
    ]
    
    for step in steps:
        print(f"   {step}")
    
    print("\n🔧 Debugging URLs:")
    debug_urls = [
        "System Diagnostics: http://localhost:8000/phonebridge/diagnostics/",
        "VitalPBX Test: http://localhost:8000/phonebridge/test/vitalpbx/",
        "Zoho Test: http://localhost:8000/phonebridge/test/zoho/",
        "Setup Page: http://localhost:8000/phonebridge/setup/",
    ]
    
    for url in debug_urls:
        print(f"   • {url}")

def main():
    """Main function to run all checks"""
    print("🔧 PhoneBridge Environment Configuration Checker")
    print("=" * 60)
    print("This script will validate your environment setup for PhoneBridge")
    print("=" * 60)
    
    # Check environment variables
    env_ok = check_environment_variables()
    
    # Validate configurations
    zoho_ok = validate_zoho_configuration()
    vitalpbx_ok = validate_vitalpbx_configuration()
    
    # Test connectivity
    connectivity_ok = test_external_connectivity()
    
    # Generate sample env file
    generate_django_env_file()
    
    # Summary
    print("\n📊 Configuration Summary")
    print("=" * 50)
    
    checks = [
        ("Environment Variables", env_ok),
        ("Zoho Configuration", zoho_ok),
        ("VitalPBX Configuration", vitalpbx_ok),
        ("External Connectivity", connectivity_ok),
    ]
    
    all_passed = True
    for check_name, passed in checks:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{check_name}: {status}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\n🎉 All checks passed! Your environment is ready.")
    else:
        print("\n⚠️  Some issues found. Please fix them before proceeding.")
    
    print_next_steps()
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())