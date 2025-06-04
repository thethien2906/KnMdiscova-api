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

# The resulting URL patterns will be:
#
# Payment Orders:
# - GET    /api/payments/orders/                                    -> list user's orders
# - GET    /api/payments/orders/{id}/                               -> get order details
# - POST   /api/payments/orders/create-registration-order/         -> create psychologist registration order
# - POST   /api/payments/orders/create-appointment-order/          -> create appointment booking order
# - POST   /api/payments/orders/{id}/initiate-payment/             -> initiate payment for order
# - POST   /api/payments/orders/{id}/cancel/                       -> cancel pending order
# - GET    /api/payments/orders/{id}/status/                       -> get order status
#
# Payments:
# - GET    /api/payments/payments/                                  -> list user's payments
# - GET    /api/payments/payments/{id}/                             -> get payment details
# - POST   /api/payments/payments/{id}/refund/                     -> process payment refund
# - POST   /api/payments/payments/check-status/                    -> check payment status with provider
#
# Transactions:
# - GET    /api/payments/transactions/                              -> list user's transaction history
# - GET    /api/payments/transactions/{id}/                        -> get transaction details
#
# Pricing:
# - GET    /api/payments/pricing/                                   -> get pricing information
#
# Webhooks:
# - POST   /api/payments/webhooks/stripe/                          -> Stripe webhook endpoint