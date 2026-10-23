from django import forms
from django.utils import timezone
from .models import BankAccount, BankBalance


class BankAccountForm(forms.ModelForm):
    class Meta:
        model  = BankAccount
        fields = ['bank_name', 'account_name', 'account_number', 'branch', 'fund_type', 'is_active']
        widgets = {
            'bank_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. KCB, Equity Bank, Co-operative Bank',
            }),
            'account_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Finance Wise Chama Account',
            }),
            'account_number': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Account number (optional)',
            }),
            'branch': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Branch name (optional)',
            }),
            'fund_type': forms.Select(attrs={
                'class': 'form-select',
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['account_number'].required = False
        self.fields['branch'].required = False
        self.fields['fund_type'].required = False
        if not self.instance.pk and not self.initial.get('fund_type'):
            self.fields['fund_type'].initial = BankAccount.FUND_TYPE_GENERAL

    def clean_fund_type(self):
        return self.cleaned_data.get('fund_type') or BankAccount.FUND_TYPE_GENERAL


class BankTopUpForm(forms.Form):
    """Form for recording a top-up (deposit) into a bank account."""
    amount = forms.DecimalField(
        min_value=0.01,
        decimal_places=2,
        label='Top-Up Amount (KES)',
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 'step': '0.01', 'min': '0.01',
            'placeholder': '0.00', 'id': 'id_topup_amount',
        }),
    )
    date = forms.DateField(
        label='Date',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    notes = forms.CharField(
        required=False,
        label='Notes',
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 2,
            'placeholder': 'e.g. Bank transfer from member, interest earned…',
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date'].initial = timezone.localdate()


class BankOpeningBalanceForm(forms.Form):
    """Form to set the opening balance for a new account."""
    opening_balance = forms.DecimalField(
        min_value=0,
        decimal_places=2,
        label='Opening Balance (KES)',
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 'step': '0.01', 'min': '0',
            'placeholder': '0.00',
        }),
    )
    date = forms.DateField(
        label='Date',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    notes = forms.CharField(
        required=False,
        label='Notes',
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 2,
            'placeholder': 'e.g. Account opened, initial deposit from group funds',
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date'].initial = timezone.localdate()


class BankBalanceForm(forms.ModelForm):
    """Legacy snapshot form — kept for backward compatibility."""
    class Meta:
        model  = BankBalance
        fields = ['balance', 'recorded_on', 'notes']
        widgets = {
            'balance': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': '0.00',
            }),
            'recorded_on': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['notes'].required = False
