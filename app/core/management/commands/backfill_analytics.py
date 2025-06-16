# Create this file: reviews/management/commands/backfill_analytics.py

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import datetime, timedelta
import logging

from reviews.analytics_computer import compute_analytics
from reviews.models import Review, HotelAnalyticsSnapshot, ReviewVolumeStats

logger = logging.getLogger('reviews')


class Command(BaseCommand):
    help = 'Backfill analytics snapshots for historical data'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--days-back',
            type=int,
            default=365,
            help='Number of days to backfill (default: 365)'
        )
        parser.add_argument(
            '--hotel-id',
            type=str,
            help='Only backfill for specific hotel ID'
        )
        parser.add_argument(
            '--chunk-size',
            type=int,
            default=30,
            help='Process this many days at a time (default: 30)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be backfilled without actually processing'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recomputation of existing snapshots'
        )
        parser.add_argument(
            '--granularity',
            type=str,
            choices=['daily', 'weekly', 'monthly', 'all'],
            default='all',
            help='Which granularity to backfill (default: all)'
        )
    
    def handle(self, *args, **options):
        """Main command handler"""
        days_back = options['days_back']
        hotel_id = options['hotel_id']
        chunk_size = options['chunk_size']
        dry_run = options['dry_run']
        force = options['force']
        granularity = options['granularity']
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Starting analytics backfill - {days_back} days back"
            )
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN - No actual processing will occur")
            )
        
        try:
            # Get hotels to process
            hotels = self._get_hotels_to_process(hotel_id, days_back)
            
            if not hotels:
                self.stdout.write(
                    self.style.WARNING("No hotels found with reviews in the specified period")
                )
                return
            
            self.stdout.write(f"Found {len(hotels)} hotels to process")
            
            # Show what would be processed
            if dry_run:
                self._show_backfill_plan(hotels, days_back, granularity)
                return
            
            # Process each hotel
            total_snapshots_created = 0
            total_snapshots_updated = 0
            
            for hotel_data in hotels:
                hotel_id_current = hotel_data['hotel_id']
                hotel_name = hotel_data['hotel_name']
                
                self.stdout.write(f"\nProcessing hotel: {hotel_name} ({hotel_id_current})")
                
                created, updated = self._backfill_hotel_analytics(
                    hotel_id_current,
                    hotel_name,
                    days_back,
                    chunk_size,
                    force,
                    granularity
                )
                
                total_snapshots_created += created
                total_snapshots_updated += updated
                
                self.stdout.write(
                    f"  Hotel completed: {created} created, {updated} updated"
                )
            
            # Summary
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nBackfill completed! "
                    f"Total snapshots created: {total_snapshots_created}, "
                    f"Total snapshots updated: {total_snapshots_updated}"
                )
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Backfill failed: {str(e)}")
            )
            logger.error(f"Backfill failed: {str(e)}", exc_info=True)
            raise CommandError(f"Backfill failed: {e}")
    
    def _get_hotels_to_process(self, hotel_id, days_back):
        """Get list of hotels that have reviews in the specified period"""
        cutoff_date = timezone.now() - timedelta(days=days_back)
        
        if hotel_id:
            hotels = Review.objects.filter(
                hotel_id=hotel_id,
                submission_date__gte=cutoff_date
            ).values('hotel_id', 'hotel_name').distinct()
        else:
            hotels = Review.objects.filter(
                submission_date__gte=cutoff_date
            ).values('hotel_id', 'hotel_name').distinct()
        
        return list(hotels)
    
    def _show_backfill_plan(self, hotels, days_back, granularity):
        """Show what would be backfilled in dry run mode"""
        self.stdout.write("\nBackfill Plan:")
        self.stdout.write(f"Period: Last {days_back} days")
        self.stdout.write(f"Granularity: {granularity}")
        self.stdout.write(f"Hotels to process: {len(hotels)}")
        
        # Estimate snapshots that would be created
        total_estimates = {}
        
        for hotel_data in hotels:
            hotel_id = hotel_data['hotel_id']
            hotel_name = hotel_data['hotel_name']
            
            # Get review count for this hotel
            cutoff_date = timezone.now() - timedelta(days=days_back)
            review_count = Review.objects.filter(
                hotel_id=hotel_id,
                submission_date__gte=cutoff_date
            ).count()
            
            # Estimate snapshots for each granularity
            estimates = self._estimate_snapshots(days_back, granularity)
            
            self.stdout.write(f"\n  {hotel_name} ({hotel_id}):")
            self.stdout.write(f"    Reviews in period: {review_count}")
            
            for gran, count in estimates.items():
                existing = HotelAnalyticsSnapshot.objects.filter(
                    hotel_id=hotel_id,
                    granularity=gran
                ).count()
                
                self.stdout.write(f"    {gran.title()} snapshots: ~{count} (existing: {existing})")
                
                if gran not in total_estimates:
                    total_estimates[gran] = 0
                total_estimates[gran] += count
        
        self.stdout.write(f"\nTotal estimated snapshots to create:")
        for gran, count in total_estimates.items():
            self.stdout.write(f"  {gran.title()}: ~{count}")
    
    def _estimate_snapshots(self, days_back, granularity):
        """Estimate number of snapshots that would be created"""
        estimates = {}
        
        if granularity == 'all' or granularity == 'daily':
            estimates['daily'] = min(days_back, 90)  # Max 90 days for daily
        
        if granularity == 'all' or granularity == 'weekly':
            estimates['weekly'] = min(days_back // 7, 52)  # Max 52 weeks
        
        if granularity == 'all' or granularity == 'monthly':
            estimates['monthly'] = min(days_back // 30, 24)  # Max 24 months
        
        return estimates
    
    def _backfill_hotel_analytics(self, hotel_id, hotel_name, days_back, chunk_size, force, granularity):
        """Backfill analytics for a single hotel"""
        snapshots_created = 0
        snapshots_updated = 0
        
        try:
            # Import the analytics computer
            from reviews.analytics_computer import AnalyticsComputer
            
            # Create computer instance
            computer = AnalyticsComputer()
            
            # Calculate date range for backfill
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=days_back)
            
            # Process in chunks to avoid memory issues
            current_date = start_date
            
            while current_date <= end_date:
                chunk_end = min(current_date + timedelta(days=chunk_size), end_date)
                
                self.stdout.write(
                    f"    Processing chunk: {current_date} to {chunk_end}"
                )
                
                # Backfill for this chunk
                created, updated = self._backfill_date_range(
                    computer,
                    hotel_id,
                    hotel_name,
                    current_date,
                    chunk_end,
                    force,
                    granularity
                )
                
                snapshots_created += created
                snapshots_updated += updated
                
                # Move to next chunk
                current_date = chunk_end + timedelta(days=1)
            
            # Also compute volume stats
            computer._compute_volume_stats(hotel_id, hotel_name)
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"    Failed to backfill {hotel_name}: {str(e)}")
            )
            logger.error(f"Backfill failed for {hotel_name}: {str(e)}", exc_info=True)
        
        return snapshots_created, snapshots_updated
    
    def _backfill_date_range(self, computer, hotel_id, hotel_name, start_date, end_date, force, granularity):
        """Backfill analytics for a specific date range"""
        snapshots_created = 0
        snapshots_updated = 0
        
        # Daily snapshots
        if granularity == 'all' or granularity == 'daily':
            created, updated = self._backfill_daily_snapshots(
                computer, hotel_id, hotel_name, start_date, end_date, force
            )
            snapshots_created += created
            snapshots_updated += updated
        
        # Weekly snapshots
        if granularity == 'all' or granularity == 'weekly':
            created, updated = self._backfill_weekly_snapshots(
                computer, hotel_id, hotel_name, start_date, end_date, force
            )
            snapshots_created += created
            snapshots_updated += updated
        
        # Monthly snapshots
        if granularity == 'all' or granularity == 'monthly':
            created, updated = self._backfill_monthly_snapshots(
                computer, hotel_id, hotel_name, start_date, end_date, force
            )
            snapshots_created += created
            snapshots_updated += updated
        
        return snapshots_created, snapshots_updated
    
    def _backfill_daily_snapshots(self, computer, hotel_id, hotel_name, start_date, end_date, force):
        """Backfill daily snapshots for date range"""
        created = 0
        updated = 0
        
        current_date = start_date
        while current_date <= end_date:
            # Skip if already exists and not forcing
            if not force and HotelAnalyticsSnapshot.objects.filter(
                hotel_id=hotel_id,
                snapshot_date=current_date,
                granularity='daily'
            ).exists():
                current_date += timedelta(days=1)
                continue
            
            # Compute analytics for this day
            analytics_data = computer._compute_analytics_for_date_range(
                hotel_id, hotel_name, current_date, current_date
            )
            
            if analytics_data['review_count'] > 0:
                snapshot, was_created = HotelAnalyticsSnapshot.objects.update_or_create(
                    hotel_id=hotel_id,
                    snapshot_date=current_date,
                    granularity='daily',
                    defaults={
                        'hotel_name': hotel_name,
                        'review_count': analytics_data['review_count'],
                        'average_rating': analytics_data['average_rating'],
                        'rating_distribution': analytics_data['rating_distribution'],
                        'sentiment_distribution': analytics_data['sentiment_distribution'],
                        'topic_distribution': analytics_data['topic_distribution'],
                    }
                )
                
                if was_created:
                    created += 1
                else:
                    updated += 1
            
            current_date += timedelta(days=1)
        
        return created, updated
    
    def _backfill_weekly_snapshots(self, computer, hotel_id, hotel_name, start_date, end_date, force):
        """Backfill weekly snapshots for date range"""
        created = 0
        updated = 0
        
        # Find first Monday in the range
        current_date = start_date
        while current_date.weekday() != 0:  # 0 = Monday
            current_date += timedelta(days=1)
            if current_date > end_date:
                return created, updated
        
        # Process weekly chunks
        while current_date <= end_date:
            week_end = current_date + timedelta(days=6)  # Sunday
            
            # Skip if already exists and not forcing
            if not force and HotelAnalyticsSnapshot.objects.filter(
                hotel_id=hotel_id,
                snapshot_date=current_date,
                granularity='weekly'
            ).exists():
                current_date += timedelta(days=7)
                continue
            
            # Compute analytics for this week
            analytics_data = computer._compute_analytics_for_date_range(
                hotel_id, hotel_name, current_date, min(week_end, end_date)
            )
            
            if analytics_data['review_count'] > 0:
                snapshot, was_created = HotelAnalyticsSnapshot.objects.update_or_create(
                    hotel_id=hotel_id,
                    snapshot_date=current_date,
                    granularity='weekly',
                    defaults={
                        'hotel_name': hotel_name,
                        'review_count': analytics_data['review_count'],
                        'average_rating': analytics_data['average_rating'],
                        'rating_distribution': analytics_data['rating_distribution'],
                        'sentiment_distribution': analytics_data['sentiment_distribution'],
                        'topic_distribution': analytics_data['topic_distribution'],
                    }
                )
                
                if was_created:
                    created += 1
                else:
                    updated += 1
            
            current_date += timedelta(days=7)
        
        return created, updated
    
    def _backfill_monthly_snapshots(self, computer, hotel_id, hotel_name, start_date, end_date, force):
        """Backfill monthly snapshots for date range"""
        created = 0
        updated = 0
        
        # Find first day of the month in the range
        current_date = start_date.replace(day=1)
        
        while current_date <= end_date:
            # Calculate month end
            if current_date.month == 12:
                month_end = current_date.replace(year=current_date.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                month_end = current_date.replace(month=current_date.month + 1, day=1) - timedelta(days=1)
            
            # Skip if already exists and not forcing
            if not force and HotelAnalyticsSnapshot.objects.filter(
                hotel_id=hotel_id,
                snapshot_date=current_date,
                granularity='monthly'
            ).exists():
                # Move to next month
                if current_date.month == 12:
                    current_date = current_date.replace(year=current_date.year + 1, month=1, day=1)
                else:
                    current_date = current_date.replace(month=current_date.month + 1, day=1)
                continue
            
            # Compute analytics for this month
            analytics_data = computer._compute_analytics_for_date_range(
                hotel_id, hotel_name, current_date, min(month_end, end_date)
            )
            
            if analytics_data['review_count'] > 0:
                snapshot, was_created = HotelAnalyticsSnapshot.objects.update_or_create(
                    hotel_id=hotel_id,
                    snapshot_date=current_date,
                    granularity='monthly',
                    defaults={
                        'hotel_name': hotel_name,
                        'review_count': analytics_data['review_count'],
                        'average_rating': analytics_data['average_rating'],
                        'rating_distribution': analytics_data['rating_distribution'],
                        'sentiment_distribution': analytics_data['sentiment_distribution'],
                        'topic_distribution': analytics_data['topic_distribution'],
                    }
                )
                
                if was_created:
                    created += 1
                else:
                    updated += 1
            
            # Move to next month
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1, day=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1, day=1)
        
        return created, updated