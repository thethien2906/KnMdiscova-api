from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from rest_framework.authtoken.admin import TokenAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Custom admin for User model
    """
    ordering = ['email']
    list_display = ['email', 'user_type', 'is_active', 'is_verified', 'created_at']
    list_filter = ['user_type', 'is_active', 'is_verified', 'created_at']
    search_fields = ['email']

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {
            'fields': ('user_type', 'profile_picture_url', 'user_timezone')
        }),
        (_('Permissions'), {
            'fields': ('is_active', 'is_verified', 'is_staff', 'is_superuser',
                      'groups', 'user_permissions')
        }),
        (_('Important dates'), {
            'fields': ('last_login_date', 'registration_date')
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'user_type', 'password1', 'password2'),
        }),
    )

    readonly_fields = ['registration_date', 'created_at', 'updated_at']


# Fix TokenAdmin to work with our custom User model
TokenAdmin.autocomplete_fields = ['user']