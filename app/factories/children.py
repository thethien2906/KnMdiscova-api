# factories/children.py
import factory
import random
from factory import fuzzy
from datetime import date, timedelta
from django.utils import timezone

from children.models import Child
from parents.models import Parent
from .base import (
    BaseFactory,
    TimestampMixin,
    RandomChoiceMixin,
    AgeCalculatorMixin,
    ConsentFormsMixin,
    generate_realistic_height_weight
)
from .parents import ParentWithUserFactory, CompletedParentProfileFactory


class ChildFactory(BaseFactory, TimestampMixin, AgeCalculatorMixin):
    """
    Factory for creating Child instances
    """

    class Meta:
        model = Child
        django_get_or_create = ('parent', 'first_name', 'date_of_birth')

    # Parent relationship - will be set by subclasses or overridden
    parent = factory.SubFactory(CompletedParentProfileFactory)

    # Required Demographics
    first_name = factory.Faker('first_name')
    date_of_birth = factory.LazyFunction(
        lambda: AgeCalculatorMixin.generate_date_of_birth_for_age(5, 17)
    )

    # Optional Demographics - realistic distribution
    last_name = factory.LazyAttribute(lambda obj: obj.parent.last_name if obj.parent.last_name else '')

    nickname = factory.Maybe(
        factory.LazyFunction(lambda: random.random() < 0.4),  # 40% have nicknames
        yes_declaration=factory.Faker('first_name'),
        no_declaration=''
    )

    gender = factory.LazyFunction(
        lambda: RandomChoiceMixin.random_choice_weighted([
            ('Male', 0.45),
            ('Female', 0.45),
            ('Non-binary', 0.05),
            ('Prefer not to say', 0.05)
        ])
    )

    # Profile picture - 20% chance
    profile_picture_url = factory.Maybe(
        factory.LazyFunction(lambda: random.random() < 0.2),
        yes_declaration=factory.Faker('image_url', width=150, height=150),
        no_declaration=None
    )

    # Physical Information - set based on age
    @factory.lazy_attribute
    def height_cm(self):
        if self.date_of_birth:
            age = self._calculate_current_age(self.date_of_birth)
            height, _ = generate_realistic_height_weight(age)
            return height if random.random() < 0.7 else None  # 70% have height recorded
        return None

    @factory.lazy_attribute
    def weight_kg(self):
        if self.date_of_birth:
            age = self._calculate_current_age(self.date_of_birth)
            _, weight = generate_realistic_height_weight(age)
            return weight if random.random() < 0.7 else None  # 70% have weight recorded
        return None

    # Health Information - optional fields with realistic distributions
    health_status = factory.Maybe(
        factory.LazyFunction(lambda: random.random() < 0.3),  # 30% have health status noted
        yes_declaration=factory.LazyFunction(
            lambda: RandomChoiceMixin.random_choice_weighted([
                ('Excellent', 0.4),
                ('Good', 0.4),
                ('Fair', 0.15),
                ('Needs attention', 0.05)
            ])
        ),
        no_declaration=''
    )

    medical_history = factory.Maybe(
        factory.LazyFunction(lambda: random.random() < 0.2),  # 20% have medical history
        yes_declaration=factory.LazyFunction(
            lambda: RandomChoiceMixin.random_choice_weighted([
                ('Asthma', 0.3),
                ('Allergies (food)', 0.2),
                ('Allergies (environmental)', 0.2),
                ('ADHD', 0.1),
                ('Diabetes', 0.05),
                ('Previous injuries', 0.1),
                ('Other medical conditions', 0.05)
            ])
        ),
        no_declaration=''
    )

    vaccination_status = factory.LazyFunction(
        lambda: RandomChoiceMixin.random_choice_weighted([
            (True, 0.85),   # 85% up to date
            (False, 0.05),  # 5% not up to date
            (None, 0.1)     # 10% unknown/not recorded
        ])
    )

    # Behavioral & Developmental Information
    emotional_issues = factory.Maybe(
        factory.LazyFunction(lambda: random.random() < 0.25),  # 25% have noted emotional issues
        yes_declaration=factory.LazyFunction(
            lambda: RandomChoiceMixin.random_choice_weighted([
                ('Occasional anxiety', 0.3),
                ('Difficulty with transitions', 0.2),
                ('Mood swings', 0.2),
                ('Separation anxiety', 0.15),
                ('Social anxiety', 0.1),
                ('Other concerns', 0.05)
            ])
        ),
        no_declaration=''
    )

    social_behavior = factory.Maybe(
        factory.LazyFunction(lambda: random.random() < 0.4),  # 40% have social behavior notes
        yes_declaration=factory.LazyFunction(
            lambda: RandomChoiceMixin.random_choice_weighted([
                ('Gets along well with peers', 0.4),
                ('Prefers small groups', 0.2),
                ('Very outgoing and social', 0.2),
                ('Somewhat shy but friendly', 0.1),
                ('Difficulty making friends', 0.05),
                ('Prefers adult company', 0.05)
            ])
        ),
        no_declaration=''
    )

    developmental_concerns = factory.Maybe(
        factory.LazyFunction(lambda: random.random() < 0.15),  # 15% have developmental concerns
        yes_declaration=factory.LazyFunction(
            lambda: RandomChoiceMixin.random_choice_weighted([
                ('Speech development', 0.3),
                ('Motor skills', 0.2),
                ('Academic performance', 0.25),
                ('Attention and focus', 0.2),
                ('Other developmental areas', 0.05)
            ])
        ),
        no_declaration=''
    )

    family_peer_relationship = factory.Maybe(
        factory.LazyFunction(lambda: random.random() < 0.35),  # 35% have relationship notes
        yes_declaration=factory.LazyFunction(
            lambda: RandomChoiceMixin.random_choice_weighted([
                ('Strong family bonds, good peer relationships', 0.4),
                ('Close with family, working on peer relationships', 0.2),
                ('Independent child, selective with friends', 0.2),
                ('Challenges with sibling relationships', 0.1),
                ('Excellent leadership qualities with peers', 0.05),
                ('Needs support building relationships', 0.05)
            ])
        ),
        no_declaration=''
    )

    # Previous Psychology Experience
    has_seen_psychologist = factory.LazyFunction(
        lambda: RandomChoiceMixin.random_bool(0.25)  # 25% have seen a psychologist
    )

    has_received_therapy = factory.LazyFunction(
        lambda: RandomChoiceMixin.random_bool(0.20)  # 20% have received therapy
    )

    # Parental Input
    parental_goals = factory.Maybe(
        factory.LazyFunction(lambda: random.random() < 0.6),  # 60% have parental goals
        yes_declaration=factory.LazyFunction(
            lambda: RandomChoiceMixin.random_choice_weighted([
                ('Improve social confidence', 0.2),
                ('Better emotional regulation', 0.2),
                ('Academic support and motivation', 0.15),
                ('Build independence and responsibility', 0.15),
                ('Develop better communication skills', 0.1),
                ('Address behavioral concerns', 0.1),
                ('Support during family transitions', 0.05),
                ('General developmental support', 0.05)
            ])
        ),
        no_declaration=''
    )

    activity_tips = factory.Maybe(
        factory.LazyFunction(lambda: random.random() < 0.3),  # 30% have activity tips
        yes_declaration=factory.LazyFunction(
            lambda: RandomChoiceMixin.random_choice_weighted([
                ('Enjoys art and creative activities', 0.2),
                ('Responds well to physical activities', 0.2),
                ('Benefits from structured routines', 0.15),
                ('Likes music and rhythm activities', 0.1),
                ('Enjoys puzzle and problem-solving games', 0.1),
                ('Responds to positive reinforcement systems', 0.15),
                ('Benefits from quiet, calm environments', 0.1)
            ])
        ),
        no_declaration=''
    )

    parental_notes = factory.Maybe(
        factory.LazyFunction(lambda: random.random() < 0.4),  # 40% have additional notes
        yes_declaration=factory.Faker('text', max_nb_chars=200),
        no_declaration=''
    )

    # Educational Information
    primary_language = factory.LazyFunction(
        lambda: RandomChoiceMixin.random_choice_weighted([
            ('English', 0.75),
            ('Spanish', 0.1),
            ('French', 0.03),
            ('Mandarin', 0.03),
            ('Portuguese', 0.02),
            ('Arabic', 0.02),
            ('German', 0.01),
            ('Italian', 0.01),
            ('Russian', 0.01),
            ('Other', 0.02)
        ])
    )

    @factory.lazy_attribute
    def school_grade_level(self):
        if self.date_of_birth:
            age = self._calculate_current_age(self.date_of_birth)
            suggestions = self._get_age_appropriate_grades(age)
            if suggestions:
                return random.choice(suggestions)
        return ''

    # Consent Management
    consent_forms_signed = factory.LazyFunction(
        ConsentFormsMixin.generate_consent_forms
    )

    # Helper methods
    def _calculate_current_age(self, date_of_birth):
        """Calculate current age from date of birth"""
        today = date.today()
        age = today.year - date_of_birth.year
        if today.month < date_of_birth.month or (today.month == date_of_birth.month and today.day < date_of_birth.day):
            age -= 1
        return age

    def _get_age_appropriate_grades(self, age):
        """Get age-appropriate grade suggestions"""
        grade_mapping = {
            5: ['Kindergarten', 'Reception', 'Year 1'],
            6: ['Grade 1', 'Year 1', 'Year 2'],
            7: ['Grade 2', 'Year 2', 'Year 3'],
            8: ['Grade 3', 'Year 3', 'Year 4'],
            9: ['Grade 4', 'Year 4', 'Year 5'],
            10: ['Grade 5', 'Year 5', 'Year 6'],
            11: ['Grade 6', 'Year 6', 'Year 7'],
            12: ['Grade 7', 'Year 7', 'Year 8'],
            13: ['Grade 8', 'Year 8', 'Year 9'],
            14: ['Grade 9', 'Year 9', 'Year 10'],
            15: ['Grade 10', 'Year 10', 'Year 11'],
            16: ['Grade 11', 'Year 11', 'Year 12'],
            17: ['Grade 12', 'Year 12', 'Year 13']
        }
        return grade_mapping.get(age, [])


class ChildForExistingParentFactory(ChildFactory):
    """
    Factory for creating children for existing parents
    """

    class Meta:
        model = Child

    # Don't create a new parent, expect it to be provided
    parent = None

    @classmethod
    def create_for_parent(cls, parent, **kwargs):
        """Create a child for an existing parent"""
        if not isinstance(parent, Parent):
            raise ValueError("parent must be a Parent instance")

        return cls.create(parent=parent, **kwargs)

    @classmethod
    def create_batch_for_parent(cls, parent, size, **kwargs):
        """Create multiple children for an existing parent"""
        return [cls.create_for_parent(parent, **kwargs) for _ in range(size)]


class RealisticChildFactory(ChildFactory):
    """
    Factory that creates children with realistic family patterns
    """

    @factory.post_generation
    def apply_family_patterns(obj, create, extracted, **kwargs):
        """Apply realistic family patterns after creation"""
        if not create:
            return

        # Siblings often share characteristics
        if hasattr(obj.parent, 'children') and obj.parent.children.count() > 1:
            siblings = obj.parent.children.exclude(id=obj.id)
            if siblings.exists():
                first_sibling = siblings.first()

                # Share some characteristics with siblings
                if random.random() < 0.3:  # 30% chance to share primary language
                    obj.primary_language = first_sibling.primary_language

                if random.random() < 0.2:  # 20% chance to have shared health concerns
                    if first_sibling.medical_history:
                        obj.medical_history = first_sibling.medical_history

                if random.random() < 0.4:  # 40% chance to share vaccination status
                    obj.vaccination_status = first_sibling.vaccination_status

                obj.save()


class YoungChildFactory(ChildFactory):
    """
    Factory for younger children (ages 5-8)
    """

    date_of_birth = factory.LazyFunction(
        lambda: AgeCalculatorMixin.generate_date_of_birth_for_age(5, 8)
    )

    # Younger children are less likely to have certain characteristics
    has_seen_psychologist = factory.LazyFunction(lambda: RandomChoiceMixin.random_bool(0.15))
    has_received_therapy = factory.LazyFunction(lambda: RandomChoiceMixin.random_bool(0.10))

    developmental_concerns = factory.Maybe(
        factory.LazyFunction(lambda: random.random() < 0.20),  # Higher concern rate for young children
        yes_declaration=factory.LazyFunction(
            lambda: RandomChoiceMixin.random_choice_weighted([
                ('Speech development', 0.4),
                ('Motor skills', 0.3),
                ('Social skills', 0.2),
                ('Behavioral concerns', 0.1)
            ])
        ),
        no_declaration=''
    )


class OlderChildFactory(ChildFactory):
    """
    Factory for older children (ages 13-17)
    """

    date_of_birth = factory.LazyFunction(
        lambda: AgeCalculatorMixin.generate_date_of_birth_for_age(13, 17)
    )

    # Older children more likely to have psychology history
    has_seen_psychologist = factory.LazyFunction(lambda: RandomChoiceMixin.random_bool(0.35))
    has_received_therapy = factory.LazyFunction(lambda: RandomChoiceMixin.random_bool(0.30))

    emotional_issues = factory.Maybe(
        factory.LazyFunction(lambda: random.random() < 0.35),  # Higher rate for adolescents
        yes_declaration=factory.LazyFunction(
            lambda: RandomChoiceMixin.random_choice_weighted([
                ('Anxiety about school/future', 0.3),
                ('Mood changes typical of adolescence', 0.25),
                ('Social pressures and relationships', 0.2),
                ('Identity and self-esteem concerns', 0.15),
                ('Family relationship changes', 0.1)
            ])
        ),
        no_declaration=''
    )

    parental_goals = factory.Maybe(
        factory.LazyFunction(lambda: random.random() < 0.7),  # Higher rate for teens
        yes_declaration=factory.LazyFunction(
            lambda: RandomChoiceMixin.random_choice_weighted([
                ('Support during adolescent transitions', 0.25),
                ('Academic motivation and college prep', 0.2),
                ('Improve family communication', 0.2),
                ('Build independence and life skills', 0.15),
                ('Address behavioral concerns', 0.1),
                ('Support social development', 0.1)
            ])
        ),
        no_declaration=''
    )


class SpecialNeedsChildFactory(ChildFactory):
    """
    Factory for children with special needs or significant developmental concerns
    """

    has_seen_psychologist = True
    has_received_therapy = factory.LazyFunction(lambda: RandomChoiceMixin.random_bool(0.8))

    developmental_concerns = factory.LazyFunction(
        lambda: RandomChoiceMixin.random_choice_weighted([
            ('Autism spectrum disorder', 0.3),
            ('ADHD', 0.25),
            ('Learning disabilities', 0.2),
            ('Speech and language delays', 0.15),
            ('Behavioral disorders', 0.1)
        ])
    )

    medical_history = factory.Maybe(
        factory.LazyFunction(lambda: random.random() < 0.6),
        yes_declaration=factory.LazyFunction(
            lambda: RandomChoiceMixin.random_choice_weighted([
                ('Developmental delays', 0.3),
                ('Neurological conditions', 0.2),
                ('Genetic conditions', 0.15),
                ('Chronic health conditions', 0.2),
                ('Multiple diagnoses', 0.15)
            ])
        ),
        no_declaration=''
    )

    parental_goals = factory.LazyFunction(
        lambda: RandomChoiceMixin.random_choice_weighted([
            ('Support educational accommodations', 0.2),
            ('Improve social skills and peer relationships', 0.2),
            ('Develop coping strategies', 0.15),
            ('Build independence skills', 0.15),
            ('Family support and understanding', 0.1),
            ('Transition planning', 0.1),
            ('Behavioral management', 0.1)
        ])
    )

    # Higher chance of having activity tips and notes
    activity_tips = factory.Maybe(
        factory.LazyFunction(lambda: random.random() < 0.7),
        yes_declaration=factory.LazyFunction(
            lambda: RandomChoiceMixin.random_choice_weighted([
                ('Benefits from sensory activities', 0.2),
                ('Structured routines and clear expectations', 0.2),
                ('Visual supports and social stories', 0.15),
                ('Physical activity for regulation', 0.15),
                ('Quiet spaces for breaks', 0.1),
                ('Special interests as motivation', 0.1),
                ('Peer interaction with support', 0.1)
            ])
        ),
        no_declaration=''
    )


class HighAchievingChildFactory(ChildFactory):
    """
    Factory for high-achieving children with different focus areas
    """

    health_status = 'Excellent'
    vaccination_status = True

    parental_goals = factory.LazyFunction(
        lambda: RandomChoiceMixin.random_choice_weighted([
            ('Support academic excellence and enrichment', 0.3),
            ('Balance achievement with social development', 0.2),
            ('Manage perfectionism and pressure', 0.2),
            ('Develop leadership skills', 0.1),
            ('Support creative and artistic talents', 0.1),
            ('Prepare for advanced academic programs', 0.1)
        ])
    )

    activity_tips = factory.Maybe(
        factory.LazyFunction(lambda: random.random() < 0.6),
        yes_declaration=factory.LazyFunction(
            lambda: RandomChoiceMixin.random_choice_weighted([
                ('Enjoys challenging academic activities', 0.25),
                ('Benefits from creative and artistic pursuits', 0.2),
                ('Thrives with independent projects', 0.2),
                ('Enjoys teaching and helping others', 0.15),
                ('Benefits from diverse experiences', 0.1),
                ('Needs balance between achievement and play', 0.1)
            ])
        ),
        no_declaration=''
    )

    emotional_issues = factory.Maybe(
        factory.LazyFunction(lambda: random.random() < 0.2),
        yes_declaration=factory.LazyFunction(
            lambda: RandomChoiceMixin.random_choice_weighted([
                ('Perfectionism and high expectations', 0.4),
                ('Social pressures related to achievement', 0.3),
                ('Anxiety about performance', 0.2),
                ('Difficulty relating to age peers', 0.1)
            ])
        ),
        no_declaration=''
    )


# Batch creation helpers
class ChildBatchFactory:
    """
    Helper class for creating batches of children with different characteristics
    """

    @staticmethod
    def create_realistic_family(parent, num_children=None):
        """
        Create a realistic family structure for a parent
        """
        if num_children is None:
            # Realistic family size distribution
            num_children = RandomChoiceMixin.random_choice_weighted([
                (1, 0.4),  # 40% single child
                (2, 0.4),  # 40% two children
                (3, 0.15), # 15% three children
                (4, 0.04), # 4% four children
                (5, 0.01)  # 1% five children
            ])

        children = []

        for i in range(num_children):
            # Siblings are usually spread out by 1-4 years
            if i == 0:
                # First child - any age
                child = RealisticChildFactory.create(parent=parent)
            else:
                # Subsequent children - younger than previous
                previous_child = children[-1]
                age_gap = random.randint(1, 4)  # 1-4 years apart

                previous_age = previous_child._calculate_current_age(previous_child.date_of_birth)
                new_age = max(5, previous_age - age_gap)  # Don't go below age 5

                new_dob = AgeCalculatorMixin.generate_date_of_birth_for_age(new_age, new_age)
                child = RealisticChildFactory.create(parent=parent, date_of_birth=new_dob)

            children.append(child)

        return children

    @staticmethod
    def create_mixed_children_for_parents(parents):
        """
        Create mixed children for a list of parents
        """
        all_children = []

        for parent in parents:
            # Some parents have no children yet (20%)
            if random.random() < 0.2:
                continue

            family = ChildBatchFactory.create_realistic_family(parent)
            all_children.extend(family)

        return all_children

    @staticmethod
    def create_diverse_population(count=100):
        """
        Create a diverse population of children with various characteristics
        """
        children = []

        # Distribution of child types
        regular_count = int(count * 0.6)      # 60% regular children
        young_count = int(count * 0.15)       # 15% specifically young children
        older_count = int(count * 0.15)       # 15% specifically older children
        special_needs_count = int(count * 0.07) # 7% special needs
        high_achieving_count = count - regular_count - young_count - older_count - special_needs_count

        children.extend(RealisticChildFactory.create_batch(regular_count))
        children.extend(YoungChildFactory.create_batch(young_count))
        children.extend(OlderChildFactory.create_batch(older_count))
        children.extend(SpecialNeedsChildFactory.create_batch(special_needs_count))
        children.extend(HighAchievingChildFactory.create_batch(high_achieving_count))

        return children

    @staticmethod
    def create_test_children():
        """
        Create test children with known data for development
        """
        from .parents import ParentWithUserFactory

        children = []

        # Create test parents first
        test_parent1 = ParentWithUserFactory.create(
            email='testparent_children1@test.com',
            first_name='Test',
            last_name='Parent'
        )

        test_parent2 = ParentWithUserFactory.create(
            email='testparent_children2@test.com',
            first_name='Demo',
            last_name='Parent'
        )

        # Test child 1 - young child with complete profile
        young_child = YoungChildFactory.create(
            parent=test_parent1,
            first_name='Emma',
            last_name='Parent',
            date_of_birth=date(2018, 5, 15),  # Age 6
            gender='Female',
            height_cm=115,
            weight_kg=20,
            school_grade_level='Grade 1',
            primary_language='English'
        )
        children.append(young_child)

        # Test child 2 - older child with some concerns
        older_child = OlderChildFactory.create(
            parent=test_parent2,
            first_name='Alex',
            last_name='Parent',
            date_of_birth=date(2010, 9, 20),  # Age 14
            gender='Male',
            height_cm=165,
            weight_kg=58,
            school_grade_level='Grade 9',
            has_seen_psychologist=True,
            emotional_issues='Mild anxiety about school performance'
        )
        children.append(older_child)

        # Test child 3 - special needs
        special_child = SpecialNeedsChildFactory.create(
            parent=test_parent1,
            first_name='Sam',
            last_name='Parent',
            date_of_birth=date(2016, 3, 10),  # Age 8
            gender='Non-binary',
            developmental_concerns='Autism spectrum disorder',
            has_received_therapy=True
        )
        children.append(special_child)

        return children


# Trait-based factories for specific scenarios
class NewlyRegisteredChildFactory(ChildFactory):
    """
    Factory for children just added to the platform (minimal info)
    """

    # Only basic required information
    last_name = ''
    nickname = ''
    height_cm = None
    weight_kg = None
    health_status = ''
    medical_history = ''
    vaccination_status = None
    emotional_issues = ''
    social_behavior = ''
    developmental_concerns = ''
    family_peer_relationship = ''
    has_seen_psychologist = False
    has_received_therapy = False
    parental_goals = ''
    activity_tips = ''
    parental_notes = ''
    school_grade_level = ''

    # Default consent forms (all pending)
    consent_forms_signed = factory.LazyFunction(
        lambda: {
            consent_type: {
                'granted': False,
                'date_signed': None,
                'parent_signature': None,
                'notes': 'Pending - newly registered',
                'version': '1.0'
            }
            for consent_type in ['service_consent', 'assessment_consent',
                               'communication_consent', 'data_sharing_consent']
        }
    )


class FullyConsentedChildFactory(ChildFactory):
    """
    Factory for children with all consents granted
    """

    consent_forms_signed = factory.LazyFunction(
        lambda: {
            consent_type: {
                'granted': True,
                'date_signed': timezone.now().isoformat(),
                'parent_signature': f"Parent_{random.randint(1000, 9999)}",
                'notes': 'Full consent granted for services',
                'version': '1.0'
            }
            for consent_type in ['service_consent', 'assessment_consent',
                               'communication_consent', 'data_sharing_consent']
        }
    )


# Helper function for external use
def create_realistic_child_population(parents=None, children_per_parent_range=(1, 3)):
    """
    Create a realistic population of children for given parents

    Args:
        parents: List of Parent objects. If None, creates parents too.
        children_per_parent_range: Tuple of (min, max) children per parent

    Returns:
        List of Child objects
    """
    if parents is None:
        from .parents import ParentBatchFactory
        parents = ParentBatchFactory.create_mixed_parents(20)

    all_children = []

    for parent in parents:
        num_children = random.randint(*children_per_parent_range)
        family_children = ChildBatchFactory.create_realistic_family(parent, num_children)
        all_children.extend(family_children)

    return all_children