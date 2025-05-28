# factories/management/commands/clear_data.py
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.contrib.auth import get_user_model
from django.conf import settings

from children.models import Child
from parents.models import Parent
from users.models import User


class Command(BaseCommand):
    help = 'Clear generated sample data with safety checks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            type=str,
            choices=['all', 'users', 'parents', 'children', 'test'],
            default='all',
            help='Type of data to clear (default: all)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompts'
        )
        parser.add_argument(
            '--exclude-admins',
            action='store_true',
            help='Keep admin users when clearing'
        )
        parser.add_argument(
            '--exclude-verified',
            action='store_true',
            help='Keep verified users when clearing'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )

    def handle(self, *args, **options):
        # Safety check for production
        if hasattr(settings, 'ENVIRONMENT') and settings.ENVIRONMENT == 'production':
            if not options['force']:
                self.stdout.write(self.style.ERROR('WARNING: You are running this on a PRODUCTION environment!'))
                confirm = input('Are you absolutely sure? Type "DELETE PRODUCTION DATA" to confirm: ')
                if confirm != 'DELETE PRODUCTION DATA':
                    self.stdout.write(self.style.ERROR('Aborted.'))
                    return

        clear_type = options['type']
        is_dry_run = options['dry_run']

        self.stdout.write(f'{"[DRY RUN] " if is_dry_run else ""}Analyzing data to clear...\n')

        try:
            with transaction.atomic():
                deletion_stats = {
                    'users': 0,
                    'parents': 0,
                    'children': 0
                }

                # Build querysets based on options
                if clear_type in ['all', 'users', 'test']:
                    user_qs = User.objects.all()

                    if clear_type == 'test':
                        # Only clear test accounts
                        test_emails = [
                            'admin@test.com',
                            'parent@test.com',
                            'parent2@test.com',
                            'parent_incomplete@test.com',
                            'psychologist@test.com',
                            'psychologist2@test.com',
                            'unverified@test.com'
                        ]
                        user_qs = user_qs.filter(email__in=test_emails)
                    else:
                        # Apply exclusions
                        if options['exclude_admins']:
                            user_qs = user_qs.exclude(user_type='Admin')
                        if options['exclude_verified']:
                            user_qs = user_qs.exclude(is_verified=True)

                    deletion_stats['users'] = user_qs.count()

                if clear_type in ['all', 'parents']:
                    parent_qs = Parent.objects.all()

                    if options['exclude_verified']:
                        parent_qs = parent_qs.exclude(user__is_verified=True)

                    deletion_stats['parents'] = parent_qs.count()

                if clear_type in ['all', 'children']:
                    children_qs = Child.objects.all()

                    if options['exclude_verified']:
                        children_qs = children_qs.exclude(parent__user__is_verified=True)

                    deletion_stats['children'] = children_qs.count()

                # Show what will be deleted
                self.stdout.write('Data to be deleted:')
                if clear_type in ['all', 'users', 'test']:
                    self.stdout.write(f'  - Users: {deletion_stats["users"]}')
                if clear_type in ['all', 'parents']:
                    self.stdout.write(f'  - Parent profiles: {deletion_stats["parents"]}')
                if clear_type in ['all', 'children']:
                    self.stdout.write(f'  - Children: {deletion_stats["children"]}')

                total_records = sum(deletion_stats.values())

                if total_records == 0:
                    self.stdout.write(self.style.WARNING('\nNo data matches the criteria. Nothing to delete.'))
                    return

                # Confirmation
                if not options['force'] and not is_dry_run:
                    self.stdout.write(f'\nTotal records to delete: {total_records}')
                    confirm = input('Are you sure you want to proceed? Type "yes" to confirm: ')
                    if confirm.lower() != 'yes':
                        self.stdout.write(self.style.ERROR('Aborted.'))
                        return

                if is_dry_run:
                    self.stdout.write(self.style.WARNING('\n[DRY RUN] No data was actually deleted.'))
                    # Rollback transaction to ensure nothing is saved
                    raise Exception('Dry run - rolling back')

                # Perform deletion
                self.stdout.write('\nDeleting data...')

                # Delete in correct order due to foreign keys
                if clear_type in ['all', 'children']:
                    deleted_children = children_qs.delete()[0]
                    self.stdout.write(self.style.SUCCESS(f'✓ Deleted {deleted_children} children'))

                if clear_type in ['all', 'parents']:
                    # Note: This will cascade delete associated children
                    deleted_parents = parent_qs.delete()[0]
                    self.stdout.write(self.style.SUCCESS(f'✓ Deleted {deleted_parents} parent profiles'))

                if clear_type in ['all', 'users', 'test']:
                    # Note: This will cascade delete associated parents and children
                    deleted_users = user_qs.delete()[0]
                    self.stdout.write(self.style.SUCCESS(f'✓ Deleted {deleted_users} users'))

                self.stdout.write(self.style.SUCCESS('\nData cleared successfully!'))

        except Exception as e:
            if is_dry_run and str(e) == 'Dry run - rolling back':
                # This is expected for dry run
                pass
            else:
                self.stdout.write(self.style.ERROR(f'Error clearing data: {str(e)}'))
                raise CommandError(f'Failed to clear data: {str(e)}')