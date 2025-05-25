from django.contrib import admin
from .models import Parent


@admin.register(Parent)
class ParentAdmin(admin.ModelAdmin):
    list_display = [
        'user__email', 'first_name', 'last_name',
        'phone_number', 'city', 'created_at'
    ]
    list_filter = ['country', 'state_province', 'created_at']
    search_fields = [
        'user__email', 'first_name', 'last_name',
        'phone_number', 'city'
    ]
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('User Account', {
            'fields': ('user',)
        }),
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'phone_number')
        }),
        ('Address', {
            'fields': (
                'address_line1', 'address_line2', 'city',
                'state_province', 'postal_code', 'country'
            ),
            'classes': ('collapse',)
        }),
        ('Preferences', {
            'fields': ('communication_preferences',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def user__email(self, obj):
        return obj.user.email
    user__email.short_description = 'Email'
    user__email.admin_order_field = 'user__email'