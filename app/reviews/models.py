
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta


class Review(models.Model):
    """Model for storing hotel reviews submitted by customers"""
    
    hotel_id = models.CharField(
        max_length=100,
        help_text="Unique identifier for the hotel"
    )
    hotel_name = models.CharField(
        max_length=255,
        help_text="Name of the hotel"
    )
    reviewer_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Name of the person leaving the review"
    )
    reviewer_email = models.EmailField(
        blank=True,
        help_text="Email address of the reviewer"
    )
    reviewer_phone = models.CharField(
        max_length=20,
        blank=True,
        help_text="Phone number of the reviewer"
    )
    rating = models.DecimalField(
        max_digits=2,
        decimal_places=1,
        validators=[MinValueValidator(1.0), MaxValueValidator(5.0)],
        help_text="Rating from 1.0 to 5.0 stars"
    )
    comment = models.TextField(
        help_text="Review comment text"
    )
    submission_date = models.DateTimeField(
        auto_now_add=True,
        help_text="When the review was submitted"
    )
    
    class Meta:
        ordering = ['-submission_date']
        indexes = [
            models.Index(fields=['hotel_id']),
            models.Index(fields=['submission_date']),
        ]
    
    def __str__(self):
        return f"{self.hotel_name} - {self.rating}★ - {self.submission_date.date()}"
    
    @property
    def has_analysis(self):
        """Check if this review has been analyzed"""
        # FIXED: Changed from 'analysisresult' to 'analysis' to match the related_name
        return hasattr(self, 'analysis') and self.analysis is not None




class AnalysisResult(models.Model):
    """Model for storing NLP analysis results of reviews"""
    
    review = models.OneToOneField(
        Review,
        on_delete=models.CASCADE,
        related_name='analysis'
    )
    processed_date = models.DateTimeField(
        auto_now_add=True,
        help_text="When the analysis was completed"
    )
    primary_sentiment = models.CharField(
        max_length=50,
        help_text="Primary sentiment classification"
    )
    primary_topic = models.CharField(
        max_length=50,
        help_text="Primary topic classification"
    )
    sentiment_scores = models.JSONField(
        help_text="Detailed sentiment scores (positive, negative, neutral)"
    )
    topic_scores = models.JSONField(
        help_text="Detailed topic classification scores"
    )
    processing_time_seconds = models.FloatField(
        null=True,
        blank=True,
        help_text="Time taken to process this review"
    )
    
    class Meta:
        ordering = ['-processed_date']
        indexes = [
            models.Index(fields=['primary_sentiment']),
            models.Index(fields=['primary_topic']),
            models.Index(fields=['processed_date']),
        ]
    
    def __str__(self):
        return f"Analysis for {self.review} - {self.primary_sentiment}/{self.primary_topic}"


class AnalysisBatch(models.Model):
    """Model for tracking batch processing jobs"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    batch_id = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique identifier for this batch"
    )
    created_date = models.DateTimeField(
        auto_now_add=True
    )
    started_date = models.DateTimeField(
        null=True,
        blank=True
    )
    completed_date = models.DateTimeField(
        null=True,
        blank=True
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    total_reviews = models.IntegerField(
        default=0,
        help_text="Total number of reviews in this batch"
    )
    processed_reviews = models.IntegerField(
        default=0,
        help_text="Number of successfully processed reviews"
    )
    failed_reviews = models.IntegerField(
        default=0,
        help_text="Number of failed reviews"
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error message if batch failed"
    )
    processing_time_seconds = models.FloatField(
        null=True,
        blank=True,
        help_text="Total time taken to process this batch"
    )
    
    class Meta:
        ordering = ['-created_date']
    
    def __str__(self):
        return f"Batch {self.batch_id} - {self.status} ({self.processed_reviews}/{self.total_reviews})"

class HotelAnalyticsSnapshot(models.Model):
    """Pre-computed analytics snapshots for fast API responses"""
    
    GRANULARITY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'), 
        ('monthly', 'Monthly')
    ]
    
    hotel_id = models.CharField(
        max_length=100,
        help_text="Hotel identifier"
    )
    hotel_name = models.CharField(
        max_length=255,
        help_text="Hotel name for quick reference"
    )
    snapshot_date = models.DateField(
        help_text="Date this snapshot represents"
    )
    granularity = models.CharField(
        max_length=10,
        choices=GRANULARITY_CHOICES,
        help_text="Time granularity of this snapshot"
    )
    
    # Core metrics
    review_count = models.IntegerField(
        default=0,
        help_text="Total reviews for this time period"
    )
    average_rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Average rating for this period"
    )
    
    # Sentiment breakdown
    sentiment_distribution = models.JSONField(
        default=dict,
        help_text="Sentiment analysis distribution"
    )
    
    # Topic breakdown  
    topic_distribution = models.JSONField(
        default=dict,
        help_text="Topic analysis distribution"
    )
    
    # Rating distribution
    rating_distribution = models.JSONField(
        default=dict,
        help_text="Distribution of 1-5 star ratings"
    )
    
    # Metadata
    computed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this snapshot was computed"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Last update time"
    )
    
    class Meta:
        unique_together = ['hotel_id', 'snapshot_date', 'granularity']
        indexes = [
            models.Index(fields=['hotel_id', 'granularity', 'snapshot_date']),
            models.Index(fields=['hotel_id', 'snapshot_date']),
            models.Index(fields=['computed_at']),
        ]
        ordering = ['-snapshot_date']
    
    def __str__(self):
        return f"{self.hotel_name} - {self.granularity} - {self.snapshot_date}"
    
    @classmethod
    def cleanup_old_snapshots(cls, days_to_keep=None):
        """Clean up old snapshots based on granularity"""
        retention_policy = {
            'daily': 90,    # Keep 3 months
            'weekly': 730,  # Keep 2 years  
            'monthly': 1095 # Keep 3 years
        }
        
        current_date = timezone.now().date()
        
        for granularity, days in retention_policy.items():
            if days_to_keep:
                days = days_to_keep
                
            cutoff_date = current_date - timedelta(days=days)
            deleted_count = cls.objects.filter(
                granularity=granularity,
                snapshot_date__lt=cutoff_date
            ).delete()[0]
            
            if deleted_count > 0:
                print(f"Cleaned up {deleted_count} old {granularity} snapshots")


class ReviewVolumeStats(models.Model):
    """Pre-computed volume statistics for ReviewMap component"""
    
    hotel_id = models.CharField(
        max_length=100,
        help_text="Hotel identifier"
    )
    hotel_name = models.CharField(
        max_length=255,
        help_text="Hotel name for quick reference"
    )
    
    # This month stats
    this_month_total = models.IntegerField(
        default=0,
        help_text="Total reviews this month"
    )
    this_month_daily_data = models.JSONField(
        default=list,
        help_text="Daily review counts for last 7 days"
    )
    this_month_growth = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Growth percentage vs last month"
    )
    
    # All time stats
    all_time_total = models.IntegerField(
        default=0,
        help_text="Total reviews all time"
    )
    all_time_monthly_data = models.JSONField(
        default=list,
        help_text="Monthly review counts for last 7 months"
    )
    all_time_growth = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Growth percentage vs previous 7 months"
    )
    
    # Metadata
    computed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this was computed"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Last update time"
    )
    
    class Meta:
        unique_together = ['hotel_id']
        indexes = [
            models.Index(fields=['hotel_id']),
            models.Index(fields=['computed_at']),
        ]
    
    def __str__(self):
        return f"{self.hotel_name} - Volume Stats"


class AnalyticsComputationLog(models.Model):
    """Log analytics computation results for monitoring"""
    
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('partial', 'Partial Success'),
        ('failed', 'Failed'),
    ]
    
    computation_date = models.DateTimeField(
        auto_now_add=True,
        help_text="When the computation ran"
    )
    hotels_processed = models.IntegerField(
        default=0,
        help_text="Number of hotels processed"
    )
    snapshots_created = models.IntegerField(
        default=0,
        help_text="Number of snapshots created"
    )
    snapshots_updated = models.IntegerField(
        default=0,
        help_text="Number of snapshots updated"
    )
    processing_time_seconds = models.FloatField(
        null=True,
        blank=True,
        help_text="Total processing time"
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='success'
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error details if failed"
    )
    
    class Meta:
        ordering = ['-computation_date']
        indexes = [
            models.Index(fields=['computation_date']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"Analytics Computation - {self.computation_date} - {self.status}"