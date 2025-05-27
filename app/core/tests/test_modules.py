from django.test import TestCase
from django.contrib.auth import get_user_model
from decimal import Decimal
from core import models


def create_user(email='test@email.com', password='test123'):
    return get_user_model().objects.create_user(email, password)

class ModelTests(TestCase):

    def test_create_user_with_email_successfull(self):
        email="test@example.com"
        password="testpass"
        user=get_user_model().objects.create_user(
            email=email,password=password
        )
        self.assertEqual(user.email, email)
        self.assertTrue(user.check_password(password))

    def test_new_user_email_normalized(self):
        sample_emails=[
            ['test1@EXAMPLE.com','test1@example.com'],
            ['Test2@Example.com', 'Test2@example.com'],
            ['TEST3@EXAMPLE.COM','TEST3@example.com'],
            ['test4@example.COM','test4@example.com']
        ]

        for email, expected in sample_emails:
            user=get_user_model().objects.create_user(email, "sample123")
            self.assertEqual(user.email, expected)

    def test_new_user_without_email_address(self):
        with self.assertRaises(ValueError):
            get_user_model().objects.create_user("", "sample123")

    def test_create_superuser(self):
        user=get_user_model().objects.create_superuser('test@example.com', "testuser")
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)

    def test_create_recepie(self):
        user=get_user_model().objects.create_user("test@example.com","testpass123")
        recipe=models.Recipe.objects.create(
            user=user,
            title="Sample recepie name",
            price=Decimal('5.50'),
            time_minutes=5,
            description='Sample receipe description.',
        )

        self.assertEqual(str(recipe), recipe.title)

    def test_create_tags(self):
        user=create_user()
        name="Dinner"
        tag=models.Tag.objects.create(user=user, name=name)
        self.assertEqual(str(tag), tag.name)






