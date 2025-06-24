# carts/views.py
from rest_framework import status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
import logging

from .models import Cart, CartItem
from .serializers import (
    CartSerializer,
    CartItemSerializer,
    AddToCartSerializer,
    CartSummarySerializer,
    CheckoutCartItemSerializer,
    CartItemAvailabilitySerializer,
    RemoveCartItemSerializer,
    CartItemUpdateSerializer,
    BookingOverviewSerializer,
    CartValidationSerializer
)
from .services import (
    CartService,
    CartServiceError,
    CartItemCreationError,
    CartItemNotFoundError,
    CheckoutError,
    SlotUnavailableError
)
from payments.serializers import OrderSerializer

logger = logging.getLogger(__name__)


class CartViewSet(GenericViewSet):
    """
    ViewSet for cart management
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Filter cart by current user"""
        if hasattr(self.request.user, 'cart'):
            return Cart.objects.filter(user=self.request.user)
        return Cart.objects.none()

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'add_item':
            return AddToCartSerializer
        elif self.action == 'summary':
            return CartSummarySerializer
        elif self.action == 'validate_cart':
            return CartValidationSerializer
        return CartSerializer

    @extend_schema(
        responses={
            200: CartSerializer,
            404: {'description': 'Cart not found'}
        },
        description="Get user's cart with all items",
        tags=['Cart']
    )
    @action(detail=False, methods=['get'])
    def my_cart(self, request):
        """
        Get current user's cart
        GET /api/carts/my-cart/
        """
        try:
            cart = CartService.get_or_create_cart(request.user)
            serializer = CartSerializer(cart)

            logger.info(f"Retrieved cart for user {request.user.email}")
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error retrieving cart for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to retrieve cart')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        request=AddToCartSerializer,
        responses={
            201: {
                'description': 'Item added to cart successfully',
                'example': {
                    'message': 'Item added to cart successfully',
                    'cart_item': {
                        'item_id': 'uuid',
                        'child_name': 'John Doe',
                        'psychologist_name': 'Dr. Jane Smith',
                        'session_type': 'OnlineMeeting'
                    }
                }
            },
            400: {'description': 'Invalid booking data'},
            403: {'description': 'Permission denied'}
        },
        description="Add booking item to cart",
        tags=['Cart']
    )
    @action(detail=False, methods=['post'])
    def add_item(self, request):
        """
        Add item to cart
        POST /api/carts/add-item/
        """
        try:
            serializer = self.get_serializer(data=request.data)

            if serializer.is_valid():
                try:
                    cart_item = serializer.save()

                    # Return created cart item data
                    result_serializer = CartItemSerializer(cart_item)

                    logger.info(f"Added item to cart: {cart_item.item_id} for user {request.user.email}")
                    return Response({
                        'message': _('Item added to cart successfully'),
                        'cart_item': result_serializer.data
                    }, status=status.HTTP_201_CREATED)

                except CartItemCreationError as e:
                    return Response({
                        'error': str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Unexpected error adding item to cart for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to add item to cart')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={
            200: CartSummarySerializer,
        },
        description="Get cart summary with totals",
        tags=['Cart']
    )
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Get cart summary
        GET /api/carts/summary/
        """
        try:
            summary_data = CartService.get_cart_summary(request.user)
            serializer = CartSummarySerializer(summary_data)

            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error getting cart summary for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to get cart summary')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={
            200: {
                'description': 'Cart cleared successfully',
                'example': {
                    'message': 'Cart cleared successfully',
                    'items_removed': 3
                }
            }
        },
        description="Clear all items from cart",
        tags=['Cart']
    )
    @action(detail=False, methods=['post'])
    def clear(self, request):
        """
        Clear all items from cart
        POST /api/carts/clear/
        """
        try:
            # Get current item count before clearing
            items = CartService.get_cart_items(request.user)
            items_count = len(items)

            if CartService.clear_cart(request.user):
                logger.info(f"Cleared cart for user {request.user.email}")
                return Response({
                    'message': _('Cart cleared successfully'),
                    'items_removed': items_count
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'error': _('Failed to clear cart')
                }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Error clearing cart for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to clear cart')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={
            200: CartValidationSerializer,
        },
        description="Validate all items in cart for availability",
        tags=['Cart']
    )
    @action(detail=False, methods=['get'])
    def validate_cart(self, request):
        """
        Validate all cart items for availability
        GET /api/carts/validate-cart/
        """
        try:
            cart_items = CartService.get_cart_items(request.user)

            valid_items = []
            expired_items = []
            unavailable_items = []
            issues_found = []

            for item in cart_items:
                if item.is_past_due:
                    expired_items.append(item)
                    issues_found.append(f"Appointment for {item.child_name} has expired")
                else:
                    availability = CartService.validate_cart_item_availability(item)
                    if availability['available']:
                        valid_items.append(item)
                    else:
                        unavailable_items.append({
                            'item': CartItemSerializer(item).data,
                            'availability': availability
                        })
                        issues_found.append(f"Appointment for {item.child_name}: {availability['reason']}")

            total_valid_amount = sum(item.total_price for item in valid_items)
            can_checkout = len(valid_items) > 0

            validation_data = {
                'valid_items': valid_items,
                'expired_items': expired_items,
                'unavailable_items': unavailable_items,
                'total_valid_amount': total_valid_amount,
                'can_checkout': can_checkout,
                'issues_found': issues_found
            }

            serializer = CartValidationSerializer(validation_data)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error validating cart for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to validate cart')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={
            200: {
                'description': 'Expired items cleaned up',
                'example': {
                    'message': 'Expired items cleaned up',
                    'items_removed': 2
                }
            }
        },
        description="Clean up expired cart items",
        tags=['Cart']
    )
    @action(detail=False, methods=['post'])
    def cleanup_expired(self, request):
        """
        Clean up expired cart items
        POST /api/carts/cleanup-expired/
        """
        try:
            removed_count = CartService.cleanup_expired_cart_items(request.user)

            return Response({
                'message': _('Expired items cleaned up'),
                'items_removed': removed_count
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error cleaning up expired items for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to cleanup expired items')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CartItemViewSet(GenericViewSet, RetrieveModelMixin):
    """
    ViewSet for individual cart item management
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Filter cart items by current user"""
        return CartItem.objects.filter(cart__user=self.request.user).select_related(
            'child', 'psychologist', 'psychologist__user'
        )

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'checkout':
            return CheckoutCartItemSerializer
        elif self.action == 'check_availability':
            return CartItemAvailabilitySerializer
        elif self.action == 'remove':
            return RemoveCartItemSerializer
        elif self.action == 'update':
            return CartItemUpdateSerializer
        elif self.action == 'booking_overview':
            return BookingOverviewSerializer
        return CartItemSerializer

    @extend_schema(
        responses={200: CartItemSerializer},
        description="Get cart item details",
        tags=['Cart Items']
    )
    def retrieve(self, request, pk=None):
        """
        Get cart item details
        GET /api/carts/items/{id}/
        """
        return super().retrieve(request, pk)

    @extend_schema(
        request=CheckoutCartItemSerializer,
        responses={
            201: {
                'description': 'Checkout successful',
                'example': {
                    'message': 'Checkout successful',
                    'order': {
                        'order_id': 'uuid',
                        'amount': '150.00',
                        'status': 'pending'
                    }
                }
            },
            400: {'description': 'Checkout failed or slots unavailable'},
            404: {'description': 'Cart item not found'}
        },
        description="Checkout cart item (create order with slot reservation)",
        tags=['Cart Items']
    )
    @action(detail=True, methods=['post'])
    def checkout(self, request, pk=None):
        """
        Checkout cart item
        POST /api/carts/items/{id}/checkout/
        """
        try:
            cart_item = self.get_object()

            serializer = self.get_serializer(
                data=request.data,
                context={'cart_item': cart_item, 'request': request}
            )

            if serializer.is_valid():
                try:
                    order = serializer.save()

                    # Return created order data
                    order_serializer = OrderSerializer(order)

                    logger.info(f"Checked out cart item {cart_item.item_id} as order {order.order_id}")
                    return Response({
                        'message': _('Checkout successful'),
                        'order': order_serializer.data
                    }, status=status.HTTP_201_CREATED)

                except Exception as e:
                    return Response({
                        'error': str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Unexpected error during checkout for item {pk}: {str(e)}")
            return Response({
                'error': _('Checkout failed')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={
            200: CartItemAvailabilitySerializer,
        },
        description="Check if cart item slots are still available",
        tags=['Cart Items']
    )
    @action(detail=True, methods=['get'])
    def check_availability(self, request, pk=None):
        """
        Check cart item availability
        GET /api/carts/items/{id}/check-availability/
        """
        try:
            cart_item = self.get_object()
            availability = CartService.validate_cart_item_availability(cart_item)

            serializer = CartItemAvailabilitySerializer(availability)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error checking availability for cart item {pk}: {str(e)}")
            return Response({
                'error': _('Failed to check availability')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={
            204: {'description': 'Item removed successfully'},
            404: {'description': 'Cart item not found'}
        },
        description="Remove item from cart",
        tags=['Cart Items']
    )
    @action(detail=True, methods=['delete'])
    def remove(self, request, pk=None):
        """
        Remove item from cart
        DELETE /api/carts/items/{id}/remove/
        """
        try:
            cart_item = self.get_object()

            if CartService.remove_item_from_cart(request.user, str(cart_item.item_id)):
                logger.info(f"Removed cart item {cart_item.item_id} for user {request.user.email}")
                return Response(status=status.HTTP_204_NO_CONTENT)
            else:
                return Response({
                    'error': _('Failed to remove item')
                }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Error removing cart item {pk}: {str(e)}")
            return Response({
                'error': _('Failed to remove item')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        request=CartItemUpdateSerializer,
        responses={
            200: CartItemSerializer,
            400: {'description': 'Update failed'},
            404: {'description': 'Cart item not found'}
        },
        description="Update cart item (notes only)",
        tags=['Cart Items']
    )
    @action(detail=True, methods=['patch'])
    def update_notes(self, request, pk=None):
        """
        Update cart item notes
        PATCH /api/carts/items/{id}/update-notes/
        """
        try:
            cart_item = self.get_object()

            serializer = CartItemUpdateSerializer(
                cart_item,
                data=request.data,
                partial=True
            )

            if serializer.is_valid():
                updated_item = serializer.save()
                result_serializer = CartItemSerializer(updated_item)

                logger.info(f"Updated cart item {cart_item.item_id} notes")
                return Response(result_serializer.data, status=status.HTTP_200_OK)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Error updating cart item {pk}: {str(e)}")
            return Response({
                'error': _('Failed to update item')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={
            200: BookingOverviewSerializer,
        },
        description="Get booking overview for cart item before checkout",
        tags=['Cart Items']
    )
    @action(detail=True, methods=['get'])
    def booking_overview(self, request, pk=None):
        """
        Get booking overview for cart item
        GET /api/carts/items/{id}/booking-overview/
        """
        try:
            cart_item = self.get_object()

            # Get availability status
            availability_status = CartService.validate_cart_item_availability(cart_item)

            # Get pricing breakdown
            from payments.services import PricingService
            pricing_breakdown = PricingService.calculate_total_with_fees(
                cart_item.price, cart_item.currency, 'stripe'
            )

            # Create booking summary
            booking_summary = {
                'appointment_date': cart_item.scheduled_start_time.date(),
                'appointment_time': cart_item.scheduled_start_time.strftime('%H:%M'),
                'duration': f"{cart_item.duration_hours} hour{'s' if cart_item.duration_hours > 1 else ''}",
                'session_type_display': cart_item.get_session_type_display(),
                'psychologist_name': cart_item.psychologist.display_name,
                'child_name': cart_item.child.display_name,
                'total_amount': pricing_breakdown['total_amount'],
                'currency': cart_item.currency,
                'can_checkout': availability_status['available'] and not cart_item.is_past_due
            }

            overview_data = {
                'cart_item': cart_item,
                'availability_status': availability_status,
                'pricing_breakdown': pricing_breakdown,
                'booking_summary': booking_summary
            }

            serializer = BookingOverviewSerializer(overview_data)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error getting booking overview for cart item {pk}: {str(e)}")
            return Response({
                'error': _('Failed to get booking overview')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)