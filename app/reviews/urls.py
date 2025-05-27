from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

# Create router and register viewsets
router = DefaultRouter()
router.register('reviews', views.ReviewViewSet, basename='review')
router.register('analysis-batches', views.AnalysisBatchViewSet, basename='analysisbatch')

app_name = 'reviews'

# URL patterns
urlpatterns = [
    # API endpoints via router
    path('api/', include(router.urls)),
    
    # Additional custom endpoints
    path('api/health/', views.health_check, name='health-check'),
    path('api/trigger-analysis/', views.trigger_manual_analysis, name='trigger-analysis'),
]

# The router automatically creates these endpoints:
# 
# Review endpoints:
# GET    /api/reviews/                     - List all reviews (with filtering)
# POST   /api/reviews/                     - Create new review
# GET    /api/reviews/{id}/                - Get specific review
# PUT    /api/reviews/{id}/                - Update review
# DELETE /api/reviews/{id}/                - Delete review
# GET    /api/reviews/{id}/analysis/       - Get analysis for specific review
# GET    /api/reviews/with_analysis/       - List reviews with analysis
# GET    /api/reviews/analytics_summary/   - Get analytics summary for hotel
# POST   /api/reviews/bulk_submit/         - Submit multiple reviews
# POST   /api/reviews/request_analysis/    - Request manual analysis
#
# Analysis Batch endpoints:
# GET    /api/analysis-batches/            - List all analysis batches
# GET    /api/analysis-batches/{id}/       - Get specific batch
# GET    /api/analysis-batches/latest/     - Get latest batch status
# GET    /api/analysis-batches/statistics/ - Get batch processing statistics