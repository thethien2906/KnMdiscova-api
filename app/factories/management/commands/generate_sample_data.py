# factories/management/commands/generate_sample_data.py
import random
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from factories.users import UserBatchFactory, ParentUserFactory, PsychologistUserFactory
from factories.parents import ParentBatchFactory
from factories.children import ChildBatchFactory

User = get_user_model()


class Command(BaseCommand):
    help = 'Generate realistic sample data for development and testing'

    def add_arguments(self, parser):
        # Data count arguments
        parser.add_argument(
            '--users',
            type=int,
            default=50,
            help='Number of users to create (default: 50)'
        )
        parser.add_argument(
            '--parent-ratio',
            type=float,
            default=0.75,
            help='Ratio of parents among users (default: 0.75)'
        )
        parser.add_argument(
            '--psychologist-ratio',
            type=float,
            default=0.23,
            help='Ratio of psychologists among users (default: 0.23)'
        )
        parser.add_argument(
            '--children-per-parent',
            type=str,
            default='1-3',
            help='Range of children per parent as "min-max" (default: 1-3)'
        )

        # Data quality arguments
        parser.add_argument(
            '--complete-profiles',
            type=float,
            default=0.4,
            help='Ratio of complete parent profiles (default: 0.4)'
        )
        parser.add_argument(
            '--verified-users',
            type=float,
            default=0.85,
            help='Ratio of verified users (default: 0.85)'
        )
        parser.add_argument(
            '--consent-rate',
            type=float,
            default=0.6,
            help='Average consent approval rate (default: 0.6)'
        )

        # Options
        parser.add_argument(
            '--no-children',
            action='store_true',
            help='Skip creating children'
        )
        parser.add_argument(
            '--seed',
            type=int,
            help='Random seed for reproducible data'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed progress'
        )

    def handle(self, *args, **options):
        # Set random seed if provided
        if options['seed']:
            random.seed(options['seed'])
            self.stdout.write(self.style.SUCCESS(f'Using random seed: {options["seed"]}'))

        # Validate ratios
        total_ratio = options['parent_ratio'] + options['psychologist_ratio']
        if total_ratio > 0.98:  # Leave room for at least 2% admins
            raise CommandError('Parent and psychologist ratios sum to more than 0.98')

        # Parse children range
        try:
            min_children, max_children = map(int, options['children_per_parent'].split('-'))
        except ValueError:
            raise CommandError('Invalid children-per-parent format. Use "min-max" (e.g., "1-3")')

        self.stdout.write('Starting sample data generation...\n')

        try:
            with transaction.atomic():
                # Track created objects
                created_users = []
                created_parents = []
                created_children = []

                # Step 1: Create users
                self.stdout.write('Creating users...')
                user_count = options['users']

                # Calculate counts
                parent_count = int(user_count * options['parent_ratio'])
                psychologist_count = int(user_count * options['psychologist_ratio'])
                admin_count = max(1, user_count - parent_count - psychologist_count)

                if options['verbose']:
                    self.stdout.write(f'  - Parents: {parent_count}')
                    self.stdout.write(f'  - Psychologists: {psychologist_count}')
                    self.stdout.write(f'  - Admins: {admin_count}')

                # Create users by type
                created_users.extend(
                    UserBatchFactory.create_mixed_users(user_count)
                )

                # Apply verification and activity patterns
                for user in created_users:
                    if random.random() < options['verified_users']:
                        user.is_verified = True
                        user.save(update_fields=['is_verified'])

                UserBatchFactory.create_realistic_activity_patterns(created_users)

                self.stdout.write(self.style.SUCCESS(f'✓ Created {len(created_users)} users'))

                # Step 2: Update parent profiles
                self.stdout.write('Updating parent profiles...')
                parent_users = [u for u in created_users if u.user_type == 'Parent']

                # Update parent profiles with realistic data
                created_parents = ParentBatchFactory.create_parents_for_existing_users(parent_users)

                # Apply profile completeness distribution
                complete_count = int(len(created_parents) * options['complete_profiles'])
                incomplete_count = int(len(created_parents) * 0.3)

                # Randomly select parents for complete/incomplete profiles
                random.shuffle(created_parents)

                for i, parent in enumerate(created_parents[:complete_count]):
                    # Complete the profile
                    if not parent.phone_number:
                        parent.phone_number = f'+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}'
                    if not parent.address_line1:
                        parent.address_line1 = f'{random.randint(100, 9999)} Main St'
                    if not parent.city:
                        parent.city = random.choice(['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix'])
                    if not parent.state_province:
                        parent.state_province = random.choice(['NY', 'CA', 'IL', 'TX', 'AZ'])
                    if not parent.postal_code:
                        parent.postal_code = f'{random.randint(10000, 99999)}'
                    parent.save()

                self.stdout.write(self.style.SUCCESS(f'✓ Updated {len(created_parents)} parent profiles'))

                # Step 3: Create children
                if not options['no_children']:
                    self.stdout.write('Creating children...')

                    for parent in created_parents:
                        # Some parents (20%) don't have children yet
                        if random.random() < 0.2:
                            continue

                        num_children = random.randint(min_children, max_children)
                        family_children = ChildBatchFactory.create_realistic_family(parent, num_children)

                        # Apply consent rate
                        for child in family_children:
                            # Update consent forms based on consent rate
                            consent_types = ['service_consent', 'assessment_consent',
                                           'communication_consent', 'data_sharing_consent']

                            for consent_type in consent_types:
                                if random.random() < options['consent_rate']:
                                    child.set_consent(
                                        consent_type=consent_type,
                                        granted=True,
                                        parent_signature=f'{parent.first_name} {parent.last_name}',
                                        notes='Generated consent'
                                    )

                        created_children.extend(family_children)

                    self.stdout.write(self.style.SUCCESS(f'✓ Created {len(created_children)} children'))

                # Summary
                self.stdout.write('\n' + self.style.SUCCESS('Sample data generation complete!'))
                self.stdout.write('\nSummary:')
                self.stdout.write(f'  - Total users: {len(created_users)}')
                self.stdout.write(f'    - Parents: {len(parent_users)}')
                self.stdout.write(f'    - Psychologists: {len([u for u in created_users if u.user_type == "Psychologist"])}')
                self.stdout.write(f'    - Admins: {len([u for u in created_users if u.user_type == "Admin"])}')
                self.stdout.write(f'  - Parent profiles: {len(created_parents)}')
                self.stdout.write(f'    - Complete: ~{complete_count}')
                self.stdout.write(f'    - Incomplete: ~{incomplete_count}')
                self.stdout.write(f'  - Children: {len(created_children)}')

                if options['verbose']:
                    # Additional statistics
                    verified_count = len([u for u in created_users if u.is_verified])
                    active_count = len([u for u in created_users if u.is_active])
                    consented_children = len([c for c in created_children if c.get_consent_status('service_consent')])

                    self.stdout.write('\nDetailed Statistics:')
                    self.stdout.write(f'  - Verified users: {verified_count} ({verified_count/len(created_users)*100:.1f}%)')
                    self.stdout.write(f'  - Active users: {active_count} ({active_count/len(created_users)*100:.1f}%)')
                    self.stdout.write(f'  - Children with service consent: {consented_children} ({consented_children/len(created_children)*100:.1f}%)')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error generating sample data: {str(e)}'))
            raise CommandError(f'Failed to generate sample data: {str(e)}')