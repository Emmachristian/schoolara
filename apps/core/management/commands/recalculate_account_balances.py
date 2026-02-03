# core/management/commands/recalculate_account_balances.py

from django.core.management.base import BaseCommand
from django.db import transaction
from finance.models import Account
from finance.utils import update_account_balance
import logging

logger = logging.getLogger(__name__)

# Usage Examples
#
# 1. Dry Run (Safe Testing)
# python manage.py recalculate_account_balances --dry-run
#
# 2. Update All Active Accounts
# python manage.py recalculate_account_balances
#
# 3. Update Specific Account
# python manage.py recalculate_account_balances --account-number 1000
#
# 4. Update All Assets
# python manage.py recalculate_account_balances --account-type ASSET
#
# 5. Include Inactive Accounts
# python manage.py recalculate_account_balances --include-inactive
#
# 6. Smaller Batches (for large databases)
# python manage.py recalculate_account_balances --batch-size 50

class Command(BaseCommand):
    help = 'Recalculate balances for all accounts based on posted journal entries'

    def add_arguments(self, parser):
        parser.add_argument(
            '--account-number',
            type=str,
            help='Recalculate specific account by account number',
        )
        parser.add_argument(
            '--account-type',
            type=str,
            help='Recalculate accounts of specific type (ASSET, LIABILITY, etc.)',
        )
        parser.add_argument(
            '--include-inactive',
            action='store_true',
            help='Include inactive accounts',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without saving',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of accounts to process in each batch (default: 100)',
        )

    def handle(self, *args, **options):
        # Build queryset
        queryset = Account.objects.all()
        
        if not options['include_inactive']:
            queryset = queryset.filter(is_active=True)
        
        if options['account_number']:
            queryset = queryset.filter(account_number=options['account_number'])
        
        if options['account_type']:
            queryset = queryset.filter(account_type__account_type=options['account_type'])
        
        # Order for consistent processing
        queryset = queryset.order_by('account_number')
        
        total_accounts = queryset.count()
        
        if total_accounts == 0:
            self.stdout.write(self.style.WARNING('No accounts found matching criteria'))
            return
        
        self.stdout.write(
            self.style.SUCCESS(f'Processing {total_accounts} accounts...')
        )
        
        # Track statistics
        stats = {
            'processed': 0,
            'updated': 0,
            'unchanged': 0,
            'errors': 0,
            'total_change': 0,
        }
        
        changes = []
        errors = []
        
        # Process in batches to avoid memory issues
        batch_size = options['batch_size']
        
        for i in range(0, total_accounts, batch_size):
            batch = queryset[i:i + batch_size]
            
            # Process batch in transaction (rollback if dry-run or error)
            with transaction.atomic():
                for account in batch:
                    try:
                        old_balance, new_balance = update_account_balance(account)
                        stats['processed'] += 1
                        
                        if old_balance != new_balance:
                            stats['updated'] += 1
                            change = new_balance - old_balance
                            stats['total_change'] += abs(change)
                            
                            changes.append({
                                'account_number': account.account_number,
                                'name': account.name,
                                'old_balance': old_balance,
                                'new_balance': new_balance,
                                'change': change,
                            })
                            
                            self.stdout.write(
                                f"  ✓ {account.account_number} - {account.name}: "
                                f"{old_balance:,.2f} → {new_balance:,.2f} "
                                f"(Δ {change:+,.2f})"
                            )
                        else:
                            stats['unchanged'] += 1
                    
                    except Exception as e:
                        stats['errors'] += 1
                        error_msg = f"{account.account_number}: {str(e)}"
                        errors.append(error_msg)
                        
                        self.stdout.write(
                            self.style.ERROR(f"  ✗ Error: {error_msg}")
                        )
                        logger.error(
                            f"Error updating account {account.account_number}: {e}",
                            exc_info=True
                        )
                
                # Rollback if dry-run
                if options['dry_run']:
                    transaction.set_rollback(True)
                    self.stdout.write(
                        self.style.WARNING(
                            f'Batch {i//batch_size + 1} processed (DRY RUN - changes not saved)'
                        )
                    )
            
            # Progress update
            progress = min(i + batch_size, total_accounts)
            self.stdout.write(
                f'Progress: {progress}/{total_accounts} accounts processed'
            )
        
        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('SUMMARY'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(f"Total Accounts Processed: {stats['processed']}")
        self.stdout.write(f"Accounts Updated: {stats['updated']}")
        self.stdout.write(f"Accounts Unchanged: {stats['unchanged']}")
        self.stdout.write(f"Errors: {stats['errors']}")
        self.stdout.write(f"Total Balance Change: {stats['total_change']:,.2f}")
        
        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING('\n⚠️  DRY RUN MODE - No changes were saved')
            )
        
        # Show errors summary if any
        if errors:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR('ERRORS:'))
            for error in errors:
                self.stdout.write(self.style.ERROR(f"  - {error}"))
        
        # Export changes to file if requested
        if changes and not options['dry_run']:
            import json
            from django.utils import timezone
            
            filename = f"balance_updates_{timezone.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w') as f:
                json.dump({
                    'timestamp': timezone.now().isoformat(),
                    'stats': stats,
                    'changes': changes,
                    'errors': errors,
                }, f, indent=2, default=str)
            
            self.stdout.write(
                self.style.SUCCESS(f'\n✓ Changes exported to {filename}')
            )