# appointments/permissions.py
from rest_framework import permissions
from django.utils.translation import gettext_lazy as _


class IsAppointmentParticipant(permissions.BasePermission):
    """
    Permission to allow appointment participants (parent or psychologist) to access appointment
    """
    message = _("You can only access appointments you are a participant in.")

    def has_permission(self, request, view):
        """
        Check if user is authenticated and has a role that can participate in appointments
        """
        if not request.user.is_authenticated:
            return False

        # Admins can access all appointments
        if request.user.is_admin or request.user.is_staff:
            return True

        # Parents and psychologists can access their own appointments
        if request.user.user_type in ['Parent', 'Psychologist']:
            return True

        return False

    def has_object_permission(self, request, view, obj):
        """
        Check if user is participant in this specific appointment
        """
        # Admins can access all appointments
        if request.user.is_admin or request.user.is_staff:
            return True

        # Parents can access appointments they booked
        if request.user.user_type == 'Parent' and hasattr(request.user, 'parent_profile'):
            return obj.parent == request.user.parent_profile

        # Psychologists can access appointments they're providing
        if request.user.user_type == 'Psychologist' and hasattr(request.user, 'psychologist_profile'):
            return obj.psychologist == request.user.psychologist_profile

        return False


class CanBookAppointments(permissions.BasePermission):
    """
    Permission for booking appointments - only verified parents
    """
    message = _("You must be a verified parent to book appointments.")

    def has_permission(self, request, view):
        """
        Check if user can book appointments
        """
        if not request.user.is_authenticated:
            return False

        # Must be a parent
        if request.user.user_type != 'Parent':
            return False

        # Must be verified and active
        if not request.user.is_verified or not request.user.is_active:
            return False

        # Must have parent profile
        if not hasattr(request.user, 'parent_profile'):
            return False

        return True


class CanManageAppointments(permissions.BasePermission):
    """
    Permission for managing appointments (updating notes, etc.)
    """
    message = _("You don't have permission to manage this appointment.")

    def has_permission(self, request, view):
        """
        Check basic permission for appointment management
        """
        if not request.user.is_authenticated:
            return False

        # Admins can manage all appointments
        if request.user.is_admin or request.user.is_staff:
            return True

        # Participants can manage their appointments
        if request.user.user_type in ['Parent', 'Psychologist']:
            return True

        return False

    def has_object_permission(self, request, view, obj):
        """
        Check object-level permissions for appointment management
        """
        # Admins can manage all appointments
        if request.user.is_admin or request.user.is_staff:
            return True

        # Parents can update their appointment notes
        if request.user.user_type == 'Parent' and hasattr(request.user, 'parent_profile'):
            if obj.parent == request.user.parent_profile:
                # Parents can only update certain fields
                return True

        # Psychologists can update their appointment notes
        if request.user.user_type == 'Psychologist' and hasattr(request.user, 'psychologist_profile'):
            if obj.psychologist == request.user.psychologist_profile:
                return True

        return False


class CanCancelAppointment(permissions.BasePermission):
    """
    Permission for cancelling appointments
    """
    message = _("You don't have permission to cancel this appointment.")

    def has_permission(self, request, view):
        """
        Check basic permission for appointment cancellation
        """
        if not request.user.is_authenticated:
            return False

        # Admins can cancel any appointment
        if request.user.is_admin or request.user.is_staff:
            return True

        # Participants can cancel their appointments
        if request.user.user_type in ['Parent', 'Psychologist']:
            return True

        return False

    def has_object_permission(self, request, view, obj):
        """
        Check object-level permissions for appointment cancellation
        """
        # Admins can cancel any appointment
        if request.user.is_admin or request.user.is_staff:
            return True

        # Check if appointment can actually be cancelled
        if not obj.can_be_cancelled:
            return False

        # Parents can cancel their appointments
        if request.user.user_type == 'Parent' and hasattr(request.user, 'parent_profile'):
            return obj.parent == request.user.parent_profile

        # Psychologists can cancel their appointments
        if request.user.user_type == 'Psychologist' and hasattr(request.user, 'psychologist_profile'):
            return obj.psychologist == request.user.psychologist_profile

        return False


class CanVerifyQRCode(permissions.BasePermission):
    """
    Permission for QR code verification
    """
    message = _("You don't have permission to verify QR codes.")

    def has_permission(self, request, view):
        """
        Check if user can verify QR codes
        """
        if not request.user.is_authenticated:
            return False

        # Admins can verify any QR code
        if request.user.is_admin or request.user.is_staff:
            return True

        # Parents can verify their appointment QR codes
        if request.user.user_type == 'Parent':
            return True

        # Psychologists can verify QR codes for their appointments
        if request.user.user_type == 'Psychologist':
            return True

        return False


class CanManageSlots(permissions.BasePermission):
    """
    Permission for managing appointment slots
    """
    message = _("You don't have permission to manage appointment slots.")

    def has_permission(self, request, view):
        """
        Check if user can manage appointment slots
        """
        if not request.user.is_authenticated:
            return False

        # Admins can manage all slots
        if request.user.is_admin or request.user.is_staff:
            return True

        # Psychologists can manage their own slots
        if request.user.user_type == 'Psychologist':
            return True

        return False

    def has_object_permission(self, request, view, obj):
        """
        Check object-level permissions for slot management
        """
        # Admins can manage all slots
        if request.user.is_admin or request.user.is_staff:
            return True

        # Psychologists can manage their own slots
        if request.user.user_type == 'Psychologist' and hasattr(request.user, 'psychologist_profile'):
            return obj.psychologist == request.user.psychologist_profile

        return False


class CanAccessAnalytics(permissions.BasePermission):
    """
    Permission for accessing appointment analytics
    """
    message = _("You don't have permission to access appointment analytics.")

    def has_permission(self, request, view):
        """
        Check if user can access analytics
        """
        if not request.user.is_authenticated:
            return False

        # Determine action type
        action = getattr(view, 'action', None)

        # Platform-wide analytics only for admins
        if action == 'platform_stats':
            return request.user.is_admin or request.user.is_staff

        # Psychologist stats for psychologists and admins
        if action == 'psychologist_stats':
            return (
                request.user.user_type == 'Psychologist' or
                request.user.is_admin or
                request.user.is_staff
            )

        # General analytics access
        return (
            request.user.user_type in ['Psychologist', 'Admin'] or
            request.user.is_admin or
            request.user.is_staff
        )


class IsMarketplaceUser(permissions.BasePermission):
    """
    Permission for marketplace users to view available slots
    """
    message = _("You must be a verified user to access booking information.")

    def has_permission(self, request, view):
        """
        Check if user can access marketplace booking features
        """
        if not request.user.is_authenticated:
            return False

        # Must be verified and active
        if not request.user.is_verified or not request.user.is_active:
            return False

        # Parents can browse and book
        if request.user.user_type == 'Parent':
            return True

        # Psychologists can view marketplace for reference
        if request.user.user_type == 'Psychologist':
            return True

        # Admins can access everything
        if request.user.is_admin or request.user.is_staff:
            return True

        return False


# Composite permissions for common use cases

class AppointmentViewPermissions(permissions.BasePermission):
    """
    Composite permission for appointment view operations
    Combines multiple permission checks based on action
    """
    message = _("You don't have permission to perform this action on appointments.")

    def has_permission(self, request, view):
        """
        Check basic permission for appointment operations
        """
        if not request.user.is_authenticated:
            return False

        # Determine action type
        action = getattr(view, 'action', None)

        # Booking permissions
        if action in ['create', 'book_appointment']:
            return CanBookAppointments().has_permission(request, view)

        # Viewing permissions
        if action in ['list', 'retrieve', 'my_appointments']:
            return IsAppointmentParticipant().has_permission(request, view)

        # Management permissions
        if action in ['update', 'partial_update']:
            return CanManageAppointments().has_permission(request, view)

        # Cancellation permissions
        if action == 'cancel':
            return CanCancelAppointment().has_permission(request, view)

        # QR verification permissions
        if action == 'verify_qr':
            return CanVerifyQRCode().has_permission(request, view)

        # Marketplace permissions
        if action in ['available_slots', 'recommended_times']:
            return IsMarketplaceUser().has_permission(request, view)

        # Default to basic authentication
        return True

    def has_object_permission(self, request, view, obj):
        """
        Check object-level permissions based on action
        """
        action = getattr(view, 'action', None)

        # Viewing permissions
        if action in ['retrieve', 'list']:
            return IsAppointmentParticipant().has_object_permission(request, view, obj)

        # Management permissions
        if action in ['update', 'partial_update']:
            return CanManageAppointments().has_object_permission(request, view, obj)

        # Cancellation permissions
        if action == 'cancel':
            return CanCancelAppointment().has_object_permission(request, view, obj)

        # Default to participant check
        return IsAppointmentParticipant().has_object_permission(request, view, obj)


class AppointmentSlotPermissions(permissions.BasePermission):
    """
    Permission for appointment slot access
    - Admins: Full access
    - Psychologists: Can view their own slots
    - Parents: Can view available marketplace slots
    """

    def has_permission(self, request, view):
        """Check if user can access appointment slots"""
        if not request.user or not request.user.is_authenticated:
            return False

        # All authenticated users can view slots (filtering in queryset)
        return True

    def has_object_permission(self, request, view, obj):
        """Check if user can access specific appointment slot"""
        if not request.user or not request.user.is_authenticated:
            return False

        # Admins can access everything
        if request.user.is_admin or request.user.is_staff:
            return True

        # Psychologists can access their own slots
        if request.user.user_type == 'Psychologist':
            try:
                from psychologists.services import PsychologistService
                psychologist = PsychologistService.get_psychologist_by_user(request.user)
                return obj.psychologist == psychologist
            except:
                return False

        # Parents can view available marketplace slots
        if request.user.user_type == 'Parent':
            from datetime import date
            return (
                not obj.is_booked and
                obj.slot_date >= date.today() and
                obj.psychologist.verification_status == 'Approved' and
                obj.psychologist.user.is_active and
                obj.psychologist.user.is_verified and
                (obj.psychologist.offers_initial_consultation or obj.psychologist.offers_online_sessions)
            )

        return False

class AppointmentAnalyticsPermissions(permissions.BasePermission):
    """
    Composite permission for appointment analytics operations
    """
    message = _("You don't have permission to access appointment analytics.")

    def has_permission(self, request, view):
        """
        Check permission for analytics access
        """
        return CanAccessAnalytics().has_permission(request, view)


# Role-specific permissions

class IsPsychologistAppointmentProvider(permissions.BasePermission):
    """
    Permission specifically for psychologists managing their appointments
    """
    message = _("Only the psychologist providing this appointment can perform this action.")

    def has_permission(self, request, view):
        """
        Check if user is a psychologist
        """
        return (
            request.user.is_authenticated and
            request.user.user_type == 'Psychologist'
        )

    def has_object_permission(self, request, view, obj):
        """
        Check if psychologist is the one providing this appointment
        """
        if hasattr(request.user, 'psychologist_profile'):
            return obj.psychologist == request.user.psychologist_profile
        return False


class IsParentAppointmentBooker(permissions.BasePermission):
    """
    Permission specifically for parents managing their appointments
    """
    message = _("Only the parent who booked this appointment can perform this action.")

    def has_permission(self, request, view):
        """
        Check if user is a parent
        """
        return (
            request.user.is_authenticated and
            request.user.user_type == 'Parent'
        )

    def has_object_permission(self, request, view, obj):
        """
        Check if parent is the one who booked this appointment
        """
        if hasattr(request.user, 'parent_profile'):
            return obj.parent == request.user.parent_profile
        return False


class CanCompleteAppointment(permissions.BasePermission):
    """
    Permission for marking appointments as completed (psychologists only)
    """
    message = _("Only psychologists can mark appointments as completed.")

    def has_permission(self, request, view):
        """
        Check if user can mark appointments as completed
        """
        return (
            request.user.is_authenticated and
            (request.user.user_type == 'Psychologist' or request.user.is_admin or request.user.is_staff)
        )

    def has_object_permission(self, request, view, obj):
        """
        Check if user can mark this specific appointment as completed
        """
        # Admins can mark any appointment as completed
        if request.user.is_admin or request.user.is_staff:
            return True

        # Only the psychologist providing the appointment can mark it as completed
        if request.user.user_type == 'Psychologist' and hasattr(request.user, 'psychologist_profile'):
            return obj.psychologist == request.user.psychologist_profile

        return False