# payments/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    OrderViewSet,
    PaymentViewSet,
    TransactionViewSet,
    PricingAPIView,
    StripeWebhookView
)

# Create router for ViewSets
router = DefaultRouter()
router.register('orders', OrderViewSet, basename='orders')
router.register('payments', PaymentViewSet, basename='payments')
router.register('transactions', TransactionViewSet, basename='transactions')

# URL patterns
urlpatterns = [
    # ViewSet routes (handled by router)
    path('', include(router.urls)),

    # Individual APIView routes
    path('pricing/', PricingAPIView.as_view(), name='pricing'),

    # Webhook endpoints
    path('webhooks/stripe/', StripeWebhookView.as_view(), name='stripe-webhook'),
]
