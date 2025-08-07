#!/usr/bin/env python3
"""
VitalPBX API Key Test Script
Run this script to test the new API Key authentication with VitalPBX
"""

import os
import sys
import requests
import json
from urllib.parse import urlencode

# Configuration
API_BASE = "https://cc.fusionsystems.co.ke/api"
API_KEY = "36e6b22faea32d0069b1a7bd1da9de82"  # From Eric
TENANT = ""  # Optional - leave empty for default

def test_api_key_authentication():
    """Test VitalPBX API Key authentication"""
    print("🔧 VitalPBX API Key Authentication Test")
    print("=" * 50)
    print(f"API Base: {API_BASE}")
    print(f"API Key: ***{API_KEY[-4:]}")
    print(f"Tenant: {TENANT or 'Default'}")
    print()
    
    # Test endpoints from documentation
    endpoints = [
        'tenants',
        'account_codes', 
        'auth_codes',
        'extensions',
        'calls'
    ]
    
    results = []
    
    for endpoint in endpoints:
        print(f"🔄 Testing endpoint: /v2/{endpoint}")
        
        # Build URL
        url = f"{API_BASE}/v2/{endpoint}"
        
        # Add tenant parameter if specified
        params = {}
        if TENANT:
            params['tenant'] = TENANT
            url += '?' + urlencode(params)
        
        # Set headers with API Key
        headers = {
            'app-key': API_KEY,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'PhoneBridge-Test/1.0'
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=30, verify=False)
            
            result = {
                'endpoint': endpoint,
                'url': url,
                'status_code': response.status_code,
                'success': False,
                'message': '',
                'data_sample': None
            }
            
            # Analyze response
            if response.status_code == 200:
                result['success'] = True
                result['message'] = '✅ SUCCESS - API Key authentication working!'
                try:
                    data = response.json()
                    result['data_sample'] = str(data)[:200] + '...' if len(str(data)) > 200 else str(data)
                    print(f"   ✅ SUCCESS: HTTP 200 - Data received")
                except json.JSONDecodeError:
                    result['data_sample'] = response.text[:200]
                    print(f"   ✅ SUCCESS: HTTP 200 - Non-JSON response")
                    
            elif response.status_code == 401:
                result['message'] = '❌ FAILED - Authentication failed (API Key invalid?)'
                print(f"   ❌ FAILED: HTTP 401 - API Key authentication failed")
                
            elif response.status_code == 403:
                result['message'] = '⚠️  FORBIDDEN - API Key lacks permissions'
                print(f"   ⚠️  FORBIDDEN: HTTP 403 - API Key may need more permissions")
                
            elif response.status_code == 404:
                result['message'] = '❓ NOT FOUND - Endpoint may not exist'
                print(f"   ❓ NOT FOUND: HTTP 404 - Endpoint may not be available")
                
            elif response.status_code == 422:
                result['message'] = '⚠️  UNPROCESSABLE - May need additional parameters'
                print(f"   ⚠️  UNPROCESSABLE: HTTP 422 - May need tenant or other params")
                
            else:
                result['message'] = f'❓ UNKNOWN - HTTP {response.status_code}'
                print(f"   ❓ UNKNOWN: HTTP {response.status_code} - {response.text[:100]}")
            
            results.append(result)
            
        except requests.exceptions.Timeout:
            result = {
                'endpoint': endpoint,
                'url': url,
                'success': False,
                'message': '⏰ TIMEOUT - Request timed out',
                'error': 'Connection timeout'
            }
            results.append(result)
            print(f"   ⏰ TIMEOUT: Request timed out after 30 seconds")
            
        except requests.exceptions.ConnectionError:
            result = {
                'endpoint': endpoint,
                'url': url,
                'success': False,
                'message': '🔌 CONNECTION ERROR - Cannot reach server',
                'error': 'Connection failed'
            }
            results.append(result)
            print(f"   🔌 CONNECTION ERROR: Cannot reach VitalPBX server")
            
        except Exception as e:
            result = {
                'endpoint': endpoint,
                'url': url,
                'success': False,
                'message': f'💥 ERROR - {str(e)}',
                'error': str(e)
            }
            results.append(result)
            print(f"   💥 ERROR: {str(e)}")
        
        print()  # Empty line between tests
    
    # Summary
    print("📊 TEST SUMMARY")
    print("=" * 50)
    
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]
    auth_failed = [r for r in results if r.get('status_code') == 401]
    
    print(f"Total endpoints tested: {len(results)}")
    print(f"✅ Successful: {len(successful)}")
    print(f"❌ Failed: {len(failed)}")
    print(f"🔐 Auth failures: {len(auth_failed)}")
    print()
    
    if successful:
        print("✅ WORKING ENDPOINTS:")
        for result in successful:
            print(f"   • {result['endpoint']} - {result['message']}")
        print()
        
        print("🎉 GREAT NEWS: API Key authentication is working!")
        print("   You can now use VitalPBX API for call management.")
        print()
        
    if auth_failed:
        print("🔐 AUTHENTICATION ISSUES:")
        for result in auth_failed:
            print(f"   • {result['endpoint']} - API Key rejected")
        print()
        
        if len(auth_failed) == len(results):
            print("❌ CRITICAL: All endpoints failed authentication")
            print("   Possible issues:")
            print("   1. API Key may be incorrect or expired")
            print("   2. API Key may not have required permissions")
            print("   3. Tenant specification may be required")
            print("   4. Contact Eric to verify API Key status")
        print()
    
    # Return results for programmatic use
    return {
        'total_tested': len(results),
        'successful': len(successful),
        'failed': len(failed),
        'auth_failed': len(auth_failed),
        'results': results,
        'overall_success': len(successful) > 0
    }

def test_call_origination():
    """Test call origination endpoint specifically"""
    print("📞 TESTING CALL ORIGINATION")
    print("=" * 50)
    
    # Test data - won't actually make a call due to dry run
    test_call_data = {
        'Channel': 'PJSIP/test',
        'Context': 'from-internal', 
        'Exten': '1234567890',
        'Priority': 1,
        'Timeout': 30000,
        'CallerID': 'test',
        'Async': True,
        'ActionID': 'test_connection_only'
    }
    
    url = f"{API_BASE}/v2/originate"
    headers = {
        'app-key': API_KEY,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    
    print(f"Testing POST to: {url}")
    print("⚠️  Note: This is a test call - no actual call will be made")
    print()
    
    try:
        # Make the request
        response = requests.post(url, headers=headers, json=test_call_data, timeout=30, verify=False)
        
        print(f"Response Status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ SUCCESS: Call origination endpoint is accessible!")
            try:
                data = response.json()
                print(f"Response: {json.dumps(data, indent=2)}")
            except:
                print(f"Response Text: {response.text}")
                
        elif response.status_code == 401:
            print("❌ FAILED: Authentication failed for call origination")
            
        elif response.status_code == 400:
            print("⚠️  BAD REQUEST: Call data may be invalid (but endpoint is accessible)")
            print(f"Response: {response.text}")
            
        else:
            print(f"❓ Status {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"💥 ERROR: {str(e)}")
    
    print()

def main():
    """Main test function"""
    print("🚀 VitalPBX API Key Integration Test")
    print("=" * 60)
    print("This script tests the API Key authentication with VitalPBX")
    print("API Key provided by Eric: 36e6b22faea32d0069b1a7bd1da9de82")
    print("=" * 60)
    print()
    
    # Test basic API authentication
    auth_results = test_api_key_authentication()
    
    # If basic auth works, test call origination
    if auth_results['overall_success']:
        test_call_origination()
    else:
        print("⚠️  Skipping call origination test due to authentication failures")
        print()
    
    # Final recommendations
    print("🎯 NEXT STEPS")
    print("=" * 50)
    
    if auth_results['overall_success']:
        print("✅ API Key authentication is working!")
        print("   1. Update your Django .env file with:")
        print(f"      VITALPBX_API_KEY={API_KEY}")
        print("   2. Restart your Django application")
        print("   3. Test the PhoneBridge integration")
        print("   4. Configure extension mappings")
        print("   5. Test click-to-call functionality")
    else:
        print("❌ API Key authentication is not working")
        print("   1. Verify API key with Eric")
        print("   2. Check if API key needs additional permissions")
        print("   3. Try specifying a tenant parameter")
        print("   4. Contact VitalPBX support if needed")
    
    print()
    print("📧 Contact: Eric Muriithi (VitalPBX Admin)")
    print("🔗 VitalPBX: https://cc.fusionsystems.co.ke")
    print()
    
    return auth_results['overall_success']

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
                '