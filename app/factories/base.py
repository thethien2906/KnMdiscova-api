# factories/base.py
import factory
from django.contrib.auth.hashers import make_password
from factory import fuzzy
import random
from datetime import date, timedelta


class BaseFactory(factory.django.DjangoModelFactory):
    """
    Base factory with common configurations
    """

    class Meta:
        abstract = True

    @classmethod
    def _setup_next_sequence(cls):
        """Ensure unique sequences for each factory"""
        return getattr(cls._meta.model, '_factory_sequence', 0)


class PasswordMixin:
    """Mixin for handling password generation"""

    @factory.lazy_attribute
    def password(self):
        """Generate a hashed password"""
        return make_password('testpass123')


class AddressMixin:
    """Mixin for generating realistic address data"""

    address_line1 = factory.Faker('street_address')
    address_line2 = factory.Faker('secondary_address', chance_of_getting=0.3)
    city = factory.Faker('city')
    state_province = factory.Faker('state')
    postal_code = factory.Faker('postcode')
    country = factory.Faker('country_code', representation='alpha-2')


class TimestampMixin:
    """Mixin for handling timestamps"""

    created_at = factory.Faker('date_time_this_year', tzinfo=None)
    updated_at = factory.LazyAttribute(lambda obj: obj.created_at)


class RandomChoiceMixin:
    """Mixin with helper methods for random choices"""

    @staticmethod
    def random_bool(true_chance=0.5):
        """Return True with specified probability"""
        return random.random() < true_chance

    @staticmethod
    def random_choice_weighted(choices_weights):
        """
        Choose from weighted options
        Example: [('option1', 0.7), ('option2', 0.3)]
        """
        total = sum(weight for _, weight in choices_weights)
        r = random.uniform(0, total)
        upto = 0
        for choice, weight in choices_weights:
            if upto + weight >= r:
                return choice
            upto += weight
        return choices_weights[-1][0]  # fallback


class AgeCalculatorMixin:
    """Mixin for age-related calculations"""

    @staticmethod
    def generate_date_of_birth_for_age(min_age=5, max_age=17):
        """Generate date of birth for a specific age range"""
        today = date.today()
        # Calculate the date range for the desired age
        max_birth_date = date(today.year - min_age, today.month, today.day)
        min_birth_date = date(today.year - max_age, today.month, today.day)

        # Generate random date in the range
        delta = max_birth_date - min_birth_date
        random_days = random.randint(0, delta.days)
        return min_birth_date + timedelta(days=random_days)


class CommunicationPreferencesMixin:
    """Mixin for generating communication preferences"""

    @staticmethod
    def generate_communication_preferences():
        """Generate realistic communication preferences"""
        preferences = {
            'email_notifications': RandomChoiceMixin.random_bool(0.8),  # 80% prefer email
            'sms_notifications': RandomChoiceMixin.random_bool(0.3),    # 30% prefer SMS
            'appointment_reminders': RandomChoiceMixin.random_bool(0.9), # 90% want reminders
            'reminder_timing': RandomChoiceMixin.random_choice_weighted([
                ('24_hours', 0.6),
                ('2_hours', 0.3),
                ('30_minutes', 0.1)
            ]),
            'growth_plan_updates': RandomChoiceMixin.random_bool(0.7),  # 70% want updates
            'new_message_alerts': RandomChoiceMixin.random_bool(0.8),   # 80% want alerts
            'marketing_emails': RandomChoiceMixin.random_bool(0.2),     # 20% want marketing
        }
        return preferences


class ConsentFormsMixin:
    """Mixin for generating consent forms"""

    @staticmethod
    def generate_consent_forms():
        """Generate consent forms with realistic patterns"""
        from django.utils import timezone

        consent_types = [
            'service_consent',
            'assessment_consent',
            'communication_consent',
            'data_sharing_consent'
        ]

        consents = {}

        # Some families are more cautious, others more open
        family_openness = random.random()  # 0-1 scale

        for consent_type in consent_types:
            # More open families grant more consents
            granted_probability = 0.3 + (family_openness * 0.6)  # 30-90% chance
            granted = random.random() < granted_probability

            consents[consent_type] = {
                'granted': granted,
                'date_signed': timezone.now().isoformat() if granted else None,
                'parent_signature': f"Parent_{random.randint(1000, 9999)}" if granted else None,
                'notes': RandomChoiceMixin.random_choice_weighted([
                    ('', 0.7),  # Most have no notes
                    ('Discussed with family', 0.1),
                    ('Will review again later', 0.1),
                    ('Conditional approval', 0.05),
                    ('Required for services', 0.05)
                ]) if granted else 'Consent not granted',
                'version': '1.0'
            }

        return consents


# Utility functions for realistic data generation

def generate_realistic_height_weight(age):
    """
    Generate realistic height/weight for child's age
    Returns tuple (height_cm, weight_kg)
    """
    # Rough averages with some variation
    height_base = {
        5: 110, 6: 115, 7: 120, 8: 125, 9: 130,
        10: 135, 11: 140, 12: 145, 13: 155, 14: 165,
        15: 170, 16: 173, 17: 175
    }

    weight_base = {
        5: 18, 6: 20, 7: 23, 8: 26, 9: 29,
        10: 32, 11: 37, 12: 42, 13: 50, 14: 58,
        15: 62, 16: 65, 17: 68
    }

    base_height = height_base.get(age, 140)
    base_weight = weight_base.get(age, 35)

    # Add realistic variation (±10% for height, ±20% for weight)
    height = int(base_height * random.uniform(0.9, 1.1))
    weight = int(base_weight * random.uniform(0.8, 1.2))

    return height, weight


def generate_phone_number():
    """Generate a realistic phone number"""
    formats = [
        '+1-{}-{}-{}',
        '({}) {}-{}',
        '{}.{}.{}',
        '{} {} {}'
    ]

    format_choice = random.choice(formats)
    area_code = random.randint(200, 999)
    exchange = random.randint(200, 999)
    number = random.randint(1000, 9999)

    return format_choice.format(area_code, exchange, number)