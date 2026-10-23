from django import forms
from .models import OtherIncome
from bank_accounts.models import BankAccount


class OtherIncomeForm(forms.ModelForm):
    class Meta:
        model = OtherIncome
        fields = [
            'source',
            'category',
            'amount',
            'date',
            'payment_method',
            'bank_account',
            'reference_number',
            'receipt_attachment',
            'description',
        ]
        widgets = {
            'source': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. KCB Fixed Deposit, CIC MMF, CBK T-Bills, Safaricom Dividend',
                'autocomplete': 'off',
            }),
            'category': forms.Select(attrs={
                'class': 'form-select',
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.01',
                'placeholder': '0.00',
            }),
            'date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'payment_method': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_payment_method',
            }),
            'bank_account': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_bank_account',
            }),
            'reference_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Bank Ref #, Cheque #, M-Pesa Code, or Receipt #',
            }),
            'receipt_attachment': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*,.pdf',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional details — interest rate, maturity terms, receipt notes…',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['description'].required = False
        self.fields['reference_number'].required = False
        self.fields['receipt_attachment'].required = False
        self.fields['bank_account'].required = False
        self.fields['bank_account'].queryset = BankAccount.objects.filter(is_active=True)
        self.fields['bank_account'].empty_label = "-- Select Destination Bank Account --"

    def clean(self):
        cleaned_data = super().clean()
        payment_method = cleaned_data.get('payment_method')
        bank_account = cleaned_data.get('bank_account')

        if payment_method in (OtherIncome.PAYMENT_BANK_TRANSFER, OtherIncome.PAYMENT_CHEQUE):
            if not bank_account:
                self.add_error(
                    'bank_account',
                    'Please select the destination bank account for direct bank transfers or cheques.'
                )
        elif payment_method in (OtherIncome.PAYMENT_CASH, OtherIncome.PAYMENT_MPESA):
            cleaned_data['bank_account'] = None

        return cleaned_data
