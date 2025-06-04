from rest_framework import status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.views import APIView
from django.utils.translation import gettext_lazy as _
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes
import logging
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
import json

from .models import Order, Payment, Transaction
from .serializers import (
    OrderSerializer,
    OrderSummarySerializer,
    PaymentSerializer,
    PaymentSummarySerializer,
    TransactionSerializer,
    CreateRegistrationOrderSerializer,
    CreateAppointmentOrderSerializer,
    InitiatePaymentSerializer,
    RefundPaymentSerializer,
    PricingSerializer,
    PaymentStatusSerializer,
    WebhookEventSerializer
)
from .services import (
    PaymentServiceError,
    OrderCreationError,
    PaymentProcessingError,
    RefundError,
    WebhookService
)
# Permissions will be handled with basic Django permissions for now

logger = logging.getLogger(__name__)


class OrderViewSet(GenericViewSet, ListModelMixin, RetrieveModelMixin):
    """
    ViewSet for managing payment orders
    """
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Filter orders by user"""
        user = self.request.user
        queryset = Order.objects.select_related(
            'user', 'psychologist', 'psychologist__user'
        ).prefetch_related('payments', 'transactions')

        # Admins can see all orders
        if user.is_admin or user.is_staff:
            return queryset

        # Users can only see their own orders
        return queryset.filter(user=user)

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'list':
            return OrderSummarySerializer
        elif self.action == 'create_registration_order':
            return CreateRegistrationOrderSerializer
        elif self.action == 'create_appointment_order':
            return CreateAppointmentOrderSerializer
        elif self.action == 'initiate_payment':
            return InitiatePaymentSerializer
        return OrderSerializer

    def get_permissions(self):
        """Set permissions based on action"""
        # For now, use basic authentication for all actions
        return [permissions.IsAuthenticated()]

    @extend_schema(
        responses={200: OrderSummarySerializer(many=True)},
        description="List user's payment orders",
        tags=['Payment Orders']
    )
    def list(self, request, *args, **kwargs):
        """List user's orders"""
        return super().list(request, *args, **kwargs)

    @extend_schema(
        responses={200: OrderSerializer},
        description="Get detailed order information",
        tags=['Payment Orders']
    )
    def retrieve(self, request, *args, **kwargs):
        """Get detailed order information"""
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        request=CreateRegistrationOrderSerializer,
        responses={
            201: {
                'description': 'Registration order created successfully',
                'example': {
                    'message': 'Registration order created successfully',
                    'order': {
                        'order_id': 'uuid',
                        'amount': '100.00',
                        'currency': 'USD',
                        'status': 'pending'
                    }
                }
            },
            400: {'description': 'Invalid data or order creation failed'},
            403: {'description': 'Permission denied'}
        },
        description="Create psychologist registration order",
        tags=['Payment Orders']
    )
    @action(detail=False, methods=['post'])
    def create_registration_order(self, request):
        """
        Create psychologist registration order
        POST /api/payments/orders/create-registration-order/
        """
        try:
            serializer = self.get_serializer(data=request.data)

            if serializer.is_valid():
                try:
                    order = serializer.save()

                    # Return created order data
                    order_serializer = OrderSerializer(order)

                    logger.info(f"Registration order created: {order.order_id} for user {request.user.email}")
                    return Response({
                        'message': _('Registration order created successfully'),
                        'order': order_serializer.data
                    }, status=status.HTTP_201_CREATED)

                except OrderCreationError as e:
                    return Response({
                        'error': str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Unexpected error creating registration order for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to create registration order')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        request=CreateAppointmentOrderSerializer,
        responses={
            201: {
                'description': 'Appointment order created successfully',
                'example': {
                    'message': 'Appointment order created successfully',
                    'order': {
                        'order_id': 'uuid',
                        'amount': '150.00',
                        'currency': 'USD',
                        'session_type': 'online_session'
                    }
                }
            },
            400: {'description': 'Invalid data or order creation failed'},
            403: {'description': 'Permission denied'}
        },
        description="Create appointment booking order",
        tags=['Payment Orders']
    )
    @action(detail=False, methods=['post'])
    def create_appointment_order(self, request):
        """
        Create appointment booking order
        POST /api/payments/orders/create-appointment-order/
        """
        try:
            serializer = self.get_serializer(data=request.data)

            if serializer.is_valid():
                try:
                    order = serializer.save()

                    # Return created order data
                    order_serializer = OrderSerializer(order)

                    logger.info(f"Appointment order created: {order.order_id} for user {request.user.email}")
                    return Response({
                        'message': _('Appointment order created successfully'),
                        'order': order_serializer.data
                    }, status=status.HTTP_201_CREATED)

                except OrderCreationError as e:
                    return Response({
                        'error': str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Unexpected error creating appointment order for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to create appointment order')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        request=InitiatePaymentSerializer,
        responses={
            200: {
                'description': 'Payment initiated successfully',
                'example': {
                    'message': 'Payment initiated successfully',
                    'payment_data': {
                        'payment_id': 'uuid',
                        'client_secret': 'pi_xxx_secret_xxx',
                        'payment_intent_id': 'pi_xxx',
                        'amount': '100.00',
                        'currency': 'USD'
                    }
                }
            },
            400: {'description': 'Payment initiation failed'},
            404: {'description': 'Order not found'}
        },
        description="Initiate payment for an order",
        tags=['Payment Orders']
    )
    @action(detail=True, methods=['post'])
    def initiate_payment(self, request, pk=None):
        """
        Initiate payment for an order
        POST /api/payments/orders/{id}/initiate-payment/
        """
        try:
            order = self.get_object()

            serializer = self.get_serializer(data=request.data, context={'order': order})

            if serializer.is_valid():
                try:
                    payment_data = serializer.save()

                    logger.info(f"Payment initiated for order {order.order_id} by user {request.user.email}")
                    return Response({
                        'message': _('Payment initiated successfully'),
                        'payment_data': payment_data
                    }, status=status.HTTP_200_OK)

                except PaymentProcessingError as e:
                    return Response({
                        'error': str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Unexpected error initiating payment for order {pk}: {str(e)}")
            return Response({
                'error': _('Failed to initiate payment')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={
            200: {
                'description': 'Order cancelled successfully',
                'example': {
                    'message': 'Order cancelled successfully',
                    'order_id': 'uuid'
                }
            },
            400: {'description': 'Order cannot be cancelled'},
            404: {'description': 'Order not found'}
        },
        description="Cancel a pending order",
        tags=['Payment Orders']
    )
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        Cancel a pending order
        POST /api/payments/orders/{id}/cancel/
        """
        try:
            order = self.get_object()

            if order.status != 'pending':
                return Response({
                    'error': _('Only pending orders can be cancelled')
                }, status=status.HTTP_400_BAD_REQUEST)

            from .services import OrderService
            if OrderService.cancel_order(order, "Cancelled by user"):
                logger.info(f"Order cancelled: {order.order_id} by user {request.user.email}")
                return Response({
                    'message': _('Order cancelled successfully'),
                    'order_id': str(order.order_id)
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'error': _('Failed to cancel order')
                }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Error cancelling order {pk}: {str(e)}")
            return Response({
                'error': _('Failed to cancel order')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={
            200: {
                'description': 'Order status',
                'example': {
                    'order_id': 'uuid',
                    'status': 'pending',
                    'can_be_paid': True,
                    'is_expired': False
                }
            }
        },
        description="Get order status and payment information",
        tags=['Payment Orders']
    )
    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """
        Get order status
        GET /api/payments/orders/{id}/status/
        """
        try:
            order = self.get_object()

            return Response({
                'order_id': str(order.order_id),
                'status': order.status,
                'can_be_paid': order.can_be_paid,
                'is_expired': order.is_expired,
                'is_pending': order.is_pending,
                'amount': order.amount,
                'currency': order.currency,
                'expires_at': order.expires_at,
                'paid_at': order.paid_at,
                'created_at': order.created_at,
                'updated_at': order.updated_at
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error getting order status {pk}: {str(e)}")
            return Response({
                'error': _('Failed to get order status')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PaymentViewSet(GenericViewSet, ListModelMixin, RetrieveModelMixin):
    """
    ViewSet for managing payments
    """
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Filter payments by user"""
        user = self.request.user
        queryset = Payment.objects.select_related(
            'order', 'order__user', 'order__psychologist'
        ).prefetch_related('transactions')

        # Admins can see all payments
        if user.is_admin or user.is_staff:
            return queryset

        # Users can only see their own payments
        return queryset.filter(order__user=user)

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'list':
            return PaymentSummarySerializer
        elif self.action == 'refund':
            return RefundPaymentSerializer
        elif self.action == 'check_status':
            return PaymentStatusSerializer
        return PaymentSerializer

    def get_permissions(self):
        """Set permissions based on action"""
        # For now, use basic authentication for all actions
        return [permissions.IsAuthenticated()]

    @extend_schema(
        responses={200: PaymentSummarySerializer(many=True)},
        description="List user's payments",
        tags=['Payments']
    )
    def list(self, request, *args, **kwargs):
        """List user's payments"""
        return super().list(request, *args, **kwargs)

    @extend_schema(
        responses={200: PaymentSerializer},
        description="Get detailed payment information",
        tags=['Payments']
    )
    def retrieve(self, request, *args, **kwargs):
        """Get detailed payment information"""
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        request=RefundPaymentSerializer,
        responses={
            200: {
                'description': 'Refund processed successfully',
                'example': {
                    'message': 'Refund processed successfully',
                    'refund_data': {
                        'refund_id': 'rf_xxx',
                        'amount': '100.00',
                        'currency': 'USD',
                        'status': 'succeeded'
                    }
                }
            },
            400: {'description': 'Refund processing failed'},
            403: {'description': 'Permission denied'},
            404: {'description': 'Payment not found'}
        },
        description="Process refund for a payment",
        tags=['Payments']
    )
    @action(detail=True, methods=['post'])
    def refund(self, request, pk=None):
        """
        Process refund for a payment
        POST /api/payments/payments/{id}/refund/
        """
        try:
            payment = self.get_object()

            serializer = self.get_serializer(data=request.data, context={'payment': payment})

            if serializer.is_valid():
                try:
                    refund_data = serializer.save()

                    logger.info(f"Refund processed for payment {payment.payment_id} by user {request.user.email}")
                    return Response({
                        'message': _('Refund processed successfully'),
                        'refund_data': refund_data
                    }, status=status.HTTP_200_OK)

                except RefundError as e:
                    return Response({
                        'error': str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Unexpected error processing refund for payment {pk}: {str(e)}")
            return Response({
                'error': _('Failed to process refund')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        request=PaymentStatusSerializer,
        responses={
            200: {
                'description': 'Payment status updated',
                'example': {
                    'message': 'Payment status updated',
                    'payment': {
                        'payment_id': 'uuid',
                        'status': 'succeeded',
                        'amount': '100.00'
                    }
                }
            },
            400: {'description': 'Status check failed'},
            404: {'description': 'Payment not found'}
        },
        description="Check and update payment status with provider",
        tags=['Payments']
    )
    @action(detail=False, methods=['post'])
    def check_status(self, request):
        """
        Check payment status with provider
        POST /api/payments/payments/check-status/
        """
        try:
            serializer = self.get_serializer(data=request.data)

            if serializer.is_valid():
                try:
                    payment = serializer.save()
                    payment_serializer = PaymentSerializer(payment)

                    logger.info(f"Payment status checked: {payment.payment_id}")
                    return Response({
                        'message': _('Payment status updated'),
                        'payment': payment_serializer.data
                    }, status=status.HTTP_200_OK)

                except Exception as e:
                    return Response({
                        'error': str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Error checking payment status: {str(e)}")
            return Response({
                'error': _('Failed to check payment status')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PricingAPIView(APIView):
    """
    API view for getting pricing information
    """
    permission_classes = [permissions.AllowAny]  # Pricing can be public
    serializer_class = PricingSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='currency',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Currency code (default: USD)',
                examples=[
                    OpenApiExample('USD', value='USD'),
                ]
            )
        ],
        responses={
            200: {
                'description': 'Pricing information',
                'example': {
                    'currency': 'USD',
                    'services': {
                        'psychologist_registration': '100.00',
                        'online_session': '150.00',
                        'initial_consultation': '280.00'
                    },
                    'fees_example': {
                        'base_amount': '100.00',
                        'provider_fee': '3.20',
                        'platform_fee': '0.00',
                        'total_amount': '103.20'
                    }
                }
            }
        },
        description="Get pricing information for all services",
        tags=['Pricing']
    )
    def get(self, request):
        """
        Get pricing information
        GET /api/payments/pricing/
        """
        try:
            currency = request.query_params.get('currency', 'USD')

            serializer = self.serializer_class(data={'currency': currency})

            if serializer.is_valid():
                return Response(serializer.to_representation(None), status=status.HTTP_200_OK)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Error getting pricing information: {str(e)}")
            return Response({
                'error': _('Failed to get pricing information')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhookView(APIView):
    """
    Stripe webhook endpoint
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # No authentication for webhooks

    @extend_schema(
        request={
            'type': 'object',
            'description': 'Stripe webhook payload'
        },
        responses={
            200: {
                'description': 'Webhook processed successfully',
                'example': {
                    'status': 'success',
                    'event_type': 'payment_intent.succeeded',
                    'processed': True
                }
            },
            400: {'description': 'Webhook processing failed'}
        },
        description="Handle Stripe webhook events",
        tags=['Webhooks']
    )
    def post(self, request):
        """
        Handle Stripe webhook events
        POST /api/payments/webhooks/stripe/
        """
        try:
            payload = request.body
            signature = request.META.get('HTTP_STRIPE_SIGNATURE', '')

            # Process webhook
            result = WebhookService.process_webhook_event(
                provider_name='stripe',
                payload=payload,
                signature=signature,
                headers=dict(request.META)
            )

            if result['status'] == 'success':
                logger.info(f"Stripe webhook processed: {result.get('event_type', 'unknown')}")
                return Response(result, status=status.HTTP_200_OK)
            else:
                logger.error(f"Stripe webhook processing failed: {result.get('error', 'unknown')}")
                return Response(result, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Unexpected error processing Stripe webhook: {str(e)}")
            return Response({
                'status': 'error',
                'error': 'Webhook processing failed',
                'processed': False
            }, status=status.HTTP_400_BAD_REQUEST)


class TransactionViewSet(GenericViewSet, ListModelMixin, RetrieveModelMixin):
    """
    ViewSet for viewing transaction history
    """
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Filter transactions by user"""
        user = self.request.user
        queryset = Transaction.objects.select_related(
            'order', 'payment', 'initiated_by'
        ).order_by('-created_at')

        # Admins can see all transactions
        if user.is_admin or user.is_staff:
            return queryset

        # Users can only see transactions for their orders
        return queryset.filter(order__user=user)

    @extend_schema(
        responses={200: TransactionSerializer(many=True)},
        description="List user's transaction history",
        tags=['Transactions']
    )
    def list(self, request, *args, **kwargs):
        """List user's transaction history"""
        return super().list(request, *args, **kwargs)

    @extend_schema(
        responses={200: TransactionSerializer},
        description="Get detailed transaction information",
        tags=['Transactions']
    )
    def retrieve(self, request, *args, **kwargs):
        """Get detailed transaction information"""
        return super().retrieve(request, *args, **kwargs)