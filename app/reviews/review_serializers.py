from rest_framework import serializers
from django.utils import timezone
from .models import Review, AnalysisResult, AnalysisBatch


class ReviewSerializer(serializers.ModelSerializer):
    """Serializer for Review model - handles review submission and listing"""
    
    class Meta:
        model = Review
        fields = [
            'id',
            'hotel_id',
            'hotel_name', 
            'reviewer_name',
            'reviewer_email',
            'reviewer_phone',
            'rating',
            'comment',
            'submission_date',
            'has_analysis'
        ]
        read_only_fields = ['id', 'submission_date', 'has_analysis']
    
    def validate_rating(self, value):
        """Ensure rating is within valid range"""
        if not (1.0 <= value <= 5.0):
            raise serializers.ValidationError("Rating must be between 1.0 and 5.0")
        return value
    
    def validate_comment(self, value):
        """Ensure comment is not empty and has minimum length"""
        if not value or len(value.strip()) < 10:
            raise serializers.ValidationError("Comment must be at least 10 characters long")
        return value.strip()


class AnalysisResultSerializer(serializers.ModelSerializer):
    """Serializer for AnalysisResult model"""
    
    class Meta:
        model = AnalysisResult
        fields = [
            'id',
            'processed_date',
            'primary_sentiment',
            'primary_topic',
            'sentiment_scores',
            'topic_scores',
            'processing_time_seconds'
        ]
        read_only_fields = ['id', 'processed_date']


class ReviewWithAnalysisSerializer(serializers.ModelSerializer):
    """Serializer that includes both review and analysis data"""
    
    analysis = AnalysisResultSerializer(read_only=True)
    
    class Meta:
        model = Review
        fields = [
            'id',
            'hotel_id',
            'hotel_name',
            'reviewer_name',
            'reviewer_email', 
            'reviewer_phone',
            'rating',
            'comment',
            'submission_date',
            'analysis'
        ]
        read_only_fields = ['id', 'submission_date']


class HotelAnalyticsSummarySerializer(serializers.Serializer):
    """Serializer for hotel analytics summary data"""
    
    hotel_id = serializers.CharField()
    hotel_name = serializers.CharField()
    total_reviews = serializers.IntegerField()
    average_rating = serializers.FloatField()
    sentiment_distribution = serializers.DictField()
    topic_distribution = serializers.DictField()
    recent_reviews_count = serializers.IntegerField()
    processed_reviews_count = serializers.IntegerField()
    date_range = serializers.DictField()


class AnalysisBatchSerializer(serializers.ModelSerializer):
    """Serializer for AnalysisBatch model"""
    
    success_rate = serializers.SerializerMethodField()
    
    class Meta:
        model = AnalysisBatch
        fields = [
            'id',
            'batch_id',
            'created_date',
            'started_date',
            'completed_date',
            'status',
            'total_reviews',
            'processed_reviews',
            'failed_reviews',
            'success_rate',
            'error_message',
            'processing_time_seconds'
        ]
        read_only_fields = ['id']
    
    def get_success_rate(self, obj):
        """Calculate success rate as percentage"""
        if obj.total_reviews == 0:
            return 0.0
        return round((obj.processed_reviews / obj.total_reviews) * 100, 2)


class BulkReviewSubmissionSerializer(serializers.Serializer):
    """Serializer for bulk review submissions"""
    
    reviews = ReviewSerializer(many=True)
    
    def validate_reviews(self, value):
        """Ensure we don't have too many reviews in one batch"""
        if len(value) > 100:
            raise serializers.ValidationError("Maximum 100 reviews per batch submission")
        if len(value) == 0:
            raise serializers.ValidationError("At least one review is required")
        return value
    
    def create(self, validated_data):
        """Create multiple reviews in a single transaction"""
        reviews_data = validated_data['reviews']
        reviews = []
        
        for review_data in reviews_data:
            review = Review.objects.create(**review_data)
            reviews.append(review)
        
        return {'reviews': reviews}


class ReviewAnalysisRequestSerializer(serializers.Serializer):
    """Serializer for manual analysis requests"""
    
    review_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
        max_length=50
    )
    priority = serializers.ChoiceField(
        choices=['low', 'normal', 'high'],
        default='normal'
    )
    
    def validate_review_ids(self, value):
        """Ensure all review IDs exist and haven't been processed"""
        existing_reviews = Review.objects.filter(id__in=value)
        if len(existing_reviews) != len(value):
            raise serializers.ValidationError("Some review IDs don't exist")
        
        already_processed = existing_reviews.filter(analysisresult__isnull=False)
        if already_processed.exists():
            processed_ids = list(already_processed.values_list('id', flat=True))
            raise serializers.ValidationError(
                f"Reviews {processed_ids} have already been processed"
            )
        
        return value