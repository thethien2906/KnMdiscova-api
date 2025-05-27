# children/tests/test_permissions.py
import uuid
from datetime import date, timedelta
from django.test import TestCase, RequestFactory
from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView
from unittest.mock import Mock
from django.utils.functional import Promise
from users.models import User
from parents.models import Parent
from children.models import Child
from children.permissions import (
    IsChildOwner,
    IsChildOwnerOrReadOnly,
    IsParentOfChild,
    CanCreateChildForParent,
    CanManageChildConsent,
    IsAdminOrReadOnlyForPsychologist,
    CanSearchChildren,
    CanViewChildReports,
    ChildProfilePermissions
)


class BasePermissionTestCase(TestCase):
    """Base class with common setup for permission tests"""

    def setUp(self):
        """Set up test data"""
        self.factory = APIRequestFactory()

        # Create parent user and profile
        self.parent_user = User.objects.create_parent(
            email='parent@test.com',
            password='testpass123',
            user_timezone='UTC'
        )
        self.parent_user.is_verified = True
        self.parent_user.save()

        # Parent profile should be created by signal
        self.parent_profile = Parent.objects.get(user=self.parent_user)
        self.parent_profile.first_name = 'Test'
        self.parent_profile.last_name = 'Parent'
        self.parent_profile.save()

        # Create another parent for testing isolation
        self.other_parent_user = User.objects.create_parent(
            email='other@test.com',
            password='testpass123',
            user_timezone='UTC'
        )
        self.other_parent_user.is_verified = True
        self.other_parent_user.save()

        self.other_parent_profile = Parent.objects.get(user=self.other_parent_user)
        self.other_parent_profile.first_name = 'Other'
        self.other_parent_profile.last_name = 'Parent'
        self.other_parent_profile.save()

        # Create psychologist user
        self.psychologist_user = User.objects.create_psychologist(
            email='psychologist@test.com',
            password='testpass123',
            user_timezone='UTC'
        )
        self.psychologist_user.is_verified = True
        self.psychologist_user.save()

        # Create admin user
        self.admin_user = User.objects.create_superuser(
            email='admin@test.com',
            password='testpass123'
        )

        # Create test children
        self.child = Child.objects.create(
            parent=self.parent_profile,
            first_name='Test',
            last_name='Child',
            date_of_birth=date.today() - timedelta(days=3650)  # ~10 years old
        )

        self.other_child = Child.objects.create(
            parent=self.other_parent_profile,
            first_name='Other',
            last_name='Child',
            date_of_birth=date.today() - timedelta(days=2920)  # ~8 years old
        )

        # Create mock view for testing
        self.mock_view = Mock(spec=APIView)
        self.mock_view.action = None

    def create_request(self, user=None, method='GET'):
        """Helper to create request with user"""
        request = self.factory.get('/test/')
        request.user = user or AnonymousUser()
        return request


class IsChildOwnerTestCase(BasePermissionTestCase):
    """Test IsChildOwner permission"""

    def setUp(self):
        super().setUp()
        self.permission = IsChildOwner()

    def test_anonymous_user_denied(self):
        """Anonymous users should be denied"""
        request = self.create_request()
        self.assertFalse(
            self.permission.has_permission(request, self.mock_view)
        )

    def test_non_parent_user_denied(self):
        """Non-parent users should be denied"""
        request = self.create_request(self.psychologist_user)
        self.assertFalse(
            self.permission.has_permission(request, self.mock_view)
        )

        request = self.create_request(self.admin_user)
        self.assertFalse(
            self.permission.has_permission(request, self.mock_view)
        )

    def test_parent_user_allowed(self):
        """Parent users should be allowed at permission level"""
        request = self.create_request(self.parent_user)
        self.assertTrue(
            self.permission.has_permission(request, self.mock_view)
        )

    def test_parent_can_access_own_child(self):
        """Parent should be able to access their own child"""
        request = self.create_request(self.parent_user)
        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, self.child)
        )

    def test_parent_cannot_access_other_child(self):
        """Parent should not be able to access other parent's child"""
        request = self.create_request(self.parent_user)
        self.assertFalse(
            self.permission.has_object_permission(request, self.mock_view, self.other_child)
        )


class IsChildOwnerOrReadOnlyTestCase(BasePermissionTestCase):
    """Test IsChildOwnerOrReadOnly permission"""

    def setUp(self):
        super().setUp()
        self.permission = IsChildOwnerOrReadOnly()

    def test_anonymous_user_denied(self):
        """Anonymous users should be denied"""
        request = self.create_request()
        self.assertFalse(
            self.permission.has_permission(request, self.mock_view)
        )

    def test_admin_full_access(self):
        """Admin should have full access"""
        request = self.create_request(self.admin_user)
        self.assertTrue(
            self.permission.has_permission(request, self.mock_view)
        )
        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, self.child)
        )
        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, self.other_child)
        )

    def test_parent_full_access_own_child(self):
        """Parent should have full access to own child"""
        request = self.create_request(self.parent_user)
        self.assertTrue(
            self.permission.has_permission(request, self.mock_view)
        )
        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, self.child)
        )

    def test_parent_no_access_other_child(self):
        """Parent should not have access to other parent's child"""
        request = self.create_request(self.parent_user)
        self.assertFalse(
            self.permission.has_object_permission(request, self.mock_view, self.other_child)
        )

    def test_psychologist_read_only_access(self):
        """Psychologist should have read-only access"""
        # Test GET request (safe method)
        request = self.factory.get('/test/')
        request.user = self.psychologist_user
        self.assertTrue(
            self.permission.has_permission(request, self.mock_view)
        )
        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, self.child)
        )

        # Test POST request (unsafe method)
        request = self.factory.post('/test/')
        request.user = self.psychologist_user
        self.assertFalse(
            self.permission.has_permission(request, self.mock_view)
        )


class CanCreateChildForParentTestCase(BasePermissionTestCase):
    """Test CanCreateChildForParent permission"""

    def setUp(self):
        super().setUp()
        self.permission = CanCreateChildForParent()

    def test_anonymous_user_denied(self):
        """Anonymous users cannot create children"""
        request = self.create_request()
        self.assertFalse(
            self.permission.has_permission(request, self.mock_view)
        )

    def test_non_parent_denied(self):
        """Non-parent users cannot create children"""
        request = self.create_request(self.psychologist_user)
        self.assertFalse(
            self.permission.has_permission(request, self.mock_view)
        )

        request = self.create_request(self.admin_user)
        self.assertFalse(
            self.permission.has_permission(request, self.mock_view)
        )

    def test_unverified_parent_denied(self):
        """Unverified parent cannot create children"""
        self.parent_user.is_verified = False
        self.parent_user.save()

        request = self.create_request(self.parent_user)
        self.assertFalse(
            self.permission.has_permission(request, self.mock_view)
        )

    def test_verified_parent_allowed(self):
        """Verified parent with profile can create children"""
        request = self.create_request(self.parent_user)
        self.assertTrue(
            self.permission.has_permission(request, self.mock_view)
        )

class CanManageChildConsentTestCase(BasePermissionTestCase):
    """Test CanManageChildConsent permission"""

    def setUp(self):
        super().setUp()
        self.permission = CanManageChildConsent()

    def test_anonymous_user_denied(self):
        """Anonymous users cannot manage consent"""
        request = self.create_request()
        self.assertFalse(
            self.permission.has_permission(request, self.mock_view)
        )

    def test_psychologist_denied(self):
        """Psychologists cannot manage consent"""
        request = self.create_request(self.psychologist_user)
        self.assertFalse(
            self.permission.has_permission(request, self.mock_view)
        )

    def test_admin_full_access(self):
        """Admin can manage all consent"""
        request = self.create_request(self.admin_user)
        self.assertTrue(
            self.permission.has_permission(request, self.mock_view)
        )
        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, self.child)
        )
        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, self.other_child)
        )

    def test_parent_can_manage_own_child_consent(self):
        """Parent can manage consent for own child"""
        request = self.create_request(self.parent_user)
        self.assertTrue(
            self.permission.has_permission(request, self.mock_view)
        )
        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, self.child)
        )

    def test_parent_cannot_manage_other_child_consent(self):
        """Parent cannot manage consent for other parent's child"""
        request = self.create_request(self.parent_user)
        self.assertFalse(
            self.permission.has_object_permission(request, self.mock_view, self.other_child)
        )


class IsAdminOrReadOnlyForPsychologistTestCase(BasePermissionTestCase):
    """Test IsAdminOrReadOnlyForPsychologist permission"""

    def setUp(self):
        super().setUp()
        self.permission = IsAdminOrReadOnlyForPsychologist()

    def test_anonymous_user_denied(self):
        """Anonymous users should be denied"""
        request = self.create_request()
        self.assertFalse(
            self.permission.has_permission(request, self.mock_view)
        )

    def test_parent_denied(self):
        """Parents should be denied"""
        request = self.create_request(self.parent_user)
        self.assertFalse(
            self.permission.has_permission(request, self.mock_view)
        )

    def test_admin_full_access(self):
        """Admin should have full access"""
        request = self.create_request(self.admin_user)
        self.assertTrue(
            self.permission.has_permission(request, self.mock_view)
        )
        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, self.child)
        )

    def test_psychologist_read_only(self):
        """Psychologist should have read-only access"""
        # Test GET request
        request = self.factory.get('/test/')
        request.user = self.psychologist_user
        self.assertTrue(
            self.permission.has_permission(request, self.mock_view)
        )
        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, self.child)
        )

        # Test POST request
        request = self.factory.post('/test/')
        request.user = self.psychologist_user
        self.assertFalse(
            self.permission.has_permission(request, self.mock_view)
        )


class CanSearchChildrenTestCase(BasePermissionTestCase):
    """Test CanSearchChildren permission"""

    def setUp(self):
        super().setUp()
        self.permission = CanSearchChildren()

    def test_anonymous_user_denied(self):
        """Anonymous users cannot search children"""
        request = self.create_request()
        self.assertFalse(
            self.permission.has_permission(request, self.mock_view)
        )

    def test_admin_can_search(self):
        """Admin can search all children"""
        request = self.create_request(self.admin_user)
        self.assertTrue(
            self.permission.has_permission(request, self.mock_view)
        )

    def test_parent_can_search(self):
        """Parent can search children"""
        request = self.create_request(self.parent_user)
        self.assertTrue(
            self.permission.has_permission(request, self.mock_view)
        )

    def test_psychologist_can_search(self):
        """Psychologist can search children"""
        request = self.create_request(self.psychologist_user)
        self.assertTrue(
            self.permission.has_permission(request, self.mock_view)
        )


class CanViewChildReportsTestCase(BasePermissionTestCase):
    """Test CanViewChildReports permission"""

    def setUp(self):
        super().setUp()
        self.permission = CanViewChildReports()

    def test_anonymous_user_denied(self):
        """Anonymous users cannot view reports"""
        request = self.create_request()
        self.assertFalse(
            self.permission.has_permission(request, self.mock_view)
        )

    def test_authenticated_user_allowed_at_permission_level(self):
        """All authenticated users allowed at permission level"""
        request = self.create_request(self.parent_user)
        self.assertTrue(
            self.permission.has_permission(request, self.mock_view)
        )

        request = self.create_request(self.psychologist_user)
        self.assertTrue(
            self.permission.has_permission(request, self.mock_view)
        )

    def test_admin_can_view_all_reports(self):
        """Admin can view all reports"""
        request = self.create_request(self.admin_user)
        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, self.child)
        )
        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, self.other_child)
        )

    def test_parent_can_view_own_child_reports(self):
        """Parent can view reports for own child"""
        request = self.create_request(self.parent_user)
        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, self.child)
        )
        self.assertFalse(
            self.permission.has_object_permission(request, self.mock_view, self.other_child)
        )

    def test_psychologist_can_view_reports(self):
        """Psychologist can view reports (for now, all reports)"""
        request = self.create_request(self.psychologist_user)
        # Current implementation allows psychologists to view all reports
        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, self.child)
        )


class ChildProfilePermissionsTestCase(BasePermissionTestCase):
    """Test composite ChildProfilePermissions"""

    def setUp(self):
        super().setUp()
        self.permission = ChildProfilePermissions()

    def test_create_action_delegates_to_creation_permission(self):
        """Create action should use creation permission"""
        self.mock_view.action = 'create'

        # Verified parent should be allowed
        request = self.create_request(self.parent_user)
        self.assertTrue(
            self.permission.has_permission(request, self.mock_view)
        )

        # Unverified parent should be denied
        self.parent_user.is_verified = False
        self.parent_user.save()
        request = self.create_request(self.parent_user)
        self.assertFalse(
            self.permission.has_permission(request, self.mock_view)
        )

    def test_search_action_delegates_to_search_permission(self):
        """Search action should use search permission"""
        self.mock_view.action = 'search'

        # All user types should be allowed to search
        request = self.create_request(self.parent_user)
        self.assertTrue(
            self.permission.has_permission(request, self.mock_view)
        )

        request = self.create_request(self.psychologist_user)
        self.assertTrue(
            self.permission.has_permission(request, self.mock_view)
        )

        request = self.create_request(self.admin_user)
        self.assertTrue(
            self.permission.has_permission(request, self.mock_view)
        )

    def test_consent_actions_delegate_to_consent_permission(self):
        """Consent actions should use consent permission"""
        self.mock_view.action = 'manage_consent'

        # Parent should be able to manage consent for own child
        request = self.create_request(self.parent_user)
        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, self.child)
        )
        self.assertFalse(
            self.permission.has_object_permission(request, self.mock_view, self.other_child)
        )

        # Psychologist should not be able to manage consent
        request = self.create_request(self.psychologist_user)
        self.assertFalse(
            self.permission.has_object_permission(request, self.mock_view, self.child)
        )

    def test_update_actions_delegate_to_owner_permission(self):
        """Update actions should use owner permission"""
        self.mock_view.action = 'update'

        # Parent can update own child
        request = self.create_request(self.parent_user)
        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, self.child)
        )
        self.assertFalse(
            self.permission.has_object_permission(request, self.mock_view, self.other_child)
        )

    def test_general_access_delegates_to_read_permission(self):
        """General access should use read permission"""
        self.mock_view.action = 'retrieve'

        # Parent can access own child
        request = self.create_request(self.parent_user)
        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, self.child)
        )

        # Admin can access all children
        request = self.create_request(self.admin_user)
        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, self.child)
        )
        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, self.other_child)
        )


class IsParentOfChildTestCase(BasePermissionTestCase):
    """Test IsParentOfChild permission"""

    def setUp(self):
        super().setUp()
        self.permission = IsParentOfChild()

    def test_non_parent_denied(self):
        """Non-parent users should be denied"""
        request = self.create_request(self.psychologist_user)
        self.assertFalse(
            self.permission.has_permission(request, self.mock_view)
        )

    def test_parent_allowed_at_permission_level(self):
        """Parent should be allowed at permission level"""
        request = self.create_request(self.parent_user)
        self.assertTrue(
            self.permission.has_permission(request, self.mock_view)
        )

    def test_parent_can_access_own_child(self):
        """Parent should be able to access own child"""
        request = self.create_request(self.parent_user)
        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, self.child)
        )

    def test_parent_cannot_access_other_child(self):
        """Parent should not be able to access other parent's child"""
        request = self.create_request(self.parent_user)
        self.assertFalse(
            self.permission.has_object_permission(request, self.mock_view, self.other_child)
        )


class PermissionMessageTestCase(BasePermissionTestCase):
    """Test permission error messages"""

    def test_permission_messages_exist(self):
        """All permissions should have meaningful error messages"""
        permissions = [
            IsChildOwner(),
            IsChildOwnerOrReadOnly(),
            IsParentOfChild(),
            CanCreateChildForParent(),
            CanManageChildConsent(),
            IsAdminOrReadOnlyForPsychologist(),
            CanSearchChildren(),
            CanViewChildReports(),
            ChildProfilePermissions()
        ]

        for permission in permissions:
            self.assertTrue(
                hasattr(permission, 'message'),
                f"{permission.__class__.__name__} should have a message attribute"
            )
            self.assertIsInstance(
                permission.message,
                (str, Promise),
                f"{permission.__class__.__name__} message should be a string or lazy string"
            )
            self.assertTrue(
                len(permission.message.strip()) > 0,
                f"{permission.__class__.__name__} message should not be empty"
            )


class EdgeCaseTestCase(BasePermissionTestCase):
    """Test edge cases and error conditions"""

    def test_deleted_parent_profile(self):
        """Test behavior when parent profile is deleted"""
        # Delete parent profile
        self.parent_profile.delete()

        permission = CanCreateChildForParent()
        request = self.create_request(self.parent_user)

        # Should be denied since parent profile doesn't exist
        self.assertFalse(
            permission.has_permission(request, self.mock_view)
        )

    def test_inactive_user(self):
        """Test behavior with inactive users"""
        self.parent_user.is_active = False
        self.parent_user.save()

        permission = IsChildOwner()
        request = self.create_request(self.parent_user)

        # Should still work at permission level (active status checked elsewhere)
        self.assertTrue(
            permission.has_permission(request, self.mock_view)
        )

    def test_none_user(self):
        """Test behavior when request.user is None"""
        request = self.factory.get('/test/')
        request.user = None

        permission = IsChildOwner()

        # Should handle gracefully
        with self.assertRaises(AttributeError):
            permission.has_permission(request, self.mock_view)

    def test_child_with_deleted_parent_user(self):
        """Test accessing child whose parent user is deleted"""
        # This is an edge case that shouldn't happen in normal operation
        # but we should handle it gracefully

        permission = IsChildOwner()
        request = self.create_request(self.other_parent_user)

        # Delete the child's parent user (this would cascade delete parent profile)
        self.parent_user.delete()

        # Refresh child from database
        try:
            self.child.refresh_from_db()
            # This should raise an error due to cascade delete
            self.fail("Child should have been deleted when parent user was deleted")
        except Child.DoesNotExist:
            # This is expected behavior
            pass