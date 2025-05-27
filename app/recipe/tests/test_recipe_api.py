
from django.test import TestCase
from django.urls import reverse
from decimal import Decimal
from rest_framework import status
from rest_framework.test import APIClient
from core.models import Recipe
from django.contrib.auth import get_user_model
from recipe.serializers import (RecipeSerializer, RecipeDetailSerializer)

RECIPE_URL=reverse('recipe:recipe-list')


def detail_url(recipe_id):
    return reverse('recipe:recipe-detail', args=[recipe_id])

def create_recipe(user, **params):
    defaults={
        'title':'sanple title',
        'time_minutes':22,
        'price':Decimal('3.4'),
        'description':'Sample',
        'link':'http://google.com'
    }

    defaults.update(params)
    recipe=Recipe.objects.create(user=user,**defaults)
    return recipe

def create_user(**params):
    return get_user_model().objects.create_user(**params)

class PublicRecipeTests(TestCase):

    def setUp(self):
        self.client=APIClient()

    def test_authentication_required(self):
        res=self.client.get(RECIPE_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

class PrivateRecipeTest(TestCase):

    def setUp(self):
        self.client=APIClient()
        self.user=create_user(email="example@gmail.com", password="testPass")
        self.client.force_authenticate(self.user)

    def test_list_recipes(self):
        create_recipe(self.user)
        create_recipe(self.user)
        res=self.client.get(RECIPE_URL)
        recipes=Recipe.objects.all().order_by('-id')
        serializer=RecipeSerializer(recipes, many=True)
        self.assertEqual(res.data, serializer.data)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_recipe_limited_to_auth_user(self):
        other_user=create_user(email="example2@email.com", password="testpass123")
        create_recipe(self.user)
        create_recipe(other_user)
        res=self.client.get(RECIPE_URL)
        recipes=Recipe.objects.all().filter(user=self.user)
        serializer=RecipeSerializer(recipes, many=True)
        self.assertEqual(res.data, serializer.data)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_get_recipe_detail(self):
        recipe=create_recipe(user=self.user)
        url=detail_url(recipe.id)
        res=self.client.get(url)
        serializer=RecipeDetailSerializer(recipe)
        self.assertEqual(res.data, serializer.data)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_create_recipe(self):
        payload={
            'title':'sample',
            'time_minutes':10,
            'price':Decimal('5.99')
        }

        res=self.client.post(RECIPE_URL,payload )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        recipe=Recipe.objects.get(id=res.data['id'])

        for k,v in payload.items():
            self.assertEqual(getattr(recipe,k),v)
        self.assertEqual(recipe.user, self.user)


    def test_partial_update(self):
        original_link="http://google.com"
        recipe=create_recipe(user=self.user, title="Sample title", link=original_link)
        payload={'title':'New Title'}
        url=detail_url(recipe.id)
        res=self.client.patch(url,payload)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        recipe.refresh_from_db()
        self.assertEqual(recipe.title,payload['title'])
        self.assertEqual(recipe.link, original_link)
        self.assertEqual(recipe.user, self.user)

    def test_full_update(self):
        recipe=create_recipe(
            user=self.user,
            title="sample title",
            description="Sample desc",
            link="http://google.com",
        )

        payload={
            'title':'New Title',
            'link':'http://google2.com',
            'description':'This is the new shit',
            'time_minutes':30,
            'price':Decimal('2.04')
        }
        url=detail_url(recipe.id)
        res=self.client.put(url, payload)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        recipe.refresh_from_db()
        for k,v in payload.items():
            self.assertEqual(getattr(recipe, k), v)
        self.assertEqual(recipe.user, self.user)

    def test_update_user_returns_error(self):
        new_user=create_user(email='user@example.com', password="test123")
        recipe=create_recipe(user=self.user)
        url=detail_url(recipe_id=recipe.id)
        payload={'user':new_user}
        self.client.patch(url, payload)
        recipe.refresh_from_db()
        self.assertEqual(recipe.user, self.user)

    def test_delete_recipe(self):
        recipe=create_recipe(user=self.user)
        url=detail_url(recipe.id)
        res=self.client.delete(url)
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Recipe.objects.filter(id=recipe.id).exists())

    def test_delete_other_user_recipe_error(self):
        new_user=create_user(email="test@email.com", password="pass123")
        recipe=create_recipe(user=new_user)
        url=detail_url(recipe.id)
        res=self.client.delete(url)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Recipe.objects.filter(id=recipe.id).exists())











