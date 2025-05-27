# children/tests/test_views.py
import uuid
import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, Mock

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.authtoken.models import Token

from users.models import User
from parents.models import Parent
from children.models import Child
from children.services import ChildService

User = get_user_model()


class BaseChildTestCase(TestCase):
    """Base test case with common setup for child tests"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()

        # Create test users
        self.parent_user = User.objects.create_parent(
            email='parent@test.com',
            password='TestPass123!',
        )
        self.parent_user.is_verified = True
        self.parent_user.save()

        self.parent_user2 = User.objects.create_parent(
            email='parent2@test.com',
            password='TestPass123!',
        )
        self.parent_user2.is_verified = True
        self.parent_user2.save()

        self.unverified_parent_user = User.objects.create_parent(
            email='unverified@test.com',
            password='TestPass123!',
        )
        # Keep unverified

        self.psychologist_user = User.objects.create_psychologist(
            email='psychologist@test.com',
            password='TestPass123!',
        )
        self.psychologist_user.is_verified = True
        self.psychologist_user.save()

        self.admin_user = User.objects.create_superuser(
            email='admin@test.com',
            password='TestPass123!',
        )

        # Create tokens
        self.parent_token = Token.objects.create(user=self.parent_user)
        self.parent2_token = Token.objects.create(user=self.parent_user2)
        self.unverified_token = Token.objects.create(user=self.unverified_parent_user)
        self.psychologist_token = Token.objects.create(user=self.psychologist_user)
        self.admin_token = Token.objects.create(user=self.admin_user)

        # Get parent profiles (created by signal)
        self.parent = Parent.objects.get(user=self.parent_user)
        self.parent2 = Parent.objects.get(user=self.parent_user2)

        # Update parent profiles with names
        self.parent.first_name = 'John'
        self.parent.last_name = 'Doe'
        self.parent.save()

        self.parent2.first_name = 'Jane'
        self.parent2.last_name = 'Smith'
        self.parent2.save()

        # Create test children
        self.child1 = Child.objects.create(
            parent=self.parent,
            first_name='Alice',
            last_name='Doe',
            date_of_birth=date.today() - timedelta(days=365*8),  # 8 years old
            gender='Female',
            primary_language='English',
            school_grade_level='Grade 3'
        )

        self.child2 = Child.objects.create(
            parent=self.parent,
            first_name='Bob',
            last_name='Doe',
            date_of_birth=date.today() - timedelta(days=365*10),  # 10 years old
            gender='Male',
            primary_language='English',
            school_grade_level='Grade 5',
            has_seen_psychologist=True
        )

        self.other_parent_child = Child.objects.create(
            parent=self.parent2,
            first_name='Charlie',
            last_name='Smith',
            date_of_birth=date.today() - timedelta(days=365*12),  # 12 years old
            gender='Male'
        )

    def authenticate(self, token):
        """Helper method to authenticate requests"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def get_valid_child_data(self):
        """Get valid child data for creation/update"""
        return {
            'first_name': 'Test',
            'last_name': 'Child',
            'date_of_birth': (date.today() - timedelta(days=365*7)).isoformat(),  # 7 years old
            'gender': 'Female',
            'primary_language': 'English',
            'school_grade_level': 'Grade 2'
        }


class ChildProfileViewSetTests(BaseChildTestCase):
    """Test cases for ChildProfileViewSet"""

    def test_my_children_authenticated_parent(self):
        """Test getting parent's own children list"""
        self.authenticate(self.parent_token)
        url = reverse('child-profile-my-children')

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(len(response.data['children']), 2)

        # Check children belong to authenticated parent
        child_ids = [child['id'] for child in response.data['children']]
        self.assertIn(str(self.child1.id), child_ids)
        self.assertIn(str(self.child2.id), child_ids)
        self.assertNotIn(str(self.other_parent_child.id), child_ids)

    def test_my_children_unauthenticated(self):
        """Test getting children list without authentication"""
        url = reverse('child-profile-my-children')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_my_children_non_parent_user(self):
        """Test psychologist cannot access my_children endpoint"""
        self.authenticate(self.psychologist_token)
        url = reverse('child-profile-my-children')

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('error', response.data)

    def test_create_child_success(self):
        """Test successful child creation"""
        self.authenticate(self.parent_token)
        url = reverse('child-profile-list')

        data = self.get_valid_child_data()
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('child', response.data)
        self.assertEqual(response.data['child']['first_name'], 'Test')
        self.assertEqual(response.data['child']['parent_email'], 'parent@test.com')

        # Verify child was created in database
        child = Child.objects.get(id=response.data['child']['id'])
        self.assertEqual(child.parent, self.parent)

    def test_create_child_unverified_parent(self):
        """Test unverified parent cannot create child"""
        self.authenticate(self.unverified_token)
        url = reverse('child-profile-list')

        data = self.get_valid_child_data()
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_child_invalid_age_too_young(self):
        """Test creating child younger than 5 years fails"""
        self.authenticate(self.parent_token)
        url = reverse('child-profile-list')

        data = self.get_valid_child_data()
        data['date_of_birth'] = (date.today() - timedelta(days=365*3)).isoformat()  # 3 years old

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('date_of_birth', response.data)

    def test_create_child_invalid_age_too_old(self):
        """Test creating child older than 17 years fails"""
        self.authenticate(self.parent_token)
        url = reverse('child-profile-list')

        data = self.get_valid_child_data()
        data['date_of_birth'] = (date.today() - timedelta(days=365*19)).isoformat()  # 19 years old

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('date_of_birth', response.data)

    def test_create_child_missing_required_fields(self):
        """Test creating child without required fields fails"""
        self.authenticate(self.parent_token)
        url = reverse('child-profile-list')

        # Missing first_name and date_of_birth
        data = {
            'last_name': 'Test'
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('first_name', response.data)
        self.assertIn('date_of_birth', response.data)

    def test_create_duplicate_child(self):
        """Test creating duplicate child (same name and DOB) fails"""
        self.authenticate(self.parent_token)
        url = reverse('child-profile-list')

        data = {
            'first_name': self.child1.first_name,
            'date_of_birth': self.child1.date_of_birth.isoformat()
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retrieve_child_success(self):
        """Test retrieving child profile"""
        self.authenticate(self.parent_token)
        url = reverse('child-profile-detail', kwargs={'pk': self.child1.id})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], str(self.child1.id))
        self.assertEqual(response.data['first_name'], 'Alice')
        self.assertIn('age', response.data)
        self.assertIn('profile_completeness', response.data)
        self.assertIn('consent_summary', response.data)

    def test_retrieve_child_not_found(self):
        """Test retrieving non-existent child"""
        self.authenticate(self.parent_token)
        fake_id = str(uuid.uuid4())
        url = reverse('child-profile-detail', kwargs={'pk': fake_id})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_child_invalid_uuid(self):
        """Test retrieving child with invalid UUID format"""
        self.authenticate(self.parent_token)
        url = reverse('child-profile-detail', kwargs={'pk': 'invalid-uuid'})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_other_parent_child_forbidden(self):
        """Test parent cannot retrieve another parent's child"""
        self.authenticate(self.parent_token)
        url = reverse('child-profile-detail', kwargs={'pk': self.other_parent_child.id})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_child_success(self):
        """Test updating child profile"""
        self.authenticate(self.parent_token)
        url = reverse('child-profile-detail', kwargs={'pk': self.child1.id})

        data = {
            'nickname': 'Ally',
            'height_cm': 130,
            'weight_kg': 30,
            'health_status': 'Good',
            'parental_goals': 'Improve social skills'
        }

        response = self.client.patch(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['child']['nickname'], 'Ally')
        self.assertEqual(response.data['child']['height_cm'], 130)
        self.assertEqual(response.data['child']['bmi'], 17.8)  # Calculated BMI

        # Verify database update
        self.child1.refresh_from_db()
        self.assertEqual(self.child1.nickname, 'Ally')

    def test_update_child_invalid_data(self):
        """Test updating child with invalid data"""
        self.authenticate(self.parent_token)
        url = reverse('child-profile-detail', kwargs={'pk': self.child1.id})

        data = {
            'height_cm': 500,  # Too tall
            'weight_kg': 5     # Too light for height
        }

        response = self.client.patch(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_other_parent_child_forbidden(self):
        """Test parent cannot update another parent's child"""
        self.authenticate(self.parent_token)
        url = reverse('child-profile-detail', kwargs={'pk': self.other_parent_child.id})

        data = {'nickname': 'Chuck'}
        response = self.client.patch(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_child_success(self):
        """Test deleting child profile"""
        self.authenticate(self.parent_token)
        url = reverse('child-profile-detail', kwargs={'pk': self.child1.id})

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Verify child was deleted
        with self.assertRaises(Child.DoesNotExist):
            Child.objects.get(id=self.child1.id)

    def test_delete_other_parent_child_forbidden(self):
        """Test parent cannot delete another parent's child"""
        self.authenticate(self.parent_token)
        url = reverse('child-profile-detail', kwargs={'pk': self.other_parent_child.id})

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Verify child still exists
        self.assertTrue(Child.objects.filter(id=self.other_parent_child.id).exists())

    def test_profile_summary(self):
        """Test getting child profile summary"""
        self.authenticate(self.parent_token)
        url = reverse('child-profile-profile-summary', kwargs={'pk': self.child1.id})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('profile_completeness', response.data)
        self.assertIn('consent_summary', response.data)
        self.assertIn('age_appropriate_grades', response.data)
        self.assertEqual(response.data['full_name'], 'Alice Doe')

    def test_manage_consent_grant(self):
        """Test granting consent for a child"""
        self.authenticate(self.parent_token)
        url = reverse('child-profile-manage-consent', kwargs={'pk': self.child1.id})

        data = {
            'consent_type': 'service_consent',
            'granted': True,
            'parent_signature': 'John Doe',
            'notes': 'I agree to the terms'
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('consent_summary', response.data)

        # Verify consent was saved
        self.child1.refresh_from_db()
        self.assertTrue(self.child1.get_consent_status('service_consent'))

    def test_manage_consent_revoke(self):
        """Test revoking consent for a child"""
        # First grant consent
        self.child1.set_consent('service_consent', True, 'John Doe')

        self.authenticate(self.parent_token)
        url = reverse('child-profile-manage-consent', kwargs={'pk': self.child1.id})

        data = {
            'consent_type': 'service_consent',
            'granted': False,
            'notes': 'Revoking consent'
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify consent was revoked
        self.child1.refresh_from_db()
        self.assertFalse(self.child1.get_consent_status('service_consent'))

    def test_manage_consent_invalid_type(self):
        """Test managing consent with invalid consent type"""
        self.authenticate(self.parent_token)
        url = reverse('child-profile-manage-consent', kwargs={'pk': self.child1.id})

        data = {
            'consent_type': 'invalid_consent',
            'granted': True
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('consent_type', response.data)

    def test_bulk_consent_update(self):
        """Test updating multiple consents at once"""
        self.authenticate(self.parent_token)
        url = reverse('child-profile-bulk-consent', kwargs={'pk': self.child1.id})

        data = {
            'consent_types': ['service_consent', 'assessment_consent', 'communication_consent'],
            'granted': True,
            'parent_signature': 'John Doe',
            'notes': 'Granting all consents'
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['updated_consents']), 3)

        # Verify all consents were granted
        self.child1.refresh_from_db()
        self.assertTrue(self.child1.get_consent_status('service_consent'))
        self.assertTrue(self.child1.get_consent_status('assessment_consent'))
        self.assertTrue(self.child1.get_consent_status('communication_consent'))

    def test_psychologist_read_access(self):
        """Test psychologist can read child profiles (future implementation)"""
        self.authenticate(self.psychologist_token)
        url = reverse('child-profile-detail', kwargs={'pk': self.child1.id})

        response = self.client.get(url)

        # Currently psychologists have read access to all children
        # This will change when appointment relationships are implemented
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_psychologist_cannot_modify(self):
        """Test psychologist cannot modify child profiles"""
        self.authenticate(self.psychologist_token)
        url = reverse('child-profile-detail', kwargs={'pk': self.child1.id})

        data = {'nickname': 'Test'}
        response = self.client.patch(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_full_access(self):
        """Test admin has full access to all child profiles"""
        self.authenticate(self.admin_token)

        # Can read any child
        url = reverse('child-profile-detail', kwargs={'pk': self.other_parent_child.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Can update any child
        data = {'nickname': 'Admin Update'}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Can delete any child
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class ChildManagementViewSetTests(BaseChildTestCase):
    """Test cases for ChildManagementViewSet"""
    def test_debug_serializer_validation(self):
        """Debug test to check serializer validation"""
        from children.serializers import ChildSearchSerializer

        # Test serializer validation
        search_data = {'gender': 'Male'}
        serializer = ChildSearchSerializer(data=search_data)

        print(f"Serializer valid: {serializer.is_valid()}")
        print(f"Serializer errors: {serializer.errors}")
        print(f"Validated data: {serializer.validated_data if serializer.is_valid() else 'N/A'}")

        # Test the service method directly with validated data
        if serializer.is_valid():
            from children.services import ChildService
            results = ChildService.search_children(serializer.validated_data, self.parent_user)
            print(f"Service method results: {len(results)}")
            for child in results:
                print(f"- {child.first_name} ({child.gender})")

        # Also test manual queryset filtering
        from children.models import Child
        queryset = Child.objects.filter(parent=self.parent)
        print(f"\nAll children for parent: {queryset.count()}")
        for child in queryset:
            print(f"- {child.first_name} ({child.gender})")

        male_children = queryset.filter(gender='Male')
        print(f"\nMale children for parent: {male_children.count()}")
        for child in male_children:
            print(f"- {child.first_name} ({child.gender})")

        # Test icontains vs exact match
        male_children_icontains = queryset.filter(gender__icontains='Male')
        print(f"\nMale children (icontains): {male_children_icontains.count()}")
        for child in male_children_icontains:
            print(f"- {child.first_name} ({child.gender})")
    def test_debug_search_results(self):
        """Debug test to see what search returns"""
        self.authenticate(self.parent_token)
        url = reverse('child-management-search')
        data = {'gender': 'Male'}
        response = self.client.post(url, data, format='json')

        print(f"Response status: {response.status_code}")
        print(f"Response data: {response.data}")
        print(f"Results: {[child['first_name'] for child in response.data.get('results', [])]}")
        print(f"Parent user: {self.parent_user.email}")
        print(f"Children for this parent: {[child.first_name for child in Child.objects.filter(parent=self.parent)]}")
    def test_list_children_as_parent(self):
        """Test parent can list only their own children"""
        self.authenticate(self.parent_token)
        url = reverse('child-management-list')

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

        # Verify only parent's children are returned
        child_ids = [child['id'] for child in response.data['results']]
        self.assertIn(str(self.child1.id), child_ids)
        self.assertIn(str(self.child2.id), child_ids)
        self.assertNotIn(str(self.other_parent_child.id), child_ids)

    def test_list_children_as_admin(self):
        """Test admin can list all children"""
        self.authenticate(self.admin_token)
        url = reverse('child-management-list')

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3)  # All children

    def test_list_children_as_psychologist(self):
        """Test psychologist gets empty list (no appointments yet)"""
        self.authenticate(self.psychologist_token)
        url = reverse('child-management-list')

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

    def test_retrieve_child_management(self):
        """Test retrieving child through management endpoint"""
        self.authenticate(self.admin_token)
        url = reverse('child-management-detail', kwargs={'pk': self.child1.id})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], str(self.child1.id))
        # Should include parent details
        self.assertIn('parent', response.data)
        self.assertEqual(response.data['parent']['email'], 'parent@test.com')

    def test_search_children_by_name(self):
        """Test searching children by name"""
        self.authenticate(self.admin_token)
        url = reverse('child-management-search')

        data = {
            'first_name': 'Alice'
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['first_name'], 'Alice')

    def test_search_children_by_age_range(self):
        """Test searching children by age range"""
        self.authenticate(self.admin_token)
        url = reverse('child-management-search')

        data = {
            'age_min': 9,
            'age_max': 12
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)  # Bob (10) and Charlie (12)

    def test_search_children_by_psychology_history(self):
        """Test searching children with psychology history"""
        self.authenticate(self.admin_token)
        url = reverse('child-management-search')

        data = {
            'has_psychology_history': True
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['first_name'], 'Bob')

    def test_search_children_parent_email(self):
        """Test searching children by parent email"""
        self.authenticate(self.admin_token)
        url = reverse('child-management-search')

        data = {
            'parent_email': 'parent@test.com'
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)

    def test_search_children_complex_filters(self):
        """Test searching with multiple filters"""
        self.authenticate(self.admin_token)
        url = reverse('child-management-search')

        data = {
            'gender': 'Male',
            'age_min': 8,
            'age_max': 10
        }

        response = self.client.post(url, data, format='json')
        print(f"Count: {response.data['count']}")
        for child in response.data['results']:
            print(f"Child: {child['first_name']} {child['last_name']}, Gender: {child['gender']}, Age: {child['age']}")


        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)  # Only Bob matches
        self.assertEqual(response.data['results'][0]['first_name'], 'Bob')

    def test_search_parent_filters_own_children(self):
        """Test parent search only returns their own children"""
        self.authenticate(self.parent_token)
        url = reverse('child-management-search')

        data = {
            'gender': 'Male'  # Both Bob and Charlie are male
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)  # Only Bob (parent's child)
        self.assertEqual(response.data['results'][0]['first_name'], 'Bob')

    def test_search_non_admin_cannot_search_all(self):
        """Test non-admin users get filtered results"""
        self.authenticate(self.parent_token)
        url = reverse('child-management-search')

        # Try to search by another parent's email
        data = {
            'parent_email': 'parent2@test.com'
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)  # No results (filtered)

    def test_statistics_admin_only(self):
        """Test only admin can access statistics"""
        url = reverse('child-management-statistics')

        # Test as parent - should be denied
        self.authenticate(self.parent_token)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Test as psychologist - should be denied
        self.authenticate(self.psychologist_token)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Test as admin - should succeed
        self.authenticate(self.admin_token)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify statistics structure
        self.assertIn('total_children', response.data)
        self.assertIn('age_distribution', response.data)
        self.assertIn('psychology_history', response.data)
        self.assertIn('gender_distribution', response.data)

        self.assertEqual(response.data['total_children'], 3)
        self.assertEqual(response.data['psychology_history']['with_history'], 1)  # Bob


class ChildViewsEdgeCaseTests(BaseChildTestCase):
    """Test edge cases and error handling"""

    def test_create_child_invalid_json(self):
        """Test creating child with invalid JSON"""
        self.authenticate(self.parent_token)
        url = reverse('child-profile-list')

        # Send invalid JSON
        response = self.client.post(
            url,
            data='{"invalid json',
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_child_empty_name(self):
        """Test creating child with empty name"""
        self.authenticate(self.parent_token)
        url = reverse('child-profile-list')

        data = self.get_valid_child_data()
        data['first_name'] = '   '  # Only spaces

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('first_name', response.data)

    def test_update_child_unusual_bmi(self):
        """Test updating child with unusual height/weight combination"""
        self.authenticate(self.parent_token)
        url = reverse('child-profile-detail', kwargs={'pk': self.child1.id})

        data = {
            'height_cm': 150,
            'weight_kg': 150  # BMI would be 66.7
        }

        response = self.client.patch(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_consent_management_with_special_characters(self):
        """Test consent management with special characters in signature"""
        self.authenticate(self.parent_token)
        url = reverse('child-profile-manage-consent', kwargs={'pk': self.child1.id})

        data = {
            'consent_type': 'service_consent',
            'granted': True,
            'parent_signature': 'John Doe & Co.',
            'notes': 'I agree to the terms & conditions'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('consent_summary', response.data)
        self.child1.refresh_from_db()
        self.assertTrue(self.child1.get_consent_status('service_consent'))
