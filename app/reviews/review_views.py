from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from django.conf import settings
from rest_framework.response import Response
from django.db.models import Avg, Count, Q
from django.utils import timezone
from datetime import timedelta
from collections import defaultdict
import logging
from django.core.management import call_command
import json

from .models import Review, AnalysisResult, AnalysisBatch
from .serializers import (
    ReviewSerializer,
    ReviewWithAnalysisSerializer,
    AnalysisResultSerializer,
    HotelAnalyticsSummarySerializer,
    AnalysisBatchSerializer,
    BulkReviewSubmissionSerializer,
    ReviewAnalysisRequestSerializer
)

logger = logging.getLogger(__name__)


class ReviewViewSet(viewsets.ModelViewSet):
    """ViewSet for managing hotel reviews"""
    
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer
    permission_classes = [permissions.AllowAny]  # Public endpoint
    
    def get_queryset(self):
        """Filter reviews based on query parameters"""
        queryset = Review.objects.all()
        
        # Filter by hotel
        hotel_id = self.request.query_params.get('hotel_id')
        if hotel_id:
            queryset = queryset.filter(hotel_id=hotel_id)
        
        # Filter by rating
        min_rating = self.request.query_params.get('min_rating')
        if min_rating:
            queryset = queryset.filter(rating__gte=float(min_rating))
        
        max_rating = self.request.query_params.get('max_rating')
        if max_rating:
            queryset = queryset.filter(rating__lte=float(max_rating))
        
        # Filter by date range
        date_from = self.request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(submission_date__gte=date_from)
        
        date_to = self.request.query_params.get('date_to')
        if date_to:
            queryset = queryset.filter(submission_date__lte=date_to)
        
        # Filter by analysis status
        has_analysis = self.request.query_params.get('has_analysis')
        if has_analysis is not None:
            if has_analysis.lower() == 'true':
                queryset = queryset.filter(analysisresult__isnull=False)
            else:
                queryset = queryset.filter(analysisresult__isnull=True)
        
        return queryset.order_by('-submission_date')
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'with_analysis':
            return ReviewWithAnalysisSerializer
        return self.serializer_class
    
    def create(self, request, *args, **kwargs):
        """Create a new review with enhanced validation"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Log review submission
        logger.info(f"New review submitted for hotel {serializer.validated_data['hotel_id']}")
        
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        
        return Response(
            {
                'message': 'Review submitted successfully',
                'review': serializer.data
            },
            status=status.HTTP_201_CREATED,
            headers=headers
        )
    
    @action(detail=False, methods=['post'])
    def bulk_submit(self, request):
        """Submit multiple reviews at once"""
        serializer = BulkReviewSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        result = serializer.save()
        reviews = result['reviews']
        
        logger.info(f"Bulk submission: {len(reviews)} reviews created")
        
        return Response(
            {
                'message': f'{len(reviews)} reviews submitted successfully',
                'review_ids': [review.id for review in reviews]
            },
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=False, methods=['get'])
    def with_analysis(self, request):
        """Get reviews with their analysis results"""
        queryset = self.filter_queryset(self.get_queryset())
        queryset = queryset.select_related('analysisresult')
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def analytics_summary(self, request):
        """Get analytics summary for a hotel"""
        hotel_id = request.query_params.get('hotel_id')
        if not hotel_id:
            return Response(
                {'error': 'hotel_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get date range (default to last 30 days)
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        
        if not date_from:
            date_from = timezone.now() - timedelta(days=30)
        if not date_to:
            date_to = timezone.now()
        
        # Get reviews for the hotel
        reviews = Review.objects.filter(
            hotel_id=hotel_id,
            submission_date__range=[date_from, date_to]
        )
        
        if not reviews.exists():
            return Response(
                {'error': f'No reviews found for hotel {hotel_id}'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Calculate basic stats
        total_reviews = reviews.count()
        average_rating = reviews.aggregate(Avg('rating'))['rating__avg']
        
        # Get sentiment distribution
        sentiment_distribution = defaultdict(int)
        topic_distribution = defaultdict(int)
        processed_count = 0
        
        for review in reviews.select_related('analysisresult'):
            if hasattr(review, 'analysisresult'):
                processed_count += 1
                analysis = review.analysisresult
                sentiment_distribution[analysis.primary_sentiment] += 1
                topic_distribution[analysis.primary_topic] += 1
        
        # Prepare response data
        summary_data = {
            'hotel_id': hotel_id,
            'hotel_name': reviews.first().hotel_name,
            'total_reviews': total_reviews,
            'average_rating': round(average_rating, 2) if average_rating else 0,
            'sentiment_distribution': dict(sentiment_distribution),
            'topic_distribution': dict(topic_distribution),
            'recent_reviews_count': reviews.filter(
                submission_date__gte=timezone.now() - timedelta(days=7)
            ).count(),
            'processed_reviews_count': processed_count,
            'date_range': {
                'from': date_from,
                'to': date_to
            }
        }
        
        serializer = HotelAnalyticsSummarySerializer(summary_data)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def request_analysis(self, request):
        """Manually request analysis for specific reviews"""
        serializer = ReviewAnalysisRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        review_ids = serializer.validated_data['review_ids']
        priority = serializer.validated_data['priority']
        
        # This would trigger the Modal service call
        # For now, we'll just log the request
        logger.info(f"Manual analysis requested for reviews {review_ids} with priority {priority}")
        
        return Response(
            {
                'message': f'Analysis requested for {len(review_ids)} reviews',
                'review_ids': review_ids,
                'priority': priority
            },
            status=status.HTTP_202_ACCEPTED
        )
    
    @action(detail=True, methods=['get'])
    def analysis(self, request, pk=None):
        """Get analysis result for a specific review"""
        review = self.get_object()
        
        if not hasattr(review, 'analysisresult'):
            return Response(
                {'error': 'Analysis not available for this review'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = AnalysisResultSerializer(review.analysisresult)
        return Response(serializer.data)


class AnalysisBatchViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing analysis batch status"""
    
    queryset = AnalysisBatch.objects.all()
    serializer_class = AnalysisBatchSerializer
    permission_classes = [permissions.AllowAny]  # Can be restricted later
    
    def get_queryset(self):
        """Filter batches based on query parameters"""
        queryset = AnalysisBatch.objects.all()
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by date range
        date_from = self.request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(created_date__gte=date_from)
        
        return queryset.order_by('-created_date')
    
    @action(detail=False, methods=['get'])
    def latest(self, request):
        """Get the latest batch processing status"""
        try:
            latest_batch = AnalysisBatch.objects.latest('created_date')
            serializer = self.get_serializer(latest_batch)
            return Response(serializer.data)
        except AnalysisBatch.DoesNotExist:
            return Response(
                {'message': 'No batch processing history found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get overall batch processing statistics"""
        batches = AnalysisBatch.objects.all()
        
        if not batches.exists():
            return Response({'message': 'No batch processing data available'})
        
        stats = {
            'total_batches': batches.count(),
            'successful_batches': batches.filter(status='completed').count(),
            'failed_batches': batches.filter(status='failed').count(),
            'total_reviews_processed': sum(batch.processed_reviews for batch in batches),
            'average_processing_time': batches.filter(
                processing_time_seconds__isnull=False
            ).aggregate(Avg('processing_time_seconds'))['processing_time_seconds__avg'],
            'latest_batch_date': batches.latest('created_date').created_date if batches.exists() else None
        }
        
        return Response(stats)

@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """Health check endpoint for the reviews service"""
    try:
        # Check database connectivity
        review_count = Review.objects.count()
        analysis_count = AnalysisResult.objects.count()
        
        # Check latest batch status
        latest_batch = None
        try:
            latest_batch = AnalysisBatch.objects.latest('created_date')
        except AnalysisBatch.DoesNotExist:
            pass
        
        health_data = {
            'status': 'healthy',
            'timestamp': timezone.now().isoformat(),
            'database': {
                'connected': True,
                'total_reviews': review_count,
                'analyzed_reviews': analysis_count,
                'analysis_coverage': f"{(analysis_count/review_count*100):.1f}%" if review_count > 0 else "0%"
            },
            'latest_batch': {
                'id': latest_batch.batch_id if latest_batch else None,
                'status': latest_batch.status if latest_batch else None,
                'created': latest_batch.created_date.isoformat() if latest_batch else None
            } if latest_batch else None,
            'settings': {
                'cron_interval_minutes': settings.REVIEW_ANALYSIS_SETTINGS['CRON_INTERVAL_MINUTES'],
                'batch_size': settings.REVIEW_ANALYSIS_SETTINGS['BATCH_SIZE'],
                'debug': settings.DEBUG
            }
        }
        
        return Response(health_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return Response(
            {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': timezone.now().isoformat()
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )


@api_view(['POST'])
@permission_classes([AllowAny])  # Can be restricted to admin users later
def trigger_manual_analysis(request):
    """Manually trigger the review analysis process"""
    try:
        # Parse request parameters
        force = request.data.get('force', False)
        hotel_id = request.data.get('hotel_id')
        batch_size = request.data.get('batch_size', settings.REVIEW_ANALYSIS_SETTINGS['BATCH_SIZE'])
        max_age_hours = request.data.get('max_age_hours', settings.REVIEW_ANALYSIS_SETTINGS['MAX_AGE_HOURS'])
        
        logger.info(f"Manual analysis triggered by user with params: force={force}, hotel_id={hotel_id}")
        
        # Build command arguments
        command_args = [
            f'--batch-size={batch_size}',
            f'--max-age-hours={max_age_hours}'
        ]
        
        if force:
            command_args.append('--force')
        
        if hotel_id:
            command_args.append(f'--hotel-id={hotel_id}')
        
        # Call the management command
        try:
            call_command('process_reviews', *command_args)
            
            return Response(
                {
                    'success': True,
                    'message': 'Analysis process triggered successfully',
                    'parameters': {
                        'force': force,
                        'hotel_id': hotel_id,
                        'batch_size': batch_size,
                        'max_age_hours': max_age_hours
                    },
                    'timestamp': timezone.now().isoformat()
                },
                status=status.HTTP_202_ACCEPTED
            )
            
        except Exception as cmd_error:
            logger.error(f"Management command failed: {str(cmd_error)}")
            return Response(
                {
                    'success': False,
                    'error': f'Analysis process failed: {str(cmd_error)}',
                    'timestamp': timezone.now().isoformat()
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
    except Exception as e:
        logger.error(f"Manual analysis trigger failed: {str(e)}")
        return Response(
            {
                'success': False,
                'error': str(e),
                'timestamp': timezone.now().isoformat()
            },
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def analysis_dashboard(request):
    """Get dashboard data for analysis overview"""
    try:
        # Get basic stats
        total_reviews = Review.objects.count()
        analyzed_reviews = AnalysisResult.objects.count()
        pending_reviews = total_reviews - analyzed_reviews
        
        # Get recent activity (last 24 hours)
        recent_cutoff = timezone.now() - timezone.timedelta(hours=24)
        recent_reviews = Review.objects.filter(submission_date__gte=recent_cutoff).count()
        recent_analysis = AnalysisResult.objects.filter(processed_date__gte=recent_cutoff).count()
        
        # Get sentiment distribution
        sentiment_stats = {}
        for result in AnalysisResult.objects.all():
            sentiment = result.primary_sentiment
            sentiment_stats[sentiment] = sentiment_stats.get(sentiment, 0) + 1
        
        # Get topic distribution
        topic_stats = {}
        for result in AnalysisResult.objects.all():
            topic = result.primary_topic
            topic_stats[topic] = topic_stats.get(topic, 0) + 1
        
        # Get batch statistics
        batches = AnalysisBatch.objects.all()
        batch_stats = {
            'total_batches': batches.count(),
            'successful_batches': batches.filter(status='completed').count(),
            'failed_batches': batches.filter(status='failed').count(),
            'pending_batches': batches.filter(status__in=['pending', 'processing']).count()
        }
        
        # Get hotel breakdown
        hotel_stats = {}
        for review in Review.objects.select_related('analysisresult'):
            hotel_key = f"{review.hotel_name} ({review.hotel_id})"
            if hotel_key not in hotel_stats:
                hotel_stats[hotel_key] = {
                    'total_reviews': 0,
                    'analyzed_reviews': 0,
                    'average_rating': 0,
                    'rating_sum': 0
                }
            
            hotel_stats[hotel_key]['total_reviews'] += 1
            hotel_stats[hotel_key]['rating_sum'] += float(review.rating)
            
            if hasattr(review, 'analysisresult'):
                hotel_stats[hotel_key]['analyzed_reviews'] += 1
        
        # Calculate averages
        for hotel, stats in hotel_stats.items():
            if stats['total_reviews'] > 0:
                stats['average_rating'] = round(stats['rating_sum'] / stats['total_reviews'], 2)
                stats['analysis_coverage'] = round((stats['analyzed_reviews'] / stats['total_reviews']) * 100, 1)
            del stats['rating_sum']  # Remove temporary field
        
        dashboard_data = {
            'overview': {
                'total_reviews': total_reviews,
                'analyzed_reviews': analyzed_reviews,
                'pending_reviews': pending_reviews,
                'analysis_coverage_percent': round((analyzed_reviews / total_reviews) * 100, 1) if total_reviews > 0 else 0
            },
            'recent_activity': {
                'new_reviews_24h': recent_reviews,
                'analyzed_24h': recent_analysis,
                'timestamp': timezone.now().isoformat()
            },
            'sentiment_distribution': sentiment_stats,
            'topic_distribution': dict(sorted(topic_stats.items(), key=lambda x: x[1], reverse=True)[:10]),  # Top 10 topics
            'batch_statistics': batch_stats,
            'hotel_breakdown': hotel_stats,
            'last_updated': timezone.now().isoformat()
        }
        
        return Response(dashboard_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Dashboard data retrieval failed: {str(e)}")
        return Response(
            {
                'error': str(e),
                'timestamp': timezone.now().isoformat()
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def hotel_insights(request, hotel_id):
    """Get detailed insights for a specific hotel"""
    try:
        # Get all reviews for the hotel
        reviews = Review.objects.filter(hotel_id=hotel_id)
        
        if not reviews.exists():
            return Response(
                {'error': f'No reviews found for hotel {hotel_id}'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Basic statistics
        total_reviews = reviews.count()
        analyzed_reviews = reviews.filter(analysisresult__isnull=False)
        analyzed_count = analyzed_reviews.count()
        
        # Rating statistics
        ratings = [float(r.rating) for r in reviews]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0
        rating_distribution = {}
        for rating in ratings:
            rating_key = str(int(rating))
            rating_distribution[rating_key] = rating_distribution.get(rating_key, 0) + 1
        
        # Sentiment analysis
        sentiment_stats = {}
        sentiment_by_rating = {}
        
        for review in analyzed_reviews:
            analysis = review.analysisresult
            sentiment = analysis.primary_sentiment
            rating_key = str(int(review.rating))
            
            # Overall sentiment stats
            sentiment_stats[sentiment] = sentiment_stats.get(sentiment, 0) + 1
            
            # Sentiment by rating
            if rating_key not in sentiment_by_rating:
                sentiment_by_rating[rating_key] = {}
            sentiment_by_rating[rating_key][sentiment] = sentiment_by_rating[rating_key].get(sentiment, 0) + 1
        
        # Topic analysis
        topic_stats = {}
        topic_by_rating = {}
        
        for review in analyzed_reviews:
            analysis = review.analysisresult
            topic = analysis.primary_topic
            rating_key = str(int(review.rating))
            
            # Overall topic stats
            topic_stats[topic] = topic_stats.get(topic, 0) + 1
            
            # Topics by rating
            if rating_key not in topic_by_rating:
                topic_by_rating[rating_key] = {}
            topic_by_rating[rating_key][topic] = topic_by_rating[rating_key].get(topic, 0) + 1
        
        # Recent trends (last 30 days)
        recent_cutoff = timezone.now() - timezone.timedelta(days=30)
        recent_reviews = reviews.filter(submission_date__gte=recent_cutoff)
        recent_avg_rating = sum(float(r.rating) for r in recent_reviews) / recent_reviews.count() if recent_reviews.exists() else 0
        
        insights_data = {
            'hotel_info': {
                'hotel_id': hotel_id,
                'hotel_name': reviews.first().hotel_name,
                'total_reviews': total_reviews,
                'analyzed_reviews': analyzed_count,
                'analysis_coverage': round((analyzed_count / total_reviews) * 100, 1) if total_reviews > 0 else 0
            },
            'rating_statistics': {
                'average_rating': round(avg_rating, 2),
                'rating_distribution': rating_distribution,
                'recent_average_rating': round(recent_avg_rating, 2),
                'recent_reviews_count': recent_reviews.count()
            },
            'sentiment_analysis': {
                'overall_distribution': sentiment_stats,
                'by_rating': sentiment_by_rating
            },
            'topic_analysis': {
                'overall_distribution': dict(sorted(topic_stats.items(), key=lambda x: x[1], reverse=True)),
                'by_rating': topic_by_rating
            },
            'recommendations': self.generate_hotel_recommendations(sentiment_stats, topic_stats, avg_rating),
            'last_updated': timezone.now().isoformat()
        }
        
        return Response(insights_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Hotel insights retrieval failed for {hotel_id}: {str(e)}")
        return Response(
            {
                'error': str(e),
                'hotel_id': hotel_id,
                'timestamp': timezone.now().isoformat()
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def generate_hotel_recommendations(sentiment_stats, topic_stats, avg_rating):
    """Generate actionable recommendations based on analysis"""
    recommendations = []
    
    # Rating-based recommendations
    if avg_rating < 3.0:
        recommendations.append({
            'type': 'urgent',
            'category': 'overall_experience',
            'message': 'Average rating is below 3.0. Immediate attention required to address guest satisfaction issues.'
        })
    elif avg_rating < 3.5:
        recommendations.append({
            'type': 'important',
            'category': 'overall_experience', 
            'message': 'Average rating could be improved. Focus on addressing common guest complaints.'
        })
    
    # Sentiment-based recommendations
    negative_sentiment = sentiment_stats.get('negative', 0)
    total_analyzed = sum(sentiment_stats.values()) if sentiment_stats else 1
    negative_percentage = (negative_sentiment / total_analyzed) * 100
    
    if negative_percentage > 30:
        recommendations.append({
            'type': 'urgent',
            'category': 'sentiment',
            'message': f'{negative_percentage:.1f}% of reviews are negative. Focus on improving guest experience.'
        })
    elif negative_percentage > 20:
        recommendations.append({
            'type': 'important',
            'category': 'sentiment',
            'message': f'{negative_percentage:.1f}% of reviews are negative. Monitor guest feedback closely.'
        })
    
    # Topic-based recommendations
    if topic_stats:
        top_issues = sorted(topic_stats.items(), key=lambda x: x[1], reverse=True)[:3]
        
        problem_topics = ['cleanliness', 'noise', 'maintenance', 'bathroom']
        for topic, count in top_issues:
            if topic in problem_topics:
                recommendations.append({
                    'type': 'actionable',
                    'category': 'operations',
                    'message': f'{topic.title()} is frequently mentioned ({count} times). Consider operational improvements.'
                })
    
    return recommendations