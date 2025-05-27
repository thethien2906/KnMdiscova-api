# children/tests/test_services.py
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date, timedelta
from unittest.mock import patch
import uuid

from users.models import User
from parents.models import Parent
from children.models import Child
from children.services import (
    ChildService,
    ChildProfileError,
    ChildNotFoundError,
    ChildAccessDeniedError,
    ChildAgeValidationError,
    ConsentManagementError
)


class ChildServiceTestCase(TestCase):
    """Test case for ChildService"""

    def setUp(self):
        """Set up test data"""
        # Create parent user and profile (signal will auto-create parent profile)
        self.parent_user = User.objects.create_parent(
            email='parent@test.com',
            password='testpass123',
            user_timezone='UTC'
        )
        self.parent_user.is_verified = True
        self.parent_user.save()

        # Get the auto-created parent profile
        self.parent = Parent.objects.get(user=self.parent_user)
        self.parent.first_name = 'John'
        self.parent.last_name = 'Doe'
        self.parent.save()

        # Create psychologist user for testing access control
        self.psychologist_user = User.objects.create_psychologist(
            email='psychologist@test.com',
            password='testpass123'
        )

        # Create admin user
        self.admin_user = User.objects.create_superuser(
            email='admin@test.com',
            password='testpass123'
        )

        # Valid child data - using proper age calculation
        # For an 8-year-old, we need to account for leap years
        today = date.today()
        eight_years_ago = date(today.year - 8, today.month, today.day)
        # Adjust if the birthday hasn't occurred yet this year
        if today < eight_years_ago:
            eight_years_ago = date(today.year - 9, today.month, today.day)

        self.valid_child_data = {
            'first_name': 'Alice',
            'last_name': 'Doe',
            'date_of_birth': eight_years_ago,
            'gender': 'Female',
            'primary_language': 'English',
            'school_grade_level': 'Grade 3'
        }

    def test_get_child_by_id_success(self):
        """Test successful child retrieval by ID"""
        # Create a child first
        child = Child.objects.create(
            parent=self.parent,
            **self.valid_child_data
        )

        # Test retrieval
        retrieved_child = ChildService.get_child_by_id(str(child.id))

        self.assertIsNotNone(retrieved_child)
        self.assertEqual(retrieved_child.id, child.id)
        self.assertEqual(retrieved_child.first_name, 'Alice')

    def test_get_child_by_id_not_found(self):
        """Test child retrieval with non-existent ID"""
        non_existent_id = str(uuid.uuid4())

        retrieved_child = ChildService.get_child_by_id(non_existent_id)

        self.assertIsNone(retrieved_child)

    def test_get_child_by_id_or_raise_success(self):
        """Test successful child retrieval or raise"""
        child = Child.objects.create(
            parent=self.parent,
            **self.valid_child_data
        )

        retrieved_child = ChildService.get_child_by_id_or_raise(str(child.id))

        self.assertEqual(retrieved_child.id, child.id)

    def test_get_child_by_id_or_raise_not_found(self):
        """Test child retrieval or raise with non-existent ID"""
        non_existent_id = str(uuid.uuid4())

        with self.assertRaises(ChildNotFoundError):
            ChildService.get_child_by_id_or_raise(non_existent_id)

    def test_get_children_for_parent(self):
        """Test getting all children for a parent"""
        # Create multiple children
        child1 = Child.objects.create(
            parent=self.parent,
            first_name='Alice',
            date_of_birth=date.today() - timedelta(days=8*365)
        )
        child2 = Child.objects.create(
            parent=self.parent,
            first_name='Bob',
            date_of_birth=date.today() - timedelta(days=10*365)
        )

        children = ChildService.get_children_for_parent(self.parent)

        self.assertEqual(len(children), 2)
        self.assertIn(child1, children)
        self.assertIn(child2, children)

    def test_create_child_profile_success(self):
        """Test successful child profile creation"""
        child = ChildService.create_child_profile(self.parent, self.valid_child_data)

        self.assertIsInstance(child, Child)
        self.assertEqual(child.parent, self.parent)
        self.assertEqual(child.first_name, 'Alice')
        self.assertEqual(child.age, 8)
        self.assertIsNotNone(child.consent_forms_signed)

    def test_create_child_profile_parent_not_verified(self):
        """Test child creation with unverified parent"""
        self.parent_user.is_verified = False
        self.parent_user.save()

        with self.assertRaises(ChildProfileError) as context:
            ChildService.create_child_profile(self.parent, self.valid_child_data)

        self.assertIn("verified", str(context.exception))

    def test_create_child_profile_parent_inactive(self):
        """Test child creation with inactive parent"""
        self.parent_user.is_active = False
        self.parent_user.save()

        with self.assertRaises(ChildProfileError) as context:
            ChildService.create_child_profile(self.parent, self.valid_child_data)

        self.assertIn("inactive", str(context.exception))

    def test_create_child_profile_duplicate_child(self):
        """Test creating duplicate child (same name + DOB)"""
        # Create first child
        ChildService.create_child_profile(self.parent, self.valid_child_data)

        # Try to create duplicate
        with self.assertRaises(ChildProfileError) as context:
            ChildService.create_child_profile(self.parent, self.valid_child_data)

        self.assertIn("already exists", str(context.exception))

    def test_create_child_profile_invalid_age_too_young(self):
        """Test child creation with age too young"""
        invalid_data = self.valid_child_data.copy()
        today = date.today()
        # Create a date for a 3-year-old (too young)
        three_years_ago = date(today.year - 3, today.month, today.day)
        if today < three_years_ago:
            three_years_ago = date(today.year - 4, today.month, today.day)
        invalid_data['date_of_birth'] = three_years_ago

        with self.assertRaises(ChildProfileError):
            ChildService.create_child_profile(self.parent, invalid_data)

    def test_create_child_profile_invalid_age_too_old(self):
        """Test child creation with age too old"""
        invalid_data = self.valid_child_data.copy()
        today = date.today()
        # Create a date for a 20-year-old (too old)
        twenty_years_ago = date(today.year - 20, today.month, today.day)
        if today < twenty_years_ago:
            twenty_years_ago = date(today.year - 21, today.month, today.day)
        invalid_data['date_of_birth'] = twenty_years_ago

        with self.assertRaises(ChildProfileError):
            ChildService.create_child_profile(self.parent, invalid_data)

    def test_update_child_profile_success(self):
        """Test successful child profile update"""
        child = Child.objects.create(
            parent=self.parent,
            **self.valid_child_data
        )

        update_data = {
            'nickname': 'Ally',
            'school_grade_level': 'Grade 4',
            'health_status': 'Excellent'
        }

        updated_child = ChildService.update_child_profile(child, update_data)

        self.assertEqual(updated_child.nickname, 'Ally')
        self.assertEqual(updated_child.school_grade_level, 'Grade 4')
        self.assertEqual(updated_child.health_status, 'Excellent')

    def test_update_child_profile_with_consent(self):
        """Test updating child profile with consent data"""
        child = Child.objects.create(
            parent=self.parent,
            **self.valid_child_data
        )

        update_data = {
            'nickname': 'Ally',
            'consent_forms_signed': {
                'service_consent': {
                    'granted': True,
                    'date_signed': timezone.now().isoformat(),
                    'parent_signature': 'John Doe',
                    'notes': 'Consent granted',
                    'version': '1.0'
                }
            }
        }

        updated_child = ChildService.update_child_profile(child, update_data)

        self.assertEqual(updated_child.nickname, 'Ally')
        self.assertTrue(updated_child.get_consent_status('service_consent'))

    def test_update_child_profile_parent_inactive(self):
        """Test updating child with inactive parent"""
        child = Child.objects.create(
            parent=self.parent,
            **self.valid_child_data
        )

        self.parent_user.is_active = False
        self.parent_user.save()

        with self.assertRaises(ChildProfileError) as context:
            ChildService.update_child_profile(child, {'nickname': 'Ally'})

        self.assertIn("inactive", str(context.exception))

    def test_delete_child_profile_success(self):
        """Test successful child profile deletion"""
        child = Child.objects.create(
            parent=self.parent,
            **self.valid_child_data
        )
        child_id = child.id

        result = ChildService.delete_child_profile(child)

        self.assertTrue(result)
        self.assertFalse(Child.objects.filter(id=child_id).exists())

    def test_get_child_profile_data(self):
        """Test getting comprehensive child profile data"""
        child = Child.objects.create(
            parent=self.parent,
            **self.valid_child_data
        )

        profile_data = ChildService.get_child_profile_data(child)

        self.assertIsInstance(profile_data, dict)
        self.assertEqual(profile_data['first_name'], 'Alice')
        self.assertEqual(profile_data['age'], 8)
        self.assertIn('profile_completeness', profile_data)
        self.assertIn('consent_summary', profile_data)
        self.assertIn('age_appropriate_grades', profile_data)

    def test_manage_consent_success(self):
        """Test successful consent management"""
        child = Child.objects.create(
            parent=self.parent,
            **self.valid_child_data
        )

        updated_child = ChildService.manage_consent(
            child=child,
            consent_type='service_consent',
            granted=True,
            parent_signature='John Doe',
            notes='Consent granted for psychological services'
        )

        self.assertTrue(updated_child.get_consent_status('service_consent'))

    def test_manage_consent_invalid_type(self):
        """Test consent management with invalid consent type"""
        child = Child.objects.create(
            parent=self.parent,
            **self.valid_child_data
        )

        with self.assertRaises(ConsentManagementError) as context:
            ChildService.manage_consent(
                child=child,
                consent_type='invalid_consent',
                granted=True
            )

        self.assertIn("Invalid consent type", str(context.exception))

    def test_bulk_consent_update_success(self):
        """Test successful bulk consent update"""
        child = Child.objects.create(
            parent=self.parent,
            **self.valid_child_data
        )

        consent_types = ['service_consent', 'assessment_consent']

        updated_child = ChildService.bulk_consent_update(
            child=child,
            consent_types=consent_types,
            granted=True,
            parent_signature='John Doe',
            notes='Bulk consent granted'
        )

        for consent_type in consent_types:
            self.assertTrue(updated_child.get_consent_status(consent_type))

    def test_bulk_consent_update_invalid_type(self):
        """Test bulk consent update with invalid consent type"""
        child = Child.objects.create(
            parent=self.parent,
            **self.valid_child_data
        )

        consent_types = ['service_consent', 'invalid_consent']

        with self.assertRaises(ConsentManagementError):
            ChildService.bulk_consent_update(
                child=child,
                consent_types=consent_types,
                granted=True
            )

    def test_get_consent_summary(self):
        """Test getting consent summary for a child"""
        child = Child.objects.create(
            parent=self.parent,
            **self.valid_child_data
        )

        # Grant one consent
        ChildService.manage_consent(
            child=child,
            consent_type='service_consent',
            granted=True,
            parent_signature='John Doe'
        )

        summary = ChildService.get_consent_summary(child)

        self.assertIsInstance(summary, dict)
        self.assertIn('total_consents', summary)
        self.assertIn('granted_count', summary)
        self.assertIn('consents', summary)
        self.assertEqual(summary['granted_count'], 1)
        self.assertTrue(summary['consents']['service_consent']['granted'])

    def test_search_children_by_name(self):
        """Test searching children by name"""
        # Create multiple children
        child1 = Child.objects.create(
            parent=self.parent,
            first_name='Alice',
            last_name='Doe',
            date_of_birth=date.today() - timedelta(days=8*365)
        )
        child2 = Child.objects.create(
            parent=self.parent,
            first_name='Bob',
            last_name='Smith',
            date_of_birth=date.today() - timedelta(days=10*365)
        )

        # Search by first name
        search_params = {'first_name': 'Alice'}
        results = ChildService.search_children(search_params, self.parent_user)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].first_name, 'Alice')

        # Search by last name
        search_params = {'last_name': 'Smith'}
        results = ChildService.search_children(search_params, self.parent_user)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].last_name, 'Smith')

    def test_search_children_by_age_range(self):
        """Test searching children by age range"""
        today = date.today()

        # Create an 8-year-old
        eight_years_ago = date(today.year - 8, today.month, today.day)
        if today < eight_years_ago:
            eight_years_ago = date(today.year - 9, today.month, today.day)

        # Create a 12-year-old
        twelve_years_ago = date(today.year - 12, today.month, today.day)
        if today < twelve_years_ago:
            twelve_years_ago = date(today.year - 13, today.month, today.day)

        child1 = Child.objects.create(
            parent=self.parent,
            first_name='Alice',
            date_of_birth=eight_years_ago
        )
        child2 = Child.objects.create(
            parent=self.parent,
            first_name='Bob',
            date_of_birth=twelve_years_ago
        )

        # Search for children aged 7-10
        search_params = {'age_min': 7, 'age_max': 10}
        results = ChildService.search_children(search_params, self.parent_user)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].first_name, 'Alice')

    def test_search_children_by_psychology_history(self):
        """Test searching children by psychology history"""
        today = date.today()

        # Create proper age dates
        eight_years_ago = date(today.year - 8, today.month, today.day)
        if today < eight_years_ago:
            eight_years_ago = date(today.year - 9, today.month, today.day)

        ten_years_ago = date(today.year - 10, today.month, today.day)
        if today < ten_years_ago:
            ten_years_ago = date(today.year - 11, today.month, today.day)

        child1 = Child.objects.create(
            parent=self.parent,
            first_name='Alice',
            date_of_birth=eight_years_ago,
            has_seen_psychologist=True
        )
        child2 = Child.objects.create(
            parent=self.parent,
            first_name='Bob',
            date_of_birth=ten_years_ago,
            has_seen_psychologist=False
        )

        # Search for children with psychology history
        search_params = {'has_psychology_history': True}
        results = ChildService.search_children(search_params, self.parent_user)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].first_name, 'Alice')

        # Search for children without psychology history
        search_params = {'has_psychology_history': False}
        results = ChildService.search_children(search_params, self.parent_user)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].first_name, 'Bob')

    def test_validate_child_data_success(self):
        """Test successful child data validation"""
        validated_data = ChildService.validate_child_data(self.valid_child_data)

        self.assertEqual(validated_data, self.valid_child_data)

    def test_validate_child_data_missing_required_fields(self):
        """Test validation with missing required fields"""
        invalid_data = {'last_name': 'Doe'}  # Missing first_name and date_of_birth

        with self.assertRaises(ValidationError) as context:
            ChildService.validate_child_data(invalid_data)

        errors = context.exception.message_dict
        self.assertIn('first_name', errors)
        self.assertIn('date_of_birth', errors)

    def test_validate_child_data_invalid_age(self):
        """Test validation with invalid age"""
        invalid_data = self.valid_child_data.copy()
        today = date.today()
        # Create a date for a 2-year-old (too young)
        two_years_ago = date(today.year - 2, today.month, today.day)
        if today < two_years_ago:
            two_years_ago = date(today.year - 3, today.month, today.day)
        invalid_data['date_of_birth'] = two_years_ago

        with self.assertRaises(ValidationError) as context:
            ChildService.validate_child_data(invalid_data)

        errors = context.exception.message_dict
        self.assertIn('date_of_birth', errors)

    def test_validate_child_data_invalid_bmi(self):
        """Test validation with invalid BMI combination"""
        invalid_data = self.valid_child_data.copy()
        invalid_data['height_cm'] = 100  # 1 meter
        invalid_data['weight_kg'] = 200  # 200 kg - unrealistic BMI

        with self.assertRaises(ValidationError) as context:
            ChildService.validate_child_data(invalid_data)

        errors = context.exception.message_dict
        self.assertIn('weight_kg', errors)

    def test_validate_child_data_invalid_consent_structure(self):
        """Test validation with invalid consent structure"""
        invalid_data = self.valid_child_data.copy()
        invalid_data['consent_forms_signed'] = "invalid_string"  # Should be dict

        with self.assertRaises(ValidationError) as context:
            ChildService.validate_child_data(invalid_data)

        errors = context.exception.message_dict
        self.assertIn('consent_forms_signed', errors)

    def test_validate_child_data_update_mode(self):
        """Test validation in update mode (less strict)"""
        # In update mode, missing required fields should be allowed
        update_data = {'nickname': 'Ally'}

        validated_data = ChildService.validate_child_data(update_data, is_update=True)

        self.assertEqual(validated_data, update_data)

    def test_check_duplicate_child(self):
        """Test duplicate child checking"""
        # Create first child
        Child.objects.create(
            parent=self.parent,
            **self.valid_child_data
        )

        # Test duplicate detection
        with self.assertRaises(ChildProfileError) as context:
            ChildService._check_duplicate_child(self.parent, self.valid_child_data)

        self.assertIn("already exists", str(context.exception))

    def test_initialize_default_consents(self):
        """Test default consent initialization"""
        child = Child.objects.create(
            parent=self.parent,
            first_name='Test',
            date_of_birth=date.today() - timedelta(days=8*365)
        )

        # Clear consent forms
        child.consent_forms_signed = {}
        child.save()

        # Initialize defaults
        ChildService._initialize_default_consents(child)

        child.refresh_from_db()

        self.assertIsNotNone(child.consent_forms_signed)
        default_types = Child.get_default_consent_types().keys()
        for consent_type in default_types:
            self.assertIn(consent_type, child.consent_forms_signed)
            self.assertFalse(child.consent_forms_signed[consent_type]['granted'])

    def test_calculate_age(self):
        """Test age calculation"""
        today = date.today()

        # Test with 8-year-old - use proper date calculation
        eight_years_ago = date(today.year - 8, today.month, today.day)
        if today < eight_years_ago:
            eight_years_ago = date(today.year - 9, today.month, today.day)

        age = ChildService._calculate_age(eight_years_ago)
        self.assertEqual(age, 8)

        # Test with string date
        age = ChildService._calculate_age(eight_years_ago.strftime('%Y-%m-%d'))
        self.assertEqual(age, 8)

    @patch('children.services.logger')
    def test_logging_on_create_success(self, mock_logger):
        """Test that successful operations are logged"""
        ChildService.create_child_profile(self.parent, self.valid_child_data)

        mock_logger.info.assert_called()
        log_message = mock_logger.info.call_args[0][0]
        self.assertIn("Child profile created", log_message)

    @patch('children.services.logger')
    def test_logging_on_error(self, mock_logger):
        """Test that errors are logged"""
        # Make parent inactive to trigger error
        self.parent_user.is_active = False
        self.parent_user.save()

        with self.assertRaises(ChildProfileError):
            ChildService.create_child_profile(self.parent, self.valid_child_data)

        mock_logger.error.assert_called()

    def tearDown(self):
        """Clean up after tests"""
        # Clean up is automatic with Django TestCase
        pass


class ChildServiceEdgeCasesTestCase(TestCase):
    """Test edge cases and error conditions"""

    def setUp(self):
        """Set up minimal test data"""
        self.parent_user = User.objects.create_parent(
            email='parent@test.com',
            password='testpass123'
        )
        self.parent_user.is_verified = True
        self.parent_user.save()

        self.parent = Parent.objects.get(user=self.parent_user)

    def test_create_child_with_non_parent_user(self):
        """Test creating child with non-parent user type"""
        # Change user type after creation (edge case)
        self.parent_user.user_type = 'Psychologist'
        self.parent_user.save()

        today = date.today()
        eight_years_ago = date(today.year - 8, today.month, today.day)
        if today < eight_years_ago:
            eight_years_ago = date(today.year - 9, today.month, today.day)

        child_data = {
            'first_name': 'Test',
            'date_of_birth': eight_years_ago
        }

        with self.assertRaises(ChildProfileError) as context:
            ChildService.create_child_profile(self.parent, child_data)

        self.assertIn("Only parents", str(context.exception))

    def test_search_with_empty_params(self):
        """Test search with empty parameters"""
        results = ChildService.search_children({}, self.parent_user)

        # Should return all children (empty list if none exist)
        self.assertIsInstance(results, list)

    def test_consent_summary_with_no_consents(self):
        """Test consent summary for child with no consent data"""
        today = date.today()
        eight_years_ago = date(today.year - 8, today.month, today.day)
        if today < eight_years_ago:
            eight_years_ago = date(today.year - 9, today.month, today.day)

        child = Child.objects.create(
            parent=self.parent,
            first_name='Test',
            date_of_birth=eight_years_ago,
            consent_forms_signed={}
        )

        summary = ChildService.get_consent_summary(child)

        self.assertEqual(summary['granted_count'], 0)
        self.assertEqual(summary['revoked_count'], 0)
        self.assertGreater(summary['pending_count'], 0)

    def test_update_child_with_empty_data(self):
        """Test updating child with empty update data"""
        today = date.today()
        eight_years_ago = date(today.year - 8, today.month, today.day)
        if today < eight_years_ago:
            eight_years_ago = date(today.year - 9, today.month, today.day)

        child = Child.objects.create(
            parent=self.parent,
            first_name='Test',
            date_of_birth=eight_years_ago
        )

        # Should not raise error, just return child unchanged
        updated_child = ChildService.update_child_profile(child, {})

        self.assertEqual(updated_child.id, child.id)

    def test_bulk_consent_with_empty_list(self):
        """Test bulk consent update with empty consent types list"""
        today = date.today()
        eight_years_ago = date(today.year - 8, today.month, today.day)
        if today < eight_years_ago:
            eight_years_ago = date(today.year - 9, today.month, today.day)

        child = Child.objects.create(
            parent=self.parent,
            first_name='Test',
            date_of_birth=eight_years_ago
        )

        # Should handle empty list gracefully
        updated_child = ChildService.bulk_consent_update(
            child=child,
            consent_types=[],
            granted=True
        )

        self.assertEqual(updated_child.id, child.id)