# carts/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import CartViewSet, CartItemViewSet

# Create router for ViewSets
router = DefaultRouter()
router.register('', CartViewSet, basename='cart')
router.register('items', CartItemViewSet, basename='cart-items')

# URL patterns
urlpatterns = [
    # ViewSet routes (handled by router)
    path('', include(router.urls)),
]