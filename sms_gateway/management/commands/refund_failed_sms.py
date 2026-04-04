"""
Management command to refund balance for failed SMS messages.

Usage:
    python manage.py refund_failed_sms [--log-id ID]

This command processes all failed SMS messages that have balance_deducted=True
and refunds the deducted amount back to the user's balance.
"""
from django.core.management.base import BaseCommand
from sms_gateway.signals import check_and_refund_failed_sms


class Command(BaseCommand):
    help = 'Refund balance for failed SMS messages'

    def add_arguments(self, parser):
        parser.add_argument(
            '--log-id',
            type=int,
            help='Specific SMS log ID to refund',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be refunded without actually refunding',
        )

    def handle(self, *args, **options):
        log_id = options.get('log_id')
        dry_run = options.get('dry_run')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No actual refunds will be made'))
        
        self.stdout.write('Checking for failed SMS to refund...')
        
        stats = check_and_refund_failed_sms(log_id=log_id)
        
        # Display results
        self.stdout.write(f"\nResults:")
        self.stdout.write(f"  SMS checked: {stats['checked']}")
        self.stdout.write(f"  SMS refunded: {stats['refunded']}")
        self.stdout.write(f"  Total refund amount: ৳{stats['total_refund_amount']:.2f}")
        
        if stats['errors']:
            self.stdout.write(self.style.ERROR(f"\nErrors ({len(stats['errors'])}):"))
            for error in stats['errors']:
                self.stdout.write(self.style.ERROR(f"  - {error}"))
        
        if stats['refunded'] > 0:
            self.stdout.write(self.style.SUCCESS(f'\nSuccessfully refunded {stats["refunded"]} SMS'))
        elif stats['checked'] == 0:
            self.stdout.write(self.style.NOTICE('\nNo failed SMS found with deducted balance'))
        else:
            self.stdout.write(self.style.NOTICE('\nNo refunds were needed'))
