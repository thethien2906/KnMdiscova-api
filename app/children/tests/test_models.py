# children/test_models.py
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date, timedelta
from children.models import Child
from parents.models import Parent
from users.models import User


class ChildModelTest(TestCase):
    """Test cases for the Child model"""

    def setUp(self):
        """Set up test data"""
        # Create parent user and profile (profile created via signal)
        self.parent_user = User.objects.create_parent(
            email='parent@test.com',
            password='testpass123',
            user_timezone='UTC'
        )
        self.parent_user.is_verified = True
        self.parent_user.save()
        # Get the automatically created parent profile
        self.parent_profile = Parent.objects.get(user=self.parent_user)

        # Create valid child data (10 years old)
        ten_years_ago = date(date.today().year - 10, date.today().month, date.today().day)
        self.valid_child_data = {
            'parent': self.parent_profile,
            'first_name': 'John',
            'last_name': 'Doe',
            'date_of_birth': ten_years_ago,
            'nickname': 'Johnny',
            'gender': 'Male',
            'height_cm': 140,
            'weight_kg': 35,
            'primary_language': 'English',
            'school_grade_level': 'Grade 5',
            'health_status': 'Good',
            'parental_goals': 'Improve social skills'
        }

    def test_child_creation_with_required_fields_only(self):
        """Test creating a child with only required fields"""
        # Create a child that is definitely 8 years old
        eight_years_ago = date(date.today().year - 8, date.today().month, date.today().day)
        child = Child.objects.create(
            parent=self.parent_profile,
            first_name='Jane',
            date_of_birth=eight_years_ago
        )

        self.assertEqual(child.first_name, 'Jane')
        self.assertEqual(child.parent, self.parent_profile)
        self.assertIsNotNone(child.id)
        self.assertEqual(child.age, 8)

    def test_child_creation_with_all_fields(self):
        """Test creating a child with all fields populated"""
        child = Child.objects.create(**self.valid_child_data)

        self.assertEqual(child.first_name, 'John')
        self.assertEqual(child.last_name, 'Doe')
        self.assertEqual(child.nickname, 'Johnny')
        self.assertEqual(child.gender, 'Male')
        self.assertEqual(child.height_cm, 140)
        self.assertEqual(child.weight_kg, 35)
        self.assertEqual(child.primary_language, 'English')
        self.assertEqual(child.school_grade_level, 'Grade 5')

    def test_child_str_representation(self):
        """Test string representation of child"""
        # With last name
        child_with_lastname = Child.objects.create(**self.valid_child_data)
        expected_str = f"John Doe (Age {child_with_lastname.age})"
        self.assertEqual(str(child_with_lastname), expected_str)

        # Without last name
        child_without_lastname = Child.objects.create(
            parent=self.parent_profile,
            first_name='Alice',
            date_of_birth=date.today() - timedelta(days=365 * 7)
        )
        expected_str = f"Alice (Age {child_without_lastname.age})"
        self.assertEqual(str(child_without_lastname), expected_str)

    def test_age_calculation(self):
        """Test age calculation property"""
        # Child born exactly 10 years ago (same date)
        ten_years_ago = date(date.today().year - 10, date.today().month, date.today().day-1)
        child = Child.objects.create(
            parent=self.parent_profile,
            first_name='Test',
            date_of_birth=ten_years_ago
        )
        self.assertEqual(child.age, 10)

        # Child with birthday not yet reached this year (should be 1 year younger)
        future_birthday_this_year = date.today() + timedelta(days=30)
        if future_birthday_this_year.month > 12:  # Handle year overflow
            future_birthday_this_year = date(date.today().year + 1, 1, 15)

        # Make it 6 years ago but with birthday in the future
        six_years_ago_future_birthday = date(
            date.today().year - 6,
            future_birthday_this_year.month,
            future_birthday_this_year.day
        )

        child_future_bday = Child.objects.create(
            parent=self.parent_profile,
            first_name='Future',
            date_of_birth=six_years_ago_future_birthday
        )
        # Should be 5 since birthday hasn't occurred this year
        self.assertEqual(child_future_bday.age, 5)

    def test_only_5_years_old_child(self):
        """Test that only children 5 years old or older can be created"""
        with self.assertRaises(ValidationError) as context:
            child = Child(
                parent=self.parent_profile,
                first_name='TooYoung',
                date_of_birth=date.today() - timedelta(days=365 * 3)  # 3 years old
            )
            child.full_clean()

        self.assertIn('Child must be at least 5 years old', str(context.exception))

    def test_full_name_property(self):
        """Test full_name property"""
        child = Child.objects.create(**self.valid_child_data)
        self.assertEqual(child.full_name, 'John Doe')

        # Child without last name
        eight_years_ago = date(date.today().year - 8, date.today().month, date.today().day)
        child_no_lastname = Child.objects.create(
            parent=self.parent_profile,
            first_name='Alice',
            date_of_birth=eight_years_ago
        )
        self.assertEqual(child_no_lastname.full_name, 'Alice')

    def test_display_name_property(self):
        """Test display_name property"""
        child = Child.objects.create(**self.valid_child_data)
        self.assertEqual(child.display_name, 'Johnny')  # Should use nickname

        # Child without nickname
        seven_years_ago = date(date.today().year - 7, date.today().month, date.today().day)
        child_no_nickname = Child.objects.create(
            parent=self.parent_profile,
            first_name='Alice',
            date_of_birth=seven_years_ago
        )
        self.assertEqual(child_no_nickname.display_name, 'Alice')  # Should use first_name

    def test_bmi_calculation(self):
        """Test BMI calculation property"""
        child = Child.objects.create(**self.valid_child_data)
        expected_bmi = round(35 / (1.4 ** 2), 1)  # weight_kg / (height_m^2)
        self.assertEqual(child.bmi, expected_bmi)

        # Child without height/weight
        eight_years_ago = date(date.today().year - 8, date.today().month, date.today().day)
        child_no_measurements = Child.objects.create(
            parent=self.parent_profile,
            first_name='NoMeasure',
            date_of_birth=eight_years_ago
        )
        self.assertIsNone(child_no_measurements.bmi)

    def test_vaccination_status_property(self):
        """Test vaccination status property"""
        eight_years_ago = date(date.today().year - 8, date.today().month, date.today().day)
        child = Child.objects.create(
            parent=self.parent_profile,
            first_name='Vax',
            date_of_birth=eight_years_ago,
            vaccination_status=True
        )
        self.assertTrue(child.is_vaccination_current)

        # Child with no vaccination status set
        child_no_vax = Child.objects.create(
            parent=self.parent_profile,
            first_name='NoVax',
            date_of_birth=eight_years_ago
        )
        self.assertFalse(child_no_vax.is_vaccination_current)  # Should default to False

    def test_psychology_history_property(self):
        """Test psychology history property"""
        child_with_history = Child.objects.create(
            parent=self.parent_profile,
            first_name='History',
            date_of_birth=date.today() - timedelta(days=365 * 8),
            has_seen_psychologist=True
        )
        self.assertTrue(child_with_history.has_psychology_history)

        child_with_therapy = Child.objects.create(
            parent=self.parent_profile,
            first_name='Therapy',
            date_of_birth=date.today() - timedelta(days=365 * 8),
            has_received_therapy=True
        )
        self.assertTrue(child_with_therapy.has_psychology_history)

        # Child with no history
        child_no_history = Child.objects.create(
            parent=self.parent_profile,
            first_name='NoHistory',
            date_of_birth=date.today() - timedelta(days=365 * 8)
        )
        self.assertFalse(child_no_history.has_psychology_history)

    def test_age_validation_too_young(self):
        """Test validation fails for children too young"""
        with self.assertRaises(ValidationError) as context:
            child = Child(
                parent=self.parent_profile,
                first_name='TooYoung',
                date_of_birth=date.today() - timedelta(days=365 * 3)  # 3 years old
            )
            child.full_clean()

        self.assertIn('Child must be at least 5 years old', str(context.exception))

    def test_age_validation_too_old(self):
        """Test validation fails for children too old"""
        with self.assertRaises(ValidationError) as context:
            child = Child(
                parent=self.parent_profile,
                first_name='TooOld',
                date_of_birth=date.today() - timedelta(days=365 * 20)  # 20 years old
            )
            child.full_clean()

        self.assertIn('Child must be 17 years old or younger', str(context.exception))

    def test_height_weight_validation(self):
        """Test height and weight validation"""
        # Invalid BMI combination
        with self.assertRaises(ValidationError) as context:
            child = Child(
                parent=self.parent_profile,
                first_name='InvalidBMI',
                date_of_birth=date.today() - timedelta(days=365 * 10),
                height_cm=150,
                weight_kg=5  # Very low weight for height
            )
            child.full_clean()

        self.assertIn('Height and weight combination seems unusual', str(context.exception))

    def test_height_validators(self):
        """Test height field validators"""
        # Height too low
        with self.assertRaises(ValidationError):
            child = Child(
                parent=self.parent_profile,
                first_name='ShortHeight',
                date_of_birth=date.today() - timedelta(days=365 * 10),
                height_cm=40
            )
            child.full_clean()

        # Height too high
        with self.assertRaises(ValidationError):
            child = Child(
                parent=self.parent_profile,
                first_name='TallHeight',
                date_of_birth=date.today() - timedelta(days=365 * 10),
                height_cm=300
            )
            child.full_clean()

    def test_weight_validators(self):
        """Test weight field validators"""
        # Weight too low
        with self.assertRaises(ValidationError):
            child = Child(
                parent=self.parent_profile,
                first_name='LowWeight',
                date_of_birth=date.today() - timedelta(days=365 * 10),
                weight_kg=5
            )
            child.full_clean()

        # Weight too high
        with self.assertRaises(ValidationError):
            child = Child(
                parent=self.parent_profile,
                first_name='HighWeight',
                date_of_birth=date.today() - timedelta(days=365 * 10),
                weight_kg=250
            )
            child.full_clean()

    def test_consent_management(self):
        """Test consent form management"""
        child = Child.objects.create(**self.valid_child_data)

        # Test setting consent
        child.set_consent('service_consent', True, 'Parent Signature', 'Initial consent')
        self.assertTrue(child.get_consent_status('service_consent'))

        # Test consent data structure
        consent_data = child.consent_forms_signed['service_consent']
        self.assertTrue(consent_data['granted'])
        self.assertEqual(consent_data['parent_signature'], 'Parent Signature')
        self.assertEqual(consent_data['notes'], 'Initial consent')
        self.assertIsNotNone(consent_data['date_signed'])

        # Test revoking consent
        child.set_consent('service_consent', False)
        self.assertFalse(child.get_consent_status('service_consent'))

    def test_consent_default_types(self):
        """Test default consent types"""
        default_types = Child.get_default_consent_types()
        expected_keys = [
            'service_consent', 'assessment_consent',
            'communication_consent', 'data_sharing_consent'
        ]
        for key in expected_keys:
            self.assertIn(key, default_types)

    def test_profile_completeness(self):
        """Test profile completeness calculation"""
        # Minimal child (only required fields)
        minimal_child = Child.objects.create(
            parent=self.parent_profile,
            first_name='Minimal',
            date_of_birth=date.today() - timedelta(days=365 * 8)
        )
        completeness = minimal_child.get_profile_completeness()
        self.assertEqual(completeness, 60.0)  # Only required fields completed

        # Complete child
        complete_child = Child.objects.create(**self.valid_child_data)
        completeness = complete_child.get_profile_completeness()
        self.assertGreater(completeness, 90.0)  # Should be nearly complete

    def test_age_appropriate_grade_suggestions(self):
        """Test grade suggestions based on age"""
        # Create a 10-year-old child (age 10 should suggest grades for 10-year-olds)
        ten_years_ago = date(date.today().year - 10, date.today().month, date.today().day - 1)
        child = Child.objects.create(
            parent=self.parent_profile,
            first_name='GradeTest',
            date_of_birth=ten_years_ago
        )

        suggestions = child.get_age_appropriate_grade_suggestions()
        # Age 10 should map to Grade 5, Year 5, Year 6 according to the model
        expected_suggestions = ['Grade 5', 'Year 5', 'Year 6']
        self.assertEqual(suggestions, expected_suggestions)
        self.assertIsInstance(suggestions, list)
        self.assertGreater(len(suggestions), 0)

    def test_model_ordering(self):
        """Test model ordering"""
        # Create multiple children
        Child.objects.create(
            parent=self.parent_profile,
            first_name='Zoe',
            last_name='Adams',
            date_of_birth=date.today() - timedelta(days=365 * 8)
        )
        Child.objects.create(
            parent=self.parent_profile,
            first_name='Alice',
            last_name='Brown',
            date_of_birth=date.today() - timedelta(days=365 * 9)
        )
        Child.objects.create(
            parent=self.parent_profile,
            first_name='Bob',
            last_name='Adams',
            date_of_birth=date.today() - timedelta(days=365 * 7)
        )

        children = list(Child.objects.all())
        # Should be ordered by first_name, then last_name
        self.assertEqual(children[0].first_name, 'Alice')
        self.assertEqual(children[1].first_name, 'Bob')
        self.assertEqual(children[2].first_name, 'Zoe')

    def test_parent_relationship(self):
        """Test parent relationship"""
        child = Child.objects.create(**self.valid_child_data)

        # Test forward relationship
        self.assertEqual(child.parent, self.parent_profile)

        # Test reverse relationship
        self.assertIn(child, self.parent_profile.children.all())

    def test_cascade_deletion(self):
        """Test that child is deleted when parent is deleted"""
        child = Child.objects.create(**self.valid_child_data)
        child_id = child.id

        # Delete parent user (should cascade to parent profile and then to child)
        self.parent_user.delete()

        # Child should no longer exist
        with self.assertRaises(Child.DoesNotExist):
            Child.objects.get(id=child_id)

    def test_json_field_initialization(self):
        """Test that JSON fields are properly initialized"""
        child = Child.objects.create(
            parent=self.parent_profile,
            first_name='JSONTest',
            date_of_birth=date.today() - timedelta(days=365 * 8)
        )

        # consent_forms_signed should be initialized as empty dict
        self.assertIsInstance(child.consent_forms_signed, dict)
        self.assertEqual(child.consent_forms_signed, {})

    def test_timestamps(self):
        """Test that timestamps are properly set"""
        child = Child.objects.create(**self.valid_child_data)

        self.assertIsNotNone(child.created_at)
        self.assertIsNotNone(child.updated_at)

        # Update child and check that updated_at changes
        original_updated_at = child.updated_at
        child.first_name = 'Updated'
        child.save()

        self.assertNotEqual(child.updated_at, original_updated_at)
        self.assertGreater(child.updated_at, original_updated_at)