# parents/permissions.py
from rest_framework import permissions
from django.utils.translation import gettext_lazy as _


class IsParentOwner(permissions.BasePermission):
    """
    Permission to only allow parents to access their own profile
    """
    message = _("You can only access your own parent profile.")

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
        Check if the parent profile belongs to the requesting user
        """
        # obj should be a Parent instance
        return obj.user == request.user


class IsParentOwnerOrReadOnly(permissions.BasePermission):
    """
    Permission to allow:
    - Parents: full access to their own profile
    - Psychologists: read-only access to their clients' parent profiles
    - Admins: full access to all parent profiles
    """
    message = _("You don't have permission to access this parent profile.")

    def has_permission(self, request, view):
        """
        Check basic permission requirements
        """
        if not request.user.is_authenticated:
            return False

        # Admins have full access
        if request.user.is_admin or request.user.is_staff:
            return True

        # Parents can access their own profiles
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

        # Parents can access their own profile
        if request.user.user_type == 'Parent' and obj.user == request.user:
            return True

        # Psychologists can read parent profiles of their clients
        if (request.user.user_type == 'Psychologist' and
            request.method in permissions.SAFE_METHODS):
            # TODO: Add logic to check if psychologist has worked with this parent's children
            # For now, allow read access to any parent profile for psychologists
            # Later: return obj.children.filter(appointments__psychologist__user=request.user).exists()
            return True

        return False


class IsAdminOrReadOnlyForPsychologist(permissions.BasePermission):
    """
    Permission for administrative functions:
    - Admins: full access
    - Psychologists: read-only access
    - Parents: no access
    """
    message = _("You don't have permission to perform this action.")

    def has_permission(self, request, view):
        """
        Check if user has permission for this view
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