# parents/permissions.py
from rest_framework import permissions
from django.utils.translation import gettext_lazy as _


class IsParent(permissions.BasePermission):
    """
    Custom permission to only allow parents to access parent-specific views.
    """
    message = _("You must be a parent to access this resource.")

    def has_permission(self, request, view):
        """
        Check if the user is authenticated and is a parent.
        """
        return (
            request.user and
            request.user.is_authenticated and
            hasattr(request.user, 'user_type') and
            request.user.user_type == 'Parent'
        )

    def has_object_permission(self, request, view, obj):
        """
        Check if the parent can access this specific object.
        Parents can only access their own profile.
        """
        # If obj is a Parent instance
        if hasattr(obj, 'user'):
            return obj.user == request.user

        # If obj is related to a parent (future use for children, etc.)
        if hasattr(obj, 'parent'):
            return obj.parent.user == request.user

        return False


class IsParentOrReadOnly(permissions.BasePermission):
    """
    Custom permission to allow parents full access and others read-only access.
    Useful for shared resources that parents can modify but others can view.
    """

    def has_permission(self, request, view):
        """
        Read permissions are allowed to any authenticated user,
        but write permissions are only allowed to parents.
        """
        if not request.user or not request.user.is_authenticated:
            return False

        # Read-only methods
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write methods require parent user type
        return (
            hasattr(request.user, 'user_type') and
            request.user.user_type == 'Parent'
        )

    def has_object_permission(self, request, view, obj):
        """
        Read permissions are allowed to authenticated users,
        but write permissions are only allowed to the parent who owns the object.
        """
        # Read permissions
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions - check ownership
        if hasattr(obj, 'user'):
            return obj.user == request.user

        if hasattr(obj, 'parent'):
            return obj.parent.user == request.user

        return False


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object or admins to access it.
    """

    def has_object_permission(self, request, view, obj):
        """
        Object-level permission to only allow owners or admins.
        """
        # Admin users have full access
        if request.user and request.user.is_staff:
            return True

        # Check if the user owns the object
        if hasattr(obj, 'user'):
            return obj.user == request.user

        if hasattr(obj, 'parent'):
            return obj.parent.user == request.user

        return False