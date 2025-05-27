# children/permissions.py
from rest_framework import permissions
from django.utils.translation import gettext_lazy as _
from parents.models import Parent


class IsChildOwner(permissions.BasePermission):
    """
    Permission to only allow parents to access their own children
    """
    message = _("You can only access your own children.")

    def has_permission(self, request, view):
        """
        Check if user is authenticated and is a parent
        """
        return (
            request.user.is_authenticated and
            request.user.user_type == 'Parent'
        )

    def has_object_permission(self, request, view, obj):
        """
        Check if the child belongs to the requesting parent
        """
        # obj should be a Child instance
        return obj.parent.user == request.user


class IsChildOwnerOrReadOnly(permissions.BasePermission):
    """
    Permission to allow:
    - Parents: full access to their own children
    - Psychologists: read-only access to children they work with
    - Admins: full access to all children
    """
    message = _("You don't have permission to access this child profile.")

    def has_permission(self, request, view):
        """
        Check basic permission requirements
        """
        if not request.user.is_authenticated:
            return False

        # Admins have full access
        if request.user.is_admin or request.user.is_staff or request.user.is_superuser:
            return True

        # Parents can access their own children
        if request.user.user_type == 'Parent':
            return True

        # Psychologists can have read-only access
        if request.user.user_type == 'Psychologist' and request.method in permissions.SAFE_METHODS:
            return True

        return False

    def has_object_permission(self, request, view, obj):
        """
        Check object-level permissions
        """
        # Admins have full access
        if request.user.is_admin or request.user.is_staff:
            return True

        # Parents can access their own children
        if request.user.user_type == 'Parent' and obj.parent.user == request.user:
            return True

        # Psychologists can read children they work with
        if (request.user.user_type == 'Psychologist' and
            request.method in permissions.SAFE_METHODS):
            # TODO: Add logic to check if psychologist has worked with this child
            # For now, allow read access to any child for psychologists
            # Later: return obj.appointments.filter(psychologist__user=request.user).exists()
            return True

        return False


class IsParentOfChild(permissions.BasePermission):
    """
    Permission to check if the authenticated user is the parent of a specific child
    Used for creation and management operations
    """
    message = _("You can only manage your own children.")

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
        Check if user is the parent of this child
        """
        return obj.parent.user == request.user


class CanCreateChildForParent(permissions.BasePermission):
    """
    Permission for creating children - ensures parent can only create for themselves
    """
    message = _("You can only create children for your own parent profile.")

    def has_permission(self, request, view):
        """
        Check if user is authenticated parent with verified email
        """
        if not request.user.is_authenticated:
            return False

        if request.user.user_type != 'Parent':
            return False

        # Check if parent has verified email
        if not request.user.is_verified:
            return False

        # Check if parent profile exists
        try:
            Parent.objects.get(user=request.user)
            return True
        except Parent.DoesNotExist:
            return False


class CanManageChildConsent(permissions.BasePermission):
    """
    Permission for managing child consent forms
    """
    message = _("You don't have permission to manage consent for this child.")

    def has_permission(self, request, view):
        """
        Check basic permission for consent management
        """
        if not request.user.is_authenticated:
            return False

        # Admins can manage all consent
        if request.user.is_admin or request.user.is_staff:
            return True

        # Parents can manage consent for their children
        if request.user.user_type == 'Parent':
            return True

        # Psychologists cannot manage consent (they can view status)
        return False

    def has_object_permission(self, request, view, obj):
        """
        Check object-level permission for consent management
        """
        # Admins can manage all consent
        if request.user.is_admin or request.user.is_staff:
            return True

        # Parents can manage consent for their own children
        if request.user.user_type == 'Parent' and obj.parent.user == request.user:
            return True

        return False


class IsAdminOrReadOnlyForPsychologist(permissions.BasePermission):
    """
    Permission for administrative functions:
    - Admins: full access
    - Psychologists: read-only access to children they work with
    - Parents: no access to other children
    """
    message = _("You don't have permission to perform this action.")

    def has_permission(self, request, view):
        """
        Check if user has permission for administrative views
        """
        if not request.user.is_authenticated:
            return False

        # Admins have full access
        if request.user.is_admin or request.user.is_staff:
            return True

        # Psychologists have read-only access
        if (request.user.user_type == 'Psychologist' and
            request.method in permissions.SAFE_METHODS):
            return True

        return False

    def has_object_permission(self, request, view, obj):
        """
        Check object-level permissions for administrative access
        """
        # Admins have full access
        if request.user.is_admin or request.user.is_staff:
            return True

        # Psychologists can read children they work with
        if (request.user.user_type == 'Psychologist' and
            request.method in permissions.SAFE_METHODS):
            # TODO: Check if psychologist has worked with this child
            # For now, allow read access
            # Later: return obj.appointments.filter(psychologist__user=request.user).exists()
            return True

        return False


class CanSearchChildren(permissions.BasePermission):
    """
    Permission for searching children with different access levels
    """
    message = _("You don't have permission to search children.")

    def has_permission(self, request, view):
        """
        Check permission for child search operations
        """
        if not request.user.is_authenticated:
            return False

        # Admins can search all children
        if request.user.is_admin or request.user.is_staff:
            return True

        # Parents can search their own children
        if request.user.user_type == 'Parent':
            return True

        # Psychologists can search children they work with
        if request.user.user_type == 'Psychologist':
            return True

        return False


class CanViewChildReports(permissions.BasePermission):
    """
    Permission for viewing child reports and assessments
    Future use for assessment/report viewing
    """
    message = _("You don't have permission to view reports for this child.")

    def has_permission(self, request, view):
        """
        Check permission for viewing child reports
        """
        if not request.user.is_authenticated:
            return False

        # All authenticated users can potentially view reports (with object-level checks)
        return True

    def has_object_permission(self, request, view, obj):
        """
        Check object-level permission for viewing reports
        """
        # Admins can view all reports
        if request.user.is_admin or request.user.is_staff:
            return True

        # Parents can view reports for their children
        if request.user.user_type == 'Parent' and obj.parent.user == request.user:
            return True

        # Psychologists can view reports for children they've worked with
        if request.user.user_type == 'Psychologist':
            # TODO: Check if psychologist created the report or worked with the child
            # For now, allow if they have any connection
            # Later: return obj.assessments.filter(psychologist__user=request.user).exists()
            return True

        return False


# Composite permissions for common use cases

class ChildProfilePermissions(permissions.BasePermission):
    """
    Composite permission for child profile operations
    Combines multiple permission checks
    """
    message = _("You don't have permission to access this child profile.")

    def has_permission(self, request, view):
        """
        Check basic permission for child profile access
        """
        if not request.user.is_authenticated:
            return False

        # Determine action type
        action = getattr(view, 'action', None)

        # Creation permissions
        if action == 'create':
            return CanCreateChildForParent().has_permission(request, view)

        # List/search permissions
        if action in ['list', 'search']:
            return CanSearchChildren().has_permission(request, view)

        # General access permissions
        return IsChildOwnerOrReadOnly().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        """
        Check object-level permissions
        """
        action = getattr(view, 'action', None)

        # Consent management
        if action in ['manage_consent', 'bulk_consent']:
            return CanManageChildConsent().has_object_permission(request, view, obj)

        # Profile modifications
        if action in ['update', 'partial_update', 'destroy']:
            return IsChildOwner().has_object_permission(request, view, obj)

        # General access
        return IsChildOwnerOrReadOnly().has_object_permission(request, view, obj)