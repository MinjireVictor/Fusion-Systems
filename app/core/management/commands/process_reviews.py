import os
import time
import uuid
import logging
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from typing import List, Dict, Any

from reviews.models import Review, AnalysisResult, AnalysisBatch

# Configure logging
logger = logging.getLogger('reviews')

class Command(BaseCommand):
    help = 'Process unanalyzed reviews using Modal NLP service'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='Number of reviews to process in one batch (default: 50)'
        )
        parser.add_argument(
            '--max-age-hours',
            type=int,
            default=getattr(settings, 'REVIEW_ANALYSIS_MAX_AGE_HOURS', 24),
            help='Only process reviews newer than this many hours (default: 24)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force reprocessing of already analyzed reviews'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without actually processing'
        )
        parser.add_argument(
            '--hotel-id',
            type=str,
            help='Only process reviews for specific hotel ID'
        )
        parser.add_argument(
            '--test-modal',
            action='store_true',
            help='Test Modal connection and exit'
        )
    
    def handle(self, *args, **options):
        """Main command handler"""
        # Test Modal import first
        if options.get('test_modal') or options.get('dry_run'):
            self.test_modal_connection()
            if options.get('test_modal'):
                return
        
        batch_size = options['batch_size']
        max_age_hours = options['max_age_hours']
        force = options['force']
        dry_run = options['dry_run']
        hotel_id = options['hotel_id']
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Starting review processing job at {timezone.now()}"
            )
        )
        logger.info(f"Starting review processing job - batch_size: {batch_size}, max_age_hours: {max_age_hours}")
        
        try:
            # Get reviews to process
            reviews_to_process = self.get_reviews_to_process(
                max_age_hours, force, hotel_id
            )
            
            if not reviews_to_process:
                self.stdout.write(
                    self.style.WARNING("No reviews found to process")
                )
                logger.info("No reviews found to process")
                return
            
            self.stdout.write(
                f"Found {len(reviews_to_process)} reviews to process"
            )
            logger.info(f"Found {len(reviews_to_process)} reviews to process")
            
            if dry_run:
                self.show_dry_run_info(reviews_to_process)
                return
            
            # Process reviews in batches
            total_processed = 0
            total_failed = 0
            
            for i in range(0, len(reviews_to_process), batch_size):
                batch = reviews_to_process[i:i + batch_size]
                processed, failed = self.process_batch(batch)
                total_processed += processed
                total_failed += failed
                
                self.stdout.write(
                    f"Batch {i//batch_size + 1}: "
                    f"Processed {processed}, Failed {failed}"
                )
                logger.info(f"Batch {i//batch_size + 1}: Processed {processed}, Failed {failed}")
            
            # Summary
            self.stdout.write(
                self.style.SUCCESS(
                    f"Processing complete! "
                    f"Total processed: {total_processed}, "
                    f"Total failed: {total_failed}"
                )
            )
            logger.info(f"Processing complete - Total processed: {total_processed}, Total failed: {total_failed}")
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Command failed: {str(e)}")
            )
            logger.error(f"Command failed: {str(e)}", exc_info=True)
            raise CommandError(f"Processing failed: {e}")
    
    def test_modal_connection(self):
        """Test Modal import and connection"""
        try:
            self.stdout.write("Testing Modal import...")
            import modal
            self.stdout.write(self.style.SUCCESS("✓ Modal imported successfully"))
            
            # Test Modal client initialization
            try:
                # Try to lookup as function first, then as class
                try:
                    analyzer = modal.Function.from_name("hotel-review-analyzer", "analyze_reviews_batch")
                    self.stdout.write(self.style.SUCCESS("✓ Modal function lookup successful"))
                except Exception:
                    analyzer = modal.Cls.from_name("hotel-review-analyzer", "analyze_reviews_batch")
                    self.stdout.write(self.style.SUCCESS("✓ Modal class lookup successful"))
                logger.info("Modal connection test successful")
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f"⚠ Modal service lookup failed: {str(e)}")
                )
                self.stdout.write("This might be expected if the service isn't deployed yet.")
                logger.warning(f"Modal service lookup failed: {str(e)}")
                
        except ImportError as e:
            self.stdout.write(
                self.style.ERROR(f"✗ Modal import failed: {str(e)}")
            )
            logger.error(f"Modal import failed: {str(e)}")
            raise CommandError("Modal is not properly installed")
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"✗ Modal test failed: {str(e)}")
            )
            logger.error(f"Modal test failed: {str(e)}")
            raise CommandError(f"Modal test failed: {e}")
    
    def get_reviews_to_process(
        self, 
        max_age_hours: int, 
        force: bool, 
        hotel_id: str = None
    ) -> List[Review]:
        """Get reviews that need to be processed"""
        
        # Base queryset
        queryset = Review.objects.all()
        
        # Filter by hotel if specified
        if hotel_id:
            queryset = queryset.filter(hotel_id=hotel_id)
        
        # Filter by age
        cutoff_time = timezone.now() - timedelta(hours=max_age_hours)
        queryset = queryset.filter(submission_date__gte=cutoff_time)
        
        # Filter by analysis status
        if not force:
            queryset = queryset.filter(analysis__isnull=True)
        
        return list(queryset.order_by('submission_date'))
    
    def show_dry_run_info(self, reviews: List[Review]):
        """Show information about what would be processed"""
        self.stdout.write(self.style.WARNING("DRY RUN - No actual processing"))
        
        # Group by hotel
        hotels = {}
        for review in reviews:
            hotel_key = f"{review.hotel_name} ({review.hotel_id})"
            if hotel_key not in hotels:
                hotels[hotel_key] = []
            hotels[hotel_key].append(review)
        
        self.stdout.write("\nReviews to process by hotel:")
        for hotel, hotel_reviews in hotels.items():
            self.stdout.write(f"  {hotel}: {len(hotel_reviews)} reviews")
        
        # Show date range
        if reviews:
            oldest = min(review.submission_date for review in reviews)
            newest = max(review.submission_date for review in reviews)
            self.stdout.write(
                f"\nDate range: {oldest.strftime('%Y-%m-%d %H:%M')} "
                f"to {newest.strftime('%Y-%m-%d %H:%M')}"
            )
    
    def process_batch(self, reviews: List[Review]) -> tuple[int, int]:
        """Process a batch of reviews using Modal service"""
        batch_id = str(uuid.uuid4())
        
        # Create batch record
        batch_record = AnalysisBatch.objects.create(
            batch_id=batch_id,
            total_reviews=len(reviews),
            status='pending'
        )
        
        self.stdout.write(f"Processing batch {batch_id} with {len(reviews)} reviews")
        logger.info(f"Processing batch {batch_id} with {len(reviews)} reviews")
        
        try:
            # Update batch status
            batch_record.status = 'processing'
            batch_record.started_date = timezone.now()
            batch_record.save()
            
            # Prepare data for Modal service
            reviews_data = self.prepare_reviews_data(reviews)
            
            # Call Modal service
            analysis_results = self.call_modal_service(reviews_data)
            
            if not analysis_results['success']:
                raise Exception(f"Modal service error: {analysis_results.get('error', 'Unknown error')}")
            
            # Save results to database
            processed_count = self.save_analysis_results(
                reviews, 
                analysis_results['results']
            )
            
            # Update batch record
            batch_record.status = 'completed'
            batch_record.completed_date = timezone.now()
            batch_record.processed_reviews = processed_count
            batch_record.processing_time_seconds = analysis_results.get('processing_time_seconds', 0)
            batch_record.save()
            
            logger.info(f"Batch {batch_id} completed successfully - processed {processed_count} reviews")
            return processed_count, len(reviews) - processed_count
            
        except Exception as e:
            # Update batch record with error
            batch_record.status = 'failed'
            batch_record.error_message = str(e)
            batch_record.completed_date = timezone.now()
            batch_record.save()
            
            self.stdout.write(
                self.style.ERROR(f"Batch {batch_id} failed: {str(e)}")
            )
            logger.error(f"Batch {batch_id} failed: {str(e)}", exc_info=True)
            return 0, len(reviews)
    
    def prepare_reviews_data(self, reviews: List[Review]) -> List[Dict[str, Any]]:
        """Prepare review data for Modal service"""
        return [
            {
                'id': review.id,
                'comment': review.comment,
                'hotel_id': review.hotel_id,
                'rating': float(review.rating)
            }
            for review in reviews
        ]
    
    def call_modal_service(self, reviews_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Call the Modal NLP service"""
        try:
            # Import Modal here to catch import errors per batch
            import modal
            
            app_name = getattr(settings, 'REVIEW_ANALYSIS_SETTINGS', {}).get('MODAL_APP_NAME', 'hotel-review-analyzer')
            function_name = getattr(settings, 'REVIEW_ANALYSIS_SETTINGS', {}).get('MODAL_FUNCTION_NAME', 'analyze_reviews_batch')
            
            # Try to get as function first, then as class
            try:
                analyzer = modal.Function.from_name(app_name, function_name)
                self.stdout.write(f"Found Modal function: {function_name}")
            except Exception:
                try:
                    analyzer = modal.Cls.from_name(app_name, function_name)
                    self.stdout.write(f"Found Modal class: {function_name}")
                except Exception as e:
                    raise Exception(f"Could not find Modal function or class '{function_name}' in app '{app_name}': {str(e)}")
            
            self.stdout.write(f"Calling Modal service with {len(reviews_data)} reviews...")
            logger.info(f"Calling Modal service with {len(reviews_data)} reviews")
            start_time = time.time()
            
            # Make the remote call with timeout
            timeout_seconds = getattr(settings, 'REVIEW_ANALYSIS_SETTINGS', {}).get('MODAL_TIMEOUT_SECONDS', 1800)
            result = analyzer.remote(reviews_data)
            
            end_time = time.time()
            processing_time = end_time - start_time
            self.stdout.write(
                f"Modal service completed in {processing_time:.2f} seconds"
            )
            logger.info(f"Modal service completed in {processing_time:.2f} seconds")
            
            # Add processing time to result
            if isinstance(result, dict):
                result['processing_time_seconds'] = processing_time
            
            return result
            
        except ImportError as e:
            error_msg = f"Modal import failed: {str(e)}"
            self.stdout.write(self.style.ERROR(error_msg))
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'results': []
            }
        except Exception as e:
            error_msg = f"Modal service call failed: {str(e)}"
            self.stdout.write(self.style.ERROR(error_msg))
            logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'error': error_msg,
                'results': []
            }
    
    @transaction.atomic
    def save_analysis_results(
        self, 
        reviews: List[Review], 
        results: List[Dict[str, Any]]
    ) -> int:
        """Save analysis results to database"""
        processed_count = 0
        
        # Create a mapping of review ID to review object
        review_map = {review.id: review for review in reviews}
        
        for result in results:
            try:
                review_id = result.get('review_id')
                if not review_id or review_id not in review_map:
                    logger.warning(f"Review ID {review_id} not found in current batch")
                    continue
                
                review = review_map[review_id]
                
                # Skip if result has errors
                if result.get('has_errors', False):
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipping review {review_id} due to processing errors"
                        )
                    )
                    logger.warning(f"Skipping review {review_id} due to processing errors")
                    continue
                
                # Create or update analysis result
                analysis_result, created = AnalysisResult.objects.update_or_create(
                    review=review,
                    defaults={
                        'primary_sentiment': result['primary_sentiment'],
                        'primary_topic': result['primary_topic'],
                        'sentiment_scores': result['sentiment'],
                        'topic_scores': result['topics'],
                        'processing_time_seconds': result.get('processing_time_seconds', 0)
                    }
                )
                
                processed_count += 1
                
                if created:
                    self.stdout.write(f"Created analysis for review {review_id}")
                    logger.info(f"Created analysis for review {review_id}")
                else:
                    self.stdout.write(f"Updated analysis for review {review_id}")
                    logger.info(f"Updated analysis for review {review_id}")
                
            except Exception as e:
                error_msg = f"Failed to save analysis for review {result.get('review_id', 'unknown')}: {str(e)}"
                self.stdout.write(self.style.ERROR(error_msg))
                logger.error(error_msg, exc_info=True)
        
        return processed_count