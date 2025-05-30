# psychologists/tests/test_permissions.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory
from rest_framework import permissions
from unittest.mock import Mock

from users.models import User
from psychologists.models import Psychologist, PsychologistAvailability
from psychologists.permissions import (
    IsPsychologistOwner,
    IsPsychologistOwnerOrReadOnly,
    CanCreatePsychologistProfile,
    CanUpdatePsychologistVerification,
    CanManagePsychologistAvailability,
    IsMarketplaceVisible,
    CanSearchPsychologists,
    IsApprovedPsychologist,
    PsychologistProfilePermissions,
    PsychologistMarketplacePermissions
)
from parents.models import Parent


class BasePermissionTestCase(TestCase):
    """Base test case with common setup for permission tests"""

    def setUp(self):
        self.factory = APIRequestFactory()

        # Create test users
        self.psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True,
            is_active=True
        )

        self.parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True,
            is_active=True
        )

        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            password='testpass123',
            user_type='Admin',
            is_staff=True,
            is_verified=True,
            is_active=True
        )

        self.other_psychologist_user = User.objects.create_user(
            email='other_psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True,
            is_active=True
        )

        # Create psychologist profiles
        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Dr. Test',
            last_name='Psychologist',
            license_number='PSY123456',
            license_issuing_authority='State Board',
            license_expiry_date='2025-12-31',
            years_of_experience=5,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Test St, Test City'
        )

        self.other_psychologist = Psychologist.objects.create(
            user=self.other_psychologist_user,
            first_name='Dr. Other',
            last_name='Psychologist',
            license_number='PSY789012',
            license_issuing_authority='State Board',
            license_expiry_date='2025-12-31',
            years_of_experience=3,
            verification_status='Pending',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='456 Other St, Other City'
        )

        # Create parent profile
        self.parent_profile = Parent.objects.get(user=self.parent_user)
    def create_mock_view(self, action=None):
        """Create a mock view with optional action"""
        view = Mock()
        view.action = action
        return view

    def create_request(self, user, method='GET'):
        """Create a request with authenticated user"""
        request = self.factory.get('/') if method == 'GET' else self.factory.post('/')
        request.user = user
        request.method = method
        return request


class IsPsychologistOwnerTest(BasePermissionTestCase):
    """Test IsPsychologistOwner permission"""

    def setUp(self):
        super().setUp()
        self.permission = IsPsychologistOwner()

    def test_has_permission_authenticated_psychologist(self):
        """Test permission for authenticated psychologist"""
        request = self.create_request(self.psychologist_user)
        view = self.create_mock_view()

        self.assertTrue(self.permission.has_permission(request, view))

    def test_has_permission_authenticated_non_psychologist(self):
        """Test permission denied for non-psychologist"""
        request = self.create_request(self.parent_user)
        view = self.create_mock_view()

        self.assertFalse(self.permission.has_permission(request, view))

    def test_has_permission_unauthenticated(self):
        """Test permission denied for unauthenticated user"""
        request = self.factory.get('/')
        request.user = Mock()
        request.user.is_authenticated = False
        view = self.create_mock_view()

        self.assertFalse(self.permission.has_permission(request, view))

    def test_has_object_permission_own_profile(self):
        """Test object permission for own profile"""
        request = self.create_request(self.psychologist_user)
        view = self.create_mock_view()

        self.assertTrue(self.permission.has_object_permission(request, view, self.psychologist))

    def test_has_object_permission_other_profile(self):
        """Test object permission denied for other's profile"""
        request = self.create_request(self.psychologist_user)
        view = self.create_mock_view()

        self.assertFalse(self.permission.has_object_permission(request, view, self.other_psychologist))


class IsPsychologistOwnerOrReadOnlyTest(BasePermissionTestCase):
    """Test IsPsychologistOwnerOrReadOnly permission"""

    def setUp(self):
        super().setUp()
        self.permission = IsPsychologistOwnerOrReadOnly()

    def test_admin_full_access(self):
        """Test admin has full access"""
        request = self.create_request(self.admin_user)
        view = self.create_mock_view()

        self.assertTrue(self.permission.has_permission(request, view))
        self.assertTrue(self.permission.has_object_permission(request, view, self.psychologist))

    def test_psychologist_own_profile_access(self):
        """Test psychologist can access own profile"""
        request = self.create_request(self.psychologist_user)
        view = self.create_mock_view()

        self.assertTrue(self.permission.has_permission(request, view))
        self.assertTrue(self.permission.has_object_permission(request, view, self.psychologist))

    def test_parent_read_only_marketplace_visible(self):
        """Test parent can read marketplace-visible psychologist"""
        request = self.create_request(self.parent_user, 'GET')
        view = self.create_mock_view()

        self.assertTrue(self.permission.has_permission(request, view))
        self.assertTrue(self.permission.has_object_permission(request, view, self.psychologist))

    def test_parent_read_only_not_marketplace_visible(self):
        """Test parent cannot read non-marketplace-visible psychologist"""
        request = self.create_request(self.parent_user, 'GET')
        view = self.create_mock_view()

        self.assertTrue(self.permission.has_permission(request, view))
        self.assertFalse(self.permission.has_object_permission(request, view, self.other_psychologist))

    def test_parent_write_denied(self):
        """Test parent cannot write to psychologist profiles"""
        request = self.create_request(self.parent_user, 'POST')
        view = self.create_mock_view()

        self.assertFalse(self.permission.has_permission(request, view))


class CanCreatePsychologistProfileTest(BasePermissionTestCase):
    """Test CanCreatePsychologistProfile permission"""

    def setUp(self):
        super().setUp()
        self.permission = CanCreatePsychologistProfile()

    def test_verified_psychologist_without_profile(self):
        """Test verified psychologist without existing profile can create"""
        # Create new user without profile
        new_user = User.objects.create_user(
            email='newpsychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True,
            is_active=True
        )

        request = self.create_request(new_user)
        view = self.create_mock_view()

        self.assertTrue(self.permission.has_permission(request, view))

    def test_psychologist_with_existing_profile(self):
        """Test psychologist with existing profile cannot create another"""
        request = self.create_request(self.psychologist_user)
        view = self.create_mock_view()

        self.assertFalse(self.permission.has_permission(request, view))

    def test_unverified_psychologist(self):
        """Test unverified psychologist cannot create profile"""
        unverified_user = User.objects.create_user(
            email='unverified@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=False,
            is_active=True
        )

        request = self.create_request(unverified_user)
        view = self.create_mock_view()

        self.assertFalse(self.permission.has_permission(request, view))

    def test_non_psychologist_user(self):
        """Test non-psychologist cannot create psychologist profile"""
        request = self.create_request(self.parent_user)
        view = self.create_mock_view()

        self.assertFalse(self.permission.has_permission(request, view))


class CanUpdatePsychologistVerificationTest(BasePermissionTestCase):
    """Test CanUpdatePsychologistVerification permission"""

    def setUp(self):
        super().setUp()
        self.permission = CanUpdatePsychologistVerification()

    def test_admin_can_update_verification(self):
        """Test admin can update verification status"""
        request = self.create_request(self.admin_user)
        view = self.create_mock_view()

        self.assertTrue(self.permission.has_permission(request, view))
        self.assertTrue(self.permission.has_object_permission(request, view, self.psychologist))

    def test_psychologist_cannot_update_own_verification(self):
        """Test psychologist cannot update own verification status"""
        request = self.create_request(self.psychologist_user)
        view = self.create_mock_view()

        self.assertFalse(self.permission.has_permission(request, view))

    def test_parent_cannot_update_verification(self):
        """Test parent cannot update verification status"""
        request = self.create_request(self.parent_user)
        view = self.create_mock_view()

        self.assertFalse(self.permission.has_permission(request, view))


class CanManagePsychologistAvailabilityTest(BasePermissionTestCase):
    """Test CanManagePsychologistAvailability permission"""

    def setUp(self):
        super().setUp()
        self.permission = CanManagePsychologistAvailability()

        # Create availability block
        self.availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time='09:00',
            end_time='17:00',
            is_recurring=True
        )

    def test_admin_can_manage_availability(self):
        """Test admin can manage any psychologist's availability"""
        request = self.create_request(self.admin_user)
        view = self.create_mock_view()

        self.assertTrue(self.permission.has_permission(request, view))
        self.assertTrue(self.permission.has_object_permission(request, view, self.availability))

    def test_psychologist_can_manage_own_availability(self):
        """Test psychologist can manage own availability"""
        request = self.create_request(self.psychologist_user)
        view = self.create_mock_view()

        self.assertTrue(self.permission.has_permission(request, view))
        self.assertTrue(self.permission.has_object_permission(request, view, self.availability))

    def test_psychologist_cannot_manage_others_availability(self):
        """Test psychologist cannot manage other's availability"""
        request = self.create_request(self.other_psychologist_user)
        view = self.create_mock_view()

        self.assertTrue(self.permission.has_permission(request, view))
        self.assertFalse(self.permission.has_object_permission(request, view, self.availability))

    def test_parent_cannot_manage_availability(self):
        """Test parent cannot manage availability"""
        request = self.create_request(self.parent_user)
        view = self.create_mock_view()

        self.assertFalse(self.permission.has_permission(request, view))


class IsMarketplaceVisibleTest(BasePermissionTestCase):
    """Test IsMarketplaceVisible permission"""

    def setUp(self):
        super().setUp()
        self.permission = IsMarketplaceVisible()

    def test_admin_can_access_any_profile(self):
        """Test admin can access any profile regardless of marketplace visibility"""
        request = self.create_request(self.admin_user)
        view = self.create_mock_view()

        self.assertTrue(self.permission.has_object_permission(request, view, self.psychologist))
        self.assertTrue(self.permission.has_object_permission(request, view, self.other_psychologist))

    def test_psychologist_can_access_own_profile(self):
        """Test psychologist can access own profile regardless of marketplace visibility"""
        request = self.create_request(self.other_psychologist_user)
        view = self.create_mock_view()

        self.assertTrue(self.permission.has_object_permission(request, view, self.other_psychologist))

    def test_parent_can_access_marketplace_visible_only(self):
        """Test parent can only access marketplace-visible psychologists"""
        request = self.create_request(self.parent_user)
        view = self.create_mock_view()

        # Approved psychologist is marketplace visible
        self.assertTrue(self.permission.has_object_permission(request, view, self.psychologist))

        # Pending psychologist is not marketplace visible
        self.assertFalse(self.permission.has_object_permission(request, view, self.other_psychologist))

    def test_other_psychologist_can_access_marketplace_visible_only(self):
        """Test other psychologists can only access marketplace-visible profiles"""
        request = self.create_request(self.psychologist_user)
        view = self.create_mock_view()

        # Can access marketplace-visible psychologist
        self.assertTrue(self.permission.has_object_permission(request, view, self.psychologist))

        # Cannot access non-marketplace-visible psychologist
        self.assertFalse(self.permission.has_object_permission(request, view, self.other_psychologist))


class CanSearchPsychologistsTest(BasePermissionTestCase):
    """Test CanSearchPsychologists permission"""

    def setUp(self):
        super().setUp()
        self.permission = CanSearchPsychologists()

    def test_admin_can_search(self):
        """Test admin can search psychologists"""
        request = self.create_request(self.admin_user)
        view = self.create_mock_view()

        self.assertTrue(self.permission.has_permission(request, view))

    def test_parent_can_search(self):
        """Test parent can search psychologists"""
        request = self.create_request(self.parent_user)
        view = self.create_mock_view()

        self.assertTrue(self.permission.has_permission(request, view))

    def test_psychologist_can_search(self):
        """Test psychologist can search other psychologists"""
        request = self.create_request(self.psychologist_user)
        view = self.create_mock_view()

        self.assertTrue(self.permission.has_permission(request, view))

    def test_unauthenticated_cannot_search(self):
        """Test unauthenticated user cannot search"""
        request = self.factory.get('/')
        request.user = Mock()
        request.user.is_authenticated = False
        view = self.create_mock_view()

        self.assertFalse(self.permission.has_permission(request, view))


class IsApprovedPsychologistTest(BasePermissionTestCase):
    """Test IsApprovedPsychologist permission"""

    def setUp(self):
        super().setUp()
        self.permission = IsApprovedPsychologist()

    def test_approved_psychologist_has_permission(self):
        """Test approved psychologist has permission"""
        request = self.create_request(self.psychologist_user)
        view = self.create_mock_view()

        self.assertTrue(self.permission.has_permission(request, view))

    def test_pending_psychologist_no_permission(self):
        """Test pending psychologist does not have permission"""
        request = self.create_request(self.other_psychologist_user)
        view = self.create_mock_view()

        self.assertFalse(self.permission.has_permission(request, view))

    def test_non_psychologist_no_permission(self):
        """Test non-psychologist does not have permission"""
        request = self.create_request(self.parent_user)
        view = self.create_mock_view()

        self.assertFalse(self.permission.has_permission(request, view))

    def test_object_permission_own_approved_profile(self):
        """Test object permission for own approved profile"""
        request = self.create_request(self.psychologist_user)
        view = self.create_mock_view()

        self.assertTrue(self.permission.has_object_permission(request, view, self.psychologist))

    def test_object_permission_own_pending_profile(self):
        """Test object permission denied for own pending profile"""
        request = self.create_request(self.other_psychologist_user)
        view = self.create_mock_view()

        self.assertFalse(self.permission.has_object_permission(request, view, self.other_psychologist))


class PsychologistProfilePermissionsTest(BasePermissionTestCase):
    """Test PsychologistProfilePermissions composite permission"""

    def setUp(self):
        super().setUp()
        self.permission = PsychologistProfilePermissions()

    def test_create_action_permissions(self):
        """Test permissions for create action"""
        # New verified psychologist can create profile
        new_user = User.objects.create_user(
            email='newpsych@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True,
            is_active=True
        )

        request = self.create_request(new_user)
        view = self.create_mock_view('create')

        self.assertTrue(self.permission.has_permission(request, view))

    def test_verification_action_permissions(self):
        """Test permissions for verification actions"""
        # Admin can update verification
        request = self.create_request(self.admin_user)
        view = self.create_mock_view('update_verification')

        self.assertTrue(self.permission.has_permission(request, view))

        # Psychologist cannot update verification
        request = self.create_request(self.psychologist_user)
        self.assertFalse(self.permission.has_permission(request, view))

    def test_availability_action_permissions(self):
        """Test permissions for availability actions"""
        request = self.create_request(self.psychologist_user)
        view = self.create_mock_view('availability')

        self.assertTrue(self.permission.has_permission(request, view))

    def test_search_action_permissions(self):
        """Test permissions for search actions"""
        request = self.create_request(self.parent_user)
        view = self.create_mock_view('search')

        self.assertTrue(self.permission.has_permission(request, view))

    def test_update_object_permissions(self):
        """Test object permissions for update action"""
        request = self.create_request(self.psychologist_user)
        view = self.create_mock_view('update')

        # Can update own profile
        self.assertTrue(self.permission.has_object_permission(request, view, self.psychologist))

        # Cannot update other's profile
        self.assertFalse(self.permission.has_object_permission(request, view, self.other_psychologist))

    def test_parent_marketplace_access(self):
        """Test parent access through marketplace visibility"""
        request = self.create_request(self.parent_user)
        view = self.create_mock_view('retrieve')

        # Can access marketplace-visible psychologist
        self.assertTrue(self.permission.has_object_permission(request, view, self.psychologist))

        # Cannot access non-marketplace-visible psychologist
        self.assertFalse(self.permission.has_object_permission(request, view, self.other_psychologist))


class PsychologistMarketplacePermissionsTest(BasePermissionTestCase):
    """Test PsychologistMarketplacePermissions"""

    def setUp(self):
        super().setUp()
        self.permission = PsychologistMarketplacePermissions()

    def test_parent_marketplace_access(self):
        """Test parent can access marketplace"""
        request = self.create_request(self.parent_user)
        view = self.create_mock_view()

        self.assertTrue(self.permission.has_permission(request, view))

    def test_psychologist_marketplace_access(self):
        """Test psychologist can access marketplace"""
        request = self.create_request(self.psychologist_user)
        view = self.create_mock_view()

        self.assertTrue(self.permission.has_permission(request, view))

    def test_admin_marketplace_access(self):
        """Test admin can access marketplace"""
        request = self.create_request(self.admin_user)
        view = self.create_mock_view()

        self.assertTrue(self.permission.has_permission(request, view))

    def test_unauthenticated_marketplace_denied(self):
        """Test unauthenticated user cannot access marketplace"""
        request = self.factory.get('/')
        request.user = Mock()
        request.user.is_authenticated = False
        view = self.create_mock_view()

        self.assertFalse(self.permission.has_permission(request, view))

    def test_parent_object_permissions(self):
        """Test parent can only see marketplace-visible psychologists"""
        request = self.create_request(self.parent_user)
        view = self.create_mock_view()

        # Can see approved psychologist
        self.assertTrue(self.permission.has_object_permission(request, view, self.psychologist))

        # Cannot see pending psychologist
        self.assertFalse(self.permission.has_object_permission(request, view, self.other_psychologist))

    def test_psychologist_object_permissions(self):
        """Test psychologist can see all profiles in marketplace context"""
        request = self.create_request(self.psychologist_user)
        view = self.create_mock_view()

        # Can see any profile in marketplace context
        self.assertTrue(self.permission.has_object_permission(request, view, self.psychologist))
        self.assertTrue(self.permission.has_object_permission(request, view, self.other_psychologist))

    def test_admin_object_permissions(self):
        """Test admin can see all profiles"""
        request = self.create_request(self.admin_user)
        view = self.create_mock_view()

        # Can see any profile
        self.assertTrue(self.permission.has_object_permission(request, view, self.psychologist))
        self.assertTrue(self.permission.has_object_permission(request, view, self.other_psychologist))


class EdgeCasePermissionsTest(BasePermissionTestCase):
    """Test edge cases and boundary conditions"""

    def test_inactive_user_permissions(self):
        """Test permissions for inactive user"""
        inactive_user = User.objects.create_user(
            email='inactive@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True,
            is_active=False
        )

        request = self.create_request(inactive_user)
        view = self.create_mock_view()

        permission = IsPsychologistOwner()
        self.assertTrue(permission.has_permission(request, view))  # Basic auth check passes

    def test_unverified_user_create_permissions(self):
        """Test create permissions for unverified user"""
        unverified_user = User.objects.create_user(
            email='unverified@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=False,
            is_active=True
        )

        request = self.create_request(unverified_user)
        view = self.create_mock_view()

        permission = CanCreatePsychologistProfile()
        self.assertFalse(permission.has_permission(request, view))

    def test_permissions_with_missing_profile(self):
        """Test permissions when psychologist profile is missing"""
        new_user = User.objects.create_user(
            email='noprofile@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True,
            is_active=True
        )

        request = self.create_request(new_user)
        view = self.create_mock_view()

        # IsApprovedPsychologist should handle missing profile gracefully
        permission = IsApprovedPsychologist()
        self.assertFalse(permission.has_permission(request, view))

    def test_permissions_with_rejected_psychologist(self):
        """Test permissions for rejected psychologist"""
        # Update psychologist to rejected status
        self.other_psychologist.verification_status = 'Rejected'
        self.other_psychologist.save()

        request = self.create_request(self.other_psychologist_user)
        view = self.create_mock_view()

        permission = IsApprovedPsychologist()
        self.assertFalse(permission.has_permission(request, view))