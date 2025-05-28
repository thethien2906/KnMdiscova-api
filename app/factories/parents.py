# factories/parents.py
import factory
import random
from factory import fuzzy

from parents.models import Parent
from users.models import User
from .base import (
    BaseFactory,
    AddressMixin,
    TimestampMixin,
    RandomChoiceMixin,
    CommunicationPreferencesMixin,
    generate_phone_number
)
from .users import ParentUserFactory


class ParentFactory(BaseFactory, AddressMixin, TimestampMixin):
    """
    Factory for creating Parent profiles
    This works with the existing signal by creating the User first,
    then updating the automatically created Parent profile
    """

    class Meta:
        model = Parent
        django_get_or_create = ('user',)

    # Create the parent user first (signal will create Parent profile)
    user = factory.SubFactory(ParentUserFactory)

    # Personal Information - these will be set after creation
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')

    # Contact Information
    phone_number = factory.LazyFunction(generate_phone_number)

    # Address Information (using AddressMixin)
    address_line2 = factory.Maybe(
        factory.LazyFunction(lambda: random.random() < 0.3),
        yes_declaration=factory.Faker('secondary_address'),
        no_declaration=''
    )

    # Communication Preferences
    communication_preferences = factory.LazyFunction(
        CommunicationPreferencesMixin.generate_communication_preferences
    )

    @factory.post_generation
    def update_profile(obj, create, extracted, **kwargs):
        """
        Post-generation hook to update the Parent profile created by signal
        """
        if not create:
            return

        # The signal has already created a Parent profile with empty fields
        # Now we update it with our factory data
        update_fields = []

        if obj.first_name:
            update_fields.append('first_name')
        if obj.last_name:
            update_fields.append('last_name')
        if obj.phone_number:
            update_fields.append('phone_number')
        if obj.address_line1:
            update_fields.append('address_line1')
        if obj.address_line2:
            update_fields.append('address_line2')
        if obj.city:
            update_fields.append('city')
        if obj.state_province:
            update_fields.append('state_province')
        if obj.postal_code:
            update_fields.append('postal_code')
        if obj.country:
            update_fields.append('country')
        if obj.communication_preferences:
            update_fields.append('communication_preferences')

        if update_fields:
            update_fields.append('updated_at')
            obj.save(update_fields=update_fields)


class ParentFromExistingUserFactory(BaseFactory, AddressMixin, TimestampMixin):
    """
    Factory for updating Parent profiles from existing User instances
    Use this when you already have a User and want to update their Parent profile
    """

    class Meta:
        model = Parent
        django_get_or_create = ('user',)

    # User should be passed in when creating
    user = factory.SubFactory(ParentUserFactory)

    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    phone_number = factory.LazyFunction(generate_phone_number)

    communication_preferences = factory.LazyFunction(
        CommunicationPreferencesMixin.generate_communication_preferences
    )

    @classmethod
    def create_for_user(cls, user, **kwargs):
        """
        Create/update parent profile for existing user
        """
        if user.user_type != 'Parent':
            raise ValueError("User must be of type 'Parent'")

        # Get or create parent profile (signal should have created it)
        try:
            parent = Parent.objects.get(user=user)
            # Update the existing profile
            for field, value in kwargs.items():
                if hasattr(parent, field):
                    setattr(parent, field, value)

            # Set factory defaults if not provided
            if not kwargs.get('first_name'):
                parent.first_name = factory.Faker('first_name').generate()
            if not kwargs.get('last_name'):
                parent.last_name = factory.Faker('last_name').generate()
            if not kwargs.get('phone_number'):
                parent.phone_number = generate_phone_number()
            if not kwargs.get('communication_preferences'):
                parent.communication_preferences = CommunicationPreferencesMixin.generate_communication_preferences()

            parent.save()
            return parent

        except Parent.DoesNotExist:
            # If somehow the signal didn't work, create manually
            factory_kwargs = {'user': user, **kwargs}
            return cls.create(**factory_kwargs)


# Alternative approach: Create User and Parent separately
class ParentWithUserFactory:
    """
    Helper class that creates User and Parent in the correct sequence
    """

    @classmethod
    def create(cls, **kwargs):
        """
        Create a parent user and let signal create parent profile,
        then update the profile with provided data
        """
        from django.db import transaction

        # Separate user and parent kwargs
        user_kwargs = {}
        parent_kwargs = {}

        user_fields = ['email', 'user_type', 'is_active', 'is_verified',
                      'profile_picture_url', 'user_timezone']

        for key, value in kwargs.items():
            if key in user_fields:
                user_kwargs[key] = value
            else:
                parent_kwargs[key] = value

        with transaction.atomic():
            # Create user (this triggers signal to create Parent)
            user = ParentUserFactory.create(**user_kwargs)

            # Get the parent profile created by signal
            parent = Parent.objects.get(user=user)

            # Update parent profile with provided data
            for field, value in parent_kwargs.items():
                if hasattr(parent, field):
                    setattr(parent, field, value)

            # Set defaults for empty fields
            if not parent.first_name:
                parent.first_name = factory.Faker('first_name').generate()
            if not parent.last_name:
                parent.last_name = factory.Faker('last_name').generate()
            if not parent.phone_number:
                parent.phone_number = generate_phone_number()
            if not parent.communication_preferences:
                parent.communication_preferences = CommunicationPreferencesMixin.generate_communication_preferences()

            parent.save()
            return parent

    @classmethod
    def create_batch(cls, size, **kwargs):
        """Create multiple parents"""
        return [cls.create(**kwargs) for _ in range(size)]


# Update other factory classes to use the new approach
class CompletedParentProfileFactory(ParentWithUserFactory):
    """
    Factory for parents with complete profiles (all fields filled)
    """

    @classmethod
    def create(cls, **kwargs):
        # Ensure all optional fields are filled
        defaults = {
            'phone_number': generate_phone_number(),
            'address_line1': factory.Faker('street_address').generate(),
            'address_line2': factory.Faker('secondary_address').generate(),
            'city': factory.Faker('city').generate(),
            'state_province': factory.Faker('state').generate(),
            'postal_code': factory.Faker('postcode').generate(),
            'country': factory.Faker('country_code', representation='alpha-2').generate(),
            'communication_preferences': CommunicationPreferencesMixin.generate_communication_preferences()
        }

        # Merge with provided kwargs (provided kwargs take precedence)
        merged_kwargs = {**defaults, **kwargs}
        return super().create(**merged_kwargs)


class IncompleteParentProfileFactory(ParentWithUserFactory):
    """
    Factory for parents with incomplete profiles (realistic for new users)
    """

    @classmethod
    def create(cls, **kwargs):
        # Only some fields are filled
        defaults = {
            'first_name': factory.Faker('first_name').generate(),
            'last_name': factory.Faker('last_name').generate() if random.random() < 0.7 else '',
            'phone_number': generate_phone_number() if random.random() < 0.5 else '',
            'address_line1': factory.Faker('street_address').generate() if random.random() < 0.4 else '',
            'address_line2': '',
            'city': factory.Faker('city').generate() if random.random() < 0.4 else '',
            'state_province': '',
            'postal_code': '',
            'country': 'US' if random.random() < 0.6 else '',
            'communication_preferences': CommunicationPreferencesMixin.generate_communication_preferences()
        }

        merged_kwargs = {**defaults, **kwargs}
        return super().create(**merged_kwargs)


# Update batch creation helpers
class ParentBatchFactory:
    """
    Helper class for creating batches of parents with different characteristics
    """

    @staticmethod
    def create_mixed_parents(count=30):
        """
        Create a mixed batch of parents with realistic distribution
        """
        parents = []

        # Distribution of parent types
        complete_count = int(count * 0.4)      # 40% complete profiles
        incomplete_count = int(count * 0.3)    # 30% incomplete profiles
        realistic_count = count - complete_count - incomplete_count  # Rest are realistic

        parents.extend(CompletedParentProfileFactory.create_batch(complete_count))
        parents.extend(IncompleteParentProfileFactory.create_batch(incomplete_count))
        parents.extend(RealisticParentFactory.create_batch(realistic_count))

        return parents

    @staticmethod
    def create_parents_for_existing_users(users):
        """
        Update parent profiles for existing parent users
        """
        parent_users = [user for user in users if user.user_type == 'Parent']
        parents = []

        for user in parent_users:
            # The signal should have already created the parent profile
            try:
                parent = Parent.objects.get(user=user)

                # Update with realistic data
                if random.random() < 0.6:  # 60% get complete profiles
                    parent.first_name = factory.Faker('first_name').generate()
                    parent.last_name = factory.Faker('last_name').generate()
                    parent.phone_number = generate_phone_number()
                    parent.address_line1 = factory.Faker('street_address').generate()
                    parent.city = factory.Faker('city').generate()
                    parent.state_province = factory.Faker('state').generate()
                    parent.postal_code = factory.Faker('postcode').generate()
                    parent.country = 'US'
                else:  # 40% get incomplete profiles
                    parent.first_name = factory.Faker('first_name').generate()
                    parent.last_name = factory.Faker('last_name').generate() if random.random() < 0.7 else ''
                    parent.phone_number = generate_phone_number() if random.random() < 0.5 else ''

                parent.communication_preferences = CommunicationPreferencesMixin.generate_communication_preferences()
                parent.save()
                parents.append(parent)

            except Parent.DoesNotExist:
                # If signal didn't work, create manually
                parent = ParentFromExistingUserFactory.create_for_user(user)
                parents.append(parent)

        return parents

    @staticmethod
    def create_test_parents():
        """
        Create test parents with known data for development
        """
        parents = []

        # Test parent with complete profile
        complete_parent = CompletedParentProfileFactory.create(
            email='testparent1@test.com',
            first_name='John',
            last_name='Doe',
            phone_number='+1-555-123-4567',
            city='Test City',
            state_province='CA',
            country='US'
        )
        parents.append(complete_parent)

        # Test parent with incomplete profile
        incomplete_parent = IncompleteParentProfileFactory.create(
            email='testparent2@test.com',
            first_name='Jane',
            last_name='',
            phone_number='',
            city='',
            state_province='',
            country=''
        )
        parents.append(incomplete_parent)

        return parents