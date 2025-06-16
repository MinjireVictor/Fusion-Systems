# Create this file: reviews/analytics_computer.py

import logging
from datetime import datetime, timedelta, date
from django.utils import timezone
from django.db.models import Count, Avg, Q
from django.db import transaction
from collections import defaultdict, Counter
from typing import List, Dict, Any, Optional
import time

from .models import Review, AnalysisResult, HotelAnalyticsSnapshot, ReviewVolumeStats, AnalyticsComputationLog

logger = logging.getLogger('reviews')


class AnalyticsComputer:
    """Handles pre-computation of analytics snapshots"""
    
    def __init__(self):
        self.computation_start_time = time.time()
        self.stats = {
            'hotels_processed': 0,
            'snapshots_created': 0,
            'snapshots_updated': 0,
            'errors': []
        }
    
    def compute_all_analytics(self, hotel_ids: Optional[List[str]] = None, force_recompute: bool = False):
        """Main entry point for computing analytics"""
        logger.info("Starting analytics computation")
        
        try:
            # Get hotels to process
            if hotel_ids:
                hotels = self._get_hotels_by_ids(hotel_ids)
            else:
                hotels = self._get_active_hotels()
            
            logger.info(f"Processing analytics for {len(hotels)} hotels")
            
            # Process each hotel
            for hotel_data in hotels:
                try:
                    self._compute_hotel_analytics(hotel_data, force_recompute)
                    self.stats['hotels_processed'] += 1
                except Exception as e:
                    error_msg = f"Failed to compute analytics for hotel {hotel_data['hotel_id']}: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    self.stats['errors'].append(error_msg)
            
            # Cleanup old snapshots
            self._cleanup_old_snapshots()
            
            # Log computation results
            self._log_computation_results()
            
            logger.info(f"Analytics computation completed. Processed {self.stats['hotels_processed']} hotels")
            
        except Exception as e:
            logger.error(f"Analytics computation failed: {str(e)}", exc_info=True)
            self._log_computation_results(status='failed', error_message=str(e))
            raise
    
    def _get_active_hotels(self) -> List[Dict[str, Any]]:
        """Get list of active hotels with recent reviews"""
        # Get hotels with reviews in the last 90 days
        recent_cutoff = timezone.now() - timedelta(days=90)
        
        hotels = Review.objects.filter(
            submission_date__gte=recent_cutoff
        ).values('hotel_id', 'hotel_name').annotate(
            review_count=Count('id')
        ).filter(review_count__gt=0)
        
        return list(hotels)
    
    def _get_hotels_by_ids(self, hotel_ids: List[str]) -> List[Dict[str, Any]]:
        """Get specific hotels by IDs"""
        hotels = Review.objects.filter(
            hotel_id__in=hotel_ids
        ).values('hotel_id', 'hotel_name').annotate(
            review_count=Count('id')
        ).filter(review_count__gt=0)
        
        return list(hotels)
    
    def _compute_hotel_analytics(self, hotel_data: Dict[str, Any], force_recompute: bool = False):
        """Compute analytics for a single hotel"""
        hotel_id = hotel_data['hotel_id']
        hotel_name = hotel_data['hotel_name']
        
        logger.debug(f"Computing analytics for hotel: {hotel_name} ({hotel_id})")
        
        current_time = timezone.now()
        current_date = current_time.date()
        
        # Determine what to compute based on current time and force flag
        compute_daily = True  # Always compute daily
        compute_weekly = current_time.weekday() == 6 or force_recompute  # Sunday
        compute_monthly = current_date.day == 1 or force_recompute  # 1st of month
        
        if compute_daily:
            self._compute_daily_snapshots(hotel_id, hotel_name, current_date)
        
        if compute_weekly:
            self._compute_weekly_snapshots(hotel_id, hotel_name, current_date)
            
        if compute_monthly:
            self._compute_monthly_snapshots(hotel_id, hotel_name, current_date)
        
        # Always compute volume stats (for ReviewMap)
        self._compute_volume_stats(hotel_id, hotel_name)
    
    def _compute_daily_snapshots(self, hotel_id: str, hotel_name: str, target_date: date):
        """Compute daily analytics snapshots"""
        # Compute for last 7 days
        for days_back in range(7):
            snapshot_date = target_date - timedelta(days=days_back)
            
            # Skip if already exists and not forcing
            if HotelAnalyticsSnapshot.objects.filter(
                hotel_id=hotel_id,
                snapshot_date=snapshot_date,
                granularity='daily'
            ).exists():
                continue
            
            analytics_data = self._compute_analytics_for_date_range(
                hotel_id, 
                hotel_name,
                snapshot_date, 
                snapshot_date
            )
            
            if analytics_data['review_count'] > 0:
                self._save_analytics_snapshot(
                    hotel_id, 
                    hotel_name, 
                    snapshot_date, 
                    'daily', 
                    analytics_data
                )
    
    def _compute_weekly_snapshots(self, hotel_id: str, hotel_name: str, target_date: date):
        """Compute weekly analytics snapshots"""
        # Compute for last 12 weeks
        for weeks_back in range(12):
            # Get start of week (Monday)
            days_to_subtract = (target_date.weekday() + 7 * weeks_back)
            week_start = target_date - timedelta(days=days_to_subtract)
            week_end = week_start + timedelta(days=6)
            
            # Skip if already exists
            if HotelAnalyticsSnapshot.objects.filter(
                hotel_id=hotel_id,
                snapshot_date=week_start,
                granularity='weekly'
            ).exists():
                continue
            
            analytics_data = self._compute_analytics_for_date_range(
                hotel_id,
                hotel_name, 
                week_start, 
                week_end
            )
            
            if analytics_data['review_count'] > 0:
                self._save_analytics_snapshot(
                    hotel_id, 
                    hotel_name, 
                    week_start, 
                    'weekly', 
                    analytics_data
                )
    
    def _compute_monthly_snapshots(self, hotel_id: str, hotel_name: str, target_date: date):
        """Compute monthly analytics snapshots"""
        # Compute for last 12 months
        for months_back in range(12):
            # Calculate month start
            if months_back == 0:
                month_start = target_date.replace(day=1)
            else:
                # Go back months_back months
                year = target_date.year
                month = target_date.month - months_back
                
                while month <= 0:
                    month += 12
                    year -= 1
                
                month_start = date(year, month, 1)
            
            # Calculate month end
            if month_start.month == 12:
                month_end = date(month_start.year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = date(month_start.year, month_start.month + 1, 1) - timedelta(days=1)
            
            # Skip if already exists
            if HotelAnalyticsSnapshot.objects.filter(
                hotel_id=hotel_id,
                snapshot_date=month_start,
                granularity='monthly'
            ).exists():
                continue
            
            analytics_data = self._compute_analytics_for_date_range(
                hotel_id, 
                hotel_name,
                month_start, 
                month_end
            )
            
            if analytics_data['review_count'] > 0:
                self._save_analytics_snapshot(
                    hotel_id, 
                    hotel_name, 
                    month_start, 
                    'monthly', 
                    analytics_data
                )
    
    def _compute_analytics_for_date_range(
        self, 
        hotel_id: str, 
        hotel_name: str,
        start_date: date, 
        end_date: date
    ) -> Dict[str, Any]:
        """Compute analytics for a specific date range"""
        
        # Get reviews for the date range
        reviews = Review.objects.filter(
            hotel_id=hotel_id,
            submission_date__date__gte=start_date,
            submission_date__date__lte=end_date
        ).select_related('analysis')
        
        if not reviews.exists():
            return self._empty_analytics_data()
        
        # Basic metrics
        review_count = reviews.count()
        average_rating = reviews.aggregate(Avg('rating'))['rating__avg']
        
        # Rating distribution
        rating_distribution = {}
        for rating in [1, 2, 3, 4, 5]:
            count = reviews.filter(rating=rating).count()
            if count > 0:
                rating_distribution[str(rating)] = count
        
        # Sentiment and topic analysis
        sentiment_distribution = defaultdict(int)
        topic_distribution = defaultdict(int)
        
        analyzed_reviews = reviews.filter(analysis__isnull=False)
        for review in analyzed_reviews:
            if hasattr(review, 'analysis'):
                sentiment_distribution[review.analysis.primary_sentiment] += 1
                topic_distribution[review.analysis.primary_topic] += 1
        
        return {
            'review_count': review_count,
            'average_rating': float(average_rating) if average_rating else None,
            'rating_distribution': dict(rating_distribution),
            'sentiment_distribution': dict(sentiment_distribution),
            'topic_distribution': dict(topic_distribution)
        }
    
    def _empty_analytics_data(self) -> Dict[str, Any]:
        """Return empty analytics data structure"""
        return {
            'review_count': 0,
            'average_rating': None,
            'rating_distribution': {},
            'sentiment_distribution': {},
            'topic_distribution': {}
        }
    
    def _save_analytics_snapshot(
        self, 
        hotel_id: str, 
        hotel_name: str, 
        snapshot_date: date, 
        granularity: str, 
        analytics_data: Dict[str, Any]
    ):
        """Save analytics snapshot to database"""
        try:
            snapshot, created = HotelAnalyticsSnapshot.objects.update_or_create(
                hotel_id=hotel_id,
                snapshot_date=snapshot_date,
                granularity=granularity,
                defaults={
                    'hotel_name': hotel_name,
                    'review_count': analytics_data['review_count'],
                    'average_rating': analytics_data['average_rating'],
                    'rating_distribution': analytics_data['rating_distribution'],
                    'sentiment_distribution': analytics_data['sentiment_distribution'],
                    'topic_distribution': analytics_data['topic_distribution'],
                }
            )
            
            if created:
                self.stats['snapshots_created'] += 1
                logger.debug(f"Created {granularity} snapshot for {hotel_name} on {snapshot_date}")
            else:
                self.stats['snapshots_updated'] += 1
                logger.debug(f"Updated {granularity} snapshot for {hotel_name} on {snapshot_date}")
                
        except Exception as e:
            error_msg = f"Failed to save {granularity} snapshot for {hotel_name}: {str(e)}"
            logger.error(error_msg)
            self.stats['errors'].append(error_msg)
    
    def _compute_volume_stats(self, hotel_id: str, hotel_name: str):
        """Compute volume statistics for ReviewMap component"""
        try:
            current_date = timezone.now().date()
            
            # This month stats
            month_start = current_date.replace(day=1)
            this_month_reviews = Review.objects.filter(
                hotel_id=hotel_id,
                submission_date__date__gte=month_start
            )
            this_month_total = this_month_reviews.count()
            
            # Last 7 days daily data
            daily_data = []
            for days_back in range(6, -1, -1):  # 6 days ago to today
                day = current_date - timedelta(days=days_back)
                day_count = Review.objects.filter(
                    hotel_id=hotel_id,
                    submission_date__date=day
                ).count()
                daily_data.append(day_count)
            
            # Growth vs last month
            last_month_start = (month_start - timedelta(days=1)).replace(day=1)
            last_month_end = month_start - timedelta(days=1)
            last_month_total = Review.objects.filter(
                hotel_id=hotel_id,
                submission_date__date__gte=last_month_start,
                submission_date__date__lte=last_month_end
            ).count()
            
            this_month_growth = None
            if last_month_total > 0:
                this_month_growth = ((this_month_total - last_month_total) / last_month_total) * 100
            
            # All time stats - last 7 months
            all_time_total = Review.objects.filter(hotel_id=hotel_id).count()
            
            monthly_data = []
            for months_back in range(6, -1, -1):  # 6 months ago to this month
                if months_back == 0:
                    target_month_start = month_start
                else:
                    year = current_date.year
                    month = current_date.month - months_back
                    
                    while month <= 0:
                        month += 12
                        year -= 1
                    
                    target_month_start = date(year, month, 1)
                
                # Month end
                if target_month_start.month == 12:
                    target_month_end = date(target_month_start.year + 1, 1, 1) - timedelta(days=1)
                else:
                    target_month_end = date(target_month_start.year, target_month_start.month + 1, 1) - timedelta(days=1)
                
                month_count = Review.objects.filter(
                    hotel_id=hotel_id,
                    submission_date__date__gte=target_month_start,
                    submission_date__date__lte=target_month_end
                ).count()
                monthly_data.append(month_count)
            
            # Growth calculation for all time (comparing recent 7 months vs previous 7 months)
            seven_months_ago = current_date - timedelta(days=210)  # Approximately 7 months
            fourteen_months_ago = current_date - timedelta(days=420)  # Approximately 14 months
            
            recent_7_months = Review.objects.filter(
                hotel_id=hotel_id,
                submission_date__date__gte=seven_months_ago
            ).count()
            
            previous_7_months = Review.objects.filter(
                hotel_id=hotel_id,
                submission_date__date__gte=fourteen_months_ago,
                submission_date__date__lt=seven_months_ago
            ).count()
            
            all_time_growth = None
            if previous_7_months > 0:
                all_time_growth = ((recent_7_months - previous_7_months) / previous_7_months) * 100
            
            # Save volume stats
            volume_stats, created = ReviewVolumeStats.objects.update_or_create(
                hotel_id=hotel_id,
                defaults={
                    'hotel_name': hotel_name,
                    'this_month_total': this_month_total,
                    'this_month_daily_data': daily_data,
                    'this_month_growth': this_month_growth,
                    'all_time_total': all_time_total,
                    'all_time_monthly_data': monthly_data,
                    'all_time_growth': all_time_growth,
                }
            )
            
            if created:
                logger.debug(f"Created volume stats for {hotel_name}")
            else:
                logger.debug(f"Updated volume stats for {hotel_name}")
                
        except Exception as e:
            error_msg = f"Failed to compute volume stats for {hotel_name}: {str(e)}"
            logger.error(error_msg)
            self.stats['errors'].append(error_msg)
    
    def _cleanup_old_snapshots(self):
        """Clean up old analytics snapshots"""
        try:
            HotelAnalyticsSnapshot.cleanup_old_snapshots()
            logger.info("Cleaned up old analytics snapshots")
        except Exception as e:
            logger.error(f"Failed to cleanup old snapshots: {str(e)}")
    
    def _log_computation_results(self, status: str = 'success', error_message: str = ''):
        """Log the computation results"""
        processing_time = time.time() - self.computation_start_time
        
        # Determine final status
        if self.stats['errors']:
            if self.stats['hotels_processed'] > 0:
                status = 'partial'
            else:
                status = 'failed'
        
        if error_message and self.stats['errors']:
            error_message = f"{error_message}\nErrors: {'; '.join(self.stats['errors'][:5])}"  # First 5 errors
        elif self.stats['errors']:
            error_message = '; '.join(self.stats['errors'][:5])
        
        try:
            AnalyticsComputationLog.objects.create(
                hotels_processed=self.stats['hotels_processed'],
                snapshots_created=self.stats['snapshots_created'],
                snapshots_updated=self.stats['snapshots_updated'],
                processing_time_seconds=processing_time,
                status=status,
                error_message=error_message
            )
        except Exception as e:
            logger.error(f"Failed to log computation results: {str(e)}")


# Convenience function for use in management commands
def compute_analytics(hotel_ids: Optional[List[str]] = None, force_recompute: bool = False):
    """Convenience function to compute analytics"""
    computer = AnalyticsComputer()
    computer.compute_all_analytics(hotel_ids=hotel_ids, force_recompute=force_recompute)