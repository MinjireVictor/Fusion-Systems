from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import main_views  # Import from the renamed file
from .views.call_control import (
    CallAnswerView, 
    CallDeclineView, 
    CallRecordingView, 
    CallStatusView,
    CallControlViewSet
)

# API Router for REST endpoints
router = DefaultRouter()
router.register(r'extensions', main_views.ExtensionMappingViewSet, basename='extensions')
router.register(r'call-logs', main_views.CallLogViewSet, basename='call-logs')
router.register(r'calls', CallControlViewSet, basename='calls')


app_name = 'phonebridge'

urlpatterns = [
    # Web interface URLs
    path('', main_views.PhoneBridgeHomeView.as_view(), name='home'),
    path('setup/', main_views.SetupView.as_view(), name='setup'),
    path('extensions/', main_views.ExtensionMappingView.as_view(), name='extensions'),
    path('calls/<str:call_id>/answer/', CallAnswerView.as_view(), name='call_answer'),
    path('calls/<str:call_id>/decline/', CallDeclineView.as_view(), name='call_decline'),
    path('calls/<str:call_id>/recording/<str:action>/', CallRecordingView.as_view(), name='call_recording'),
    path('calls/<str:call_id>/status/', CallStatusView.as_view(), name='call_status'),
    
    # Zoho OAuth URLs
    path('zoho/connect/', main_views.ZohoConnectView.as_view(), name='zoho_connect'),
    path('zoho/callback/', main_views.ZohoCallbackView.as_view(), name='zoho_callback'),
    path('zoho/disconnect/', main_views.ZohoDisconnectView.as_view(), name='zoho_disconnect'),
    path('zoho/status/', main_views.ZohoStatusView.as_view(), name='zoho_status'),
    
    # Click-to-call URLs
    path('click-to-call/', main_views.ClickToCallView.as_view(), name='click_to_call'),
    
    # Webhook URLs
    path('webhooks/vitalpbx/', main_views.VitalPBXWebhookView.as_view(), name='vitalpbx_webhook'),
    path('webhooks/zoho/', main_views.ZohoWebhookView.as_view(), name='zoho_webhook'),
    
    # Enhanced Test/Debug URLs
    path('test/vitalpbx/', main_views.TestVitalPBXView.as_view(), name='test_vitalpbx'),
    path('test/zoho/', main_views.TestZohoView.as_view(), name='test_zoho'),
    path('diagnostics/', main_views.SystemDiagnosticsView.as_view(), name='system_diagnostics'),
    
    # API URLs
    path('api/', include(router.urls)),
]