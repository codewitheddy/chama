from django import forms
from .models import Expense, ExpenseCategory


class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Transport, Stationery, Venue Hire',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
                'placeholder': 'Optional description of this category',
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            'category', 'description', 'amount', 'date',
            'receipt_number', 'notes',
            'fund_source', 'fund_source_bank', 'fund_source_label',
        ]
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select', 'id': 'id_category'}),
            'description': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Venue hire for AGM, Printing of minutes',
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0.01', 'placeholder': '0.00',
            }),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'receipt_number': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Receipt / invoice number',
            }),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'fund_source': forms.Select(attrs={
                'class': 'form-select', 'id': 'id_fund_source',
            }),
            'fund_source_bank': forms.Select(attrs={
                'class': 'form-select', 'id': 'id_fund_source_bank',
            }),
            'fund_source_label': forms.TextInput(attrs={
                'class': 'form-control', 'id': 'id_fund_source_label',
                'placeholder': 'e.g. Petty cash, Mpesa till, Donor grant',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = ExpenseCategory.objects.filter(is_active=True).order_by('name')
        self.fields['category'].empty_label = '— Select category —'
        self.fields['fund_source_bank'].required = False
        self.fields['fund_source_label'].required = False
        self.fields['receipt_number'].required = False
        self.fields['notes'].required = False
        try:
            from bank_accounts.models import BankAccount
            self.fields['fund_source_bank'].queryset = (
                BankAccount.objects.filter(is_active=True).order_by('bank_name')
            )
        except Exception:
            pass

    def clean(self):
        cleaned = super().clean()
        fund_source = cleaned.get('fund_source')
        fund_source_bank = cleaned.get('fund_source_bank')
        if fund_source == 'bank_account' and not fund_source_bank:
            self.add_error('fund_source_bank', 'Please select a bank account.')
        return cleaned
