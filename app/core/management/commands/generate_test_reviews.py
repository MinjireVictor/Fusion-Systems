import random
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from reviews.models import Review


class Command(BaseCommand):
    help = 'Generate test review data for development and testing'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=20,
            help='Number of reviews to generate (default: 20)'
        )
        parser.add_argument(
            '--hotel-id',
            type=str,
            help='Specific hotel ID to generate reviews for'
        )
        parser.add_argument(
            '--days-back',
            type=int,
            default=7,
            help='Generate reviews from this many days back (default: 7)'
        )
        parser.add_argument(
            '--clear-existing',
            action='store_true',
            help='Clear existing reviews before generating new ones'
        )
    
    def handle(self, *args, **options):
        count = options['count']
        hotel_id = options['hotel_id']
        days_back = options['days_back']
        clear_existing = options['clear_existing']
        
        if clear_existing:
            Review.objects.all().delete()
            self.stdout.write(
                self.style.WARNING("Cleared all existing reviews")
            )
        
        self.stdout.write(f"Generating {count} test reviews...")
        
        # Generate reviews
        reviews_created = []
        for i in range(count):
            review = self.create_random_review(hotel_id, days_back)
            reviews_created.append(review)
        
        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully created {len(reviews_created)} reviews"
            )
        )
        
        # Show breakdown by hotel
        hotels = {}
        for review in reviews_created:
            hotel_key = f"{review.hotel_name} ({review.hotel_id})"
            hotels[hotel_key] = hotels.get(hotel_key, 0) + 1
        
        self.stdout.write("\nReviews created by hotel:")
        for hotel, count in hotels.items():
            self.stdout.write(f"  {hotel}: {count} reviews")
    
    def create_random_review(self, specific_hotel_id=None, days_back=7):
        """Create a single random review"""
        
        # Hotel data
        if specific_hotel_id:
            hotel_id = specific_hotel_id
            hotel_name = f"Hotel {specific_hotel_id.upper()}"
        else:
            hotel_data = random.choice(self.get_hotel_options())
            hotel_id = hotel_data['id']
            hotel_name = hotel_data['name']
        
        # Reviewer data
        reviewer_data = random.choice(self.get_reviewer_options())
        
        # Rating (weighted towards higher ratings)
        rating = random.choices(
            [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
            weights=[2, 1, 3, 2, 8, 10, 20, 25, 29]  # Weighted towards positive
        )[0]
        
        # Comment based on rating
        comment = self.generate_comment(rating, hotel_name)
        
        # Random submission date within the specified range
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days_back)
        random_date = start_date + timedelta(
            seconds=random.randint(0, int((end_date - start_date).total_seconds()))
        )
        
        # Create review
        review = Review.objects.create(
            hotel_id=hotel_id,
            hotel_name=hotel_name,
            reviewer_name=reviewer_data['name'],
            reviewer_email=reviewer_data['email'],
            reviewer_phone=reviewer_data.get('phone', ''),
            rating=rating,
            comment=comment,
            submission_date=random_date
        )
        
        return review
    
    def get_hotel_options(self):
        """Get list of sample hotels"""
        return [
            {'id': 'h001', 'name': 'Oceanview Resort & Spa'},
            {'id': 'h002', 'name': 'Metropolitan Grand Hotel'},
            {'id': 'h003', 'name': 'Riverside Inn'},
            {'id': 'h004', 'name': 'Alpine Lodge'},
            {'id': 'h005', 'name': 'Urban Boutique Hotel'},
            {'id': 'h006', 'name': 'Beachside Bungalows'},
            {'id': 'h007', 'name': 'Historic Grand Hotel'},
            {'id': 'h008', 'name': 'Desert Oasis Resort'},
            {'id': 'h009', 'name': 'Parkside Budget Inn'},
            {'id': 'h010', 'name': 'Skyline Tower Hotel'},
        ]
    
    def get_reviewer_options(self):
        """Get list of sample reviewer names and emails"""
        return [
            {'name': 'James Wilson', 'email': 'james.wilson@example.com', 'phone': '+1-555-0101'},
            {'name': 'Sophia Chen', 'email': 'sophia.chen@example.com', 'phone': '+1-555-0102'},
            {'name': 'Michael Rodriguez', 'email': 'm.rodriguez@example.com'},
            {'name': 'Emma Thompson', 'email': 'emma.thompson@example.com', 'phone': '+1-555-0104'},
            {'name': 'Robert Johnson', 'email': 'robert.j@example.com'},
            {'name': 'Jessica Martinez', 'email': 'j.martinez@example.com', 'phone': '+1-555-0106'},
            {'name': 'David Kim', 'email': 'd.kim@example.com'},
            {'name': 'Sarah Williams', 'email': 's.williams@example.com', 'phone': '+1-555-0108'},
            {'name': 'Thomas Garcia', 'email': 't.garcia@example.com'},
            {'name': 'Jennifer Lee', 'email': 'j.lee@example.com'},
            {'name': 'William Brown', 'email': 'w.brown@example.com', 'phone': '+1-555-0111'},
            {'name': 'Olivia Taylor', 'email': 'o.taylor@example.com'},
            {'name': 'Daniel Miller', 'email': 'd.miller@example.com'},
            {'name': 'Sophia Anderson', 'email': 's.anderson@example.com', 'phone': '+1-555-0114'},
            {'name': 'Christopher Wilson', 'email': 'c.wilson@example.com'},
            {'name': 'Emily Roberts', 'email': 'e.roberts@example.com'},
            {'name': 'Matthew Clark', 'email': 'm.clark@example.com', 'phone': '+1-555-0117'},
            {'name': 'Amanda Johnson', 'email': 'a.johnson@example.com'},
            {'name': 'Ryan Thompson', 'email': 'r.thompson@example.com'},
            {'name': 'Natalie Garcia', 'email': 'n.garcia@example.com', 'phone': '+1-555-0120'},
        ]
    
    def generate_comment(self, rating, hotel_name):
        """Generate a comment based on rating"""
        
        if rating >= 4.5:
            # Very positive comments
            positive_comments = [
                f"Absolutely breathtaking stay at {hotel_name}! The staff was exceptional and the amenities were world-class. The room was spotless with stunning views. Would definitely return and recommend to everyone!",
                f"Perfect experience at {hotel_name}! From check-in to check-out, everything was flawless. The bed was incredibly comfortable, and the bathroom was luxurious. Special thanks to the staff who remembered our names throughout the stay.",
                f"Outstanding! {hotel_name} exceeded all expectations. The location is unbeatable, the service is impeccable, and the facilities are top-notch. This was truly a memorable vacation.",
                f"Five stars well deserved! {hotel_name} provided the perfect getaway. Clean rooms, friendly staff, delicious food, and beautiful surroundings. We'll be back next year!",
                f"Exceptional service and beautiful accommodations at {hotel_name}. Every detail was perfect, from the welcome champagne to the turndown service. Highly recommend for special occasions."
            ]
            return random.choice(positive_comments)
        
        elif rating >= 3.5:
            # Positive comments with minor issues
            good_comments = [
                f"Had a lovely stay at {hotel_name}. The location is great and the staff was friendly. Room was clean and comfortable, though it could use some updating. Overall a pleasant experience.",
                f"Good value at {hotel_name}. The amenities were nice and the service was generally good. Had a minor issue with housekeeping but it was resolved quickly. Would consider returning.",
                f"Solid choice for accommodation. {hotel_name} offers comfortable rooms and decent service. The breakfast was excellent, though dinner options were limited. Nice for a weekend getaway.",
                f"Pleasant stay overall. {hotel_name} has a great location and the staff was helpful. Room was spacious but showing some wear. The facilities were well-maintained.",
                f"Good experience at {hotel_name}. The bed was comfortable and the bathroom was clean. Service was a bit slow at times but the staff was apologetic. Decent value for money."
            ]
            return random.choice(good_comments)
        
        elif rating >= 2.5:
            # Mixed/mediocre comments
            mixed_comments = [
                f"Average experience at {hotel_name}. The location is good but the room needed updating. Service was inconsistent - sometimes great, sometimes not. Probably wouldn't return.",
                f"Mixed feelings about {hotel_name}. While the grounds are beautiful, our room had several maintenance issues. Front desk was helpful but housekeeping was sporadic.",
                f"Mediocre stay. {hotel_name} has potential but needs improvement. The room was clean but dated, and service was slow. For the price, expected more.",
                f"Decent location but disappointing overall. {hotel_name} seems to be coasting on its reputation. Room was okay but nothing special. Staff seemed overwhelmed.",
                f"Not terrible but not great either. {hotel_name} is fine for a basic stay but don't expect luxury. Several minor issues that added up to an underwhelming experience."
            ]
            return random.choice(mixed_comments)
        
        else:
            # Negative comments
            negative_comments = [
                f"Very disappointed with {hotel_name}. The room was dirty with stained carpets and the bathroom had mold. Despite multiple complaints, issues were never resolved. Would not recommend.",
                f"Terrible experience at {hotel_name}. The room had maintenance problems, housekeeping was poor, and the staff was unhelpful. For the price paid, this was completely unacceptable.",
                f"Avoid {hotel_name} at all costs! Our room was tiny, dirty, and noisy. The staff was rude when we complained, and no efforts were made to resolve issues. Ruined our vacation.",
                f"Extremely poor service at {hotel_name}. Check-in was chaotic, the room was not ready despite confirmation, and cleanliness was below standard. Never staying here again.",
                f"Complete nightmare stay. {hotel_name} failed on every level - dirty rooms, broken amenities, terrible service, and overpriced for what you get. One star is too generous."
            ]
            return random.choice(negative_comments)