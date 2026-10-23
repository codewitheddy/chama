from django import forms
from django.core.exceptions import ValidationError
from .models import Investment, InvestmentValuation, InvestmentReturn, InvestmentWithdrawal, InvestmentType, InvestmentCategory


class InvestmentCategoryForm(forms.ModelForm):
    """Form for creating investment categories."""

    class Meta:
        model = InvestmentCategory
        fields = [
            'name',
            'description',
            'icon',
            'color_code',
            'display_order',
            'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Real Estate, Stocks, Fixed Deposits',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Brief description of this category...',
            }),
            'icon': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'bi-briefcase, bi-building, bi-graph-up',
            }),
            'color_code': forms.TextInput(attrs={
                'class': 'form-control form-control-color',
                'type': 'color',
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['description'].required = False
        self.fields['icon'].required = False
        self.fields['color_code'].required = False
        self.fields['is_active'].required = False


class InvestmentTypeForm(forms.ModelForm):
    """Form for creating investment types."""

    class Meta:
        model = InvestmentType
        fields = [
            'name',
            'category',
            'description',
            'expected_return_rate',
            'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Land - Residential Plot, Shares - NSE',
            }),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Brief description of this investment product template...',
            }),
            'expected_return_rate': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': '8.50',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['description'].required = False
        self.fields['is_active'].required = False
        self.fields['category'].queryset = InvestmentCategory.objects.all().order_by('display_order', 'name')
        self.fields['category'].empty_label = '— Select an Investment Category —'
        self.fields['category'].widget.attrs.update({'class': 'form-select'})


class InvestmentForm(forms.ModelForm):
    """Form for creating/editing an investment."""

    class Meta:
        model = Investment
        fields = [
            'investment_type',
            'initial_amount',
            'date_invested',
            'quantity',
            'description',
            'fund_source',
            'fund_source_bank',
            'fund_source_label',
            'payment_type',
            'mpesa_code',
            'certificate_number',
            'document',
            'status',
        ]
        widgets = {
            'investment_type': forms.Select(attrs={'class': 'form-select'}),
            'initial_amount': forms.NumberInput(attrs={
                'class': 'form-control font-monospace',
                'step': '0.01',
                'placeholder': '0.00',
            }),
            'date_invested': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.0001',
                'placeholder': '1.0000',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Property details, plot number, broker info, shares purchase reference, etc.',
            }),
            'fund_source': forms.Select(attrs={'class': 'form-select'}),
            'fund_source_bank': forms.Select(attrs={'class': 'form-select'}),
            'fund_source_label': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Direct Sponsor, External Partner, Grant',
            }),
            'payment_type': forms.RadioSelect(attrs={'class': 'payment-type-radio'}),
            'mpesa_code': forms.TextInput(attrs={
                'class': 'form-control text-uppercase font-monospace',
                'placeholder': 'e.g. QHX4Y2Z1AB or REF-12345',
                'maxlength': '30',
            }),
            'certificate_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Title Deed No. / Share Cert # / Bond No.',
            }),
            'document': forms.FileInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from bank_accounts.models import BankAccount
        
        self.fields['quantity'].required = False
        self.fields['description'].required = False
        self.fields['fund_source_bank'].required = False
        self.fields['fund_source_label'].required = False
        self.fields['mpesa_code'].required = False
        self.fields['certificate_number'].required = False
        self.fields['document'].required = False

        # Format investment types with category hint
        self.fields['investment_type'].queryset = InvestmentType.objects.filter(is_active=True).select_related('category')
        self.fields['investment_type'].label_from_instance = (
            lambda obj: f"{obj.name} ({obj.category.name})" if obj.category else obj.name
        )
        self.fields['investment_type'].empty_label = '— Select Investment Type / Asset —'

        # Format bank accounts with live current balance
        self.fields['fund_source_bank'].queryset = BankAccount.objects.filter(is_active=True)
        self.fields['fund_source_bank'].label_from_instance = (
            lambda obj: f"{obj.bank_name} — {obj.account_name} ({obj.account_number or 'No Acc #'}) [Bal: KES {obj.current_balance:,.2f}]"
        )
        self.fields['fund_source_bank'].empty_label = '— Select Chama Bank Account —'

    def clean(self):
        cleaned_data = super().clean()
        fund_source = cleaned_data.get('fund_source')
        fund_source_bank = cleaned_data.get('fund_source_bank')
        fund_source_label = cleaned_data.get('fund_source_label')
        payment_type = cleaned_data.get('payment_type')
        mpesa_code = cleaned_data.get('mpesa_code', '').strip()
        initial_amount = cleaned_data.get('initial_amount')

        # Validate fund source dependencies
        if fund_source == 'bank_account' and not fund_source_bank:
            self.add_error('fund_source_bank', 'Please select a bank account when fund source is "Bank Account".')
        
        if fund_source == 'other' and not fund_source_label:
            self.add_error('fund_source_label', 'Please provide a description when fund source is "Other".')

        # ── Balance validation on creation (not editing) ──────────────────────
        if not self.instance.pk and initial_amount:
            from utils.financials import get_available_fund_balance
            
            if fund_source == 'group_funds':
                available = get_available_fund_balance()
                if initial_amount > available:
                    self.add_error(
                        'initial_amount',
                        f'Investment amount (KES {initial_amount:,.2f}) exceeds available group fund balance '
                        f'of KES {available:,.2f}. Funds will be verified and deducted upon approval.'
                    )
            
            elif fund_source in ('bank_account', 'bank_transfer') and fund_source_bank:
                available = fund_source_bank.current_balance
                if initial_amount > available:
                    self.add_error(
                        'initial_amount',
                        f'Investment amount (KES {initial_amount:,.2f}) exceeds {fund_source_bank.bank_name} '
                        f'balance of KES {available:,.2f}. Funds will be verified and deducted upon approval.'
                    )

        # Validate Transaction / M-Pesa code
        if payment_type == 'mpesa':
            if not mpesa_code:
                self.add_error('mpesa_code', 'M-Pesa confirmation code is required for M-Pesa payments.')
            elif not mpesa_code.replace(' ', '').isalnum() or len(mpesa_code) < 6:
                self.add_error('mpesa_code', 'Enter a valid M-Pesa code (alphanumeric, at least 6 chars).')
        elif payment_type == 'bank_transfer':
            # For bank transfer, mpesa_code can hold bank transaction reference if provided
            cleaned_data['mpesa_code'] = mpesa_code
        else:
            cleaned_data['mpesa_code'] = ''

        return cleaned_data


class InvestmentValuationForm(forms.ModelForm):
    """Form for recording investment valuations."""

    class Meta:
        model = InvestmentValuation
        fields = [
            'valuation_date',
            'current_value',
            'value_per_unit',
            'notes',
        ]
        widgets = {
            'valuation_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'current_value': forms.NumberInput(attrs={
                'class': 'form-control font-monospace',
                'step': '0.01',
                'placeholder': '0.00',
            }),
            'value_per_unit': forms.NumberInput(attrs={
                'class': 'form-control font-monospace',
                'step': '0.01',
                'placeholder': '0.00 (optional)',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Market conditions, valuation method, appraiser name...',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['value_per_unit'].required = False
        self.fields['notes'].required = False


class InvestmentReturnForm(forms.ModelForm):
    """Form for recording investment returns/dividends/interest."""

    class Meta:
        model = InvestmentReturn
        fields = [
            'return_type',
            'amount',
            'return_date',
            'payment_type',
            'mpesa_code',
            'bank_account',
            'description',
        ]
        widgets = {
            'return_type': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control font-monospace',
                'step': '0.01',
                'placeholder': '0.00',
            }),
            'return_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'payment_type': forms.RadioSelect(attrs={'class': 'payment-type-radio'}),
            'mpesa_code': forms.TextInput(attrs={
                'class': 'form-control text-uppercase font-monospace',
                'placeholder': 'e.g. QHX4Y2Z1AB',
                'maxlength': '30',
            }),
            'bank_account': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'e.g., Annual dividend payout, fixed deposit quarterly interest, rental revenue...',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from bank_accounts.models import BankAccount
        self.fields['mpesa_code'].required = False
        self.fields['bank_account'].required = False
        self.fields['description'].required = False
        self.fields['bank_account'].queryset = BankAccount.objects.filter(is_active=True)
        self.fields['bank_account'].label_from_instance = (
            lambda obj: f"{obj.bank_name} — {obj.account_name} ({obj.account_number or 'No Acc #'}) [Bal: KES {obj.current_balance:,.2f}]"
        )
        self.fields['bank_account'].empty_label = '— Select Deposit Bank Account —'

    def clean(self):
        cleaned_data = super().clean()
        payment_type = cleaned_data.get('payment_type')
        mpesa_code = cleaned_data.get('mpesa_code', '').strip()
        bank_account = cleaned_data.get('bank_account')

        if payment_type == 'mpesa':
            if not mpesa_code:
                self.add_error('mpesa_code', 'M-Pesa confirmation code is required.')
            elif not mpesa_code.replace(' ', '').isalnum() or len(mpesa_code) < 6:
                self.add_error('mpesa_code', 'Enter a valid M-Pesa code (alphanumeric, at least 6 chars).')
        elif payment_type == 'bank_transfer':
            if not bank_account:
                self.add_error('bank_account', 'Please select a receiving bank account for bank transfers.')

        return cleaned_data


class InvestmentWithdrawalForm(forms.ModelForm):
    """Form for recording investment withdrawals/liquidations."""

    class Meta:
        model = InvestmentWithdrawal
        fields = [
            'withdrawal_type',
            'quantity_withdrawn',
            'amount_received',
            'withdrawal_date',
            'payment_type',
            'mpesa_code',
            'bank_account',
            'buyer_name',
            'notes',
        ]
        widgets = {
            'withdrawal_type': forms.Select(attrs={'class': 'form-select'}),
            'quantity_withdrawn': forms.NumberInput(attrs={
                'class': 'form-control font-monospace',
                'step': '0.0001',
                'placeholder': '0.0000',
            }),
            'amount_received': forms.NumberInput(attrs={
                'class': 'form-control font-monospace',
                'step': '0.01',
                'placeholder': '0.00',
            }),
            'withdrawal_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'payment_type': forms.RadioSelect(attrs={'class': 'payment-type-radio'}),
            'mpesa_code': forms.TextInput(attrs={
                'class': 'form-control text-uppercase font-monospace',
                'placeholder': 'e.g. QHX4Y2Z1AB or REF-12345',
                'maxlength': '30',
            }),
            'bank_account': forms.Select(attrs={'class': 'form-select'}),
            'buyer_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Buyer name or purchasing entity (optional)',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Sale terms, conditions, contract references...',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from bank_accounts.models import BankAccount
        self.fields['mpesa_code'].required = False
        self.fields['bank_account'].required = False
        self.fields['buyer_name'].required = False
        self.fields['notes'].required = False
        self.fields['bank_account'].queryset = BankAccount.objects.filter(is_active=True)
        self.fields['bank_account'].label_from_instance = (
            lambda obj: f"{obj.bank_name} — {obj.account_name} ({obj.account_number or 'No Acc #'}) [Bal: KES {obj.current_balance:,.2f}]"
        )
        self.fields['bank_account'].empty_label = '— Select Deposit Bank Account —'

    def clean(self):
        cleaned_data = super().clean()
        withdrawal_type = cleaned_data.get('withdrawal_type')
        quantity_withdrawn = cleaned_data.get('quantity_withdrawn')
        payment_type = cleaned_data.get('payment_type')
        mpesa_code = cleaned_data.get('mpesa_code', '').strip()
        bank_account = cleaned_data.get('bank_account')

        # Validate quantity against investment
        if hasattr(self, 'instance') and hasattr(self.instance, 'investment') and self.instance.investment:
            if quantity_withdrawn and quantity_withdrawn > self.instance.investment.quantity:
                self.add_error('quantity_withdrawn', f'Cannot withdraw more than the total quantity invested ({self.instance.investment.quantity}).')

        if payment_type == 'mpesa':
            if not mpesa_code:
                self.add_error('mpesa_code', 'M-Pesa confirmation code is required.')
        elif payment_type == 'bank_transfer':
            if not bank_account:
                self.add_error('bank_account', 'Please select a receiving bank account for bank transfers.')

        return cleaned_data
