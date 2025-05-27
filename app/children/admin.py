# children/admin.py
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count, Q
from django.utils import timezone
from datetime import date
import json

from .models import Child


@admin.register(Child)
class ChildAdmin(admin.ModelAdmin):
    """Admin configuration for Child model"""

    list_display = [
        'full_name',
        'age',
        'parent_email',
        'gender',
        'school_grade_level',
        'has_psychology_history',
        'profile_completeness_display',
        'consent_status_display',
        'created_at',
    ]

    list_filter = [
        'gender',
        'has_seen_psychologist',
        'has_received_therapy',
        'vaccination_status',
        'school_grade_level',
        'parent__user__is_verified',
        'parent__user__is_active',
        'created_at',
        'updated_at',
    ]

    search_fields = [
        'first_name',
        'last_name',
        'nickname',
        'parent__user__email',
        'parent__first_name',
        'parent__last_name',
        'primary_language',
    ]

    readonly_fields = [
        'id',
        'parent_link',
        'age',
        'age_in_months',
        'full_name',
        'display_name',
        'bmi',
        'has_psychology_history',
        'is_vaccination_current',
        'profile_completeness_display',
        'consent_summary_display',
        'age_appropriate_grades_display',
        'created_at',
        'updated_at',
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'id',
                'parent_link',
                'first_name',
                'last_name',
                'nickname',
                'full_name',
                'display_name',
                'date_of_birth',
                'age',
                'age_in_months',
                'gender',
                'profile_picture_url',
            )
        }),
        (_('Physical Information'), {
            'fields': (
                'height_cm',
                'weight_kg',
                'bmi',
            ),
            'classes': ('collapse',)
        }),
        (_('Health Information'), {
            'fields': (
                'health_status',
                'medical_history',
                'vaccination_status',
                'is_vaccination_current',
            ),
            'classes': ('collapse',)
        }),
        (_('Behavioral & Developmental'), {
            'fields': (
                'emotional_issues',
                'social_behavior',
                'developmental_concerns',
                'family_peer_relationship',
            ),
            'classes': ('collapse',)
        }),
        (_('Psychology History'), {
            'fields': (
                'has_seen_psychologist',
                'has_received_therapy',
                'has_psychology_history',
            )
        }),
        (_('Parental Input'), {
            'fields': (
                'parental_goals',
                'activity_tips',
                'parental_notes',
            ),
            'classes': ('collapse',)
        }),
        (_('Educational Information'), {
            'fields': (
                'primary_language',
                'school_grade_level',
                'age_appropriate_grades_display',
            )
        }),
        (_('Consent Management'), {
            'fields': (
                'consent_summary_display',
            ),
            'classes': ('collapse',)
        }),
        (_('Profile Metrics'), {
            'fields': (
                'profile_completeness_display',
            )
        }),
        (_('Timestamps'), {
            'fields': (
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',)
        }),
    )

    # Custom filters
    class AgeRangeFilter(admin.SimpleListFilter):
        title = _('Age Range')
        parameter_name = 'age_range'

        def lookups(self, request, model_admin):
            return (
                ('5-8', _('5-8 years (Early Elementary)')),
                ('9-12', _('9-12 years (Late Elementary)')),
                ('13-15', _('13-15 years (Middle School)')),
                ('16-17', _('16-17 years (High School)')),
            )

        def queryset(self, request, queryset):
            today = date.today()

            if self.value() == '5-8':
                start_date = date(today.year - 8, today.month, today.day)
                end_date = date(today.year - 5, today.month, today.day)
                return queryset.filter(date_of_birth__gte=start_date, date_of_birth__lte=end_date)
            elif self.value() == '9-12':
                start_date = date(today.year - 12, today.month, today.day)
                end_date = date(today.year - 9, today.month, today.day)
                return queryset.filter(date_of_birth__gte=start_date, date_of_birth__lte=end_date)
            elif self.value() == '13-15':
                start_date = date(today.year - 15, today.month, today.day)
                end_date = date(today.year - 13, today.month, today.day)
                return queryset.filter(date_of_birth__gte=start_date, date_of_birth__lte=end_date)
            elif self.value() == '16-17':
                start_date = date(today.year - 17, today.month, today.day)
                end_date = date(today.year - 16, today.month, today.day)
                return queryset.filter(date_of_birth__gte=start_date, date_of_birth__lte=end_date)

    class ConsentStatusFilter(admin.SimpleListFilter):
        title = _('Consent Status')
        parameter_name = 'consent_status'

        def lookups(self, request, model_admin):
            return (
                ('fully_consented', _('Fully Consented')),
                ('partially_consented', _('Partially Consented')),
                ('no_consent', _('No Consent Given')),
            )

        def queryset(self, request, queryset):
            if self.value() == 'fully_consented':
                # Children with all consent types granted
                return queryset.filter(
                    consent_forms_signed__isnull=False
                ).exclude(consent_forms_signed__exact={})
            elif self.value() == 'partially_consented':
                # Children with some but not all consents
                return queryset.filter(
                    consent_forms_signed__isnull=False
                ).exclude(consent_forms_signed__exact={})
            elif self.value() == 'no_consent':
                # Children with no consent or empty consent forms
                return queryset.filter(
                    Q(consent_forms_signed__isnull=True) | Q(consent_forms_signed__exact={})
                )

    list_filter = list_filter + [AgeRangeFilter, ConsentStatusFilter]

    # Display methods
    def parent_email(self, obj):
        """Display parent email"""
        return obj.parent.user.email
    parent_email.short_description = _('Parent Email')
    parent_email.admin_order_field = 'parent__user__email'

    def full_name(self, obj):
        """Display child's full name with nickname"""
        name = obj.full_name
        if obj.nickname and obj.nickname != obj.first_name:
            name += f' ("{obj.nickname}")'
        return name
    full_name.short_description = _('Full Name')
    full_name.admin_order_field = 'first_name'

    def age(self, obj):
        """Display age with formatting"""
        age = obj.age
        if age is not None:
            return f"{age} years"
        return "—"
    age.short_description = _('Age')

    def has_psychology_history(self, obj):
        """Display psychology history status"""
        return obj.has_psychology_history
    has_psychology_history.short_description = _('Psychology History')
    has_psychology_history.boolean = True

    def profile_completeness_display(self, obj):
        """Display profile completeness with color coding"""
        completeness = obj.get_profile_completeness()

        if completeness >= 80:
            color = 'green'
            icon = '●'
        elif completeness >= 60:
            color = 'orange'
            icon = '●'
        else:
            color = 'red'
            icon = '●'

        return format_html(
            '<span style="color: {};">{} {}%</span>',
            color,
            icon,
            completeness
        )
    profile_completeness_display.short_description = _('Profile Completeness')

    def consent_status_display(self, obj):
        """Display consent status summary"""
        if not obj.consent_forms_signed:
            return format_html('<span style="color: red;">No Consent</span>')

        consent_types = Child.get_default_consent_types()
        granted_count = 0
        total_count = len(consent_types)

        for consent_type in consent_types.keys():
            if obj.get_consent_status(consent_type):
                granted_count += 1

        if granted_count == total_count:
            color = 'green'
            status = f'Full ({granted_count}/{total_count})'
        elif granted_count > 0:
            color = 'orange'
            status = f'Partial ({granted_count}/{total_count})'
        else:
            color = 'red'
            status = f'None ({granted_count}/{total_count})'

        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            status
        )
    consent_status_display.short_description = _('Consent Status')

    def parent_link(self, obj):
        """Display link to parent admin"""
        url = reverse('admin:parents_parent_change', args=[obj.parent.user.id])
        return format_html(
            '<a href="{}">{} ({})</a>',
            url,
            obj.parent.full_name or obj.parent.user.email,
            obj.parent.user.email
        )
    parent_link.short_description = _('Parent')

    def consent_summary_display(self, obj):
        """Display detailed consent summary"""
        if not obj.consent_forms_signed:
            return format_html('<span style="color: red;">No consent forms signed</span>')

        consent_types = Child.get_default_consent_types()
        html_parts = ['<ul style="margin: 0; padding-left: 20px;">']

        for consent_type, description in consent_types.items():
            status = obj.get_consent_status(consent_type)
            consent_details = obj.consent_forms_signed.get(consent_type, {})

            if status:
                icon = '✓'
                color = 'green'
                date_signed = consent_details.get('date_signed', 'Unknown date')
                if date_signed and date_signed != 'Unknown date':
                    try:
                        # Parse ISO format date
                        from datetime import datetime
                        dt = datetime.fromisoformat(date_signed.replace('Z', '+00:00'))
                        date_display = dt.strftime('%Y-%m-%d')
                    except:
                        date_display = date_signed
                else:
                    date_display = 'Unknown date'
                status_text = f'Granted ({date_display})'
            elif consent_details:
                icon = '✗'
                color = 'red'
                status_text = 'Revoked'
            else:
                icon = '?'
                color = 'gray'
                status_text = 'Pending'

            html_parts.append(
                f'<li><strong>{description}:</strong> '
                f'<span style="color: {color};">{icon} {status_text}</span></li>'
            )

        html_parts.append('</ul>')
        return format_html(''.join(html_parts))
    consent_summary_display.short_description = _('Consent Details')

    def age_appropriate_grades_display(self, obj):
        """Display age-appropriate grade suggestions"""
        grades = obj.get_age_appropriate_grade_suggestions()
        if grades:
            return ', '.join(grades)
        return '—'
    age_appropriate_grades_display.short_description = _('Suggested Grades')

    # Queryset optimization
    def get_queryset(self, request):
        """Optimize queryset with select_related and prefetch_related"""
        return super().get_queryset(request).select_related(
            'parent',
            'parent__user'
        )

    # Custom actions
    @admin.action(description=_('Reset consent forms to pending'))
    def reset_consent_forms(self, request, queryset):
        """Reset consent forms for selected children"""
        updated_count = 0
        for child in queryset:
            try:
                child.consent_forms_signed = {}
                child.save(update_fields=['consent_forms_signed', 'updated_at'])
                updated_count += 1
            except Exception:
                pass

        self.message_user(
            request,
            _(f'Successfully reset consent forms for {updated_count} children.')
        )

    @admin.action(description=_('Export children data to CSV'))
    def export_children_csv(self, request, queryset):
        """Export selected children data to CSV"""
        import csv
        from django.http import HttpResponse

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="children_export.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'ID', 'Full Name', 'Age', 'Gender', 'Parent Email',
            'School Grade', 'Has Psychology History', 'Profile Completeness',
            'Consent Status', 'Created Date'
        ])

        for child in queryset:
            consent_types = Child.get_default_consent_types()
            granted_count = sum(1 for ct in consent_types.keys() if child.get_consent_status(ct))
            consent_status = f"{granted_count}/{len(consent_types)}"

            writer.writerow([
                str(child.id),
                child.full_name,
                child.age or 'Unknown',
                child.gender or 'Not specified',
                child.parent.user.email,
                child.school_grade_level or 'Not specified',
                'Yes' if child.has_psychology_history else 'No',
                f"{child.get_profile_completeness()}%",
                consent_status,
                child.created_at.strftime('%Y-%m-%d')
            ])

        return response

    actions = ['reset_consent_forms', 'export_children_csv']

    # Permissions
    def has_add_permission(self, request):
        """Prevent manual creation of child profiles through admin"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Allow deletion but warn it's permanent"""
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        """Allow changes for staff"""
        return request.user.is_staff

    # Custom views and inlines could be added here
    def get_readonly_fields(self, request, obj=None):
        """Make certain fields readonly based on user permissions"""
        readonly = list(self.readonly_fields)

        # Non-superusers cannot edit sensitive fields
        if not request.user.is_superuser:
            readonly.extend([
                'parent',
                'consent_forms_signed',
            ])

        return readonly

    # Add custom CSS/JS if needed
    class Media:
        css = {
            'all': ('admin/css/child_admin.css',)  # Create this file if needed
        }
        js = ('admin/js/child_admin.js',)  # Create this file if needed

    # Override admin URLs if needed for custom views
    def get_urls(self):
        """Add custom admin URLs"""
        urls = super().get_urls()
        from django.urls import path

        custom_urls = [
            # Add custom admin views here if needed
            # path('consent-report/', self.admin_site.admin_view(self.consent_report_view), name='children_consent_report'),
        ]

        return custom_urls + urls

    # Add methods for custom admin views
    def consent_report_view(self, request):
        """Custom view for consent reporting"""
        # Implementation for custom consent report view
        pass

    # Add changelist customizations
    def changelist_view(self, request, extra_context=None):
        """Add extra context to changelist"""
        extra_context = extra_context or {}

        # Add summary statistics
        queryset = self.get_queryset(request)
        extra_context.update({
            'total_children': queryset.count(),
            'children_with_psychology_history': queryset.filter(
                Q(has_seen_psychologist=True) | Q(has_received_therapy=True)
            ).count(),
            'fully_consented_children': queryset.exclude(
                Q(consent_forms_signed__isnull=True) | Q(consent_forms_signed__exact={})
            ).count(),
            'verified_parents_children': queryset.filter(
                parent__user__is_verified=True
            ).count(),
        })

        return super().changelist_view(request, extra_context=extra_context)