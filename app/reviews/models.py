
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.models import User


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
        return hasattr(self, 'analysisresult')


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