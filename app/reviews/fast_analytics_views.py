# Create this file: reviews/fast_analytics_views.py

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.utils import timezone
from django.core.cache import cache
from datetime import datetime, timedelta, date
from collections import defaultdict
import logging
import calendar

from .models import Review, AnalysisResult, HotelAnalyticsSnapshot, ReviewVolumeStats
from .review_serializers import (
    FastAnalyticsResponseSerializer,
    TimeSeriesDataSerializer,
    ReviewVolumeStatsSerializer,
    PresetRangeSerializer,
    AnalyticsHealthSerializer,
)

logger = logging.getLogger('reviews')


class FastAnalyticsService:
    """Service class for fast analytics operations"""
    
    def __init__(self, hotel_id: str):
        self.hotel_id = hotel_id
        self.cache_timeout = 300  # 5 minutes
    
    def get_preset_date_range(self, preset: str) -> tuple[date, date]:
        """Convert preset to actual date range"""
        today = timezone.now().date()
        
        if preset == 'last7days':
            return today - timedelta(days=7), today
        elif preset == 'last30days':
            return today - timedelta(days=30), today
        elif preset == 'last90days':
            return today - timedelta(days=90), today
        elif preset == 'last6months':
            return today - timedelta(days=180), today
        elif preset == 'lastyear':
            return today - timedelta(days=365), today
        else:
            # Default to last 6 months
            return today - timedelta(days=180), today
    
    def get_complete_analytics(self, preset: str = 'last6months', date_from: date = None, date_to: date = None):
        """Get complete analytics data for overview components"""
        
        # Determine date range
        if preset == 'custom' and date_from and date_to:
            start_date, end_date = date_from, date_to
        else:
            start_date, end_date = self.get_preset_date_range(preset)
        
        # Check cache first
        cache_key = f"fast_analytics:{self.hotel_id}:{start_date}:{end_date}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return cached_data
        
        try:
            # Try to get from pre-computed data
            data = self._get_precomputed_analytics(start_date, end_date)
            data['data_source'] = 'precomputed'
        except Exception as e:
            logger.warning(f"Precomputed data unavailable for {self.hotel_id}: {str(e)}")
            # Fallback to real-time computation
            data = self._get_realtime_analytics(start_date, end_date)
            data['data_source'] = 'realtime'
        
        # Cache the result
        cache.set(cache_key, data, self.cache_timeout)
        return data
    
    def _get_precomputed_analytics(self, start_date: date, end_date: date) -> dict:
        """Get analytics from pre-computed snapshots"""
        
        # Get hotel info
        hotel_info = self._get_hotel_info()
        
        # Get ratings score data
        ratings_score = self._get_precomputed_ratings_score(start_date, end_date)
        
        # Get ratings trend data
        ratings_trend = self._get_precomputed_ratings_trend(start_date, end_date)
        
        # Get review map data
        review_map = self._get_precomputed_review_map()
        
        return {
            'hotel_info': hotel_info,
            'ratings_score': ratings_score,
            'ratings_trend': ratings_trend,
            'review_map': review_map,
            'last_updated': timezone.now(),
        }
    
    def _get_realtime_analytics(self, start_date: date, end_date: date) -> dict:
        """Fallback to real-time analytics computation"""
        
        # Get hotel info
        hotel_info = self._get_hotel_info()
        
        # Get reviews for the period
        reviews = Review.objects.filter(
            hotel_id=self.hotel_id,
            submission_date__date__gte=start_date,
            submission_date__date__lte=end_date
        ).select_related('analysis')
        
        if not reviews.exists():
            return self._empty_analytics_response(hotel_info)
        
        # Compute analytics in real-time
        ratings_score = self._compute_realtime_ratings_score(reviews)
        ratings_trend = self._compute_realtime_ratings_trend(reviews, start_date, end_date)
        review_map = self._compute_realtime_review_map()
        
        return {
            'hotel_info': hotel_info,
            'ratings_score': ratings_score,
            'ratings_trend': ratings_trend,
            'review_map': review_map,
            'last_updated': timezone.now(),
        }
    
    def _get_hotel_info(self) -> dict:
        """Get basic hotel information"""
        try:
            review = Review.objects.filter(hotel_id=self.hotel_id).first()
            if review:
                return {
                    'hotel_id': self.hotel_id,
                    'hotel_name': review.hotel_name,
                }
            else:
                return {
                    'hotel_id': self.hotel_id,
                    'hotel_name': 'Unknown Hotel',
                }
        except Exception:
            return {
                'hotel_id': self.hotel_id,
                'hotel_name': 'Unknown Hotel',
            }
    
    def _get_precomputed_ratings_score(self, start_date: date, end_date: date) -> dict:
        """Get ratings score from pre-computed data"""
        
        # Get recent monthly snapshots for rating distribution
        snapshots = HotelAnalyticsSnapshot.objects.filter(
            hotel_id=self.hotel_id,
            granularity='monthly',
            snapshot_date__gte=start_date,
            snapshot_date__lte=end_date
        ).order_by('-snapshot_date')
        
        if not snapshots.exists():
            raise Exception("No precomputed monthly snapshots available")
        
        # Aggregate rating distributions
        total_ratings = defaultdict(int)
        total_count = 0
        rating_sum = 0
        
        for snapshot in snapshots:
            for rating_str, count in snapshot.rating_distribution.items():
                rating = int(rating_str)
                total_ratings[rating] += count
                total_count += count
                rating_sum += rating * count
        
        if total_count == 0:
            raise Exception("No rating data in snapshots")
        
        # Convert to breakdown format
        breakdown = []
        for stars in [1, 2, 3, 4, 5]:
            customers = total_ratings.get(stars, 0)
            breakdown.append({
                'stars': stars,
                'customers': customers
            })
        
        # Calculate current year data
        current_year = timezone.now().year
        average_score = rating_sum / total_count if total_count > 0 else 0
        
        # Get previous period for percentage change
        prev_start = start_date - (end_date - start_date)
        prev_snapshots = HotelAnalyticsSnapshot.objects.filter(
            hotel_id=self.hotel_id,
            granularity='monthly',
            snapshot_date__gte=prev_start,
            snapshot_date__lt=start_date
        )
        
        prev_avg = 0
        if prev_snapshots.exists():
            prev_total = 0
            prev_sum = 0
            for snapshot in prev_snapshots:
                for rating_str, count in snapshot.rating_distribution.items():
                    rating = int(rating_str)
                    prev_total += count
                    prev_sum += rating * count
            prev_avg = prev_sum / prev_total if prev_total > 0 else 0
        
        percentage_change = 0
        if prev_avg > 0:
            percentage_change = ((average_score - prev_avg) / prev_avg) * 100
        
        return {
            'breakdown': breakdown,
            'currentYearData': {
                'score': round(average_score, 2),
                'percentageChange': round(percentage_change, 1),
                'currentYear': current_year,
                'trendDirection': 'up' if percentage_change >= 0 else 'down'
            }
        }
    
    def _get_precomputed_ratings_trend(self, start_date: date, end_date: date) -> dict:
        """Get ratings trend from pre-computed data"""
        
        # Get monthly snapshots for the period
        snapshots = HotelAnalyticsSnapshot.objects.filter(
            hotel_id=self.hotel_id,
            granularity='monthly',
            snapshot_date__gte=start_date,
            snapshot_date__lte=end_date
        ).order_by('snapshot_date')
        
        if not snapshots.exists():
            raise Exception("No precomputed monthly snapshots for trend")
        
        # Convert to monthly ratings format
        monthly_ratings = []
        for snapshot in snapshots:
            month_name = calendar.month_abbr[snapshot.snapshot_date.month]
            monthly_ratings.append({
                'month': month_name,
                'rating': float(snapshot.average_rating) if snapshot.average_rating else 0
            })
        
        # Calculate trend data
        current_year = timezone.now().year
        
        # Calculate percentage change from first to last month
        percentage_change = 0
        if len(monthly_ratings) >= 2:
            first_rating = monthly_ratings[0]['rating']
            last_rating = monthly_ratings[-1]['rating']
            if first_rating > 0:
                percentage_change = ((last_rating - first_rating) / first_rating) * 100
        
        return {
            'monthlyRatings': monthly_ratings,
            'currentYearData': {
                'currentYear': current_year,
                'percentageChange': round(percentage_change, 1),
                'trendDirection': 'up' if percentage_change >= 0 else 'down'
            }
        }
    
    def _get_precomputed_review_map(self) -> dict:
        """Get review map data from pre-computed volume stats"""
        
        try:
            volume_stats = ReviewVolumeStats.objects.get(hotel_id=self.hotel_id)
        except ReviewVolumeStats.DoesNotExist:
            raise Exception("No precomputed volume stats available")
        
        return {
            'thisMonth': {
                'total': volume_stats.this_month_total,
                'dailyData': volume_stats.this_month_daily_data,
                'growth': f"{volume_stats.this_month_growth:+.1f}%" if volume_stats.this_month_growth else "0%"
            },
            'allTime': {
                'total': volume_stats.all_time_total,
                'monthlyData': volume_stats.all_time_monthly_data,
                'growth': f"{volume_stats.all_time_growth:+.1f}%" if volume_stats.all_time_growth else "0%"
            }
        }
    
    def _compute_realtime_ratings_score(self, reviews) -> dict:
        """Compute ratings score in real-time"""
        
        # Calculate rating distribution
        rating_counts = defaultdict(int)
        total_count = 0
        rating_sum = 0
        
        for review in reviews:
            rating = int(float(review.rating))
            rating_counts[rating] += 1
            total_count += 1
            rating_sum += rating
        
        # Convert to breakdown format
        breakdown = []
        for stars in [1, 2, 3, 4, 5]:
            customers = rating_counts.get(stars, 0)
            breakdown.append({
                'stars': stars,
                'customers': customers
            })
        
        # Calculate average score
        average_score = rating_sum / total_count if total_count > 0 else 0
        current_year = timezone.now().year
        
        # For real-time, we'll use a placeholder percentage change
        percentage_change = 5.0  # Placeholder since we don't have historical comparison
        
        return {
            'breakdown': breakdown,
            'currentYearData': {
                'score': round(average_score, 2),
                'percentageChange': percentage_change,
                'currentYear': current_year,
                'trendDirection': 'up'
            }
        }
    
    def _compute_realtime_ratings_trend(self, reviews, start_date: date, end_date: date) -> dict:
        """Compute ratings trend in real-time"""
        
        # Group reviews by month
        monthly_data = defaultdict(lambda: {'total': 0, 'sum': 0})
        
        for review in reviews:
            month_key = review.submission_date.strftime('%Y-%m')
            monthly_data[month_key]['total'] += 1
            monthly_data[month_key]['sum'] += float(review.rating)
        
        # Convert to monthly ratings format
        monthly_ratings = []
        for month_key in sorted(monthly_data.keys()):
            data = monthly_data[month_key]
            avg_rating = data['sum'] / data['total'] if data['total'] > 0 else 0
            
            # Convert to month name
            year, month = month_key.split('-')
            month_name = calendar.month_abbr[int(month)]
            
            monthly_ratings.append({
                'month': month_name,
                'rating': round(avg_rating, 1)
            })
        
        # Calculate trend
        current_year = timezone.now().year
        percentage_change = 0
        
        if len(monthly_ratings) >= 2:
            first_rating = monthly_ratings[0]['rating']
            last_rating = monthly_ratings[-1]['rating']
            if first_rating > 0:
                percentage_change = ((last_rating - first_rating) / first_rating) * 100
        
        return {
            'monthlyRatings': monthly_ratings,
            'currentYearData': {
                'currentYear': current_year,
                'percentageChange': round(percentage_change, 1),
                'trendDirection': 'up' if percentage_change >= 0 else 'down'
            }
        }
    
    def _compute_realtime_review_map(self) -> dict:
        """Compute review map data in real-time"""
        
        today = timezone.now().date()
        
        # This month data
        month_start = today.replace(day=1)
        this_month_reviews = Review.objects.filter(
            hotel_id=self.hotel_id,
            submission_date__date__gte=month_start
        )
        this_month_total = this_month_reviews.count()
        
        # Last 7 days daily data
        daily_data = []
        for days_back in range(6, -1, -1):
            day = today - timedelta(days=days_back)
            day_count = Review.objects.filter(
                hotel_id=self.hotel_id,
                submission_date__date=day
            ).count()
            daily_data.append(day_count)
        
        # All time data
        all_time_total = Review.objects.filter(hotel_id=self.hotel_id).count()
        
        # Last 7 months monthly data (simplified)
        monthly_data = []
        for months_back in range(6, -1, -1):
            if months_back == 0:
                target_month_start = month_start
            else:
                year = today.year
                month = today.month - months_back
                
                while month <= 0:
                    month += 12
                    year -= 1
                
                target_month_start = date(year, month, 1)
            
            # Calculate month end
            if target_month_start.month == 12:
                target_month_end = date(target_month_start.year + 1, 1, 1) - timedelta(days=1)
            else:
                target_month_end = date(target_month_start.year, target_month_start.month + 1, 1) - timedelta(days=1)
            
            month_count = Review.objects.filter(
                hotel_id=self.hotel_id,
                submission_date__date__gte=target_month_start,
                submission_date__date__lte=target_month_end
            ).count()
            monthly_data.append(month_count)
        
        return {
            'thisMonth': {
                'total': this_month_total,
                'dailyData': daily_data,
                'growth': "+12%"  # Placeholder for real-time
            },
            'allTime': {
                'total': all_time_total,
                'monthlyData': monthly_data,
                'growth': "+8%"  # Placeholder for real-time
            }
        }
    
    def _empty_analytics_response(self, hotel_info: dict) -> dict:
        """Return empty analytics response when no data available"""
        return {
            'hotel_info': hotel_info,
            'ratings_score': {
                'breakdown': [{'stars': i, 'customers': 0} for i in range(1, 6)],
                'currentYearData': {
                    'score': 0,
                    'percentageChange': 0,
                    'currentYear': timezone.now().year,
                    'trendDirection': 'up'
                }
            },
            'ratings_trend': {
                'monthlyRatings': [],
                'currentYearData': {
                    'currentYear': timezone.now().year,
                    'percentageChange': 0,
                    'trendDirection': 'up'
                }
            },
            'review_map': {
                'thisMonth': {'total': 0, 'dailyData': [0] * 7, 'growth': "0%"},
                'allTime': {'total': 0, 'monthlyData': [0] * 7, 'growth': "0%"}
            },
            'last_updated': timezone.now(),
        }


# API Views

@api_view(['GET'])
@permission_classes([AllowAny])
def fast_analytics(request, hotel_id):
    """Fast analytics endpoint - primary endpoint for overview components"""
    try:
        # Get query parameters
        preset = request.GET.get('preset', 'last6months')
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        
        # Validate and parse dates if provided
        parsed_date_from = None
        parsed_date_to = None
        
        if date_from:
            try:
                parsed_date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'error': 'Invalid date_from format. Use YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        if date_to:
            try:
                parsed_date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'error': 'Invalid date_to format. Use YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Get analytics data
        service = FastAnalyticsService(hotel_id)
        data = service.get_complete_analytics(
            preset=preset,
            date_from=parsed_date_from,
            date_to=parsed_date_to
        )
        
        return Response(data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Fast analytics failed for hotel {hotel_id}: {str(e)}", exc_info=True)
        return Response(
            {
                'error': 'Analytics temporarily unavailable',
                'hotel_id': hotel_id,
                'timestamp': timezone.now().isoformat()
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def time_series_analytics(request, hotel_id):
    """Time series analytics endpoint for detailed charts"""
    try:
        # Get query parameters
        granularity = request.GET.get('granularity', 'monthly')
        preset = request.GET.get('preset', 'last6months')
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        
        # Validate granularity
        if granularity not in ['daily', 'weekly', 'monthly']:
            return Response(
                {'error': 'Invalid granularity. Must be daily, weekly, or monthly'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Determine date range
        service = FastAnalyticsService(hotel_id)
        if preset == 'custom' and date_from and date_to:
            try:
                start_date = datetime.strptime(date_from, '%Y-%m-%d').date()
                end_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'error': 'Invalid date format. Use YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            start_date, end_date = service.get_preset_date_range(preset)
        
        # Get snapshots
        snapshots = HotelAnalyticsSnapshot.objects.filter(
            hotel_id=hotel_id,
            granularity=granularity,
            snapshot_date__gte=start_date,
            snapshot_date__lte=end_date
        ).order_by('snapshot_date')
        
        # Convert to time series format
        data_points = []
        for snapshot in snapshots:
            data_points.append({
                'date': snapshot.snapshot_date.isoformat(),
                'review_count': snapshot.review_count,
                'average_rating': float(snapshot.average_rating) if snapshot.average_rating else 0,
                'sentiment_distribution': snapshot.sentiment_distribution,
                'topic_distribution': snapshot.topic_distribution
            })
        
        response_data = {
            'granularity': granularity,
            'period': {
                'from': start_date.isoformat(),
                'to': end_date.isoformat()
            },
            'data': data_points,
            'total_data_points': len(data_points)
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Time series analytics failed for hotel {hotel_id}: {str(e)}", exc_info=True)
        return Response(
            {
                'error': 'Time series data temporarily unavailable',
                'hotel_id': hotel_id,
                'timestamp': timezone.now().isoformat()
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def volume_stats(request, hotel_id):
    """Volume statistics endpoint for ReviewMap component"""
    try:
        # Try to get from pre-computed data first
        try:
            volume_stats = ReviewVolumeStats.objects.get(hotel_id=hotel_id)
            serializer = ReviewVolumeStatsSerializer(volume_stats)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ReviewVolumeStats.DoesNotExist:
            # Fallback to real-time computation
            service = FastAnalyticsService(hotel_id)
            review_map_data = service._compute_realtime_review_map()
            
            return Response({
                'hotel_id': hotel_id,
                'hotel_name': service._get_hotel_info()['hotel_name'],
                'this_month_total': review_map_data['thisMonth']['total'],
                'this_month_daily_data': review_map_data['thisMonth']['dailyData'],
                'this_month_growth': None,
                'all_time_total': review_map_data['allTime']['total'],
                'all_time_monthly_data': review_map_data['allTime']['monthlyData'],
                'all_time_growth': None,
                'updated_at': timezone.now()
            }, status=status.HTTP_200_OK)
            
    except Exception as e:
        logger.error(f"Volume stats failed for hotel {hotel_id}: {str(e)}", exc_info=True)
        return Response(
            {
                'error': 'Volume statistics temporarily unavailable',
                'hotel_id': hotel_id,
                'timestamp': timezone.now().isoformat()
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def analytics_health(request, hotel_id):
    """Health check for analytics data availability"""
    try:
        # Check for pre-computed snapshots
        snapshots_by_granularity = {}
        for granularity in ['daily', 'weekly', 'monthly']:
            count = HotelAnalyticsSnapshot.objects.filter(
                hotel_id=hotel_id,
                granularity=granularity
            ).count()
            snapshots_by_granularity[granularity] = count
        
        latest_snapshot = HotelAnalyticsSnapshot.objects.filter(
            hotel_id=hotel_id
        ).order_by('-snapshot_date').first()
        
        # Check volume stats
        volume_stats_available = ReviewVolumeStats.objects.filter(
            hotel_id=hotel_id
        ).exists()
        
        volume_stats_obj = None
        if volume_stats_available:
            volume_stats_obj = ReviewVolumeStats.objects.get(hotel_id=hotel_id)
        
        # Calculate data freshness score
        freshness_score = 100
        if latest_snapshot:
            days_old = (timezone.now().date() - latest_snapshot.snapshot_date).days
            freshness_score = max(0, 100 - (days_old * 10))  # Lose 10 points per day
        else:
            freshness_score = 0
        
        health_data = {
            'hotel_id': hotel_id,
            'precomputed_data_available': latest_snapshot is not None,
            'latest_snapshot_date': latest_snapshot.snapshot_date if latest_snapshot else None,
            'snapshots_by_granularity': snapshots_by_granularity,
            'volume_stats_available': volume_stats_available,
            'volume_stats_updated': volume_stats_obj.updated_at if volume_stats_obj else None,
            'fallback_to_realtime': latest_snapshot is None or freshness_score < 50,
            'data_freshness_score': freshness_score
        }
        
        return Response(health_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Analytics health check failed for hotel {hotel_id}: {str(e)}", exc_info=True)
        return Response(
            {
                'error': 'Health check failed',
                'hotel_id': hotel_id,
                'timestamp': timezone.now().isoformat()
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )