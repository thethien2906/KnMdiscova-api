# parents/tests/test_permissions.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory
from rest_framework import permissions
from unittest.mock import Mock, patch

from parents.models import Parent
from parents.permissions import (
    IsParentOwner,
    IsParentOwnerOrReadOnly,
    IsAdminOrReadOnlyForPsychologist
)

User = get_user_model()


class BasePermissionTestCase(TestCase):
    """Base test case with common setup for permission tests"""

    def setUp(self):
        """Set up test data"""
        self.factory = APIRequestFactory()

        # Create users of different types
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            password='testpass123',
            user_type='Admin',
            is_staff=True,
            is_verified=True
        )

        self.parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )

        self.another_parent_user = User.objects.create_user(
            email='parent2@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )

        self.psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )

        # Create an unauthenticated user (for testing)
        self.anonymous_user = Mock()
        self.anonymous_user.is_authenticated = False

        # Parent profiles should be created automatically via signals
        # Let's verify they exist
        self.parent_profile = Parent.objects.get(user=self.parent_user)
        self.another_parent_profile = Parent.objects.get(user=self.another_parent_user)

        # Create mock view for testing
        self.mock_view = Mock()

    def create_request(self, user, method='GET'):
        """Helper to create request with user"""
        if method.upper() == 'GET':
            request = self.factory.get('/')
        elif method.upper() == 'POST':
            request = self.factory.post('/')
        elif method.upper() == 'PATCH':
            request = self.factory.patch('/')
        elif method.upper() == 'PUT':
            request = self.factory.put('/')
        elif method.upper() == 'DELETE':
            request = self.factory.delete('/')
        else:
            request = self.factory.get('/')

        request.user = user
        return request


class IsParentOwnerPermissionTest(BasePermissionTestCase):
    """Test IsParentOwner permission class"""

    def setUp(self):
        super().setUp()
        self.permission = IsParentOwner()

    def test_has_permission_with_authenticated_parent_user(self):
        """Test permission granted for authenticated parent user"""
        request = self.create_request(self.parent_user)

        has_permission = self.permission.has_permission(request, self.mock_view)

        self.assertTrue(has_permission)

    def test_has_permission_with_unauthenticated_user(self):
        """Test permission denied for unauthenticated user"""
        request = self.create_request(self.anonymous_user)

        has_permission = self.permission.has_permission(request, self.mock_view)

        self.assertFalse(has_permission)

    def test_has_permission_with_admin_user(self):
        """Test permission denied for admin user (not parent type)"""
        request = self.create_request(self.admin_user)

        has_permission = self.permission.has_permission(request, self.mock_view)

        self.assertFalse(has_permission)

    def test_has_permission_with_psychologist_user(self):
        """Test permission denied for psychologist user (not parent type)"""
        request = self.create_request(self.psychologist_user)

        has_permission = self.permission.has_permission(request, self.mock_view)

        self.assertFalse(has_permission)

    def test_has_object_permission_with_own_profile(self):
        """Test object permission granted for parent accessing own profile"""
        request = self.create_request(self.parent_user)

        has_permission = self.permission.has_object_permission(
            request, self.mock_view, self.parent_profile
        )

        self.assertTrue(has_permission)

    def test_has_object_permission_with_other_profile(self):
        """Test object permission denied for parent accessing another's profile"""
        request = self.create_request(self.parent_user)

        has_permission = self.permission.has_object_permission(
            request, self.mock_view, self.another_parent_profile
        )

        self.assertFalse(has_permission)

    def test_has_object_permission_with_admin_accessing_parent_profile(self):
        """Test object permission denied for admin (class is parent-only)"""
        request = self.create_request(self.admin_user)

        has_permission = self.permission.has_object_permission(
            request, self.mock_view, self.parent_profile
        )

        self.assertFalse(has_permission)


class IsParentOwnerOrReadOnlyPermissionTest(BasePermissionTestCase):
    """Test IsParentOwnerOrReadOnly permission class"""

    def setUp(self):
        super().setUp()
        self.permission = IsParentOwnerOrReadOnly()

    def test_has_permission_with_unauthenticated_user(self):
        """Test permission denied for unauthenticated user"""
        request = self.create_request(self.anonymous_user)

        has_permission = self.permission.has_permission(request, self.mock_view)

        self.assertFalse(has_permission)

    def test_has_permission_with_admin_user(self):
        """Test permission granted for admin user"""
        request = self.create_request(self.admin_user)

        has_permission = self.permission.has_permission(request, self.mock_view)

        self.assertTrue(has_permission)

    def test_has_permission_with_staff_user(self):
        """Test permission granted for staff user"""
        staff_user = User.objects.create_user(
            email='staff@test.com',
            password='testpass123',
            user_type='Admin',
            is_staff=True,
            is_verified=True
        )
        request = self.create_request(staff_user)

        has_permission = self.permission.has_permission(request, self.mock_view)

        self.assertTrue(has_permission)

    def test_has_permission_with_parent_user(self):
        """Test permission granted for parent user"""
        request = self.create_request(self.parent_user)

        has_permission = self.permission.has_permission(request, self.mock_view)

        self.assertTrue(has_permission)

    def test_has_permission_with_psychologist_get_request(self):
        """Test permission granted for psychologist with GET request"""
        request = self.create_request(self.psychologist_user, 'GET')

        has_permission = self.permission.has_permission(request, self.mock_view)

        self.assertTrue(has_permission)

    def test_has_permission_with_psychologist_post_request(self):
        """Test permission denied for psychologist with POST request"""
        request = self.create_request(self.psychologist_user, 'POST')

        has_permission = self.permission.has_permission(request, self.mock_view)

        self.assertFalse(has_permission)

    def test_has_permission_with_psychologist_patch_request(self):
        """Test permission denied for psychologist with PATCH request"""
        request = self.create_request(self.psychologist_user, 'PATCH')

        has_permission = self.permission.has_permission(request, self.mock_view)

        self.assertFalse(has_permission)

    def test_has_object_permission_admin_full_access(self):
        """Test admin has full object permission"""
        request = self.create_request(self.admin_user, 'DELETE')

        has_permission = self.permission.has_object_permission(
            request, self.mock_view, self.parent_profile
        )

        self.assertTrue(has_permission)

    def test_has_object_permission_staff_full_access(self):
        """Test staff has full object permission"""
        staff_user = User.objects.create_user(
            email='staff2@test.com',
            password='testpass123',
            user_type='Admin',
            is_staff=True,
            is_verified=True
        )
        request = self.create_request(staff_user, 'DELETE')

        has_permission = self.permission.has_object_permission(
            request, self.mock_view, self.parent_profile
        )

        self.assertTrue(has_permission)

    def test_has_object_permission_parent_own_profile(self):
        """Test parent can access own profile"""
        request = self.create_request(self.parent_user, 'PATCH')

        has_permission = self.permission.has_object_permission(
            request, self.mock_view, self.parent_profile
        )

        self.assertTrue(has_permission)

    def test_has_object_permission_parent_other_profile(self):
        """Test parent cannot access other parent's profile"""
        request = self.create_request(self.parent_user, 'PATCH')

        has_permission = self.permission.has_object_permission(
            request, self.mock_view, self.another_parent_profile
        )

        self.assertFalse(has_permission)

    def test_has_object_permission_psychologist_read_access(self):
        """Test psychologist has read access to parent profiles"""
        request = self.create_request(self.psychologist_user, 'GET')

        has_permission = self.permission.has_object_permission(
            request, self.mock_view, self.parent_profile
        )

        self.assertTrue(has_permission)

    def test_has_object_permission_psychologist_write_denied(self):
        """Test psychologist denied write access to parent profiles"""
        request = self.create_request(self.psychologist_user, 'PATCH')

        has_permission = self.permission.has_object_permission(
            request, self.mock_view, self.parent_profile
        )

        self.assertFalse(has_permission)


class IsAdminOrReadOnlyForPsychologistPermissionTest(BasePermissionTestCase):
    """Test IsAdminOrReadOnlyForPsychologist permission class"""

    def setUp(self):
        super().setUp()
        self.permission = IsAdminOrReadOnlyForPsychologist()

    def test_has_permission_with_unauthenticated_user(self):
        """Test permission denied for unauthenticated user"""
        request = self.create_request(self.anonymous_user)

        has_permission = self.permission.has_permission(request, self.mock_view)

        self.assertFalse(has_permission)

    def test_has_permission_with_admin_user(self):
        """Test permission granted for admin user"""
        request = self.create_request(self.admin_user, 'DELETE')

        has_permission = self.permission.has_permission(request, self.mock_view)

        self.assertTrue(has_permission)

    def test_has_permission_with_staff_user(self):
        """Test permission granted for staff user"""
        staff_user = User.objects.create_user(
            email='staff3@test.com',
            password='testpass123',
            user_type='Admin',
            is_staff=True,
            is_verified=True
        )
        request = self.create_request(staff_user, 'POST')

        has_permission = self.permission.has_permission(request, self.mock_view)

        self.assertTrue(has_permission)

    def test_has_permission_with_psychologist_read_request(self):
        """Test permission granted for psychologist with read request"""
        request = self.create_request(self.psychologist_user, 'GET')

        has_permission = self.permission.has_permission(request, self.mock_view)

        self.assertTrue(has_permission)

    def test_has_permission_with_psychologist_write_request(self):
        """Test permission denied for psychologist with write request"""
        request = self.create_request(self.psychologist_user, 'POST')

        has_permission = self.permission.has_permission(request, self.mock_view)

        self.assertFalse(has_permission)

    def test_has_permission_with_psychologist_patch_request(self):
        """Test permission denied for psychologist with PATCH request"""
        request = self.create_request(self.psychologist_user, 'PATCH')

        has_permission = self.permission.has_permission(request, self.mock_view)

        self.assertFalse(has_permission)

    def test_has_permission_with_psychologist_delete_request(self):
        """Test permission denied for psychologist with DELETE request"""
        request = self.create_request(self.psychologist_user, 'DELETE')

        has_permission = self.permission.has_permission(request, self.mock_view)

        self.assertFalse(has_permission)

    def test_has_permission_with_parent_user(self):
        """Test permission denied for parent user"""
        request = self.create_request(self.parent_user, 'GET')

        has_permission = self.permission.has_permission(request, self.mock_view)

        self.assertFalse(has_permission)


class PermissionIntegrationTest(BasePermissionTestCase):
    """Integration tests for permission combinations"""

    def test_parent_profile_creation_via_signal(self):
        """Test that parent profiles are created automatically via signals"""
        # Create a new parent user
        new_parent_user = User.objects.create_user(
            email='newparent@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )

        # Verify parent profile was created automatically
        self.assertTrue(
            Parent.objects.filter(user=new_parent_user).exists()
        )

        parent_profile = Parent.objects.get(user=new_parent_user)
        self.assertEqual(parent_profile.user, new_parent_user)
        self.assertIsNotNone(parent_profile.communication_preferences)

    def test_permission_with_auto_created_profile(self):
        """Test permissions work correctly with auto-created parent profiles"""
        # Create new parent user (profile created via signal)
        new_parent_user = User.objects.create_user(
            email='autoparent@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )

        # Get the auto-created profile
        new_parent_profile = Parent.objects.get(user=new_parent_user)

        # Test IsParentOwner permission
        permission = IsParentOwner()
        request = self.create_request(new_parent_user)

        # Should have permission for view
        self.assertTrue(permission.has_permission(request, self.mock_view))

        # Should have object permission for own profile
        self.assertTrue(
            permission.has_object_permission(request, self.mock_view, new_parent_profile)
        )

        # Should not have object permission for other profile
        self.assertFalse(
            permission.has_object_permission(request, self.mock_view, self.parent_profile)
        )

    def test_safe_methods_identification(self):
        """Test that safe methods are correctly identified"""
        safe_methods = ['GET', 'HEAD', 'OPTIONS']
        unsafe_methods = ['POST', 'PUT', 'PATCH', 'DELETE']

        permission = IsParentOwnerOrReadOnly()

        # Test safe methods grant permission to psychologist
        for method in safe_methods:
            request = self.create_request(self.psychologist_user, method)
            self.assertTrue(
                permission.has_permission(request, self.mock_view),
                f"Safe method {method} should grant permission to psychologist"
            )

        # Test unsafe methods deny permission to psychologist
        for method in unsafe_methods:
            request = self.create_request(self.psychologist_user, method)
            self.assertFalse(
                permission.has_permission(request, self.mock_view),
                f"Unsafe method {method} should deny permission to psychologist"
            )

    def test_permission_message_attributes(self):
        """Test that permission classes have appropriate error messages"""
        self.assertTrue(hasattr(IsParentOwner, 'message'))
        self.assertTrue(hasattr(IsParentOwnerOrReadOnly, 'message'))
        self.assertTrue(hasattr(IsAdminOrReadOnlyForPsychologist, 'message'))

        # Messages should be localized strings
        self.assertIsNotNone(IsParentOwner.message)
        self.assertIsNotNone(IsParentOwnerOrReadOnly.message)
        self.assertIsNotNone(IsAdminOrReadOnlyForPsychologist.message)

    def test_permission_with_inactive_user(self):
        """Test permissions work correctly with inactive users"""
        # Create inactive parent user
        inactive_parent = User.objects.create_user(
            email='inactive@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True,
            is_active=False
        )

        permission = IsParentOwner()
        request = self.create_request(inactive_parent)

        # Should still have permission (authentication vs authorization)
        # The view logic should handle active/inactive status
        self.assertTrue(permission.has_permission(request, self.mock_view))

    def test_permission_with_unverified_user(self):
        """Test permissions work correctly with unverified users"""
        # Create unverified parent user
        unverified_parent = User.objects.create_user(
            email='unverified@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=False
        )

        permission = IsParentOwner()
        request = self.create_request(unverified_parent)

        # Should still have permission (verification handled in views)
        self.assertTrue(permission.has_permission(request, self.mock_view))


class PermissionEdgeCaseTest(BasePermissionTestCase):
    """Test edge cases and error conditions"""

    def test_permission_with_none_user(self):
        """Test permission handling when user is None"""
        request = self.factory.get('/')
        request.user = None

        permission = IsParentOwner()

        # Should handle None user gracefully
        with self.assertRaises(AttributeError):
            permission.has_permission(request, self.mock_view)

    def test_object_permission_with_invalid_object(self):
        """Test object permission with non-Parent object"""
        request = self.create_request(self.parent_user)
        permission = IsParentOwner()

        # Test with a mock object that's not a Parent
        mock_object = Mock()
        mock_object.user = self.parent_user

        # Should work if object has user attribute
        result = permission.has_object_permission(request, self.mock_view, mock_object)
        self.assertTrue(result)

        # Test with object without user attribute
        mock_object_no_user = Mock()
        del mock_object_no_user.user

        with self.assertRaises(AttributeError):
            permission.has_object_permission(request, self.mock_view, mock_object_no_user)

    def test_permission_inheritance_structure(self):
        """Test that permission classes inherit from BasePermission"""
        from rest_framework.permissions import BasePermission

        self.assertTrue(issubclass(IsParentOwner, BasePermission))
        self.assertTrue(issubclass(IsParentOwnerOrReadOnly, BasePermission))
        self.assertTrue(issubclass(IsAdminOrReadOnlyForPsychologist, BasePermission))