from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from money_movement.models import MoneyAccount, MoneyTransfer, CashReconciliation, BankReconciliation
from money_movement.services import get_funds_position, get_account_balances
from bank_accounts.models import BankAccount


class MoneyTransferForm(forms.ModelForm):
    require_approval = forms.BooleanField(
        required=False,
        initial=False,
        label="Require Second Officer Signoff",
        help_text="If checked, this transfer will be submitted as 'Pending' awaiting approval from the Chairperson or Secretary."
    )

    class Meta:
        model = MoneyTransfer
        fields = [
            'from_account',
            'to_account',
            'transfer_type',
            'amount',
            'transfer_date',
            'reference',
            'deposited_by',
            'notes',
            'slip_attachment',
        ]
        widgets = {
            'from_account': forms.Select(attrs={'class': 'form-select', 'id': 'id_from_account'}),
            'to_account': forms.Select(attrs={'class': 'form-select', 'id': 'id_to_account'}),
            'transfer_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_transfer_type'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00', 'min': '0.01'}),
            'transfer_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Deposit Slip #, M-Pesa Code, Cheque #'}),
            'deposited_by': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Name of treasurer/member who banked the cash'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Purpose or transaction notes'}),
            'slip_attachment': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        MoneyAccount.get_or_create_default_cash()
        MoneyAccount.get_or_create_default_mpesa()
        MoneyAccount.get_or_create_default_investments()
        MoneyAccount.sync_bank_accounts()

        self.fields['from_account'].queryset = MoneyAccount.objects.filter(is_active=True)
        self.fields['to_account'].queryset = MoneyAccount.objects.filter(is_active=True)

        if not self.initial.get('transfer_date'):
            self.initial['transfer_date'] = timezone.localdate()

    def clean(self):
        cleaned_data = super().clean()
        from_acc = cleaned_data.get('from_account')
        to_acc = cleaned_data.get('to_account')
        amount = cleaned_data.get('amount')
        transfer_type = cleaned_data.get('transfer_type')
        ref = cleaned_data.get('reference')

        if from_acc and to_acc and from_acc == to_acc:
            raise ValidationError("Source and destination cannot be the same account.")

        if amount is not None:
            if amount <= Decimal('0.00'):
                raise ValidationError({'amount': "Amount must be strictly greater than KES 0.00."})

            # Check available balance in source account
            balances = get_account_balances()
            available = balances.get(from_acc.pk, Decimal('0.00')) if from_acc else Decimal('0.00')

            if amount > available:
                raise ValidationError({
                    'amount': (
                        f"Insufficient funds in {from_acc.name}. "
                        f"Available balance is KES {available:,.2f}, but you attempted to transfer KES {amount:,.2f}."
                    )
                })

        # Require reference for banking cash, mpesa, or bank withdrawal
        if transfer_type in [
            MoneyTransfer.TYPE_CASH_TO_BANK,
            MoneyTransfer.TYPE_MPESA_TO_BANK,
            MoneyTransfer.TYPE_BANK_TO_CASH,
            MoneyTransfer.TYPE_MPESA_TO_CASH
        ] and not ref:
            self.add_error('reference', "Reference (e.g. deposit slip #, transaction code, or receipt ref) is required for this transfer type.")

        return cleaned_data


class TransferReversalForm(forms.Form):
    reversal_reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Provide a detailed explanation for reversing this transfer (audit mandatory)...'
        }),
        required=True,
        label="Reason for Reversal",
        help_text="This reason will be recorded in the permanent audit trail."
    )


class CashReconciliationForm(forms.ModelForm):
    class Meta:
        model = CashReconciliation
        fields = [
            'reconciliation_date',
            'notes_1000',
            'notes_500',
            'notes_200',
            'notes_100',
            'notes_50',
            'coins_amount',
            'notes',
        ]
        widgets = {
            'reconciliation_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes_1000': forms.NumberInput(attrs={'class': 'form-control denom-input', 'min': '0', 'data-value': '1000'}),
            'notes_500': forms.NumberInput(attrs={'class': 'form-control denom-input', 'min': '0', 'data-value': '500'}),
            'notes_200': forms.NumberInput(attrs={'class': 'form-control denom-input', 'min': '0', 'data-value': '200'}),
            'notes_100': forms.NumberInput(attrs={'class': 'form-control denom-input', 'min': '0', 'data-value': '100'}),
            'notes_50': forms.NumberInput(attrs={'class': 'form-control denom-input', 'min': '0', 'data-value': '50'}),
            'coins_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.50', 'min': '0.00', 'placeholder': '0.00'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Notes, explanations for variance, or physical count location'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.initial.get('reconciliation_date'):
            self.initial['reconciliation_date'] = timezone.localdate()


class BankReconciliationForm(forms.ModelForm):
    class Meta:
        model = BankReconciliation
        fields = [
            'bank_account',
            'statement_date',
            'statement_balance',
            'unreconciled_items_notes',
            'notes',
        ]
        widgets = {
            'bank_account': forms.Select(attrs={'class': 'form-select'}),
            'statement_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'statement_balance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
            'unreconciled_items_notes': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'List uncredited deposits, outstanding cheques, pending bank fees, etc.'
            }),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'General remarks'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['bank_account'].queryset = BankAccount.objects.filter(is_active=True)
        if not self.initial.get('statement_date'):
            self.initial['statement_date'] = timezone.localdate()
