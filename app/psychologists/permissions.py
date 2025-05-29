from rest_framework.permissions import BasePermission

class IsPsychologist(BasePermission):
    """Allow access only to users with user_type 'Psychologist'."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == 'Psychologist'

class IsParent(BasePermission):
    """Allow access only to users with user_type 'Parent'."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == 'Parent'

class IsAdmin(BasePermission):
    """Allow access only to users with user_type 'Admin'."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == 'Admin'