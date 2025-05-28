# factories/users.py
import factory
from factory import fuzzy
from django.utils import timezone
import random

from users.models import User
from .base import (
    BaseFactory,
    PasswordMixin,
    TimestampMixin,
    RandomChoiceMixin
)


class UserFactory(BaseFactory, PasswordMixin, TimestampMixin):
    """
    Factory for creating User instances
    """

    class Meta:
        model = User
        django_get_or_create = ('email',)  # Avoid duplicate emails

    # Generate unique email addresses
    email = factory.Sequence(lambda n: f'user{n}@example.com')

    # User type distribution: More parents than psychologists, few admins
    user_type = factory.LazyFunction(
        lambda: RandomChoiceMixin.random_choice_weighted([
            ('Parent', 0.75),        # 75% parents
            ('Psychologist', 0.23),  # 23% psychologists
            ('Admin', 0.02)          # 2% admins
        ])
    )

    # Most users are active and verified
    is_active = factory.LazyFunction(lambda: RandomChoiceMixin.random_bool(0.95))
    is_verified = factory.LazyFunction(lambda: RandomChoiceMixin.random_bool(0.85))

    # Staff status only for admins
    is_staff = factory.LazyAttribute(lambda obj: obj.user_type == 'Admin')
    is_superuser = factory.LazyAttribute(lambda obj: obj.user_type == 'Admin')

    # Optional profile picture (30% chance)
    profile_picture_url = factory.Maybe(
        factory.LazyFunction(lambda: random.random() < 0.3),
        yes_declaration=factory.Faker('image_url', width=200, height=200),
        no_declaration=None
    )

    # Random timezone from common ones
    user_timezone = factory.Faker('random_element', elements=[
        'UTC', 'US/Eastern', 'US/Central', 'US/Mountain', 'US/Pacific',
        'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Asia/Tokyo',
        'Australia/Sydney', 'America/Toronto', 'America/New_York'
    ])

    # Registration date in the past year
    registration_date = factory.Faker('date_time_between',
                                    start_date='-1y',
                                    end_date='now',
                                    tzinfo=timezone.get_current_timezone())

    # Last login recent for active users
    last_login_date = factory.Maybe(
        'is_active',
        yes_declaration=factory.Faker('date_time_between',
                                    start_date='-30d',
                                    end_date='now',
                                    tzinfo=timezone.get_current_timezone()),
        no_declaration=None
    )


class ParentUserFactory(UserFactory):
    """
    Factory specifically for Parent users
    """
    user_type = 'Parent'
    is_verified = factory.LazyFunction(lambda: RandomChoiceMixin.random_bool(0.9))  # Higher verification rate

    # Parent-specific email patterns
    email = factory.Sequence(lambda n: f'parent{n}@{random.choice(["gmail.com", "yahoo.com", "hotmail.com", "outlook.com"])}')


class PsychologistUserFactory(UserFactory):
    """
    Factory specifically for Psychologist users
    """
    user_type = 'Psychologist'
    is_verified = True  # All psychologists should be verified
    is_active = True    # All psychologists should be active

    # Professional email patterns
    email = factory.Sequence(lambda n: f'dr.psychologist{n}@{random.choice(["clinic.com", "psychology.com", "therapy.org", "counseling.net"])}')


class AdminUserFactory(UserFactory):
    """
    Factory specifically for Admin users
    """
    user_type = 'Admin'
    is_verified = True
    is_active = True
    is_staff = True
    is_superuser = True

    # Admin email patterns
    email = factory.Sequence(lambda n: f'admin{n}@kmdiscova.com')


class UnverifiedUserFactory(UserFactory):
    """
    Factory for unverified users (for testing verification flows)
    """
    is_verified = False
    is_active = True
    last_login_date = None


class InactiveUserFactory(UserFactory):
    """
    Factory for inactive users
    """
    is_active = False
    is_verified = factory.LazyFunction(lambda: RandomChoiceMixin.random_bool(0.5))
    last_login_date = factory.Faker('date_time_between',
                                  start_date='-1y',
                                  end_date='-3m',
                                  tzinfo=timezone.get_current_timezone())


# Batch creation helpers

class UserBatchFactory:
    """
    Helper class for creating batches of users
    """

    @staticmethod
    def create_mixed_users(count=50):
        """
        Create a mixed batch of users with realistic distribution
        """
        users = []

        # Calculate counts based on distribution
        parent_count = int(count * 0.75)
        psychologist_count = int(count * 0.23)
        admin_count = max(1, count - parent_count - psychologist_count)  # At least 1 admin

        # Create users
        users.extend(ParentUserFactory.create_batch(parent_count))
        users.extend(PsychologistUserFactory.create_batch(psychologist_count))
        users.extend(AdminUserFactory.create_batch(admin_count))

        return users

    @staticmethod
    def create_test_users():
        """
        Create a set of test users with known credentials for development
        """
        users = []

        # Test parent
        parent_user = ParentUserFactory.create(
            email='parent@test.com',
            is_verified=True,
            is_active=True
        )
        users.append(parent_user)

        # Test psychologist
        psychologist_user = PsychologistUserFactory.create(
            email='psychologist@test.com',
            is_verified=True,
            is_active=True
        )
        users.append(psychologist_user)

        # Test admin
        admin_user = AdminUserFactory.create(
            email='admin@test.com',
            is_verified=True,
            is_active=True
        )
        users.append(admin_user)

        # Unverified parent for testing verification flow
        unverified_user = ParentUserFactory.create(
            email='unverified@test.com',
            is_verified=False,
            is_active=True
        )
        users.append(unverified_user)

        return users

    @staticmethod
    def create_realistic_activity_patterns(users):
        """
        Update users with realistic activity patterns
        """
        for user in users:
            # Some users haven't logged in recently
            if random.random() < 0.2:  # 20% are inactive
                user.last_login_date = factory.Faker('date_time_between',
                                                   start_date='-6m',
                                                   end_date='-1m',
                                                   tzinfo=timezone.get_current_timezone()).generate()
            else:
                # Active users have recent logins
                user.last_login_date = factory.Faker('date_time_between',
                                                   start_date='-7d',
                                                   end_date='now',
                                                   tzinfo=timezone.get_current_timezone()).generate()

            user.save(update_fields=['last_login_date'])


# Trait-based factories for specific scenarios

class NewUserFactory(UserFactory):
    """
    Factory for newly registered users
    """
    registration_date = factory.LazyFunction(timezone.now)
    last_login_date = None
    is_verified = False


class ActiveUserFactory(UserFactory):
    """
    Factory for highly active users
    """
    is_active = True
    is_verified = True
    last_login_date = factory.Faker('date_time_between',
                                  start_date='-1d',
                                  end_date='now',
                                  tzinfo=timezone.get_current_timezone())


class LongTimeUserFactory(UserFactory):
    """
    Factory for users who have been on the platform for a long time
    """
    registration_date = factory.Faker('date_time_between',
                                    start_date='-2y',
                                    end_date='-6m',
                                    tzinfo=timezone.get_current_timezone())
    is_verified = True
    is_active = True