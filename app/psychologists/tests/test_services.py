# psychologists/tests/test_services.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from unittest.mock import patch, Mock
from datetime import date, time, timedelta, datetime
import uuid

from psychologists.services import (
	PsychologistService,
	AvailabilityService,
	PsychologistRegistrationError,
	PsychologistNotFoundError,
	AvailabilityConflictError,
	VerificationError
)
from psychologists.models import Psychologist, PsychologistAvailability
from users.services import UserService

User = get_user_model()


class PsychologistServiceTestCase(TestCase):
	"""Test cases for PsychologistService"""

	def setUp(self):
		"""Set up test data"""
		self.valid_registration_data = {
			'email': 'test.psychologist@example.com',
			'password': 'SecurePassword123!',
			'password_confirm': 'SecurePassword123!',
			'first_name': 'Jane',
			'last_name': 'Smith',
			'license_number': 'PSY123456',
			'license_issuing_authority': 'State Psychology Board',
			'license_expiry_date': date.today() + timedelta(days=365),
			'years_of_experience': 5,
			'biography': 'Experienced child psychologist',
			'hourly_rate': 150.00
		}

		# Create a test psychologist for update tests
		self.test_user = User.objects.create_user(
			email='existing@example.com',
			password='TestPassword123!',
			user_type='Psychologist'
		)
		self.test_psychologist = Psychologist.objects.create(
			user=self.test_user,
			first_name='John',
			last_name='Doe',
			license_number='PSY654321',
			license_issuing_authority='Test Board',
			license_expiry_date=date.today() + timedelta(days=180),
			years_of_experience=3,
			hourly_rate=120.00,
			verification_status='Pending'
		)

	def test_register_psychologist_success(self):
		"""Test successful psychologist registration"""
		# Create a real user instance (saved in the DB)
		real_user = User.objects.create(
		email=self.valid_registration_data['email'],
		user_type='Psychologist',
		is_verified=True,  # or other required fields
		)
		real_user.set_password(self.valid_registration_data['password'])
		real_user.save()

		with patch.object(UserService, 'create_user', return_value=real_user) as mock_create_user:
			psychologist = PsychologistService.register_psychologist(
				self.valid_registration_data.copy()
			)

			# Verify user creation was called correctly
			mock_create_user.assert_called_once_with(
				email=self.valid_registration_data['email'],
				password=self.valid_registration_data['password'],
				user_type='Psychologist'
			)

			# Verify psychologist was created
			self.assertIsInstance(psychologist, Psychologist)
			self.assertEqual(psychologist.first_name, 'Jane')
			self.assertEqual(psychologist.license_number, 'PSY123456')



	def test_register_psychologist_duplicate_license(self):
		"""Test registration with duplicate license number"""
		# Create existing psychologist with same license
		existing_user = User.objects.create_user(
			email='existing2@example.com',
			password='TestPassword123!',
			user_type='Psychologist'
		)
		Psychologist.objects.create(
			user=existing_user,
			first_name='Existing',
			last_name='User',
			license_number='PSY123456',  # Same as in valid_registration_data
			license_issuing_authority='Test Board',
			years_of_experience=2,
			hourly_rate=100.00
		)

		with self.assertRaises(PsychologistRegistrationError):
			PsychologistService.register_psychologist(
				self.valid_registration_data.copy()
			)

	def test_register_psychologist_user_creation_failure(self):
		"""Test registration when user creation fails"""
		with patch.object(UserService, 'create_user') as mock_create_user:
			mock_create_user.side_effect = Exception("User creation failed")

			with self.assertRaises(PsychologistRegistrationError) as context:
				PsychologistService.register_psychologist(
					self.valid_registration_data.copy()
				)

			self.assertIn("Registration failed", str(context.exception))

	def test_get_psychologist_by_user_id_success(self):
		"""Test successful retrieval by user ID"""
		psychologist = PsychologistService.get_psychologist_by_user_id(
			str(self.test_user.id)
		)

		self.assertEqual(psychologist, self.test_psychologist)
		self.assertEqual(psychologist.first_name, 'John')

	def test_get_psychologist_by_user_id_not_found(self):
		"""Test retrieval with non-existent user ID"""
		non_existent_id = str(uuid.uuid4())

		with self.assertRaises(PsychologistNotFoundError) as context:
			PsychologistService.get_psychologist_by_user_id(non_existent_id)

		self.assertIn(non_existent_id, str(context.exception))

	def test_get_psychologist_by_license_success(self):
		"""Test successful retrieval by license number"""
		psychologist = PsychologistService.get_psychologist_by_license('PSY654321')

		self.assertEqual(psychologist, self.test_psychologist)
		self.assertEqual(psychologist.license_number, 'PSY654321')

	def test_get_psychologist_by_license_not_found(self):
		"""Test retrieval with non-existent license"""
		with self.assertRaises(PsychologistNotFoundError) as context:
			PsychologistService.get_psychologist_by_license('NONEXISTENT')

		self.assertIn('NONEXISTENT', str(context.exception))

	def test_update_psychologist_profile_basic_fields(self):
		"""Test updating basic profile fields"""
		update_data = {
			'first_name': 'UpdatedJohn',
			'biography': 'Updated biography',
			'hourly_rate': 130.00
		}

		updated_psychologist = PsychologistService.update_psychologist_profile(
			self.test_psychologist, update_data
		)

		self.assertEqual(updated_psychologist.first_name, 'UpdatedJohn')
		self.assertEqual(updated_psychologist.biography, 'Updated biography')
		self.assertEqual(updated_psychologist.hourly_rate, 130.00)

	def test_update_psychologist_profile_restricted_fields_pending(self):
		"""Test updating restricted fields when status is Pending"""
		update_data = {
			'license_number': 'PSY999999',
			'license_issuing_authority': 'New Authority'
		}

		updated_psychologist = PsychologistService.update_psychologist_profile(
			self.test_psychologist, update_data
		)

		self.assertEqual(updated_psychologist.license_number, 'PSY999999')
		self.assertEqual(updated_psychologist.verification_status, 'Pending')

	def test_update_psychologist_profile_restricted_fields_approved(self):
		"""Test updating restricted fields when status is Approved triggers re-verification"""
		self.test_psychologist.verification_status = 'Approved'
		self.test_psychologist.save()

		update_data = {
			'license_number': 'PSY999999',
			'license_issuing_authority': 'New Authority'
		}

		updated_psychologist = PsychologistService.update_psychologist_profile(
			self.test_psychologist, update_data
		)

		self.assertEqual(updated_psychologist.license_number, 'PSY999999')
		self.assertEqual(updated_psychologist.verification_status, 'Pending')

	def test_search_psychologists_basic(self):
		"""Test basic psychologist search"""
		# Create approved psychologist
		approved_user = User.objects.create_user(
			email='approved@example.com',
			password='TestPassword123!',
			user_type='Psychologist'
		)
		approved_psychologist = Psychologist.objects.create(
			user=approved_user,
			first_name='Approved',
			last_name='Psychologist',
			license_number='PSY111111',
			license_issuing_authority='Test Board',
			years_of_experience=10,
			hourly_rate=200.00,
			verification_status='Approved'
		)

		search_params = {}
		result = PsychologistService.search_psychologists(search_params)

		self.assertIn('queryset', result)
		self.assertIn('total_count', result)
		self.assertEqual(result['total_count'], 1)  # Only approved psychologist

	def test_search_psychologists_with_text_search(self):
		"""Test psychologist search with text query"""
		# Create approved psychologist with specific name
		approved_user = User.objects.create_user(
			email='specialist@example.com',
			password='TestPassword123!',
			user_type='Psychologist'
		)
		Psychologist.objects.create(
			user=approved_user,
			first_name='Child',
			last_name='Specialist',
			license_number='PSY222222',
			license_issuing_authority='Test Board',
			years_of_experience=8,
			hourly_rate=180.00,
			verification_status='Approved',
			biography='Specializes in child development'
		)

		search_params = {'search': 'Child'}
		result = PsychologistService.search_psychologists(search_params)

		self.assertEqual(result['total_count'], 1)

	def test_search_psychologists_with_experience_filter(self):
		"""Test psychologist search with experience filters"""
		# Create multiple approved psychologists
		for i, exp in enumerate([5, 10, 15]):
			user = User.objects.create_user(
				email=f'exp{i}@example.com',
				password='TestPassword123!',
				user_type='Psychologist'
			)
			Psychologist.objects.create(
				user=user,
				first_name=f'Psychologist{i}',
				last_name='Test',
				license_number=f'PSY{i}0000',
				license_issuing_authority='Test Board',
				years_of_experience=exp,
				hourly_rate=150.00,
				verification_status='Approved'
			)

		search_params = {'min_experience': 8, 'max_experience': 12}
		result = PsychologistService.search_psychologists(search_params)

		self.assertEqual(result['total_count'], 1)  # Only 10 years experience

	def test_verify_psychologist_approve(self):
		"""Test approving a psychologist"""
		verification_data = {
			'verification_status': 'Approved',
			'admin_notes': 'All documents verified'
		}

		verified_psychologist = PsychologistService.verify_psychologist(
			self.test_psychologist, verification_data
		)

		self.assertEqual(verified_psychologist.verification_status, 'Approved')
		self.assertEqual(verified_psychologist.admin_notes, 'All documents verified')

	def test_verify_psychologist_reject_without_notes(self):
		"""Test rejecting psychologist without admin notes raises error"""
		verification_data = {
			'verification_status': 'Rejected',
			'admin_notes': ''
		}

		with self.assertRaises(VerificationError) as context:
			PsychologistService.verify_psychologist(
				self.test_psychologist, verification_data
			)

		self.assertIn('Admin notes are required', str(context.exception))

	def test_verify_psychologist_approve_with_expired_license(self):
		"""Test approving psychologist with expired license"""
		self.test_psychologist.license_expiry_date = date.today() - timedelta(days=1)
		self.test_psychologist.save()

		verification_data = {
			'verification_status': 'Approved',
			'admin_notes': 'Approval attempt'
		}

		with self.assertRaises(VerificationError) as context:
			PsychologistService.verify_psychologist(
				self.test_psychologist, verification_data
			)

		self.assertIn('expired license', str(context.exception))

	def test_verify_psychologist_approved_to_pending_forbidden(self):
		"""Test that approved psychologist cannot be changed back to pending"""
		self.test_psychologist.verification_status = 'Approved'
		self.test_psychologist.save()

		verification_data = {
			'verification_status': 'Pending',
			'admin_notes': 'Reverting status'
		}

		with self.assertRaises(VerificationError) as context:
			PsychologistService.verify_psychologist(
				self.test_psychologist, verification_data
			)

		self.assertIn('Cannot change status from Approved back to Pending', str(context.exception))


class AvailabilityServiceTestCase(TestCase):
	"""Test cases for AvailabilityService"""

	def setUp(self):
		"""Set up test data"""
		self.user = User.objects.create_user(
			email='psychologist@example.com',
			password='TestPassword123!',
			user_type='Psychologist'
		)
		self.psychologist = Psychologist.objects.create(
			user=self.user,
			first_name='Test',
			last_name='Psychologist',
			license_number='PSY123456',
			license_issuing_authority='Test Board',
			years_of_experience=5,
			hourly_rate=150.00
		)

		self.valid_slot_data = {
			'day_of_week': 1,  # Monday
			'start_time': time(9, 0),
			'end_time': time(10, 0),
			'is_recurring': True
		}

	def test_create_availability_slot_success(self):
		"""Test successful creation of availability slot"""
		slot = AvailabilityService.create_availability_slot(
			self.psychologist, self.valid_slot_data
		)

		self.assertIsInstance(slot, PsychologistAvailability)
		self.assertEqual(slot.psychologist, self.psychologist)
		self.assertEqual(slot.day_of_week, 1)
		self.assertEqual(slot.start_time, time(9, 0))
		self.assertEqual(slot.end_time, time(10, 0))
		self.assertTrue(slot.is_recurring)

	def test_create_availability_slot_conflict(self):
		"""Test creating conflicting availability slot"""
		# Create first slot
		PsychologistAvailability.objects.create(
			psychologist=self.psychologist,
			day_of_week=1,
			start_time=time(9, 30),
			end_time=time(10, 30),
			is_recurring=True
		)

		# Try to create overlapping slot
		conflicting_data = {
			'day_of_week': 1,
			'start_time': time(9, 0),
			'end_time': time(10, 0),
			'is_recurring': True
		}

		with self.assertRaises(AvailabilityConflictError) as context:
			AvailabilityService.create_availability_slot(
				self.psychologist, conflicting_data
			)

		self.assertIn('conflicts with existing availability', str(context.exception))

	def test_create_specific_date_availability(self):
		"""Test creating specific date availability"""
		specific_date_data = {
			'specific_date': date.today() + timedelta(days=7),
			'start_time': time(14, 0),
			'end_time': time(15, 0),
			'is_recurring': False
		}

		slot = AvailabilityService.create_availability_slot(
			self.psychologist, specific_date_data
		)

		self.assertFalse(slot.is_recurring)
		self.assertEqual(slot.specific_date, date.today() + timedelta(days=7))

	def test_update_availability_slot_success(self):
		"""Test successful update of availability slot"""
		slot = PsychologistAvailability.objects.create(
			psychologist=self.psychologist,
			day_of_week=1,
			start_time=time(9, 0),
			end_time=time(10, 0),
			is_recurring=True
		)

		update_data = {
			'start_time': time(10, 0),
			'end_time': time(11, 0)
		}

		updated_slot = AvailabilityService.update_availability_slot(
			slot, update_data
		)

		self.assertEqual(updated_slot.start_time, time(10, 0))
		self.assertEqual(updated_slot.end_time, time(11, 0))

	def test_update_booked_availability_slot(self):
		"""Test updating booked availability slot raises error"""
		slot = PsychologistAvailability.objects.create(
			psychologist=self.psychologist,
			day_of_week=1,
			start_time=time(9, 0),
			end_time=time(10, 0),
			is_recurring=True,
			is_booked=True
		)

		update_data = {'start_time': time(10, 0)}

		with self.assertRaises(AvailabilityConflictError) as context:
			AvailabilityService.update_availability_slot(slot, update_data)

		self.assertIn('Cannot modify booked availability slot', str(context.exception))

	def test_update_availability_slot_creates_conflict(self):
		"""Test updating slot to create conflict"""
		# Create two slots
		slot1 = PsychologistAvailability.objects.create(
			psychologist=self.psychologist,
			day_of_week=1,
			start_time=time(9, 0),
			end_time=time(10, 0),
			is_recurring=True
		)

		PsychologistAvailability.objects.create(
			psychologist=self.psychologist,
			day_of_week=1,
			start_time=time(11, 0),
			end_time=time(12, 0),
			is_recurring=True
		)

		# Try to update first slot to overlap with second
		update_data = {
			'start_time': time(10, 30),
			'end_time': time(11, 30)
		}

		with self.assertRaises(AvailabilityConflictError):
			AvailabilityService.update_availability_slot(slot1, update_data)

	def test_delete_availability_slot_success(self):
		"""Test successful deletion of availability slot"""
		slot = PsychologistAvailability.objects.create(
			psychologist=self.psychologist,
			day_of_week=1,
			start_time=time(9, 0),
			end_time=time(10, 0),
			is_recurring=True
		)

		slot_id = slot.id
		AvailabilityService.delete_availability_slot(slot)

		with self.assertRaises(PsychologistAvailability.DoesNotExist):
			PsychologistAvailability.objects.get(id=slot_id)

	def test_delete_booked_availability_slot(self):
		"""Test deleting booked availability slot raises error"""
		slot = PsychologistAvailability.objects.create(
			psychologist=self.psychologist,
			day_of_week=1,
			start_time=time(9, 0),
			end_time=time(10, 0),
			is_recurring=True,
			is_booked=True
		)

		with self.assertRaises(AvailabilityConflictError) as context:
			AvailabilityService.delete_availability_slot(slot)

		self.assertIn('Cannot delete booked availability slot', str(context.exception))

	def test_bulk_create_availability(self):
		"""Test bulk creation of availability slots"""
		bulk_data = {
			'operation': 'create',
			'availability_slots': [
				{
					'day_of_week': 1,
					'start_time': time(9, 0),
					'end_time': time(10, 0),
					'is_recurring': True
				},
				{
					'day_of_week': 2,
					'start_time': time(9, 0),
					'end_time': time(10, 0),
					'is_recurring': True
				}
			]
		}

		results = AvailabilityService.bulk_manage_availability(
			self.psychologist, bulk_data
		)

		self.assertEqual(results['operation'], 'create')
		self.assertEqual(len(results['successful']), 2)
		self.assertEqual(len(results['failed']), 0)
		self.assertEqual(results['total_processed'], 2)

	def test_bulk_create_with_conflicts(self):
		"""Test bulk creation with some conflicts"""
		# Create existing slot
		PsychologistAvailability.objects.create(
			psychologist=self.psychologist,
			day_of_week=1,
			start_time=time(9, 0),
			end_time=time(10, 0),
			is_recurring=True
		)

		bulk_data = {
			'operation': 'create',
			'availability_slots': [
				{
					'day_of_week': 1,  # This will conflict
					'start_time': time(9, 30),
					'end_time': time(10, 30),
					'is_recurring': True
				},
				{
					'day_of_week': 2,  # This should succeed
					'start_time': time(9, 0),
					'end_time': time(10, 0),
					'is_recurring': True
				}
			]
		}

		results = AvailabilityService.bulk_manage_availability(
			self.psychologist, bulk_data
		)

		self.assertEqual(len(results['successful']), 1)
		self.assertEqual(len(results['failed']), 1)
		self.assertEqual(results['total_processed'], 2)

	def test_bulk_update_availability(self):
		"""Test bulk update of availability slots"""
		slot1 = PsychologistAvailability.objects.create(
			psychologist=self.psychologist,
			day_of_week=1,
			start_time=time(9, 0),
			end_time=time(10, 0),
			is_recurring=True
		)

		slot2 = PsychologistAvailability.objects.create(
			psychologist=self.psychologist,
			day_of_week=2,
			start_time=time(9, 0),
			end_time=time(10, 0),
			is_recurring=True
		)

		bulk_data = {
			'operation': 'update',
			'availability_slots': [
				{
					'id': slot1.id,
					'start_time': time(10, 0),
					'end_time': time(11, 0)
				},
				{
					'id': slot2.id,
					'start_time': time(11, 0),
					'end_time': time(12, 0)
				}
			]
		}

		results = AvailabilityService.bulk_manage_availability(
			self.psychologist, bulk_data
		)

		self.assertEqual(len(results['successful']), 2)
		self.assertEqual(len(results['failed']), 0)

		# Verify updates
		slot1.refresh_from_db()
		slot2.refresh_from_db()
		self.assertEqual(slot1.start_time, time(10, 0))
		self.assertEqual(slot2.start_time, time(11, 0))

	def test_bulk_delete_availability(self):
		"""Test bulk deletion of availability slots"""
		slot1 = PsychologistAvailability.objects.create(
			psychologist=self.psychologist,
			day_of_week=1,
			start_time=time(9, 0),
			end_time=time(10, 0),
			is_recurring=True
		)

		slot2 = PsychologistAvailability.objects.create(
			psychologist=self.psychologist,
			day_of_week=2,
			start_time=time(9, 0),
			end_time=time(10, 0),
			is_recurring=True
		)

		bulk_data = {
			'operation': 'delete',
			'slot_ids': [slot1.id, slot2.id]
		}

		results = AvailabilityService.bulk_manage_availability(
			self.psychologist, bulk_data
		)

		self.assertEqual(len(results['successful']), 2)
		self.assertEqual(len(results['failed']), 0)

		# Verify deletions
		self.assertEqual(PsychologistAvailability.objects.filter(
			psychologist=self.psychologist
		).count(), 0)

	def test_get_psychologist_availability_no_date_range(self):
		"""Test getting all psychologist availability"""
		# Create various availability slots
		PsychologistAvailability.objects.create(
			psychologist=self.psychologist,
			day_of_week=1,
			start_time=time(9, 0),
			end_time=time(10, 0),
			is_recurring=True
		)

		PsychologistAvailability.objects.create(
			psychologist=self.psychologist,
			specific_date=date.today() + timedelta(days=7),
			start_time=time(14, 0),
			end_time=time(15, 0),
			is_recurring=False
		)

		availability = AvailabilityService.get_psychologist_availability(
			self.psychologist
		)

		self.assertEqual(availability.count(), 2)

	def test_get_psychologist_availability_with_date_range(self):
		"""Test getting psychologist availability within date range"""
		today = date.today()

		# Create slots: one within range, one outside
		PsychologistAvailability.objects.create(
			psychologist=self.psychologist,
			specific_date=today + timedelta(days=7),  # Within range
			start_time=time(14, 0),
			end_time=time(15, 0),
			is_recurring=False
		)

		PsychologistAvailability.objects.create(
			psychologist=self.psychologist,
			specific_date=today + timedelta(days=30),  # Outside range
			start_time=time(14, 0),
			end_time=time(15, 0),
			is_recurring=False
		)

		# Create recurring slot (should always be included)
		PsychologistAvailability.objects.create(
			psychologist=self.psychologist,
			day_of_week=1,
			start_time=time(9, 0),
			end_time=time(10, 0),
			is_recurring=True
		)

		date_range = (today, today + timedelta(days=14))
		availability = AvailabilityService.get_psychologist_availability(
			self.psychologist, date_range
		)

		self.assertEqual(availability.count(), 2)  # Recurring + within range specific

	def test_check_conflicts_recurring_overlap(self):
		"""Test conflict detection for recurring slots"""
		# Create existing slot
		PsychologistAvailability.objects.create(
			psychologist=self.psychologist,
			day_of_week=1,
			start_time=time(9, 0),
			end_time=time(10, 0),
			is_recurring=True
		)

		# Check for conflict with overlapping slot
		slot_data = {
			'day_of_week': 1,
			'start_time': time(9, 30),
			'end_time': time(10, 30),
			'is_recurring': True
		}

		conflicts = AvailabilityService._check_conflicts(
			self.psychologist, slot_data
		)

		self.assertTrue(conflicts.exists())

	def test_check_conflicts_specific_date_overlap(self):
		"""Test conflict detection for specific date slots"""
		test_date = date.today() + timedelta(days=7)

		# Create existing slot
		PsychologistAvailability.objects.create(
			psychologist=self.psychologist,
			specific_date=test_date,
			start_time=time(14, 0),
			end_time=time(15, 0),
			is_recurring=False
		)

		# Check for conflict with overlapping slot
		slot_data = {
			'specific_date': test_date,
			'start_time': time(14, 30),
			'end_time': time(15, 30),
			'is_recurring': False
		}

		conflicts = AvailabilityService._check_conflicts(
			self.psychologist, slot_data
		)

		self.assertTrue(conflicts.exists())

	def test_check_conflicts_no_overlap(self):
		"""Test no conflict detection when slots don't overlap"""
		# Create existing slot
		PsychologistAvailability.objects.create(
			psychologist=self.psychologist,
			day_of_week=1,
			start_time=time(9, 0),
			end_time=time(10, 0),
			is_recurring=True
		)

		# Check for conflict with non-overlapping slot
		slot_data = {
			'day_of_week': 1,
			'start_time': time(11, 0),
			'end_time': time(12, 0),
			'is_recurring': True
		}

		conflicts = AvailabilityService._check_conflicts(
			self.psychologist, slot_data
		)

		self.assertFalse(conflicts.exists())

	def test_check_conflicts_exclude_slot(self):
		"""Test conflict detection excluding specific slot"""
		slot = PsychologistAvailability.objects.create(
			psychologist=self.psychologist,
			day_of_week=1,
			start_time=time(9, 0),
			end_time=time(10, 0),
			is_recurring=True
		)

		# Check for conflict with same slot data but exclude the existing slot
		slot_data = {
			'day_of_week': 1,
			'start_time': time(9, 0),
			'end_time': time(10, 0),
			'is_recurring': True
		}

		conflicts = AvailabilityService._check_conflicts(
			self.psychologist,
			slot_data,
			exclude_slot_id=slot.id
		)

		# Should not find conflicts when excluding the same slot
		self.assertFalse(conflicts)

		# Create another overlapping slot
		overlapping_slot = PsychologistAvailability.objects.create(
			psychologist=self.psychologist,
			day_of_week=1,
			start_time=time(9, 30),
			end_time=time(10, 30),
			is_recurring=True
		)

		# Now check conflicts excluding only the first slot
		conflicts = AvailabilityService._check_conflicts(
			self.psychologist,
			slot_data,
			exclude_slot_id=slot.id
		)

		# Should find conflict with the overlapping slot
		self.assertTrue(conflicts)
		self.assertEqual(len(conflicts), 1)
		self.assertEqual(conflicts[0].id, overlapping_slot.id)