# factories/management/commands/generate_load_test_data.py
import random
import time
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, connection
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.conf import settings

from factories.users import UserBatchFactory, ParentUserFactory, PsychologistUserFactory
from factories.parents import ParentBatchFactory, ParentWithUserFactory
from factories.children import ChildBatchFactory

User = get_user_model()


class Command(BaseCommand):
    help = 'Generate large volumes of realistic data for load testing and performance analysis'

    def add_arguments(self, parser):
        # Scale arguments
        parser.add_argument(
            '--scale',
            type=str,
            choices=['small', 'medium', 'large', 'xlarge'],
            default='small',
            help='Predefined scale of data to generate (default: small)'
        )
        parser.add_argument(
            '--users',
            type=int,
            help='Custom number of users to create (overrides scale)'
        )
        parser.add_argument(
            '--max-children-per-parent',
            type=int,
            default=5,
            help='Maximum children per parent (default: 5)'
        )

        # Performance options
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Batch size for bulk operations (default: 100)'
        )
        parser.add_argument(
            '--commit-frequency',
            type=int,
            default=1000,
            help='Commit every N records (default: 1000)'
        )
        parser.add_argument(
            '--no-bulk-create',
            action='store_true',
            help='Disable bulk creation optimizations'
        )

        # Data distribution options
        parser.add_argument(
            '--active-user-ratio',
            type=float,
            default=0.8,
            help='Ratio of active users (default: 0.8)'
        )
        parser.add_argument(
            '--verified-user-ratio',
            type=float,
            default=0.7,
            help='Ratio of verified users (default: 0.7)'
        )
        parser.add_argument(
            '--complete-profile-ratio',
            type=float,
            default=0.5,
            help='Ratio of complete parent profiles (default: 0.5)'
        )

        # Control options
        parser.add_argument(
            '--seed',
            type=int,
            help='Random seed for reproducible data'
        )
        parser.add_argument(
            '--progress-interval',
            type=int,
            default=500,
            help='Show progress every N records (default: 500)'
        )
        parser.add_argument(
            '--skip-children',
            action='store_true',
            help='Skip creating children (faster generation)'
        )
        parser.add_argument(
            '--memory-efficient',
            action='store_true',
            help='Use memory-efficient creation patterns'
        )

    def handle(self, *args, **options):
        # Production safety check
        if hasattr(settings, 'ENVIRONMENT') and settings.ENVIRONMENT == 'production':
            self.stdout.write(self.style.ERROR('WARNING: Load test data generation on PRODUCTION!'))
            confirm = input('Are you sure? Type "GENERATE LOAD DATA" to confirm: ')
            if confirm != 'GENERATE LOAD DATA':
                self.stdout.write(self.style.ERROR('Aborted.'))
                return

        # Set random seed
        if options['seed']:
            random.seed(options['seed'])
            self.stdout.write(self.style.SUCCESS(f'Using random seed: {options["seed"]}'))

        # Determine scale
        scale_configs = {
            'small': {'users': 1000, 'description': '1K users, ~2K children'},
            'medium': {'users': 5000, 'description': '5K users, ~10K children'},
            'large': {'users': 20000, 'description': '20K users, ~40K children'},
            'xlarge': {'users': 50000, 'description': '50K users, ~100K children'}
        }

        if options['users']:
            user_count = options['users']
            scale_description = f'Custom: {user_count} users'
        else:
            scale_config = scale_configs[options['scale']]
            user_count = scale_config['users']
            scale_description = scale_config['description']

        self.stdout.write(f'Generating load test data: {scale_description}')
        self.stdout.write(f'Batch size: {options["batch_size"]}, Commit frequency: {options["commit_frequency"]}\n')

        start_time = time.time()

        try:
            # Calculate user distribution
            parent_count = int(user_count * 0.75)  # 75% parents
            psychologist_count = int(user_count * 0.23)  # 23% psychologists
            admin_count = max(1, user_count - parent_count - psychologist_count)  # Rest admins

            self.stdout.write(f'Distribution: {parent_count} parents, {psychologist_count} psychologists, {admin_count} admins')

            # Track statistics
            stats = {
                'users_created': 0,
                'parents_updated': 0,
                'children_created': 0,
                'batches_processed': 0,
                'start_time': start_time
            }

            # Create users in batches
            self.stdout.write('\n1. Creating users...')
            created_users = self._create_users_in_batches(
                parent_count, psychologist_count, admin_count,
                options, stats
            )

            # Update parent profiles
            self.stdout.write('\n2. Updating parent profiles...')
            parent_users = [u for u in created_users if u.user_type == 'Parent']
            self._update_parent_profiles_in_batches(
                parent_users, options, stats
            )

            # Create children
            if not options['skip_children']:
                self.stdout.write('\n3. Creating children...')
                parents = self._get_parents_for_children(parent_users)
                self._create_children_in_batches(
                    parents, options, stats
                )
            else:
                self.stdout.write('\n3. Skipping children creation')

            # Final statistics
            end_time = time.time()
            total_time = end_time - start_time

            self.stdout.write('\n' + self.style.SUCCESS('Load test data generation complete!'))
            self._print_final_statistics(stats, total_time, options)

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\nGeneration interrupted by user'))
            self._print_partial_statistics(stats, time.time() - start_time)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error generating load test data: {str(e)}'))
            raise CommandError(f'Failed to generate load test data: {str(e)}')

    def _create_users_in_batches(self, parent_count, psychologist_count, admin_count, options, stats):
        """Create users in batches for better performance"""
        all_users = []
        batch_size = options['batch_size']
        progress_interval = options['progress_interval']

        # Create parents
        for i in range(0, parent_count, batch_size):
            batch_count = min(batch_size, parent_count - i)

            if options['memory_efficient']:
                # Create one by one to avoid memory buildup
                batch_users = []
                for _ in range(batch_count):
                    user = ParentUserFactory.create()
                    # Apply status based on ratios
                    if random.random() > options['active_user_ratio']:
                        user.is_active = False
                    if random.random() > options['verified_user_ratio']:
                        user.is_verified = False
                    user.save(update_fields=['is_active', 'is_verified'])
                    batch_users.append(user)
            else:
                # Bulk create for speed
                batch_users = ParentUserFactory.create_batch(batch_count)

                # Update status fields in bulk
                for user in batch_users:
                    if random.random() > options['active_user_ratio']:
                        user.is_active = False
                    if random.random() > options['verified_user_ratio']:
                        user.is_verified = False

                User.objects.bulk_update(batch_users, ['is_active', 'is_verified'], batch_size=100)

            all_users.extend(batch_users)
            stats['users_created'] += len(batch_users)
            stats['batches_processed'] += 1

            if stats['users_created'] % progress_interval == 0:
                self._print_progress('parents', stats['users_created'], parent_count, stats['start_time'])

        # Create psychologists
        for i in range(0, psychologist_count, batch_size):
            batch_count = min(batch_size, psychologist_count - i)

            if options['memory_efficient']:
                batch_users = []
                for _ in range(batch_count):
                    user = PsychologistUserFactory.create()
                    batch_users.append(user)
            else:
                batch_users = PsychologistUserFactory.create_batch(batch_count)

            all_users.extend(batch_users)
            stats['users_created'] += len(batch_users)

        # Create admins
        admin_users = []
        for _ in range(admin_count):
            from factories.users import AdminUserFactory
            admin_user = AdminUserFactory.create()
            admin_users.append(admin_user)

        all_users.extend(admin_users)
        stats['users_created'] += len(admin_users)

        self.stdout.write(self.style.SUCCESS(f'✓ Created {stats["users_created"]} users'))
        return all_users

    def _update_parent_profiles_in_batches(self, parent_users, options, stats):
        """Update parent profiles in batches"""
        batch_size = options['batch_size']
        progress_interval = options['progress_interval']
        complete_profile_ratio = options['complete_profile_ratio']

        for i in range(0, len(parent_users), batch_size):
            batch = parent_users[i:i + batch_size]

            for user in batch:
                try:
                    # Get the parent profile created by signal
                    from parents.models import Parent
                    parent = Parent.objects.get(user=user)

                    # Complete profile based on ratio
                    if random.random() < complete_profile_ratio:
                        # Complete profile
                        parent.first_name = parent.first_name or f'Parent{user.id}'
                        parent.last_name = parent.last_name or f'User{random.randint(1000, 9999)}'
                        parent.phone_number = f'+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}'
                        parent.address_line1 = f'{random.randint(100, 9999)} Test St'
                        parent.city = random.choice(['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix'])
                        parent.state_province = random.choice(['NY', 'CA', 'IL', 'TX', 'AZ'])
                        parent.postal_code = f'{random.randint(10000, 99999)}'
                        parent.country = 'US'
                    else:
                        # Partial profile
                        parent.first_name = parent.first_name or f'Parent{user.id}'
                        if random.random() < 0.7:
                            parent.last_name = f'User{random.randint(1000, 9999)}'
                        if random.random() < 0.5:
                            parent.phone_number = f'+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}'

                    parent.save()
                    stats['parents_updated'] += 1

                except Exception as e:
                    # Skip problematic parents
                    self.stdout.write(f'Warning: Could not update parent for user {user.id}: {e}')
                    continue

            if stats['parents_updated'] % progress_interval == 0:
                self._print_progress('parent profiles', stats['parents_updated'], len(parent_users), stats['start_time'])

        self.stdout.write(self.style.SUCCESS(f'✓ Updated {stats["parents_updated"]} parent profiles'))

    def _get_parents_for_children(self, parent_users):
        """Get parent objects for child creation"""
        from parents.models import Parent

        parent_ids = [user.id for user in parent_users]
        parents = Parent.objects.filter(user_id__in=parent_ids).select_related('user')

        return list(parents)

    def _create_children_in_batches(self, parents, options, stats):
        """Create children in batches"""
        batch_size = options['batch_size']
        progress_interval = options['progress_interval']
        max_children = options['max_children_per_parent']

        # Estimate total children for progress tracking
        estimated_children = len(parents) * 2  # Average 2 children per parent

        for i, parent in enumerate(parents):
            # Some parents don't have children (20%)
            if random.random() < 0.2:
                continue

            # Random number of children (weighted toward 1-2)
            num_children = min(
                max_children,
                random.choices(
                    [1, 2, 3, 4, 5],
                    weights=[40, 35, 15, 7, 3],
                    k=1
                )[0]
            )

            try:
                # Create family using existing factory method
                family_children = ChildBatchFactory.create_realistic_family(parent, num_children)

                # Apply consent patterns efficiently
                for child in family_children:
                    # Random consent approval (60% average)
                    if random.random() < 0.6:
                        consent_types = ['service_consent', 'assessment_consent']
                        for consent_type in consent_types:
                            child.set_consent(
                                consent_type=consent_type,
                                granted=True,
                                parent_signature=f'{parent.first_name} {parent.last_name}',
                                notes='Load test consent'
                            )

                stats['children_created'] += len(family_children)

                # Progress reporting
                if stats['children_created'] % progress_interval == 0:
                    self._print_progress('children', stats['children_created'], estimated_children, stats['start_time'])

            except Exception as e:
                self.stdout.write(f'Warning: Could not create children for parent {parent.id}: {e}')
                continue

        self.stdout.write(self.style.SUCCESS(f'✓ Created {stats["children_created"]} children'))

    def _print_progress(self, entity_type, current, total, start_time):
        """Print progress information"""
        elapsed = time.time() - start_time
        rate = current / elapsed if elapsed > 0 else 0
        percent = (current / total * 100) if total > 0 else 0

        self.stdout.write(
            f'  Progress: {current:,} {entity_type} ({percent:.1f}%) - '
            f'{rate:.1f}/sec - {elapsed:.1f}s elapsed'
        )

    def _print_final_statistics(self, stats, total_time, options):
        """Print final generation statistics"""
        self.stdout.write('\nGeneration Statistics:')
        self.stdout.write(f'  - Total time: {total_time:.2f} seconds')
        self.stdout.write(f'  - Users created: {stats["users_created"]:,}')
        self.stdout.write(f'  - Parent profiles updated: {stats["parents_updated"]:,}')
        self.stdout.write(f'  - Children created: {stats["children_created"]:,}')
        self.stdout.write(f'  - Total records: {stats["users_created"] + stats["children_created"]:,}')
        self.stdout.write(f'  - Batches processed: {stats["batches_processed"]:,}')

        # Performance metrics
        total_records = stats["users_created"] + stats["children_created"]
        if total_time > 0:
            self.stdout.write(f'  - Average rate: {total_records / total_time:.1f} records/second')

        # Memory usage if available
        try:
            import psutil
            import os
            process = psutil.Process(os.getpid())
            memory_mb = process.memory_info().rss / 1024 / 1024
            self.stdout.write(f'  - Peak memory usage: {memory_mb:.1f} MB')
        except ImportError:
            pass

        # Database statistics
        self._print_database_statistics()

    def _print_partial_statistics(self, stats, elapsed_time):
        """Print statistics for interrupted generation"""
        self.stdout.write('\nPartial Generation Statistics:')
        self.stdout.write(f'  - Time elapsed: {elapsed_time:.2f} seconds')
        self.stdout.write(f'  - Users created: {stats["users_created"]:,}')
        self.stdout.write(f'  - Parent profiles updated: {stats["parents_updated"]:,}')
        self.stdout.write(f'  - Children created: {stats["children_created"]:,}')

    def _print_database_statistics(self):
        """Print database table statistics"""
        try:
            with connection.cursor() as cursor:
                # Get table row counts
                tables = [
                    ('users', 'users'),
                    ('parents', 'parents'),
                    ('children', 'children')
                ]

                self.stdout.write('\nDatabase Statistics:')
                for table_name, table_db_name in tables:
                    cursor.execute(f'SELECT COUNT(*) FROM {table_db_name}')
                    count = cursor.fetchone()[0]
                    self.stdout.write(f'  - {table_name.title()}: {count:,} records')

        except Exception as e:
            self.stdout.write(f'Could not retrieve database statistics: {e}')