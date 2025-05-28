# factories/management/commands/generate_test_data.py
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import date

from factories.users import UserBatchFactory, ParentUserFactory, PsychologistUserFactory, AdminUserFactory
from factories.parents import ParentWithUserFactory, CompletedParentProfileFactory
from factories.children import YoungChildFactory, OlderChildFactory, SpecialNeedsChildFactory

User = get_user_model()


class Command(BaseCommand):
    help = 'Generate fixed test data with known credentials for development'

    def add_arguments(self, parser):
        parser.add_argument(
            '--password',
            type=str,
            default='testpass123',
            help='Password for all test accounts (default: testpass123)'
        )
        parser.add_argument(
            '--clear-existing',
            action='store_true',
            help='Clear existing test accounts before creating new ones'
        )

    def handle(self, *args, **options):
        test_password = options['password']

        self.stdout.write('Creating test data with known credentials...\n')

        try:
            with transaction.atomic():
                # Clear existing test accounts if requested
                if options['clear_existing']:
                    self.stdout.write('Clearing existing test accounts...')
                    test_emails = [
                        'admin@test.com',
                        'parent@test.com',
                        'parent2@test.com',
                        'parent_incomplete@test.com',
                        'psychologist@test.com',
                        'psychologist2@test.com',
                        'unverified@test.com'
                    ]
                    deleted_count = User.objects.filter(email__in=test_emails).delete()[0]
                    self.stdout.write(self.style.SUCCESS(f'✓ Deleted {deleted_count} existing test accounts'))

                created_users = []
                created_parents = []
                created_children = []

                # 1. Create Admin User
                self.stdout.write('Creating admin user...')
                admin_user = AdminUserFactory.create(
                    email='admin@test.com',
                    is_verified=True,
                    is_active=True,
                    is_staff=True,
                    is_superuser=True
                )
                admin_user.set_password(test_password)
                admin_user.save()
                created_users.append(admin_user)
                self.stdout.write(self.style.SUCCESS('✓ Admin: admin@test.com'))

                # 2. Create Verified Parent with Complete Profile
                self.stdout.write('Creating parent with complete profile...')
                parent1 = CompletedParentProfileFactory.create(
                    email='parent@test.com',
                    first_name='John',
                    last_name='Doe',
                    phone_number='+1-555-123-4567',
                    address_line1='123 Test Street',
                    address_line2='Apt 4B',
                    city='Test City',
                    state_province='CA',
                    postal_code='90210',
                    country='US',
                    is_verified=True,
                    is_active=True
                )
                parent1.user.set_password(test_password)
                parent1.user.save()
                created_users.append(parent1.user)
                created_parents.append(parent1)
                self.stdout.write(self.style.SUCCESS('✓ Parent 1: parent@test.com'))

                # 3. Create Second Parent with Multiple Children
                self.stdout.write('Creating parent with multiple children...')
                parent2 = CompletedParentProfileFactory.create(
                    email='parent2@test.com',
                    first_name='Jane',
                    last_name='Smith',
                    phone_number='+1-555-987-6543',
                    city='New York',
                    state_province='NY',
                    country='US',
                    is_verified=True,
                    is_active=True
                )
                parent2.user.set_password(test_password)
                parent2.user.save()
                created_users.append(parent2.user)
                created_parents.append(parent2)
                self.stdout.write(self.style.SUCCESS('✓ Parent 2: parent2@test.com'))

                # 4. Create Parent with Incomplete Profile
                self.stdout.write('Creating parent with incomplete profile...')
                parent3 = ParentWithUserFactory.create(
                    email='parent_incomplete@test.com',
                    first_name='Bob',
                    last_name='',
                    phone_number='',
                    city='',
                    is_verified=True,
                    is_active=True
                )
                parent3.user.set_password(test_password)
                parent3.user.save()
                created_users.append(parent3.user)
                created_parents.append(parent3)
                self.stdout.write(self.style.SUCCESS('✓ Parent 3 (incomplete): parent_incomplete@test.com'))

                # 5. Create Unverified Parent
                self.stdout.write('Creating unverified parent...')
                unverified_parent = ParentWithUserFactory.create(
                    email='unverified@test.com',
                    first_name='Alice',
                    last_name='Unverified',
                    is_verified=False,
                    is_active=True
                )
                unverified_parent.user.set_password(test_password)
                unverified_parent.user.save()
                created_users.append(unverified_parent.user)
                created_parents.append(unverified_parent)
                self.stdout.write(self.style.SUCCESS('✓ Unverified Parent: unverified@test.com'))

                # 6. Create Psychologists
                self.stdout.write('Creating psychologists...')
                psychologist1 = PsychologistUserFactory.create(
                    email='psychologist@test.com',
                    is_verified=True,
                    is_active=True
                )
                psychologist1.set_password(test_password)
                psychologist1.save()
                created_users.append(psychologist1)
                self.stdout.write(self.style.SUCCESS('✓ Psychologist 1: psychologist@test.com'))

                psychologist2 = PsychologistUserFactory.create(
                    email='psychologist2@test.com',
                    is_verified=True,
                    is_active=True
                )
                psychologist2.set_password(test_password)
                psychologist2.save()
                created_users.append(psychologist2)
                self.stdout.write(self.style.SUCCESS('✓ Psychologist 2: psychologist2@test.com'))

                # 7. Create Children for Parents
                self.stdout.write('\nCreating children...')

                # Children for Parent 1
                child1 = YoungChildFactory.create(
                    parent=parent1,
                    first_name='Emma',
                    last_name='Doe',
                    date_of_birth=date(2018, 5, 15),  # Age 6-7
                    gender='Female',
                    height_cm=115,
                    weight_kg=20,
                    school_grade_level='Grade 1',
                    primary_language='English',
                    health_status='Excellent',
                    parental_goals='Improve social confidence'
                )
                # Grant all consents
                for consent_type in ['service_consent', 'assessment_consent', 'communication_consent', 'data_sharing_consent']:
                    child1.set_consent(consent_type, True, 'John Doe', 'Test consent')
                created_children.append(child1)
                self.stdout.write(self.style.SUCCESS(f'  ✓ Child: {child1.full_name} (parent1)'))

                # Children for Parent 2 (multiple)
                child2 = OlderChildFactory.create(
                    parent=parent2,
                    first_name='Michael',
                    last_name='Smith',
                    date_of_birth=date(2010, 9, 20),  # Age 14
                    gender='Male',
                    height_cm=165,
                    weight_kg=58,
                    school_grade_level='Grade 9',
                    has_seen_psychologist=True,
                    emotional_issues='Mild anxiety about school performance',
                    parental_goals='Academic support and stress management'
                )
                # Partial consents
                child2.set_consent('service_consent', True, 'Jane Smith')
                child2.set_consent('assessment_consent', True, 'Jane Smith')
                created_children.append(child2)
                self.stdout.write(self.style.SUCCESS(f'  ✓ Child: {child2.full_name} (parent2)'))

                child3 = SpecialNeedsChildFactory.create(
                    parent=parent2,
                    first_name='Sarah',
                    last_name='Smith',
                    date_of_birth=date(2016, 3, 10),  # Age 8-9
                    gender='Female',
                    developmental_concerns='ADHD',
                    has_received_therapy=True,
                    medical_history='ADHD diagnosed at age 6',
                    parental_goals='Support educational accommodations'
                )
                # No consents yet
                created_children.append(child3)
                self.stdout.write(self.style.SUCCESS(f'  ✓ Child: {child3.full_name} (parent2)'))

                child4 = YoungChildFactory.create(
                    parent=parent2,
                    first_name='Tommy',
                    last_name='Smith',
                    date_of_birth=date(2019, 11, 5),  # Age 5-6
                    gender='Male',
                    school_grade_level='Kindergarten'
                )
                # Full consents
                for consent_type in ['service_consent', 'assessment_consent', 'communication_consent', 'data_sharing_consent']:
                    child4.set_consent(consent_type, True, 'Jane Smith')
                created_children.append(child4)
                self.stdout.write(self.style.SUCCESS(f'  ✓ Child: {child4.full_name} (parent2)'))

                # Child for incomplete parent
                child5 = YoungChildFactory.create(
                    parent=parent3,
                    first_name='Charlie',
                    last_name='Test',
                    date_of_birth=date(2017, 7, 22),  # Age 7-8
                    gender='Male'
                )
                created_children.append(child5)
                self.stdout.write(self.style.SUCCESS(f'  ✓ Child: {child5.full_name} (parent3)'))

                # Summary
                self.stdout.write('\n' + self.style.SUCCESS('Test data generation complete!'))
                self.stdout.write('\nTest Accounts:')
                self.stdout.write(self.style.WARNING(f'Password for all accounts: {test_password}'))
                self.stdout.write('\nAdmin:')
                self.stdout.write('  - admin@test.com (superuser)')
                self.stdout.write('\nParents:')
                self.stdout.write('  - parent@test.com (complete profile, 1 child)')
                self.stdout.write('  - parent2@test.com (complete profile, 3 children)')
                self.stdout.write('  - parent_incomplete@test.com (incomplete profile, 1 child)')
                self.stdout.write('  - unverified@test.com (unverified email, no children)')
                self.stdout.write('\nPsychologists:')
                self.stdout.write('  - psychologist@test.com')
                self.stdout.write('  - psychologist2@test.com')
                self.stdout.write(f'\nTotal: {len(created_users)} users, {len(created_children)} children')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error generating test data: {str(e)}'))
            raise CommandError(f'Failed to generate test data: {str(e)}')