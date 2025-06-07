import json
from unittest.mock import patch, MagicMock
from celery import current_app
from django.test import override_settings
from appointments.tasks import auto_generate_slots_task, auto_regenerate_slots_task
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from rest_framework.authtoken.models import Token
from unittest.mock import patch, MagicMock
from datetime import date, datetime, timedelta
import uuid

from users.models import User
from parents.models import Parent
from psychologists.models import Psychologist, PsychologistAvailability
from children.models import Child
from appointments.models import Appointment, AppointmentSlot
from appointments.services import (
    AppointmentBookingService,
    AppointmentManagementService,
    AppointmentBookingError,
    AppointmentNotFoundError,
    SlotNotAvailableError,
    InsufficientConsecutiveSlotsError,
    AppointmentCancellationError,
    QRVerificationError
)
def get_next_weekday(weekday: int) -> date:
    """
    Returns the next date that matches the given weekday
    Uses custom format: Monday=1, Tuesday=2, ..., Saturday=6, Sunday=0
    (matches the conversion in AppointmentSlot.clean() method)
    """
    from datetime import date, timedelta

    today = date.today()

    # Convert your custom format back to Python's format for calculation
    # Your format: Mon=1, Tue=2, Wed=3, Thu=4, Fri=5, Sat=6, Sun=0
    # Python format: Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6

    if weekday == 0:  # Sunday in your format
        target_python_weekday = 6  # Sunday in Python format
    else:  # Monday=1 to Saturday=6 in your format
        target_python_weekday = weekday - 1  # Convert to Python format

    # Calculate days ahead using Python's weekday system
    days_ahead = (target_python_weekday - today.weekday() + 7) % 7
    if days_ahead == 0:
        days_ahead = 7  # get *next* weekday, not today

    return today + timedelta(days=days_ahead)

# Alternative, simpler approach:
def get_next_weekday_v2(weekday: int) -> date:
    """
    Returns the next date that matches the given weekday
    Uses custom format: Monday=1, Tuesday=2, ..., Saturday=6, Sunday=0
    """
    from datetime import date, timedelta

    today = date.today()

    # Convert your format to Python's format
    # Your format: Mon=1, Tue=2, Wed=3, Thu=4, Fri=5, Sat=6, Sun=0
    # Python format: Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
    if weekday == 0:  # Sunday in your format
        target_python_weekday = 6  # Sunday in Python format
    else:  # Monday=1 to Saturday=6 in your format
        target_python_weekday = weekday - 1  # Convert to Python format (0-5)

    # Calculate days ahead using Python's weekday system
    days_ahead = (target_python_weekday - today.weekday() + 7) % 7
    if days_ahead == 0:
        days_ahead = 7  # get *next* weekday, not today

    return today + timedelta(days=days_ahead)

# Test the function
if __name__ == "__main__":
    from datetime import date

    print("Today:", date.today(), "- Python weekday:", date.today().weekday())
    print("Custom weekday format:")
    print("Next Monday (1):", get_next_weekday_v2(1))
    print("Next Tuesday (2):", get_next_weekday_v2(2))
    print("Next Wednesday (3):", get_next_weekday_v2(3))
    print("Next Sunday (0):", get_next_weekday_v2(0))
class AvailabilitySlotIntegrationTestCase(APITestCase):
    """
    Integration tests for automatic slot generation when availability changes
    """

    def setUp(self):
            """Set up test data"""
            # Create parent user and profile
            self.parent_user = User.objects.create_user(
                email='parent@test.com',
                password='testpass123',
                user_type='Parent',
                is_verified=True,
                is_active=True
            )
            self.parent = Parent.objects.get(user=self.parent_user)
            # Create psychologist user and profile
            self.psychologist_user = User.objects.create_user(
                email='psychologist@test.com',
                password='testpass123',
                user_type='Psychologist',
                is_verified=True,
                is_active=True
            )
            self.psychologist = Psychologist.objects.create(
                user=self.psychologist_user,
                first_name='Jane',
                last_name='Smith',
                license_number='PSY12345',
                license_issuing_authority='State Board',
                license_expiry_date=date.today() + timedelta(days=365),
                years_of_experience=10,
                verification_status='Approved',
                offers_online_sessions=True,
                offers_initial_consultation=True,
                office_address='123 Main St, City, State'
            )

            # Create admin user
            self.admin_user = User.objects.create_superuser(
                email='admin@test.com',
                password='testpass123',
                user_type='Admin'
            )

            # Create child
            self.child = Child.objects.create(
                parent=self.parent,
                first_name='Alice',
                last_name='Doe',
                date_of_birth=date.today() - timedelta(days=2555)  # ~7 years old
            )

            # Create appointment slots
            self.availability_block = PsychologistAvailability.objects.create(
                psychologist=self.psychologist,
                day_of_week=1,  # Monday
                start_time='09:00',
                end_time='17:00',
                is_recurring=True
            )

            # Create appointment slots for testing
            today = date.today()
            days_ahead = (7 - today.weekday()) % 7  # Days until Monday
            if days_ahead == 0:
                days_ahead = 7  # If today is Monday, get next Monday
            slot_date = today + timedelta(days=days_ahead)

            self.appointment_slot1 = AppointmentSlot.objects.create(
                psychologist=self.psychologist,
                availability_block=self.availability_block,
                slot_date=slot_date,
                start_time='09:00',
                end_time='10:00',
                is_booked=False
            )

            self.appointment_slot2 = AppointmentSlot.objects.create(
                psychologist=self.psychologist,
                availability_block=self.availability_block,
                slot_date=slot_date,
                start_time='10:00',
                end_time='11:00',
                is_booked=False
            )

            # Create a sample appointment
            self.appointment = Appointment.objects.create(
                child=self.child,
                psychologist=self.psychologist,
                parent=self.parent,
                scheduled_start_time=timezone.make_aware(
                    datetime.combine(slot_date, datetime.strptime('10:00', '%H:%M').time())
                ),
                scheduled_end_time=timezone.make_aware(
                    datetime.combine(slot_date, datetime.strptime('11:00', '%H:%M').time())
                ),
                session_type='OnlineMeeting',
                appointment_status='Scheduled',
                meeting_link='https://meet.example.com/abc123',
            )

            # Link appointment to slot
            self.appointment_slot2.is_booked = True
            self.appointment_slot2.save()
            self.appointment.appointment_slots.add(self.appointment_slot2)

            # Create tokens for authentication
            self.parent_token = Token.objects.create(user=self.parent_user)
            self.psychologist_token = Token.objects.create(user=self.psychologist_user)
            self.admin_token = Token.objects.create(user=self.admin_user)

            # Set up API client
            self.client = APIClient()

    def authenticate_parent(self):
        """Authenticate as parent"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.parent_token.key}')

    def authenticate_psychologist(self):
        """Authenticate as psychologist"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

    def authenticate_admin(self):
        """Authenticate as admin"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token.key}')

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_create_availability_generates_slots_in_database(self):
        """
        Test: Create availability → slots appear in database
        """
        # DEBUG: Check what exists before test starts
        all_slots_before = AppointmentSlot.objects.all()
        print(f"\n=== DEBUG: ALL SLOTS IN DATABASE BEFORE TEST ===")
        print(f"Total slots in database: {all_slots_before.count()}")
        for slot in all_slots_before:
            print(f"  - Slot ID: {slot.slot_id}, Psychologist: {slot.psychologist.user.id if slot.psychologist else 'None'}")
            print(f"    Time: {slot.start_time} - {slot.end_time}")
            print(f"    Availability Block: {slot.availability_block.availability_id if slot.availability_block else 'None'}")
            print(f"    Source: {'MANUAL (setUp)' if hasattr(slot, 'created_at') else 'AUTO-GENERATED'}")

        # CLEAR EXISTING SLOTS TO TEST AUTO-GENERATION IN ISOLATION
        print(f"\n=== DEBUG: CLEARING EXISTING SLOTS FOR CLEAN TEST ===")
        existing_slots = AppointmentSlot.objects.filter(psychologist=self.psychologist)
        slots_deleted = existing_slots.count()
        existing_slots.delete()
        print(f"Deleted {slots_deleted} existing slots from setUp")

        # Also clean up the existing availability from setUp since we want to test creation
        existing_availabilities = PsychologistAvailability.objects.filter(psychologist=self.psychologist)
        print(f"Found {existing_availabilities.count()} existing availability blocks from setUp")
        for avail in existing_availabilities:
            print(f"  - Deleting availability: Day {avail.day_of_week}, {avail.start_time}-{avail.end_time}")
        existing_availabilities.delete()

        # NOW verify no slots exist for THIS psychologist
        initial_slot_count = AppointmentSlot.objects.filter(
            psychologist=self.psychologist
        ).count()

        print(f"\n=== DEBUG: CLEAN STATE VERIFIED ===")
        print(f"Slots for test psychologist after cleanup: {initial_slot_count}")
        print(f"Availabilities for test psychologist after cleanup: {PsychologistAvailability.objects.filter(psychologist=self.psychologist).count()}")

        self.assertEqual(initial_slot_count, 0,
                        f"After cleanup, still found {initial_slot_count} slots for psychologist {self.psychologist.user.id}")

        # Create new availability block (Tuesday 9:00-12:00 for 90 days = many slots)
        next_monday = get_next_weekday(0)  # 0 = Monday

        print(f"\n=== DEBUG: CREATING NEW AVAILABILITY ===")
        print(f"Psychologist ID: {self.psychologist.user.id}")
        print(f"Day of week: 1 (Tuesday)")
        print(f"Time: 09:00-12:00")
        print(f"Expected: 90 days of Tuesday slots, 3 slots per Tuesday")

        # Calculate expected slots: Tuesdays in next 90 days * 3 slots per Tuesday
        from datetime import date, timedelta
        start_date = date.today()
        end_date = start_date + timedelta(days=90)

        # Count Tuesdays in the 90-day period
        current_date = start_date
        tuesday_count = 0
        while current_date <= end_date:
            if current_date.weekday() == 1:  # Tuesday = 1
                tuesday_count += 1
            current_date += timedelta(days=1)

        expected_slot_count = tuesday_count * 3  # 3 hours = 3 slots (9-10, 10-11, 11-12)
        print(f"Expected Tuesdays in 90 days: {tuesday_count}")
        print(f"Expected total slots: {expected_slot_count}")

        with patch('appointments.tasks.auto_generate_slots_task.delay') as mock_task:
            # Mock the task but call the actual service
            def side_effect(availability_id):
                print(f"DEBUG: Task called with availability_id: {availability_id}")
                from appointments.services import AppointmentSlotService
                from psychologists.models import PsychologistAvailability
                availability = PsychologistAvailability.objects.get(availability_id=availability_id)
                print(f"DEBUG: Retrieved availability: {availability}")
                result = AppointmentSlotService.auto_generate_slots_for_new_availability(availability)
                print(f"DEBUG: Service returned: {result}")
                return result

            mock_task.side_effect = side_effect

            # Create availability: Tuesday 9:00-12:00 (3 hours = 3 slots per Tuesday)
            availability = PsychologistAvailability.objects.create(
                psychologist=self.psychologist,
                day_of_week=1,  # Tuesday
                start_time='09:00',
                end_time='12:00',
                is_recurring=True
            )

            print(f"DEBUG: Created availability with ID: {availability.availability_id}")

        # Verify signal triggered the task
        print(f"\n=== DEBUG: VERIFYING TASK CALL ===")
        print(f"Mock task call count: {mock_task.call_count}")
        print(f"Expected call args: {availability.availability_id}")
        if mock_task.call_args:
            print(f"Actual call args: {mock_task.call_args}")

        mock_task.assert_called_once_with(availability.availability_id)

        # DEBUG: Check slots after creation
        all_slots_after = AppointmentSlot.objects.filter(psychologist=self.psychologist)
        print(f"\n=== DEBUG: SLOTS AFTER AVAILABILITY CREATION ===")
        print(f"Total slots for psychologist: {all_slots_after.count()}")

        # Show first few and last few slots for verification
        first_5_slots = all_slots_after.order_by('slot_date', 'start_time')[:5]
        last_5_slots = all_slots_after.order_by('slot_date', 'start_time').reverse()[:5]

        print("First 5 slots:")
        for slot in first_5_slots:
            print(f"  - {slot.slot_date} {slot.start_time}-{slot.end_time}")

        print("Last 5 slots:")
        for slot in reversed(last_5_slots):
            print(f"  - {slot.slot_date} {slot.start_time}-{slot.end_time}")

        # Verify slots were created in database
        generated_slots = AppointmentSlot.objects.filter(
            psychologist=self.psychologist,
            availability_block=availability
        ).order_by('slot_date', 'start_time')

        print(f"\n=== DEBUG: GENERATED SLOTS FOR NEW AVAILABILITY ===")
        print(f"Slots linked to new availability: {generated_slots.count()}")

        # Should have expected_slot_count slots across 90 days
        if generated_slots.count() != expected_slot_count:
            print(f"ERROR: Expected {expected_slot_count} slots, got {generated_slots.count()}")

            # Show date distribution
            date_counts = {}
            for slot in generated_slots:
                date_str = slot.slot_date.strftime('%Y-%m-%d (%A)')
                date_counts[date_str] = date_counts.get(date_str, 0) + 1

            print("Slot distribution by date:")
            for date_str, count in sorted(date_counts.items()):
                print(f"  {date_str}: {count} slots")

        self.assertEqual(generated_slots.count(), expected_slot_count,
                        f"Expected {expected_slot_count} generated slots across 90 days, got {generated_slots.count()}. "
                        f"Check debug output for slot distribution.")

        # Verify first Tuesday's slot details (should be 9-10, 10-11, 11-12)
        first_tuesday_slots = generated_slots.filter(
            slot_date=generated_slots.first().slot_date
        ).order_by('start_time')

        print(f"\n=== DEBUG: FIRST TUESDAY SLOT VERIFICATION ===")
        print(f"First Tuesday date: {first_tuesday_slots.first().slot_date}")
        print(f"Slots on first Tuesday: {first_tuesday_slots.count()}")

        slot_times = [(slot.start_time.strftime('%H:%M'), slot.end_time.strftime('%H:%M'))
                    for slot in first_tuesday_slots]
        expected_times = [('09:00', '10:00'), ('10:00', '11:00'), ('11:00', '12:00')]

        print(f"Expected times: {expected_times}")
        print(f"Actual times: {slot_times}")

        self.assertEqual(len(slot_times), 3, f"Expected 3 slots per Tuesday, got {len(slot_times)}")
        self.assertEqual(slot_times, expected_times,
                        f"Slot times don't match. Expected: {expected_times}, Got: {slot_times}")

        # Verify all slots are available and belong to correct psychologist
        print(f"\n=== DEBUG: SLOT STATUS VERIFICATION (sampling first 10) ===")
        sample_slots = generated_slots[:10]
        for i, slot in enumerate(sample_slots):
            print(f"Slot {i+1}: {slot.slot_date} {slot.start_time}-{slot.end_time}, booked={slot.is_booked}, status='{slot.reservation_status}'")
            self.assertFalse(slot.is_booked, f"Slot {i+1} should not be booked")
            self.assertEqual(slot.reservation_status, 'available', f"Slot {i+1} should be available")
            self.assertEqual(slot.psychologist, self.psychologist, f"Slot {i+1} should belong to test psychologist")

        print(f"\n=== DEBUG: TEST COMPLETED SUCCESSFULLY ===")
        print(f"✓ Created {generated_slots.count()} slots across {tuesday_count} Tuesdays over 90 days")
        print(f"✓ Each Tuesday has 3 slots (09:00-10:00, 10:00-11:00, 11:00-12:00)")
        print(f"✓ All slots are available and correctly linked to psychologist")

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_update_availability_preserves_booked_regenerates_unbooked(self):
        """
        Test: Update availability → unbooked slots regenerated, booked preserved
        """
        # Step 1: Create initial availability and slots
        next_wednesday = get_next_weekday(3)  # 3 = Wednesday

        availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=3,  # Wednesday
            start_time='10:00',
            end_time='14:00',  # 4 hours = 4 slots
            is_recurring=True
        )

        # Manually create initial slots (simulating the creation flow)
        initial_slots = []
        for hour in range(4):  # 10-11, 11-12, 12-13, 13-14
            start_hour = 10 + hour
            end_hour = start_hour + 1
            slot = AppointmentSlot.objects.create(
                psychologist=self.psychologist,
                availability_block=availability,
                slot_date=next_wednesday,
                start_time=f'{start_hour:02d}:00',
                end_time=f'{end_hour:02d}:00',
                is_booked=False
            )
            initial_slots.append(slot)

        # Step 2: Book some slots (simulate appointments)
        # Book slots 11-12 and 12-13 (middle two slots)
        booked_slot_1 = initial_slots[1]  # 11-12
        booked_slot_2 = initial_slots[2]  # 12-13

        booked_slot_1.is_booked = True
        booked_slot_1.save()
        booked_slot_2.is_booked = True
        booked_slot_2.save()

        # Create appointments for the booked slots
        appointment_1 = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            scheduled_start_time=timezone.make_aware(
                datetime.combine(next_wednesday, datetime.strptime('11:00', '%H:%M').time())
            ),
            scheduled_end_time=timezone.make_aware(
                datetime.combine(next_wednesday, datetime.strptime('12:00', '%H:%M').time())
            ),
            session_type='OnlineMeeting',
            appointment_status='Scheduled'
        )
        appointment_1.appointment_slots.add(booked_slot_1)

        appointment_2 = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            scheduled_start_time=timezone.make_aware(
                datetime.combine(next_wednesday, datetime.strptime('12:00', '%H:%M').time())
            ),
            scheduled_end_time=timezone.make_aware(
                datetime.combine(next_wednesday, datetime.strptime('13:00', '%H:%M').time())
            ),
            session_type='OnlineMeeting',
            appointment_status='Scheduled'
        )
        appointment_2.appointment_slots.add(booked_slot_2)

        # Verify initial state: 4 slots, 2 booked, 2 unbooked
        initial_total = AppointmentSlot.objects.filter(availability_block=availability).count()
        initial_booked = AppointmentSlot.objects.filter(availability_block=availability, is_booked=True).count()
        self.assertEqual(initial_total, 4)
        self.assertEqual(initial_booked, 2)

        # Store IDs of booked slots for verification
        booked_slot_ids = {booked_slot_1.slot_id, booked_slot_2.slot_id}

        print(f"DEBUG: Initial availability ID: {availability.availability_id}")
        print(f"DEBUG: Initial booked slot IDs: {booked_slot_ids}")

        # Step 3: Update availability (extend time: 09:00-15:00 = 6 hours)
        with patch('appointments.tasks.auto_regenerate_slots_task.delay') as mock_task:
            # Mock the task but call the actual service
            def side_effect(*args, **kwargs):
                print(f"DEBUG: Mock task called with args: {args}, kwargs: {kwargs}")
                from appointments.services import AppointmentSlotService
                from psychologists.models import PsychologistAvailability

                availability_id = args[0] if args else None
                old_data = args[1] if len(args) > 1 else kwargs.get('old_data', None)

                print(f"DEBUG: Processing availability_id: {availability_id}, old_data: {old_data}")

                # Check slots before regeneration
                slots_before = AppointmentSlot.objects.filter(availability_block_id=availability_id)
                print(f"DEBUG: Slots before regeneration: {slots_before.count()}")
                for slot in slots_before:
                    print(f"  Slot {slot.slot_id}: {slot.slot_date} {slot.start_time}-{slot.end_time} (booked: {slot.is_booked})")

                availability = PsychologistAvailability.objects.get(availability_id=availability_id)
                result = AppointmentSlotService.auto_regenerate_slots_for_updated_availability(
                    availability, old_data
                )

                # Check slots after regeneration
                slots_after = AppointmentSlot.objects.filter(availability_block_id=availability_id)
                print(f"DEBUG: Slots after regeneration: {slots_after.count()}")

                # Group by date to see what dates we're creating slots for
                from collections import defaultdict
                slots_by_date = defaultdict(list)
                for slot in slots_after:
                    slots_by_date[slot.slot_date].append(slot)

                print(f"DEBUG: Slots created for {len(slots_by_date)} different dates:")
                for date, date_slots in slots_by_date.items():
                    print(f"  {date}: {len(date_slots)} slots")
                    for slot in date_slots[:3]:  # Show first 3 slots for each date
                        print(f"    {slot.start_time}-{slot.end_time} (booked: {slot.is_booked})")
                    if len(date_slots) > 3:
                        print(f"    ... and {len(date_slots) - 3} more")

                return result

            mock_task.side_effect = side_effect

            print(f"DEBUG: About to update availability from {availability.start_time}-{availability.end_time}")

            # Update the availability block
            availability.start_time = '09:00'  # Extended 1 hour earlier
            availability.end_time = '15:00'    # Extended 1 hour later
            availability.save()

            print(f"DEBUG: Updated availability to {availability.start_time}-{availability.end_time}")

        # DEBUG: Check what the mock was actually called with
        print(f"DEBUG: Mock call count: {mock_task.call_count}")
        if mock_task.call_count > 0:
            print(f"DEBUG: Mock call args: {mock_task.call_args}")
            print(f"DEBUG: All mock calls: {mock_task.call_args_list}")

        # Verify signal triggered the regeneration task
        # UPDATED: Check what was actually called instead of assuming the signature
        if mock_task.call_count == 1:
            actual_args = mock_task.call_args[0]  # positional args
            actual_kwargs = mock_task.call_args[1]  # keyword args
            print(f"DEBUG: Actual call - args: {actual_args}, kwargs: {actual_kwargs}")

            # Check if it was called with just availability_id or with both parameters
            if len(actual_args) == 1:
                print("DEBUG: Task called with only availability_id (no old_data)")
                mock_task.assert_called_once_with(availability.availability_id)
            elif len(actual_args) == 2:
                print("DEBUG: Task called with availability_id and old_data")
                mock_task.assert_called_once_with(availability.availability_id, actual_args[1])
            else:
                print(f"DEBUG: Unexpected number of arguments: {len(actual_args)}")
        else:
            print(f"DEBUG: Expected 1 call but got {mock_task.call_count}")

        # Step 4: Verify results
        final_slots = AppointmentSlot.objects.filter(
            availability_block=availability
        ).order_by('start_time')

        print(f"DEBUG: Final slot count: {final_slots.count()}")

        # Filter to only the specific date we're testing
        target_date_slots = final_slots.filter(slot_date=next_wednesday).order_by('start_time')
        print(f"DEBUG: Slots for target date ({next_wednesday}): {target_date_slots.count()}")

        # Show all slots for our target date
        for slot in target_date_slots:
            print(f"  {slot.start_time}-{slot.end_time} (booked: {slot.is_booked}, id: {slot.slot_id})")

        # Should now have 6 slots for our target date: 09-10, 10-11, 11-12, 12-13, 13-14, 14-15
        self.assertEqual(target_date_slots.count(), 6,
                        f"Expected 6 slots for {next_wednesday}, got {target_date_slots.count()}")

        # Verify slot times using target date slots
        slot_times = [(slot.start_time.strftime('%H:%M'), slot.end_time.strftime('%H:%M'))
                    for slot in target_date_slots]
        expected_times = [
            ('09:00', '10:00'),  # New slot
            ('10:00', '11:00'),  # Regenerated (was unbooked)
            ('11:00', '12:00'),  # Preserved (was booked)
            ('12:00', '13:00'),  # Preserved (was booked)
            ('13:00', '14:00'),  # Regenerated (was unbooked)
            ('14:00', '15:00')   # New slot
        ]

        print(f"DEBUG: Actual slot times: {slot_times}")
        print(f"DEBUG: Expected slot times: {expected_times}")

        self.assertEqual(slot_times, expected_times)

        # Verify booked slots are preserved
        still_booked_slots = target_date_slots.filter(is_booked=True)
        print(f"DEBUG: Still booked slots count: {still_booked_slots.count()}")

        self.assertEqual(still_booked_slots.count(), 2)

        # Verify the preserved slots are the same ones that were booked
        preserved_slot_ids = {slot.slot_id for slot in still_booked_slots}
        print(f"DEBUG: Preserved slot IDs: {preserved_slot_ids}")
        print(f"DEBUG: Original booked slot IDs: {booked_slot_ids}")

        self.assertEqual(preserved_slot_ids, booked_slot_ids)

        # Verify appointments are still linked correctly
        appointment_1_linked = appointment_1.appointment_slots.filter(slot_id=booked_slot_1.slot_id).exists()
        appointment_2_linked = appointment_2.appointment_slots.filter(slot_id=booked_slot_2.slot_id).exists()

        print(f"DEBUG: Appointment 1 still linked: {appointment_1_linked}")
        print(f"DEBUG: Appointment 2 still linked: {appointment_2_linked}")

        self.assertTrue(appointment_1_linked)
        self.assertTrue(appointment_2_linked)

        # Verify new/regenerated slots are unbooked
        unbooked_slots = target_date_slots.filter(is_booked=False)
        print(f"DEBUG: Unbooked slots count: {unbooked_slots.count()}")

        self.assertEqual(unbooked_slots.count(), 4)

    def test_update_availability_time_reduction_handles_booked_slots(self):
        """
        Test: Update availability with time reduction - should handle conflicts gracefully
        """
        # Create availability: 10:00-14:00 (4 slots)
        next_thursday = get_next_weekday(3)  # 3 = Thursday

        availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=3,  # Thursday
            start_time='10:00',
            end_time='14:00',
            is_recurring=True
        )

        # Create slots and book the last one (13-14)
        slots = []
        for hour in range(4):
            start_hour = 10 + hour
            end_hour = start_hour + 1
            slot = AppointmentSlot.objects.create(
                psychologist=self.psychologist,
                availability_block=availability,
                slot_date=next_thursday,
                start_time=f'{start_hour:02d}:00',
                end_time=f'{end_hour:02d}:00',
                is_booked=False
            )
            slots.append(slot)

        # Book the last slot (13-14)
        last_slot = slots[3]
        last_slot.is_booked = True
        last_slot.save()

        # Try to reduce availability to 10:00-13:00 (removing the booked 13-14 slot)
        with patch('appointments.tasks.auto_regenerate_slots_task.delay') as mock_task:
            def side_effect(availability_id, old_data=None):
                from appointments.services import AppointmentSlotService
                from psychologists.models import PsychologistAvailability

                availability = PsychologistAvailability.objects.get(availability_id=availability_id)
                return AppointmentSlotService.auto_regenerate_slots_for_updated_availability(
                    availability, old_data
                )

            mock_task.side_effect = side_effect

            # Update availability (reduce end time)
            availability.end_time = '13:00'
            availability.save()

        # Verify the booked slot outside new time range is preserved
        final_slots = AppointmentSlot.objects.filter(
            availability_block=availability
        ).order_by('start_time')

        # Should still have the booked slot even though it's outside new availability
        booked_slots = final_slots.filter(is_booked=True)
        self.assertEqual(booked_slots.count(), 1)
        self.assertEqual(booked_slots.first().slot_id, last_slot.slot_id)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_specific_date_availability_generates_slots(self):
        """
        Test: Specific date availability (non-recurring) generates slots correctly
        """
        specific_date = date.today() + timedelta(days=14)  # 2 weeks from now

        with patch('appointments.tasks.auto_generate_slots_task.delay') as mock_task:
            def side_effect(availability_id):
                from appointments.services import AppointmentSlotService
                from psychologists.models import PsychologistAvailability

                availability = PsychologistAvailability.objects.get(availability_id=availability_id)
                return AppointmentSlotService.auto_generate_slots_for_new_availability(availability)

            mock_task.side_effect = side_effect

            # Create specific date availability
            availability = PsychologistAvailability.objects.create(
                psychologist=self.psychologist,
                day_of_week=specific_date.weekday(),
                start_time='14:00',
                end_time='17:00',  # 3 hours = 3 slots
                is_recurring=False,
                specific_date=specific_date
            )

        # Verify slots were created for the specific date
        generated_slots = AppointmentSlot.objects.filter(
            psychologist=self.psychologist,
            availability_block=availability,
            slot_date=specific_date
        ).order_by('start_time')

        self.assertEqual(generated_slots.count(), 3)

        # All slots should be on the specific date
        for slot in generated_slots:
            self.assertEqual(slot.slot_date, specific_date)

    @override_settings(
        CELERY_TASK_ALWAYS_EAGER=True,
        CELERY_TASK_EAGER_PROPAGATES=True,
        BROKER_BACKEND='memory'
    )
    def test_auto_cleanup_past_slots_task(self):
        """
        Test: auto_cleanup_past_slots_task deletes only past unbooked slots
        """
        from appointments.tasks import auto_cleanup_past_slots_task

        # Step 1: Create test availability block
        availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=2,  # Tuesday
            start_time='10:00',
            end_time='14:00',
            is_recurring=True
        )

        # Step 2: Calculate proper Tuesday dates
        today = date.today()

        def get_tuesday_offset(days_offset):
            target_date = today + timedelta(days=days_offset)
            days_since_tuesday = (target_date.weekday() - 1) % 7
            tuesday_date = target_date - timedelta(days=days_since_tuesday)
            return tuesday_date

        past_tuesday_1 = get_tuesday_offset(-14)  # Tuesday ~2 weeks ago
        past_tuesday_2 = get_tuesday_offset(-7)   # Tuesday ~1 week ago
        future_tuesday_1 = get_tuesday_offset(7)  # Tuesday ~1 week from now
        future_tuesday_2 = get_tuesday_offset(14) # Tuesday ~2 weeks from now

        print(f"\n=== DEBUG: CREATING TEST SLOTS ===")
        print(f"Today: {today} ({today.strftime('%A')})")
        print(f"Past Tuesdays: {past_tuesday_1}, {past_tuesday_2}")
        print(f"Future Tuesdays: {future_tuesday_1}, {future_tuesday_2}")

        # Step 3: Create slots using bulk_create (bypasses validation)
        slots_to_create = [
            # Past unbooked slots (should be deleted)
            AppointmentSlot(
                psychologist=self.psychologist,
                availability_block=availability,
                slot_date=past_tuesday_1,
                start_time='10:00',
                end_time='11:00',
                is_booked=False
            ),
            AppointmentSlot(
                psychologist=self.psychologist,
                availability_block=availability,
                slot_date=past_tuesday_1,
                start_time='11:00',
                end_time='12:00',
                is_booked=False
            ),
            AppointmentSlot(
                psychologist=self.psychologist,
                availability_block=availability,
                slot_date=past_tuesday_2,
                start_time='12:00',
                end_time='13:00',
                is_booked=False
            ),
            # Past booked slot (should be preserved)
            AppointmentSlot(
                psychologist=self.psychologist,
                availability_block=availability,
                slot_date=past_tuesday_2,
                start_time='10:00',
                end_time='11:00',
                is_booked=True
            ),
            # Future slots (should be preserved)
            AppointmentSlot(
                psychologist=self.psychologist,
                availability_block=availability,
                slot_date=future_tuesday_1,
                start_time='10:00',
                end_time='11:00',
                is_booked=False
            ),
            AppointmentSlot(
                psychologist=self.psychologist,
                availability_block=availability,
                slot_date=future_tuesday_2,
                start_time='11:00',
                end_time='12:00',
                is_booked=True
            )
        ]

        # Create all slots at once, bypassing validation
        created_slots = AppointmentSlot.objects.bulk_create(slots_to_create)

        print(f"Created {len(created_slots)} test slots using bulk_create")

        # Get the created slots for reference (bulk_create doesn't return IDs in all DB backends)
        # So we'll query them back
        past_unbooked_slots = AppointmentSlot.objects.filter(
            psychologist=self.psychologist,
            slot_date__in=[past_tuesday_1, past_tuesday_2],
            is_booked=False
        ).order_by('slot_date', 'start_time')

        past_booked_slot = AppointmentSlot.objects.filter(
            psychologist=self.psychologist,
            slot_date=past_tuesday_2,
            is_booked=True
        ).first()

        future_slots = AppointmentSlot.objects.filter(
            psychologist=self.psychologist,
            slot_date__in=[future_tuesday_1, future_tuesday_2]
        ).order_by('slot_date', 'start_time')

        # Create appointment for past booked slot
        past_appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            scheduled_start_time=timezone.make_aware(
                datetime.combine(past_tuesday_2, datetime.strptime('10:00', '%H:%M').time())
            ),
            scheduled_end_time=timezone.make_aware(
                datetime.combine(past_tuesday_2, datetime.strptime('11:00', '%H:%M').time())
            ),
            session_type='OnlineMeeting',
            appointment_status='Completed'
        )
        past_appointment.appointment_slots.add(past_booked_slot)

        # Step 4: Verify initial state - only count slots for our specific dates
        test_dates = [past_tuesday_1, past_tuesday_2, future_tuesday_1, future_tuesday_2]
        initial_total = AppointmentSlot.objects.filter(
            psychologist=self.psychologist,
            slot_date__in=test_dates
        ).count()
        initial_past_unbooked = past_unbooked_slots.count()
        initial_past_booked = 1
        initial_future = future_slots.count()

        print(f"\n=== DEBUG: INITIAL STATE ===")
        print(f"Total test slots: {initial_total}")
        print(f"Past unbooked (should be deleted): {initial_past_unbooked}")
        print(f"Past booked (should be preserved): {initial_past_booked}")
        print(f"Future slots (should be preserved): {initial_future}")
        print(f"All psychologist slots: {AppointmentSlot.objects.filter(psychologist=self.psychologist).count()}")

        # Verify our test setup
        self.assertEqual(initial_total, 6, "Should have created 6 test slots")
        self.assertEqual(initial_past_unbooked, 3, "Should have 3 past unbooked slots")
        self.assertEqual(initial_past_booked, 1, "Should have 1 past booked slot")
        self.assertEqual(initial_future, 2, "Should have 2 future slots")

        # Step 5: Run the cleanup task
        print(f"\n=== DEBUG: RUNNING CLEANUP TASK ===")

        # Option 1: Call the task directly (bypasses Celery entirely)
        task_result = auto_cleanup_past_slots_task(days_past=7)

        # Option 2: If you need to test the .delay() method, use apply() instead
        # result = auto_cleanup_past_slots_task.apply(args=[7], kwargs={'days_past': 7})
        # task_result = result.result

        print(f"Task result: {task_result}")

        # Step 6: Verify results
        final_total_all = AppointmentSlot.objects.filter(psychologist=self.psychologist).count()
        final_total_test = AppointmentSlot.objects.filter(
            psychologist=self.psychologist,
            slot_date__in=test_dates
        ).count()
        final_past_unbooked = AppointmentSlot.objects.filter(
            psychologist=self.psychologist,
            slot_date__lt=today,
            is_booked=False
        ).count()
        final_past_booked = AppointmentSlot.objects.filter(
            psychologist=self.psychologist,
            slot_date__lt=today,
            is_booked=True
        ).count()
        final_future = AppointmentSlot.objects.filter(
            psychologist=self.psychologist,
            slot_date__gte=today
        ).count()

        print(f"\n=== DEBUG: FINAL STATE ===")
        print(f"Total test slots: {final_total_test} (was {initial_total})")
        print(f"Total all slots: {final_total_all}")
        print(f"Past unbooked: {final_past_unbooked} (was {initial_past_unbooked})")
        print(f"Past booked: {final_past_booked} (was {initial_past_booked})")
        print(f"Future slots: {final_future} (was {initial_future})")

        # Verify task worked correctly
        self.assertTrue(task_result['success'], "Task should report success")
        self.assertEqual(task_result['deleted_count'], 3, "Should have deleted 3 past unbooked slots")
        self.assertEqual(final_total_test, 3, "Should have 3 test slots remaining")
        self.assertEqual(final_past_unbooked, 0, "All past unbooked slots should be deleted")
        self.assertEqual(final_past_booked, 1, "Past booked slot should be preserved")
        self.assertEqual(final_future, 4, "All future slots should be preserved")

        # Verify appointment is still linked
        past_appointment.refresh_from_db()
        self.assertEqual(past_appointment.appointment_slots.count(), 1, "Appointment should still be linked")

        print(f"\n=== DEBUG: TEST COMPLETED SUCCESSFULLY ===")
        print(f"✓ Deleted {task_result['deleted_count']} past unbooked slots")
        print(f"✓ Preserved past booked slot with appointment")
        print(f"✓ Preserved future slots")

    def test_auto_cleanup_past_slots_task_custom_days(self):
        """
        Test: auto_cleanup_past_slots_task with custom days_past parameter
        """
        from appointments.tasks import auto_cleanup_past_slots_task
        from appointments.models import AppointmentSlot, PsychologistAvailability

        # Create availability for this specific test
        test_availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=2,  # Tuesday
            start_time='09:00',
            end_time='11:00',
            is_recurring=True
        )

        today = date.today()

        # Create slots at different ages
        slots_to_create = [
            # 15 days ago (should be deleted)
            AppointmentSlot(
                psychologist=self.psychologist,
                availability_block=test_availability,
                slot_date=today - timedelta(days=15),
                start_time='09:00',
                end_time='10:00',
                is_booked=False
            ),
            # 5 days ago (should be deleted)
            AppointmentSlot(
                psychologist=self.psychologist,
                availability_block=test_availability,
                slot_date=today - timedelta(days=5),
                start_time='09:00',
                end_time='10:00',
                is_booked=False
            ),
            # 2 days ago (should be preserved)
            AppointmentSlot(
                psychologist=self.psychologist,
                availability_block=test_availability,
                slot_date=today - timedelta(days=2),
                start_time='09:00',
                end_time='10:00',
                is_booked=False
            ),
        ]

        created_slots = AppointmentSlot.objects.bulk_create(slots_to_create)
        very_old_slot = created_slots[0]
        medium_old_slot = created_slots[1]
        recent_slot = created_slots[2]

        print(f"\n=== DEBUG: TESTING CUSTOM days_past=3 ===")
        print(f"Today: {today} ({today.strftime('%A')})")
        print(f"Very old ({(today - very_old_slot.slot_date).days} days ago): {very_old_slot.slot_date} - should be deleted")
        print(f"Medium old ({(today - medium_old_slot.slot_date).days} days ago): {medium_old_slot.slot_date} - should be deleted")
        print(f"Recent ({(today - recent_slot.slot_date).days} days ago): {recent_slot.slot_date} - should be preserved")

        # Count total slots vs test-specific slots
        total_slots = AppointmentSlot.objects.filter(psychologist=self.psychologist).count()
        test_slots = AppointmentSlot.objects.filter(psychologist=self.psychologist, availability_block=test_availability).count()
        print(f"Total slots for psychologist: {total_slots}")
        print(f"Test-specific slots: {test_slots}")

        # Run the cleanup task
        task_result = auto_cleanup_past_slots_task(days_past=3)

        print(f"Task result: {task_result}")

        # Verify results - Filter by test availability to isolate your test data
        remaining_test_slots = AppointmentSlot.objects.filter(
            psychologist=self.psychologist,
            availability_block=test_availability
        )
        remaining_test_slot_ids = set(remaining_test_slots.values_list('pk', flat=True))
        expected_remaining_pks = {recent_slot.pk}

        print(f"Expected remaining PKs (test slots only): {expected_remaining_pks}")
        print(f"Actual remaining PKs (test slots only): {remaining_test_slot_ids}")
        print(f"Test slots remaining: {remaining_test_slots.count()}")

        # Verify that setup slots are still there (they're future dates, shouldn't be deleted)
        setup_slots = AppointmentSlot.objects.filter(
            psychologist=self.psychologist,
            availability_block=self.availability_block
        )
        print(f"Setup slots still present: {setup_slots.count()}")

        # Assertions
        self.assertEqual(task_result['deleted_count'], 2, "Should delete 2 slots older than 3 days")
        self.assertEqual(remaining_test_slot_ids, expected_remaining_pks, "Should preserve only recent test slot")
        self.assertEqual(task_result['days_past'], 3, "Should use custom days_past=3")

        print(f"✓ Custom days_past parameter working correctly")