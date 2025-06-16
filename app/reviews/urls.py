# Update your reviews/urls.py file with these additions

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import review_views
# Import the new fast analytics views
from .fast_analytics_views import (
    fast_analytics,
    time_series_analytics, 
    volume_stats,
    analytics_health
)

# Create router and register viewsets
router = DefaultRouter()
router.register('reviews', review_views.ReviewViewSet, basename='review')
router.register('analysis-batches', review_views.AnalysisBatchViewSet, basename='analysisbatch')

app_name = 'reviews'

# URL patterns
urlpatterns = [
    # API endpoints via router
    path('api/', include(router.urls)),
    
    # Existing custom endpoints
    path('api/health/', review_views.health_check, name='health-check'),
    path('api/trigger-analysis/', review_views.trigger_manual_analysis, name='trigger-analysis'),
    path('api/dashboard/', review_views.analysis_dashboard, name='analysis-dashboard'),
    path('api/hotel-insights/<str:hotel_id>/', review_views.hotel_insights, name='hotel-insights'),
    
    # NEW: Fast Analytics Endpoints
    path('api/analytics-fast/<str:hotel_id>/', fast_analytics, name='fast-analytics'),
    path('api/time-series/<str:hotel_id>/', time_series_analytics, name='time-series-analytics'),
    path('api/volume-stats/<str:hotel_id>/', volume_stats, name='volume-stats'),
    path('api/analytics-health/<str:hotel_id>/', analytics_health, name='analytics-health'),
]

# Updated endpoint documentation:
# 
# Existing Review endpoints:
# GET    /api/reviews/                     - List all reviews (with filtering)
# POST   /api/reviews/                     - Create new review
# GET    /api/reviews/{id}/                - Get specific review
# PUT    /api/reviews/{id}/                - Update review
# DELETE /api/reviews/{id}/                - Delete review
# GET    /api/reviews/{id}/analysis/       - Get analysis for specific review
# GET    /api/reviews/with_analysis/       - List reviews with analysis
# GET    /api/reviews/analytics_summary/   - Get analytics summary for hotel (LEGACY)
# POST   /api/reviews/bulk_submit/         - Submit multiple reviews
# POST   /api/reviews/request_analysis/    - Request manual analysis
# GET    /api/hotel-insights/{hotel_id}/   - Get detailed hotel insights (LEGACY)
#
# Analysis Batch endpoints:
# GET    /api/analysis-batches/            - List all analysis batches
# GET    /api/analysis-batches/{id}/       - Get specific batch
# GET    /api/analysis-batches/latest/     - Get latest batch status
# GET    /api/analysis-batches/statistics/ - Get batch processing statistics
#
# NEW: Fast Analytics Endpoints:
# GET    /api/analytics-fast/{hotel_id}/   - Complete analytics for overview components
#        Query params: ?preset=last6months&date_from=2024-01-01&date_to=2024-12-31
#        Presets: last7days, last30days, last90days, last6months, lastyear, custom
#
# GET    /api/time-series/{hotel_id}/      - Time series data for detailed charts
#        Query params: ?granularity=monthly&preset=last6months
#        Granularity: daily, weekly, monthly
#
# GET    /api/volume-stats/{hotel_id}/     - Volume statistics for ReviewMap component
#
# GET    /api/analytics-health/{hotel_id}/ - Health check for analytics data availability
#
# Utility endpoints:
# GET    /api/health/                      - Service health check
# POST   /api/trigger-analysis/            - Manually trigger review analysis
# GET    /api/dashboard/                   - Analysis dashboard overview