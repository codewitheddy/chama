#!/usr/bin/env python
"""Fix the do_rollover method in loans/models.py"""
import re
from pathlib import Path

filepath = Path('loans/models.py')
content = filepath.read_text()

# Old method to replace - using exact string match with proper indentation
old_method = '''    def do_rollover(self, duration_months=None):
        """
        Roll over the loan:
        - The outstanding balance becomes the new principal
        - A fresh 10% interest is charged on that balance
        - due_date is extended by duration_months (defaults to original duration)
        - A LoanRollover record is created for audit trail
        """
        import calendar
        from datetime import date
        from django.db import transaction

        outstanding = self.balance
        new_interest = (outstanding * INTEREST_RATE).quantize(Decimal('0.01'))
        new_total = outstanding + new_interest

        months = duration_months or self.duration_months
        base = date.today()
        month = base.month - 1 + months
        year = base.year + month // 12
        month = month % 12 + 1
        day = min(base.day, calendar.monthrange(year, month)[1])
        new_due = date(year, month, day)

        with transaction.atomic():
            # log the rollover before mutating
            LoanRollover.objects.create(
                loan=self,
                balance_before=outstanding,
                new_interest=new_interest,
                new_total=new_total,
                rolled_on=date.today(),
            )
            # update loan in-place — bypass save() recalculation by using update()
            Loan.objects.filter(pk=self.pk).update(
                loan_amount=outstanding,
                interest_amount=new_interest,
                total_payable=new_total,
                amount_paid=Decimal('0.00'),
                due_date=new_due,
                status='active',
                rollover_count=self.rollover_count + 1,
            )
        self.refresh_from_db()'''

new_method = '''    def do_rollover(self, duration_months=None):
        """
        Roll over the loan by creating a new Loan instance:
        - The outstanding balance becomes the new principal on the new loan
        - A fresh 10% interest is charged on that balance
        - due_date is extended by duration_months (defaults to original duration)
        - The old loan is marked as 'rolled_over' and its payment history is preserved
        - A LoanRollover record links the old and new loans for audit trail
        """
        import calendar
        from datetime import date
        from django.db import transaction

        outstanding = self.balance
        if outstanding == 0:
            raise ValueError("Cannot roll over a fully paid loan.")

        new_interest = (outstanding * INTEREST_RATE).quantize(Decimal('0.01'))
        new_total = outstanding + new_interest
        months = duration_months or self.duration_months

        # Calculate new due date from today (not from original date_taken)
        base = date.today()
        month = base.month - 1 + months
        year = base.year + month // 12
        month = month % 12 + 1
        day = min(base.day, calendar.monthrange(year, month)[1])
        new_due = date(year, month, day)

        with transaction.atomic():
            # Create rollover audit record
            rollover = LoanRollover.objects.create(
                loan=self,
                balance_before=outstanding,
                new_interest=new_interest,
                new_total=new_total,
                rolled_on=date.today(),
            )

            # Mark the old loan as rolled_over (preserve its payment history)
            Loan.objects.filter(pk=self.pk).update(
                status='rolled_over',
                rollover_count=self.rollover_count + 1,
            )

            # Create a brand-new loan for the rolled amount
            new_loan = Loan.objects.create(
                member=self.member,
                loan_amount=outstanding,
                duration_months=months,
                date_taken=date.today(),
                due_date=new_due,
                status='active',
                parent_loan=self,
                notes=f"Rolled over from Loan #{self.pk}. " + (self.notes or ''),
            )
            # Link the rollover record to the new loan as well (for forward tracing)
            rollover.new_loan = new_loan
            rollover.save(update_fields=['new_loan'])

        return new_loan'''

if old_method in content:
    content_new = content.replace(old_method, new_method)
    filepath.write_text(content_new)
    print("SUCCESS: do_rollover method updated")
else:
    print("ERROR: Could not find exact match for old method")
    # Show context around where do_rollover appears
    idx = content.find('def do_rollover')
    if idx >= 0:
        print("Found method at position", idx)
        print("Snippet:", content[idx:idx+200])
    else:
        print("Method not found in file")
