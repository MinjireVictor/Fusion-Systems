from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from recipe.serializers import TagSerializer
from core.models import Tag

TAGS_URL=reverse('recipe:tag-list')

def detail_url(tag_id):
    return reverse('recipe:tag-detail', args=[tag_id])

def create_user(email='user@example.com', password='testpass123'):
    return get_user_model().objects.create_user(email, password)

class PublicTagsApiTest(TestCase):

    def setUp(self):
        self.client=APIClient()
        self.user=create_user()

    def test_authentication_required(self):
        Tag.objects.create(user=self.user, name="Breakfast")
        Tag.objects.create(user=self.user, name="Dinner")

        res=self.client.get(TAGS_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

class PrivateTagsApiTest(TestCase):

    def setUp(self):
        self.client=APIClient()
        self.user=create_user()
        self.client.force_authenticate(self.user)

    def test_retrieve_tags(self):
        Tag.objects.create(user=self.user, name="Breakfast")
        Tag.objects.create(user=self.user, name="Desert")
        tags=Tag.objects.all().order_by('-name')
        res=self.client.get(TAGS_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        serializer=TagSerializer(tags, many=True)
        self.assertEqual(res.data, serializer.data)

    def test_tags_limites_to_user(self):
        user2=create_user(email="user2@example.com")
        Tag.objects.create(user=user2, name="Breakfast")
        tag=Tag.objects.create(user=self.user,name="Desert")
        res=self.client.get(TAGS_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0].name,tag.name )
        self.assertEqual(res.data[0].id,tag.id)

    def test_update_tags(self):
        tag=Tag.objects.create(user=self.user, name="Test")
        payload={'name':'Dinner'}
        url=detail_url(tag.id)
        res=self.client.patch(url, payload)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        tag.refresh_from_db()
        self.assertEqual(tag.name, payload["name"])

    def test_delete_tag(self):
        tag=Tag.objects.create(user=self.user, name="TEST")
        url=detail_url(tag.id)
        res=self.client.delete(url)
        self.assertEqual(res.data, status.HTTP_204_NO_CONTENT)
        tags=Tag.objects.filter(user=self.user)
        self.assertFalse(tags.exists())

