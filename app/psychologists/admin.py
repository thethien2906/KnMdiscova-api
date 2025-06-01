# psychologists/admin.py
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
import json

from .models import Psychologist, PsychologistAvailability


class PsychologistAvailabilityInline(admin.TabularInline):
    """Inline admin for PsychologistAvailability"""
    model = PsychologistAvailability
    extra = 0
    fields = [
        'day_of_week', 'start_time', 'end_time', 'is_recurring',
        'specific_date', 'duration_hours', 'max_appointable_slots'
    ]
    readonly_fields = ['duration_hours', 'max_appointable_slots']

    def duration_hours(self, obj):
        """Display duration in hours"""
        if obj and obj.start_time and obj.end_time:
            return f"{obj.duration_hours:.1f}h"
        return "—"
    duration_hours.short_description = _('Duration')

    def max_appointable_slots(self, obj):
        """Display max appointable slots"""
        if obj and obj.start_time and obj.end_time:
            return f"{obj.max_appointable_slots} slots"
        return "—"
    max_appointable_slots.short_description = _('Max Slots')


@admin.register(Psychologist)
class PsychologistAdmin(admin.ModelAdmin):
    """Admin configuration for Psychologist model"""

    list_display = [
        'user_email',
        'full_name',
        'license_number',
        'verification_status',
        'license_is_valid',
        'services_offered_display',
        'availability_blocks_count',
        'is_marketplace_visible',
        'created_at'
    ]

    list_filter = [
        'verification_status',
        'offers_initial_consultation',
        'offers_online_sessions',
        'license_expiry_date',
        'created_at',
        'updated_at'
    ]

    search_fields = [
        'user__email',
        'first_name',
        'last_name',
        'license_number',
        'license_issuing_authority'
    ]

    readonly_fields = [
        'user_link',
        'created_at',
        'updated_at',
        'full_name',
        'display_name',
        'is_verified',
        'is_marketplace_visible',
        'license_is_valid',
        'profile_completeness_display',
        'verification_requirements_display',
        'education_display',
        'certifications_display',
        'availability_summary'
    ]

    fieldsets = (
        (_('User Information'), {
            'fields': ('user_link', 'display_name')
        }),
        (_('Personal Information'), {
            'fields': (
                'first_name',
                'last_name'
            )
        }),
        (_('Professional Credentials'), {
            'fields': (
                'license_number',
                'license_issuing_authority',
                'license_expiry_date',
                'license_is_valid',
                'years_of_experience'
            )
        }),
        (_('Professional Profile'), {
            'fields': (
                'biography',
                'education_display',
                'certifications_display',
                'website_url',
                'linkedin_url'
            )
        }),
        (_('Service Offerings'), {
            'fields': (
                'offers_online_sessions',
                'offers_initial_consultation',
                'office_address'
            )
        }),
        (_('Pricing (Optional - MVP)'), {
            'fields': (
                'hourly_rate',
                'initial_consultation_rate'
            ),
            'classes': ('collapse',),
            'description': 'Pricing fields are optional in MVP version. Fixed rates will be used for now.'
        }),
        (_('Availability'), {
            'fields': ('availability_summary',),
            'classes': ('collapse',)
        }),
        (_('Verification'), {
            'fields': (
                'verification_status',
                'is_verified',
                'is_marketplace_visible',
                'admin_notes',
                'verification_requirements_display'
            )
        }),
        (_('Profile Metrics'), {
            'fields': ('profile_completeness_display',),
            'classes': ('collapse',)
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    inlines = [PsychologistAvailabilityInline]

    actions = ['approve_verification', 'reject_verification', 'reset_to_pending']

    def user_email(self, obj):
        """Display user email"""
        return obj.user.email
    user_email.short_description = _('Email')
    user_email.admin_order_field = 'user__email'

    def full_name(self, obj):
        """Display full name"""
        return obj.full_name or '—'
    full_name.short_description = _('Full Name')

    def license_is_valid(self, obj):
        """Display license validity status"""
        return obj.license_is_valid
    license_is_valid.short_description = _('License Valid')
    license_is_valid.boolean = True

    def is_marketplace_visible(self, obj):
        """Display marketplace visibility status"""
        return obj.is_marketplace_visible
    is_marketplace_visible.short_description = _('Marketplace Visible')
    is_marketplace_visible.boolean = True

    def services_offered_display(self, obj):
        """Display services offered"""
        services = obj.services_offered
        if not services:
            return '—'

        service_badges = []
        for service in services:
            if service == 'Online Sessions':
                color = 'blue'
            else:  # Initial Consultations
                color = 'green'

            service_badges.append(
                f'<span style="background-color: {color}; color: white; '
                f'padding: 2px 6px; border-radius: 3px; font-size: 10px;">{service}</span>'
            )

        return format_html(' '.join(service_badges))
    def availability_blocks_count(self, obj):
        """Display count of availability blocks"""
        count = obj.availability_blocks.count()
        if count == 0:
            return format_html('<span style="color: red;">No availability set</span>')
        return f"{count} blocks"
    availability_blocks_count.short_description = _('Availability Blocks')

    def availability_summary(self, obj):
        """Display availability summary"""
        recurring = obj.availability_blocks.filter(is_recurring=True).order_by('day_of_week', 'start_time')
        specific = obj.availability_blocks.filter(is_recurring=False).order_by('specific_date', 'start_time')

        if not recurring.exists() and not specific.exists():
            return format_html('<span style="color: red;">No availability set</span>')

        html_parts = []

        if recurring.exists():
            html_parts.append('<h4>Recurring Availability:</h4>')
            html_parts.append('<ul style="margin: 5px 0; padding-left: 20px;">')
            for avail in recurring:
                html_parts.append(
                    f'<li>{avail.get_day_name()}: {avail.get_time_range_display()} '
                    f'({avail.max_appointable_slots} slots)</li>'
                )
            html_parts.append('</ul>')

        if specific.exists():
            html_parts.append('<h4>Specific Date Availability:</h4>')
            html_parts.append('<ul style="margin: 5px 0; padding-left: 20px;">')
            for avail in specific[:5]:  # Show only first 5
                html_parts.append(
                    f'<li>{avail.specific_date}: {avail.get_time_range_display()} '
                    f'({avail.max_appointable_slots} slots)</li>'
                )
            if specific.count() > 5:
                html_parts.append(f'<li><em>... and {specific.count() - 5} more</em></li>')
            html_parts.append('</ul>')

        return format_html(''.join(html_parts))
    availability_summary.short_description = _('Availability Summary')

    def user_link(self, obj):
        """Display link to user admin"""
        url = reverse('admin:users_user_change', args=[obj.user.id])
        return format_html(
            '<a href="{}">{}</a>',
            url,
            obj.user.email
        )
    user_link.short_description = _('User Account')

    def profile_completeness_display(self, obj):
        """Display profile completeness percentage"""
        completeness = obj.get_profile_completeness()

        if completeness >= 80:
            color = 'green'
        elif completeness >= 60:
            color = 'orange'
        else:
            color = 'red'

        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
            color,
            completeness
        )
    profile_completeness_display.short_description = _('Profile Completeness')

    def verification_requirements_display(self, obj):
        """Display verification requirements"""
        requirements = obj.get_verification_requirements()

        if not requirements:
            return format_html('<span style="color: green;">✓ All requirements met</span>')

        html_parts = ['<ul style="margin: 0; padding-left: 20px; color: red;">']
        for req in requirements:
            html_parts.append(f'<li>{req}</li>')
        html_parts.append('</ul>')

        return format_html(''.join(html_parts))
    verification_requirements_display.short_description = _('Verification Requirements')

    def education_display(self, obj):
        """Display education in a readable format"""
        if not obj.education:
            return '—'

        html_parts = ['<ul style="margin: 0; padding-left: 20px;">']
        for edu in obj.education:
            degree = edu.get('degree', 'Unknown Degree')
            institution = edu.get('institution', 'Unknown Institution')
            year = edu.get('year', 'Unknown Year')
            html_parts.append(f'<li><strong>{degree}</strong> from {institution} ({year})</li>')
        html_parts.append('</ul>')

        return format_html(''.join(html_parts))
    education_display.short_description = _('Education')

    def certifications_display(self, obj):
        """Display certifications in a readable format"""
        if not obj.certifications:
            return '—'

        html_parts = ['<ul style="margin: 0; padding-left: 20px;">']
        for cert in obj.certifications:
            name = cert.get('name', 'Unknown Certification')
            institution = cert.get('institution', 'Unknown Institution')
            year = cert.get('year', 'Unknown Year')
            html_parts.append(f'<li><strong>{name}</strong> from {institution} ({year})</li>')
        html_parts.append('</ul>')

        return format_html(''.join(html_parts))
    certifications_display.short_description = _('Certifications')

    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related('user')

    def has_add_permission(self, request):
        """Prevent manual creation of psychologist profiles"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of psychologist profiles (should be done through User)"""
        return False

    # Admin Actions
    def approve_verification(self, request, queryset):
        """Approve selected psychologists"""
        updated = queryset.update(
            verification_status='Approved',
            updated_at=timezone.now()
        )
        self.message_user(
            request,
            f'{updated} psychologist(s) approved successfully.'
        )
    approve_verification.short_description = _('Approve selected psychologists')

    def reject_verification(self, request, queryset):
        """Reject selected psychologists"""
        updated = queryset.update(
            verification_status='Rejected',
            updated_at=timezone.now()
        )
        self.message_user(
            request,
            f'{updated} psychologist(s) rejected.'
        )
    reject_verification.short_description = _('Reject selected psychologists')

    def reset_to_pending(self, request, queryset):
        """Reset verification status to pending"""
        updated = queryset.update(
            verification_status='Pending',
            updated_at=timezone.now()
        )
        self.message_user(
            request,
            f'{updated} psychologist(s) reset to pending verification.'
        )
    reset_to_pending.short_description = _('Reset to pending verification')


@admin.register(PsychologistAvailability)
class PsychologistAvailabilityAdmin(admin.ModelAdmin):
    """Admin configuration for PsychologistAvailability model"""

    list_display = [
        'psychologist_name',
        'get_display_date',
        'get_time_range_display',
        'duration_hours_display',
        'max_appointable_slots',
        'is_recurring',
        'created_at'
    ]

    list_filter = [
        'is_recurring',
        'day_of_week',
        'psychologist__verification_status',
        'created_at'
    ]

    search_fields = [
        'psychologist__user__email',
        'psychologist__first_name',
        'psychologist__last_name'
    ]

    readonly_fields = [
        'psychologist_link',
        'duration_hours_display',
        'max_appointable_slots',
        'slot_times_display',
        'created_at',
        'updated_at'
    ]

    fieldsets = (
        (_('Psychologist'), {
            'fields': ('psychologist_link',)
        }),
        (_('Time Configuration'), {
            'fields': (
                'day_of_week',
                'start_time',
                'end_time',
                'duration_hours_display',
                'max_appointable_slots'
            )
        }),
        (_('Recurrence'), {
            'fields': (
                'is_recurring',
                'specific_date'
            )
        }),
        (_('Generated Slots'), {
            'fields': ('slot_times_display',),
            'classes': ('collapse',)
        }),
        (_('Legacy'), {
            'fields': ('is_booked',),
            'classes': ('collapse',),
            'description': 'Legacy field - DO NOT USE for booking logic'
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def psychologist_name(self, obj):
        """Display psychologist name"""
        return obj.psychologist.display_name
    psychologist_name.short_description = _('Psychologist')
    psychologist_name.admin_order_field = 'psychologist__first_name'

    def psychologist_link(self, obj):
        """Display link to psychologist admin"""
        url = reverse('admin:psychologists_psychologist_change', args=[obj.psychologist.user.id])
        return format_html(
            '<a href="{}">{}</a>',
            url,
            obj.psychologist.display_name
        )
    psychologist_link.short_description = _('Psychologist')

    def duration_hours_display(self, obj):
        """Display duration in hours"""
        return f"{obj.duration_hours:.1f} hours"
    duration_hours_display.short_description = _('Duration')

    def slot_times_display(self, obj):
        """Display generated slot times"""
        if not obj.start_time or not obj.end_time:
            return '—'

        slots = obj.generate_slot_times()
        if not slots:
            return 'No slots generated'

        slot_strings = [slot.strftime('%H:%M') for slot in slots]
        return format_html(
            '<div style="font-family: monospace;">{}</div>',
            ', '.join(slot_strings)
        )
    slot_times_display.short_description = _('Generated Slot Times')

    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related('psychologist__user')