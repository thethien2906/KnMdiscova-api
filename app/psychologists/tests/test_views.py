"""
Tests for psychologist views in the K&Mdiscova platform.
"""
import uuid
from datetime import date, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from psychologists.models import Psychologist, PsychologistAvailability
from psychologists.services import (
    AvailabilityConflictError,
    AvailabilityService,
    PsychologistNotFoundError,
    PsychologistRegistrationError,
    PsychologistService,
    VerificationError,
)

User = get_user_model()


class BasePsychologistTestCase(APITestCase):
    """Base class for shared setup and helper methods."""

    def setUp(self):
        self.client = self.client_class()
        self.unique_id = uuid.uuid4().hex
        self.psychologist_data = {
            "email": f"psychologist_{self.unique_id}@example.com",
            "password": "TestPassword123!",
            "password_confirm": "TestPassword123!",
            "first_name": "Jane",
            "last_name": "Smith",
            "license_number": f"PSY{self.unique_id[:6].upper()}",
            "license_issuing_authority": "State Board of Psychology",
            "license_expiry_date": (date.today() + timedelta(days=365)).isoformat(),
            "years_of_experience": 5,
            "biography": "Experienced child psychologist",
            "hourly_rate": 150.00,
            "education": [{"degree": "PhD", "institution": "University", "year": "2015"}],
            "certifications": [{"name": "Child Psychology", "institution": "APA", "year": "2016"}],
            "website_url": "https://example.com",
            "linkedin_url": "https://linkedin.com/in/jane",
        }
        self.parent_user = User.objects.create_user(
            email=f"parent_{uuid.uuid4()}@example.com",
            password="TestPassword123!",
            user_type="Parent",
        )
        self.admin_user = User.objects.create_user(
            email=f"admin_{uuid.uuid4()}@example.com",
            password="TestPassword123!",
            user_type="Admin",
            is_staff=True,
        )
        self.psychologist_user = User.objects.create_user(
            email=f"psychologist_user_{self.unique_id}@example.com",
            password="TestPassword123!",
            user_type="Psychologist",
        )
        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name="Jane",
            last_name="Smith",
            license_number=f"PSY_user_{self.unique_id[:6]}",
            license_issuing_authority="State Board",
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            biography="Experienced child psychologist",
            hourly_rate=Decimal("150.00"),
            verification_status="Approved",
        )

    def create_availability_slot(self, **kwargs):
        """Helper to create an availability slot."""
        defaults = {
            "psychologist": self.psychologist,
            "day_of_week": 1,
            "start_time": time(9, 0),
            "end_time": time(10, 0),
            "is_recurring": True,
        }
        defaults.update(kwargs)
        return PsychologistAvailability.objects.create(**defaults)


class PsychologistRegistrationViewTests(BasePsychologistTestCase):
    """Tests for POST /psychologists/register/."""

    def setUp(self):
        super().setUp()
        self.url = reverse("psychologists:register")

    @patch("psychologists.services.PsychologistService.register_psychologist")
    def test_successful_registration(self, mock_register):
        """Test successful psychologist registration."""
        mock_psychologist = self.psychologist
        mock_psychologist.user.email = self.psychologist_data["email"]
        mock_register.return_value = mock_psychologist
        response = self.client.post(self.url, self.psychologist_data, format="json")
        if response.status_code != status.HTTP_201_CREATED:
            print("Response data:", response.data)  # Debug output
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["email"], self.psychologist_data["email"])
        self.assertEqual(response.data["first_name"], self.psychologist_data["first_name"])
        self.assertEqual(Decimal(response.data["hourly_rate"]), Decimal("150.00"))
        mock_register.assert_called_once()

    def test_invalid_email(self):
        """Test registration with invalid email."""
        invalid_data = self.psychologist_data.copy()
        invalid_data["email"] = "invalid-email"
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_password_mismatch(self):
        """Test registration with mismatched passwords."""
        invalid_data = self.psychologist_data.copy()
        invalid_data["password_confirm"] = "DifferentPassword123!"
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password_confirm", response.data)

    @patch("psychologists.services.PsychologistService.register_psychologist")
    def test_service_error(self, mock_register):
        """Test registration with service error."""
        mock_register.side_effect = PsychologistRegistrationError("Duplicate license")
        response = self.client.post(self.url, self.psychologist_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
        self.assertEqual(response.data["error"], "Duplicate license")

    def test_missing_fields(self):
        """Test registration with missing required fields."""
        incomplete_data = {
            "email": f"psychologist_{uuid.uuid4()}@example.com",
            "password": "TestPassword123!",
        }
        response = self.client.post(self.url, incomplete_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("first_name", response.data)

    def test_duplicate_email(self):
        """Test registration with duplicate email."""
        User.objects.create_user(
            email=self.psychologist_data["email"],
            password="TestPassword123!",
            user_type="regular",
        )
        response = self.client.post(self.url, self.psychologist_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_expired_license_date(self):
        """Test registration with past license expiry date."""
        invalid_data = self.psychologist_data.copy()
        invalid_data["license_expiry_date"] = (date.today() - timedelta(days=1)).isoformat()
        response = self.client.post(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("license_expiry_date", response.data)


class PsychologistProfileViewTests(BasePsychologistTestCase):
    """Tests for GET/PATCH /psychologists/me/."""

    def setUp(self):
        super().setUp()
        self.url = reverse("psychologists:profile")
        self.client.force_authenticate(user=self.psychologist_user)

    @patch("psychologists.services.PsychologistService.get_psychologist_by_user_id")
    def test_get_profile(self, mock_get):
        """Test retrieving psychologist profile."""
        mock_get.return_value = self.psychologist
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["first_name"], "Jane")
        self.assertEqual(response.data["license_number"], self.psychologist.license_number)
        mock_get.assert_called_once_with(self.psychologist_user.id)

    @patch("psychologists.services.PsychologistService.get_psychologist_by_user_id")
    def test_get_profile_nonexistent(self, mock_get):
        """Test retrieving profile when not found."""
        mock_get.side_effect = PsychologistNotFoundError("Not found")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error", response.data)

    @patch("psychologists.services.PsychologistService.get_psychologist_by_user_id")
    @patch("psychologists.services.PsychologistService.update_psychologist_profile")
    def test_update_profile_success(self, mock_update, mock_get):
        """Test updating psychologist profile."""
        mock_get.return_value = self.psychologist
        updated_psychologist = self.psychologist
        updated_psychologist.first_name = "Jane"
        updated_psychologist.biography = "Updated biography"
        mock_update.return_value = updated_psychologist
        update_data = {"first_name": "Dr", "biography": "Updated biography"}
        response = self.client.patch(self.url, update_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["first_name"], "Jane")
        mock_update.assert_called_once()

    def test_update_profile_invalid(self):
        """Test updating profile with invalid data."""
        update_data = {"hourly_rate": -10}
        response = self.client.patch(self.url, update_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hourly_rate", response.data)

    def test_get_profile_unauthenticated(self):
        """Test profile access without authentication."""
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_profile_non_psychologist(self):
        """Test profile access by non-psychologist."""
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_invalid_education_format(self):
        """Test updating profile with invalid education format."""
        update_data = {"education": [{"degree": "PhD"}]}
        response = self.client.patch(self.url, update_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("education", response.data)


class PsychologistSearchViewTests(BasePsychologistTestCase):
    """Tests for GET /psychologists/search/."""

    def setUp(self):
        super().setUp()
        self.url = reverse("psychologists:search")
        self.client.force_authenticate(user=self.parent_user)
        self.psychologist2 = Psychologist.objects.create(
            user=User.objects.create_user(
                email=f"psych2_{self.unique_id}@example.com",
                password="TestPassword123!",
                user_type="Psychologist",
            ),
            first_name="Dr. Bob",
            last_name="Wilson",
            license_number=f"PSY2_{self.unique_id[:6]}",
            years_of_experience=3,
            hourly_rate=Decimal("120.00"),
            verification_status="Approved",
        )

    @patch("psychologists.services.PsychologistService.search_psychologists")
    def test_search_no_filters(self, mock_search):
        """Test searching psychologists without filters."""
        mock_search.return_value = {
            'psychologists': [self.psychologist, self.psychologist2],  # Changed from 'queryset'
            'total_count': 2,
            'search_params': {},
        }
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_count"], 2)
        self.assertEqual(len(response.data.get("psychologists", [])), 2)
        self.assertEqual(response.data["psychologists"][0]["display_name"], "Dr. Jane Smith")
        mock_search.assert_called_once()

    @patch("psychologists.services.PsychologistService.search_psychologists")
    def test_search_with_filters(self, mock_search):
        """Test searching with filters."""
        search_params = {"search": "Jane", "min_experience": 5, "max_rate": 200}
        mock_search.return_value = {
            "psychologists": [self.psychologist],
            "total_count": 1,
            "search_params": search_params,
        }
        response = self.client.get(self.url, search_params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_count"], 1)
        self.assertEqual(response.data["psychologists"][0]["display_name"], "Dr. Jane Smith")
        mock_search.assert_called_once()

    def test_search_invalid_params(self):
        """Test search with invalid parameters."""
        invalid_params = {"min_experience": "invalid"}
        response = self.client.get(self.url, invalid_params)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("min_experience", response.data)

    def test_search_unauthenticated(self):
        """Test search without authentication."""
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_search_non_parent(self):
        """Test search by non-parent user."""
        self.client.force_authenticate(user=self.psychologist_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_search_past_available_date(self):
        """Test search with past available_on date."""
        params = {"available_on": (date.today() - timedelta(days=1)).isoformat()}
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("available_on", response.data)


class PsychologistVerificationViewTests(BasePsychologistTestCase):
    """Tests for PATCH /psychologists/{psychologist_id}/verify/."""

    def setUp(self):
        super().setUp()
        self.psychologist.verification_status = "Pending"
        self.psychologist.save()
        self.url = reverse(
            "psychologists:verify", kwargs={"psychologist_id": str(self.psychologist_user.id)}
        )
        self.client.force_authenticate(user=self.admin_user)

    @patch("psychologists.services.PsychologistService.get_psychologist_by_user_id")
    @patch("psychologists.services.PsychologistService.verify_psychologist")
    def test_successful_verification(self, mock_verify, mock_get):
        """Test successful psychologist verification."""
        mock_get.return_value = self.psychologist
        updated_psychologist = self.psychologist
        updated_psychologist.verification_status = "Approved"
        mock_verify.return_value = updated_psychologist
        verification_data = {"verification_status": "Approved", "admin_notes": "All documents verified"}
        response = self.client.patch(self.url, verification_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["verification_status"], "Approved")
        mock_verify.assert_called_once()

    def test_invalid_verification_data(self):
        """Test verification with invalid data."""
        invalid_data = {"verification_status": "Rejected", "admin_notes": ""}
        response = self.client.patch(self.url, invalid_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("admin_notes", response.data)

    @patch("psychologists.services.PsychologistService.get_psychologist_by_user_id")
    @patch("psychologists.services.PsychologistService.verify_psychologist")
    def test_service_error(self, mock_verify, mock_get):
        """Test verification with service error."""
        mock_get.return_value = self.psychologist
        mock_verify.side_effect = VerificationError("Expired license")
        verification_data = {"verification_status": "Approved"}
        response = self.client.patch(self.url, verification_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_unauthenticated_access(self):
        """Test verification without authentication."""
        self.client.force_authenticate(user=None)
        response = self.client.patch(self.url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_admin_access(self):
        """Test verification by non-admin."""
        self.client.force_authenticate(user=self.psychologist_user)
        response = self.client.patch(
            self.url, {"verification_status": "Approved"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AvailabilityViewTests(BasePsychologistTestCase):
    """Tests for availability endpoints (create, list, bulk, detail)."""

    def setUp(self):
        super().setUp()
        self.create_url = reverse("psychologists:availability-create")
        self.list_url = reverse("psychologists:availability-list")
        self.bulk_url = reverse("psychologists:availability-bulk")
        self.client.force_authenticate(user=self.psychologist_user)
        self.slot = self.create_availability_slot()
        self.detail_url = reverse(
            "psychologists:availability-detail", kwargs={"availability_id": self.slot.id}
        )

    @patch("psychologists.services.PsychologistService.get_psychologist_by_user_id")
    @patch("psychologists.services.AvailabilityService.create_availability_slot")
    def test_create_availability_success(self, mock_create, mock_get):
        """Test creating an availability slot."""
        mock_get.return_value = self.psychologist
        mock_create.return_value = self.slot
        slot_data = {
            "day_of_week": 1,
            "start_time": "09:00",
            "end_time": "10:00",
            "is_recurring": True,
        }
        response = self.client.post(self.create_url, slot_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["day_of_week"], 1)
        mock_create.assert_called_once()

    def test_create_availability_invalid_data(self):
        """Test creating slot with invalid data."""
        slot_data = {
            "day_of_week": 1,
            "start_time": "10:00",
            "end_time": "09:00",
            "is_recurring": True,
        }
        response = self.client.post(self.create_url, slot_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("end_time", response.data)

    @patch("psychologists.services.PsychologistService.get_psychologist_by_user_id")
    @patch("psychologists.services.AvailabilityService.create_availability_slot")
    def test_create_availability_conflict(self, mock_create, mock_get):
        """Test creating slot with conflict."""
        mock_get.return_value = self.psychologist
        mock_create.side_effect = AvailabilityConflictError("Time slot conflicts")
        slot_data = {
            "day_of_week": 1,
            "start_time": "09:00",
            "end_time": "10:00",
            "is_recurring": True,
        }
        response = self.client.post(self.create_url, slot_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    @patch("psychologists.services.PsychologistService.get_psychologist_by_user_id")
    @patch("psychologists.services.AvailabilityService.get_psychologist_availability")
    def test_list_availability_success(self, mock_list, mock_get):
        """Test listing availability slots."""
        mock_get.return_value = self.psychologist
        mock_list.return_value = [self.slot]
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["day_of_week"], 1)
        mock_list.assert_called_once()

    @patch("psychologists.services.PsychologistService.get_psychologist_by_user_id")
    @patch("psychologists.services.AvailabilityService.bulk_manage_availability")
    def test_bulk_create_availability(self, mock_bulk, mock_get):
        """Test bulk creating availability slots."""
        mock_get.return_value = self.psychologist
        mock_bulk.return_value = {
            "operation": "create",
            "successful": [{"id": 1, "day_of_week": 1}],
            "failed": [],
            "total_processed": 1,
        }
        bulk_data = {
            "operation": "create",
            "availability_slots": [
                {"day_of_week": 1, "start_time": "09:00", "end_time": "10:00", "is_recurring": True}
            ],
        }
        response = self.client.post(self.bulk_url, bulk_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["successful"]), 1)
        mock_bulk.assert_called_once()

    @patch("psychologists.services.PsychologistService.get_psychologist_by_user_id")
    @patch("psychologists.services.AvailabilityService.bulk_manage_availability")
    def test_bulk_delete_availability(self, mock_bulk, mock_get):
        """Test bulk deleting availability slots."""
        mock_get.return_value = self.psychologist
        mock_bulk.return_value = {
            "operation": "delete",
            "successful": [{"id": self.slot.id}],
            "failed": [],
            "total_processed": 1,
        }
        bulk_data = {"operation": "delete", "slot_ids": [self.slot.id]}
        response = self.client.post(self.bulk_url, bulk_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["successful"]), 1)
        mock_bulk.assert_called_once()

    @patch("psychologists.services.AvailabilityService.update_availability_slot")
    def test_update_availability_success(self, mock_update):
        """Test updating an availability slot."""
        updated_slot = self.slot
        updated_slot.start_time = time(10, 0)
        updated_slot.end_time = time(11, 0)
        mock_update.return_value = updated_slot
        update_data = {"start_time": "10:00", "end_time": "11:00"}
        response = self.client.patch(self.detail_url, update_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["start_time"], "10:00:00")
        mock_update.assert_called_once()

    def test_update_availability_invalid_data(self):
        """Test updating slot with invalid data."""
        update_data = {"start_time": "11:00", "end_time": "10:00"}
        response = self.client.patch(self.detail_url, update_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("end_time", response.data)

    @patch("psychologists.services.AvailabilityService.update_availability_slot")
    def test_update_availability_conflict(self, mock_update):
        """Test updating a conflicting slot."""
        mock_update.side_effect = AvailabilityConflictError("Cannot modify booked slot")
        update_data = {"start_time": "10:00"}
        response = self.client.patch(self.detail_url, update_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    @patch("psychologists.services.AvailabilityService.delete_availability_slot")
    def test_delete_availability_success(self, mock_delete):
        """Test deleting an availability slot."""
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        mock_delete.assert_called_once()

    @patch("psychologists.services.AvailabilityService.delete_availability_slot")
    def test_delete_availability_conflict(self, mock_delete):
        """Test deleting a conflicting slot."""
        mock_delete.side_effect = AvailabilityConflictError("Cannot delete booked slot")
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_access_other_psychologist_slot(self):
        """Test accessing another psychologist's slot."""
        other_user = User.objects.create_user(
            email=f"other_{uuid.uuid4()}@example.com",
            password="TestPassword123!",
            user_type="Psychologist",
        )
        self.client.force_authenticate(user=other_user)
        response = self.client.patch(self.detail_url, {"start_time": "10:00"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_availability_unauthenticated(self):
        """Test availability access without authentication."""
        self.client.force_authenticate(user=None)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_availability_non_psychologist(self):
        """Test availability access by non-psychologist."""
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("psychologists.services.PsychologistService.get_psychologist_by_user_id")
    @patch("psychologists.services.AvailabilityService.bulk_manage_availability")
    def test_bulk_update_availability(self, mock_bulk, mock_get):
        """Test bulk updating availability slots."""
        mock_get.return_value = self.psychologist
        mock_bulk.return_value = {
            "operation": "update",
            "successful": [{"id": self.slot.id, "start_time": "10:00"}],
            "failed": [],
            "total_processed": 1,
        }
        bulk_data = {
            "operation": "update",
            "availability_slots": [
                {"id": self.slot.id, "start_time": "10:00", "end_time": "11:00", "is_recurring": True}
            ],
        }
        response = self.client.post(self.bulk_url, bulk_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["successful"]), 1)
        mock_bulk.assert_called_once()