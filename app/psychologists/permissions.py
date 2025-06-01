# psychologists/permissions.py
from rest_framework import permissions
from django.utils.translation import gettext_lazy as _


class IsPsychologistOwner(permissions.BasePermission):
    """
    Permission to only allow psychologists to access their own profile
    """
    message = _("You can only access your own psychologist profile.")

    def has_permission(self, request, view):
        """
        Check if user is authenticated and is a psychologist
        """
        return (
            request.user.is_authenticated and
            request.user.user_type == 'Psychologist'
        )

    def has_object_permission(self, request, view, obj):
        """
        Check if the psychologist profile belongs to the requesting user
        """
        # obj should be a Psychologist instance
        return obj.user == request.user


class IsPsychologistOwnerOrReadOnly(permissions.BasePermission):
    """
    Permission to allow:
    - Psychologists: full access to their own profile
    - Parents: read-only access to marketplace-visible psychologist profiles
    - Admins: full access to all psychologist profiles
    """
    message = _("You don't have permission to access this psychologist profile.")

    def has_permission(self, request, view):
        """
        Check basic permission requirements
        """
        if not request.user.is_authenticated:
            return False

        # Admins have full access
        if request.user.is_admin or request.user.is_staff:
            return True

        # Psychologists can access their own profiles
        if request.user.user_type == 'Psychologist':
            return True

        # Parents can have read-only access to marketplace psychologists
        if request.user.user_type == 'Parent' and request.method in permissions.SAFE_METHODS:
            return True

        return False

    def has_object_permission(self, request, view, obj):
        """
        Check object-level permissions
        """
        # Admins have full access
        if request.user.is_admin or request.user.is_staff:
            return True

        # Psychologists can access their own profile
        if request.user.user_type == 'Psychologist' and obj.user == request.user:
            return True

        # Parents can read marketplace-visible psychologist profiles
        if (request.user.user_type == 'Parent' and
            request.method in permissions.SAFE_METHODS):
            # Only allow access to marketplace-visible psychologists
            return obj.is_marketplace_visible

        return False


class CanCreatePsychologistProfile(permissions.BasePermission):
    """
    Permission for creating psychologist profiles - ensures user can only create for themselves
    """
    message = _("You can only create a psychologist profile for your own account.")

    def has_permission(self, request, view):
        """
        Check if user is authenticated psychologist with verified email
        """
        if not request.user.is_authenticated:
            return False

        if request.user.user_type != 'Psychologist':
            return False

        # Check if psychologist has verified email
        if not request.user.is_verified:
            return False

        # Check if psychologist profile doesn't already exist
        from .models import Psychologist
        try:
            Psychologist.objects.get(user=request.user)
            # Profile already exists, can't create another
            return False
        except Psychologist.DoesNotExist:
            return True


class CanUpdatePsychologistVerification(permissions.BasePermission):
    """
    Permission for updating psychologist verification status (Admin only)
    """
    message = _("Only administrators can update verification status.")

    def has_permission(self, request, view):
        """
        Check if user is admin
        """
        return (
            request.user.is_authenticated and
            (request.user.is_admin or request.user.is_staff)
        )

    def has_object_permission(self, request, view, obj):
        """
        Admins can update any psychologist's verification status
        """
        return request.user.is_admin or request.user.is_staff


class CanManagePsychologistAvailability(permissions.BasePermission):
    """
    Permission for managing psychologist availability
    """
    message = _("You don't have permission to manage this psychologist's availability.")

    def has_permission(self, request, view):
        """
        Check basic permission for availability management
        """
        if not request.user.is_authenticated:
            return False

        # Admins can manage all availability
        if request.user.is_admin or request.user.is_staff:
            return True

        # Psychologists can manage their own availability
        if request.user.user_type == 'Psychologist':
            return True

        return False

    def has_object_permission(self, request, view, obj):
        """
        Check object-level permission for availability management
        """
        # Admins can manage all availability
        if request.user.is_admin or request.user.is_staff:
            return True

        # Psychologists can manage their own availability
        if request.user.user_type == 'Psychologist':
            # obj could be PsychologistAvailability or Psychologist
            if hasattr(obj, 'psychologist'):
                # obj is PsychologistAvailability
                return obj.psychologist.user == request.user
            else:
                # obj is Psychologist
                return obj.user == request.user

        return False


class IsMarketplaceVisible(permissions.BasePermission):
    """
    Permission to ensure only marketplace-visible psychologists are accessible to parents
    """
    message = _("This psychologist profile is not available in the marketplace.")

    def has_permission(self, request, view):
        """
        Basic permission check - authenticated users only
        """
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """
        Check if psychologist is marketplace visible for parent access
        """
        # Admins and the psychologist themselves can always access
        if (request.user.is_admin or request.user.is_staff or
            (request.user.user_type == 'Psychologist' and obj.user == request.user)):
            return True

        # For parents, only allow access to marketplace-visible psychologists
        if request.user.user_type == 'Parent':
            return obj.is_marketplace_visible

        # For other psychologists, allow read access to marketplace-visible profiles
        if request.user.user_type == 'Psychologist':
            return obj.is_marketplace_visible

        return False


class CanSearchPsychologists(permissions.BasePermission):
    """
    Permission for searching psychologists with different access levels
    """
    message = _("You don't have permission to search psychologists.")

    def has_permission(self, request, view):
        """
        Check permission for psychologist search operations
        """
        if not request.user.is_authenticated:
            return False

        # Admins can search all psychologists
        if request.user.is_admin or request.user.is_staff:
            return True

        # Parents can search marketplace psychologists
        if request.user.user_type == 'Parent':
            return True

        # Psychologists can search other psychologists (for networking/reference)
        if request.user.user_type == 'Psychologist':
            return True

        return False


class CanViewPsychologistReports(permissions.BasePermission):
    """
    Permission for viewing psychologist performance reports and analytics
    Future use for admin analytics
    """
    message = _("You don't have permission to view psychologist reports.")

    def has_permission(self, request, view):
        """
        Check permission for viewing psychologist reports
        """
        if not request.user.is_authenticated:
            return False

        # Admins can view all reports
        if request.user.is_admin or request.user.is_staff:
            return True

        # Psychologists can view their own performance reports
        if request.user.user_type == 'Psychologist':
            return True

        return False

    def has_object_permission(self, request, view, obj):
        """
        Check object-level permission for viewing reports
        """
        # Admins can view all reports
        if request.user.is_admin or request.user.is_staff:
            return True

        # Psychologists can view their own reports
        if request.user.user_type == 'Psychologist' and obj.user == request.user:
            return True

        return False


class IsApprovedPsychologist(permissions.BasePermission):
    """
    Permission to ensure only approved psychologists can perform certain actions
    """
    message = _("Your psychologist profile must be approved to perform this action.")

    def has_permission(self, request, view):
        """
        Check if user is an approved psychologist
        """
        if not request.user.is_authenticated:
            return False

        if request.user.user_type != 'Psychologist':
            return False

        # Check if psychologist profile exists and is approved
        from .models import Psychologist
        try:
            psychologist = Psychologist.objects.get(user=request.user)
            return psychologist.verification_status == 'Approved'
        except Psychologist.DoesNotExist:
            return False

    def has_object_permission(self, request, view, obj):
        """
        Object-level check for approved status
        """
        # If accessing own profile, check approval status
        if hasattr(obj, 'user') and obj.user == request.user:
            return obj.verification_status == 'Approved'

        # For other objects related to psychologist, check if requesting user is approved
        return self.has_permission(request, view)


# Composite permissions for common use cases

class PsychologistProfilePermissions(permissions.BasePermission):
    """
    Composite permission for psychologist profile operations
    Combines multiple permission checks based on action
    """
    message = _("You don't have permission to access this psychologist profile.")

    def has_permission(self, request, view):
        """
        Check basic permission for psychologist profile access
        """
        if not request.user.is_authenticated:
            return False

        # Determine action type
        action = getattr(view, 'action', None)

        # Creation permissions
        if action == 'create':
            return CanCreatePsychologistProfile().has_permission(request, view)

        # Verification permissions (admin only)
        if action in ['update_verification', 'verify', 'approve', 'reject']:
            return CanUpdatePsychologistVerification().has_permission(request, view)

        # Availability management
        if action in ['availability', 'create_availability', 'update_availability']:
            return CanManagePsychologistAvailability().has_permission(request, view)

        # List/search permissions
        if action in ['list', 'search', 'marketplace']:
            return CanSearchPsychologists().has_permission(request, view)

        # General access permissions
        return IsPsychologistOwnerOrReadOnly().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        """
        Check object-level permissions based on action
        """
        action = getattr(view, 'action', None)

        # Verification management (admin only)
        if action in ['update_verification', 'verify', 'approve', 'reject']:
            return CanUpdatePsychologistVerification().has_object_permission(request, view, obj)

        # Availability management
        if action in ['availability', 'create_availability', 'update_availability']:
            return CanManagePsychologistAvailability().has_object_permission(request, view, obj)

        # Profile modifications (psychologist own profile or admin)
        if action in ['update', 'partial_update', 'destroy']:
            return IsPsychologistOwner().has_object_permission(request, view, obj)

        # Marketplace visibility check for parent access
        if request.user.user_type == 'Parent':
            return IsMarketplaceVisible().has_object_permission(request, view, obj)

        # General access
        return IsPsychologistOwnerOrReadOnly().has_object_permission(request, view, obj)


class PsychologistAvailabilityPermissions(permissions.BasePermission):
    """
    Composite permission for psychologist availability operations
    """
    message = _("You don't have permission to manage this availability.")

    def has_permission(self, request, view):
        """
        Check basic permission for availability operations
        """
        return CanManagePsychologistAvailability().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        """
        Check object-level permissions for availability
        """
        return CanManagePsychologistAvailability().has_object_permission(request, view, obj)


class PsychologistMarketplacePermissions(permissions.BasePermission):
    """
    Permission for marketplace-related operations
    """
    message = _("You don't have permission to access the psychologist marketplace.")

    def has_permission(self, request, view):
        """
        Check permission for marketplace access
        """
        if not request.user.is_authenticated:
            return False

        # Parents can browse marketplace
        if request.user.user_type == 'Parent':
            return True

        # Psychologists can view marketplace (for reference)
        if request.user.user_type == 'Psychologist':
            return True

        # Admins can access marketplace
        if request.user.is_admin or request.user.is_staff:
            return True

        return False

    def has_object_permission(self, request, view, obj):
        """
        Check object-level permissions for marketplace access
        """
        # For marketplace operations, only show approved psychologists to parents
        if request.user.user_type == 'Parent':
            return obj.is_marketplace_visible

        # Psychologists and admins can see all profiles
        return True