# carts/admin.py
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html

from .models import Cart, CartItem


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    """
    Admin interface for Cart model
    """
    list_display = [
        'cart_id',
        'user_email',
        'total_items',
        'total_amount_display',
        'created_at',
        'updated_at'
    ]
    list_filter = [
        'created_at',
        'updated_at'
    ]
    search_fields = [
        'user__email',
        'user__first_name',
        'user__last_name'
    ]
    readonly_fields = [
        'cart_id',
        'total_items',
        'total_amount',
        'created_at',
        'updated_at'
    ]

    def user_email(self, obj):
        """Display user email"""
        return obj.user.email
    user_email.short_description = _('User Email')

    def total_amount_display(self, obj):
        """Display total amount with currency"""
        return f"${obj.total_amount:.2f}"
    total_amount_display.short_description = _('Total Amount')

    def get_queryset(self, request):
        """Optimize queryset"""
        return super().get_queryset(request).select_related('user').prefetch_related('items')


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    """
    Admin interface for CartItem model
    """
    list_display = [
        'item_id',
        'user_email',
        'child_name',
        'psychologist_name',
        'session_type',
        'scheduled_start_time',
        'price_display',
        'is_past_due_display',
        'created_at'
    ]
    list_filter = [
        'session_type',
        'currency',
        'created_at',
        'scheduled_start_time'
    ]
    search_fields = [
        'cart__user__email',
        'child__first_name',
        'child__last_name',
        'psychologist__first_name',
        'psychologist__last_name'
    ]
    readonly_fields = [
        'item_id',
        'price',
        'currency',
        'scheduled_start_time',
        'scheduled_end_time',
        'duration_hours',
        'total_price',
        'is_past_due',
        'created_at',
        'updated_at'
    ]
    fieldsets = [
        (_('Basic Information'), {
            'fields': ['item_id', 'cart', 'child', 'psychologist']
        }),
        (_('Booking Details'), {
            'fields': [
                'session_type',
                'start_slot_id',
                'scheduled_start_time',
                'scheduled_end_time',
                'duration_hours'
            ]
        }),
        (_('Pricing'), {
            'fields': ['price', 'currency', 'total_price']
        }),
        (_('Notes'), {
            'fields': ['parent_notes']
        }),
        (_('Status'), {
            'fields': ['is_past_due']
        }),
        (_('Metadata'), {
            'fields': ['metadata'],
            'classes': ['collapse']
        }),
        (_('Timestamps'), {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse']
        })
    ]

    def user_email(self, obj):
        """Display user email"""
        return obj.cart.user.email
    user_email.short_description = _('User Email')

    def child_name(self, obj):
        """Display child name"""
        return obj.child.display_name
    child_name.short_description = _('Child')

    def psychologist_name(self, obj):
        """Display psychologist name"""
        return obj.psychologist.display_name
    psychologist_name.short_description = _('Psychologist')

    def price_display(self, obj):
        """Display price with currency"""
        return f"{obj.price} {obj.currency}"
    price_display.short_description = _('Price')

    def is_past_due_display(self, obj):
        """Display past due status with color coding"""
        if obj.is_past_due:
            return format_html('<span style="color: red;">●</span> {}', _('Expired'))
        else:
            return format_html('<span style="color: green;">●</span> {}', _('Valid'))
    is_past_due_display.short_description = _('Status')

    def get_queryset(self, request):
        """Optimize queryset"""
        return super().get_queryset(request).select_related(
            'cart__user',
            'child',
            'psychologist__user'
        )

    actions = ['mark_as_expired', 'cleanup_expired_items']

    def mark_as_expired(self, request, queryset):
        """Admin action to remove expired items"""
        from django.utils import timezone
        expired_count = queryset.filter(scheduled_start_time__lte=timezone.now()).delete()[0]
        self.message_user(request, f"Removed {expired_count} expired cart items.")
    mark_as_expired.short_description = _("Remove expired cart items")

    def cleanup_expired_items(self, request, queryset):
        """Admin action to cleanup expired items across all carts"""
        from .services import CartService
        removed_count = CartService.cleanup_expired_cart_items()
        self.message_user(request, f"Cleaned up {removed_count} expired cart items across all carts.")
    cleanup_expired_items.short_description = _("Cleanup all expired cart items")