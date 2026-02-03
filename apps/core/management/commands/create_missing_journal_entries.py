# fees/management/commands/create_missing_journal_entries.py

from django.core.management.base import BaseCommand
from django.db import transaction
from fees.models import FeeInvoice
from fees.invoice_generators import UnifiedStudentInvoiceGenerator
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Create journal entries for invoices that are missing them'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--status',
            type=str,
            default='PENDING',
            help='Only process invoices with this status (default: PENDING)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        status_filter = options['status']
        
        # Find invoices without journal entries
        invoices_without_journal = FeeInvoice.objects.filter(
            journal_entry__isnull=True
        )
        
        if status_filter:
            invoices_without_journal = invoices_without_journal.filter(
                status=status_filter
            )
        
        total_count = invoices_without_journal.count()
        
        self.stdout.write(
            self.style.WARNING(
                f"Found {total_count} invoices without journal entries"
            )
        )
        
        if dry_run:
            self.stdout.write(
                self.style.NOTICE("DRY RUN - No changes will be made")
            )
            for invoice in invoices_without_journal[:10]:  # Show first 10
                self.stdout.write(
                    f"  - {invoice.invoice_number} ({invoice.student.get_full_name()}) "
                    f"- {invoice.status} - {invoice.total_amount}"
                )
            if total_count > 10:
                self.stdout.write(f"  ... and {total_count - 10} more")
            return
        
        # Process each invoice
        success_count = 0
        error_count = 0
        errors = []
        
        for invoice in invoices_without_journal:
            try:
                with transaction.atomic():
                    # Create journal entry
                    journal_entry = UnifiedStudentInvoiceGenerator._create_journal_entry(invoice)
                    
                    if journal_entry:
                        # If invoice is already POSTED, post the journal entry too
                        if invoice.status == 'POSTED':
                            journal_entry.post()
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"✓ Created and POSTED journal entry for {invoice.invoice_number}"
                                )
                            )
                        else:
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"✓ Created DRAFT journal entry for {invoice.invoice_number}"
                                )
                            )
                        success_count += 1
                    else:
                        error_msg = f"Failed to create journal entry for {invoice.invoice_number}"
                        errors.append(error_msg)
                        error_count += 1
                        self.stdout.write(self.style.ERROR(f"✗ {error_msg}"))
                        
            except Exception as e:
                error_msg = f"{invoice.invoice_number}: {str(e)}"
                errors.append(error_msg)
                error_count += 1
                logger.error(f"Error creating journal entry for {invoice.invoice_number}: {e}", exc_info=True)
                self.stdout.write(
                    self.style.ERROR(f"✗ Error: {invoice.invoice_number} - {str(e)}")
                )
        
        # Summary
        self.stdout.write("\n" + "="*60)
        self.stdout.write(
            self.style.SUCCESS(f"✓ Successfully created: {success_count}")
        )
        if error_count > 0:
            self.stdout.write(
                self.style.ERROR(f"✗ Errors: {error_count}")
            )
            self.stdout.write("\nError details:")
            for error in errors[:20]:  # Show first 20 errors
                self.stdout.write(f"  - {error}")
        self.stdout.write("="*60)