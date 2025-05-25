# parents/admin.py
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count
import json

from .models import Parent


@admin.register(Parent)
class ParentAdmin(admin.ModelAdmin):
    """Admin configuration for Parent model"""

    list_display = [
        'user_email',
        'full_name',
        'phone_number',
        'city',
        'country',
        'created_at',
        'is_active'
    ]

    list_filter = [
        'country',
        'state_province',
        'created_at',
        'updated_at'
    ]

    search_fields = [
        'user__email',
        'first_name',
        'last_name',
        'phone_number',
        'city',
        'postal_code'
    ]

    readonly_fields = [
        'user_link',
        'created_at',
        'updated_at',
        'full_address',
        'communication_preferences_display'
    ]

    fieldsets = (
        (_('User Information'), {
            'fields': ('user_link',)
        }),
        (_('Personal Information'), {
            'fields': (
                'first_name',
                'last_name',
                'phone_number'
            )
        }),
        (_('Address'), {
            'fields': (
                'address_line1',
                'address_line2',
                'city',
                'state_province',
                'postal_code',
                'country',
                'full_address'
            )
        }),
        (_('Communication Preferences'), {
            'fields': ('communication_preferences_display',),
            'classes': ('collapse',)
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def user_email(self, obj):
        """Display user email"""
        return obj.user.email
    user_email.short_description = _('Email')
    user_email.admin_order_field = 'user__email'

    def full_name(self, obj):
        """Display full name"""
        return obj.full_name or '—'
    full_name.short_description = _('Full Name')

    def is_active(self, obj):
        """Display user active status"""
        return obj.user.is_active
    is_active.short_description = _('Active')
    is_active.boolean = True
    is_active.admin_order_field = 'user__is_active'

    def user_link(self, obj):
        """Display link to user admin"""
        url = reverse('admin:users_user_change', args=[obj.user.id])
        return format_html(
            '<a href="{}">{}</a>',
            url,
            obj.user.email
        )
    user_link.short_description = _('User Account')

    def communication_preferences_display(self, obj):
        """Display communication preferences in a readable format"""
        if not obj.communication_preferences:
            return '—'

        prefs = obj.communication_preferences
        html_parts = ['<ul style="margin: 0; padding-left: 20px;">']

        pref_labels = {
            'email_notifications': _('Email Notifications'),
            'sms_notifications': _('SMS Notifications'),
            'appointment_reminders': _('Appointment Reminders'),
            'reminder_timing': _('Reminder Timing'),
            'growth_plan_updates': _('Growth Plan Updates'),
            'new_message_alerts': _('New Message Alerts'),
            'marketing_emails': _('Marketing Emails')
        }

        for key, label in pref_labels.items():
            if key in prefs:
                value = prefs[key]
                if isinstance(value, bool):
                    icon = '✓' if value else '✗'
                    color = 'green' if value else 'red'
                    display_value = format_html(
                        '<span style="color: {};">{}</span>',
                        color,
                        icon
                    )
                else:
                    display_value = str(value)

                html_parts.append(
                    f'<li><strong>{label}:</strong> {display_value}</li>'
                )

        html_parts.append('</ul>')
        return format_html(''.join(html_parts))

    communication_preferences_display.short_description = _('Communication Preferences')

    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related('user')

    def has_add_permission(self, request):
        """Prevent manual creation of parent profiles"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of parent profiles (should be done through User)"""
        return False