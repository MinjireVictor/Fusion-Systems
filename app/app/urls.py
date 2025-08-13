"""app URL Configuration

Updated to handle Zoho OAuth callback at root level
Redirect URI: http://zoho.fusionsystems.co.ke:8000
"""
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

# Import the callback view for root-level handling
from phonebridge.main_views import ZohoCallbackView

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # ADD: Authentication URLs for login/logout functionality
    path('accounts/', include('django.contrib.auth.urls')),
    
    # UPDATED: Handle Zoho OAuth callback at root level
    # This matches the simple redirect URI: http://zoho.fusionsystems.co.ke:8000
    path('', ZohoCallbackView.as_view(), name='zoho_callback_root'),
    
    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='api-schema'),
    path(
        'api/docs/',
        SpectacularSwaggerView.as_view(url_name='api-schema'),
        name='api-docs',
    ),
    
    # Existing API endpoints
    path('api/user/', include('user.urls')),
    path('api/recipe/', include('recipe.urls')),
    path('reviews/', include('reviews.urls')),
    
    # PhoneBridge endpoints
    path('phonebridge/', include('phonebridge.urls')),
]

# Optional: Add a dashboard redirect
from django.http import HttpResponseRedirect
from django.shortcuts import redirect

def dashboard_redirect(request):
    """Redirect to PhoneBridge dashboard if no OAuth params"""
    # If there are OAuth parameters, let the callback handle it
    if request.GET.get('code') or request.GET.get('error'):
        # OAuth callback - will be handled by ZohoCallbackView
        return None
    else:
        # Regular visit - redirect to dashboard
        return redirect('/phonebridge/')

# You can uncomment this if you want root to redirect to dashboard when not OAuth
# urlpatterns.insert(-1, path('', dashboard_redirect))