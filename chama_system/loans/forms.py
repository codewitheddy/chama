from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Sum
from .models import (
    Loan, Collateral, LoanGuarantor, NonMemberApplicant, LoanProduct, LoanApplication,
    LoanRestructure, RepaymentSchedule,
)
from members.models import Member


DURATION_CHOICES = [(i, f"{i} month{'s' if i > 1 else ''}") for i in range(1, 25)]


class LoanForm(forms.ModelForm):
    duration_months = forms.ChoiceField(
        choices=DURATION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_duration_months'})
    )
    interest_rate = forms.DecimalField(
        min_value=0,
        max_value=100,
        decimal_places=2,
        required=False,
        initial=10,
        label='Interest Rate (%)',
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'min': '0',
            'max': '100',
            'placeholder': '10.00',
            'id': 'id_interest_rate_pct',
        }),
        help_text='Flat: one-off % on principal. Reducing: monthly % on outstanding balance.',
    )

    class Meta:
        model = Loan
        fields = [
            'product', 'borrower_type', 'member', 'non_member',
            'loan_amount', 'loan_type', 'interest_rate',
            'duration_months', 'date_taken', 'notes',
            'fund_source', 'fund_source_bank', 'fund_source_label',
        ]
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select', 'id': 'id_product'}),
            'borrower_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_borrower_type'}),
            'member': forms.Select(attrs={'class': 'form-select', 'id': 'id_member'}),
            'non_member': forms.Select(attrs={'class': 'form-select', 'id': 'id_non_member'}),
            'loan_amount': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '100',
                'id': 'id_loan_amount', 'placeholder': '0.00'
            }),
            'loan_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_loan_type'}),
            'date_taken': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'fund_source': forms.Select(attrs={'class': 'form-select', 'id': 'id_fund_source'}),
            'fund_source_bank': forms.Select(attrs={'class': 'form-select', 'id': 'id_fund_source_bank'}),
            'fund_source_label': forms.TextInput(attrs={
                'class': 'form-control', 'id': 'id_fund_source_label',
                'placeholder': 'e.g. Donor Fund, Savings Account, External Partner',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        is_emergency = False
        if self.instance and self.instance.pk:
            if self.instance.loan_type == 'emergency' or (self.instance.product and (self.instance.product.is_emergency or self.instance.product.interest_type == 'emergency')):
                is_emergency = True
                self.initial['interest_rate'] = 0.0
                self.initial['loan_type'] = 'emergency'
            elif self.instance.interest_rate is not None:
                self.initial['interest_rate'] = float(self.instance.interest_rate) * 100
        else:
            init_loan_type = self.initial.get('loan_type') or (self.data.get('loan_type') if self.data else None)
            init_product = self.initial.get('product') or (self.data.get('product') if self.data else None)
            if init_loan_type == 'emergency':
                is_emergency = True
                self.initial['interest_rate'] = 0.0
            elif init_product:
                try:
                    p = LoanProduct.objects.get(pk=init_product) if isinstance(init_product, (int, str)) and str(init_product).isdigit() else init_product
                    if getattr(p, 'is_emergency', False) or getattr(p, 'interest_type', '') == 'emergency':
                        is_emergency = True
                        self.initial['interest_rate'] = 0.0
                        self.initial['loan_type'] = 'emergency'
                except Exception:
                    pass
            
            if not is_emergency and 'interest_rate' not in self.initial:
                from .models import get_default_interest_rate
                default_rate = get_default_interest_rate()
                self.initial['interest_rate'] = float(default_rate) * 100
        
        # Make loan_type and interest_rate optional (will be filled by clean() for emergency loans)
        self.fields['loan_type'].required = False
        self.fields['interest_rate'].required = False
        
        self.fields['product'].required = False
        self.fields['product'].queryset = LoanProduct.objects.filter(is_active=True).order_by('name')
        self.fields['non_member'].queryset = NonMemberApplicant.objects.filter(
            qualification_status='qualified'
        ).order_by('full_name')
        self.fields['non_member'].required = False
        self.fields['member'].required = False
        self.fields['fund_source_bank'].required = False
        self.fields['fund_source_label'].required = False
        # Populate bank account choices with balance hint
        try:
            from bank_accounts.models import BankAccount
            self.fields['fund_source_bank'].queryset = (
                BankAccount.objects.filter(is_active=True, fund_type=BankAccount.FUND_TYPE_GENERAL).order_by('bank_name')
            )
        except Exception:
            pass

    def clean_duration_months(self):
        return int(self.cleaned_data['duration_months'])

    def clean_interest_rate(self):
        """User enters percentage (e.g. 10); store as decimal (0.10)."""
        pct = self.cleaned_data.get('interest_rate')
        if pct is None:
            return None
        if pct < 0:
            raise forms.ValidationError("Interest rate must be 0 or greater.")
        from decimal import Decimal
        return (Decimal(str(pct)) / Decimal('100')).quantize(Decimal('0.0001'))

    def clean_loan_amount(self):
        amount = self.cleaned_data.get('loan_amount')
        if amount is None or amount <= 0:
            raise ValidationError("Loan amount must be greater than zero.")
        return amount

    def clean(self):
        cleaned = super().clean()
        borrower_type = cleaned.get('borrower_type', 'member')
        member = cleaned.get('member')
        non_member = cleaned.get('non_member')
        product = cleaned.get('product')
        loan_type = cleaned.get('loan_type')
        interest_rate = cleaned.get('interest_rate')

        # Check if this is an emergency loan product
        is_emergency = (
            (product and (product.is_emergency or product.interest_type == 'emergency'))
            or loan_type == 'emergency'
        )

        # For emergency loans: force loan_type to 'emergency' and interest rate to 0%
        if is_emergency:
            # Override the fields for emergency loans
            # Note: fields may be empty because they're disabled in HTML,
            # so we set them here regardless
            cleaned['loan_type'] = 'emergency'
            cleaned['interest_rate'] = Decimal('0.00')
        else:
            # For non-emergency loans: require loan_type and interest_rate
            # These should only be missing if product is_emergency
            if not loan_type:
                raise ValidationError("Please select a Loan Type.")
            if interest_rate is None:
                raise ValidationError("Please enter an Interest Rate.")

        if borrower_type == 'member':
            if not member:
                raise ValidationError("Please select a member.")
            if not self.instance.pk:
                if Loan.objects.filter(member=member, status__in=['active', 'late']).exists():
                    raise ValidationError(
                        f"{member.name} already has an active loan. "
                        "It must be cleared before issuing a new one."
                    )
        else:
            if not non_member:
                raise ValidationError("Please select a qualified non-member applicant.")
            if not non_member.is_qualified:
                raise ValidationError(
                    f"{non_member.full_name} has not been qualified yet. "
                    "The admin must mark them as Qualified before a loan can be issued."
                )
            if not self.instance.pk and non_member.has_active_loan:
                raise ValidationError(
                    f"{non_member.full_name} already has an active loan."
                )
        return cleaned


class LoanGuarantorForm(forms.ModelForm):
    class Meta:
        model = LoanGuarantor
        fields = ['guarantor', 'amount_guaranteed', 'notes']
        widgets = {
            'guarantor': forms.Select(attrs={'class': 'form-select'}),
            'amount_guaranteed': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '100', 'placeholder': '0.00'
            }),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Optional notes'}),
        }

    def __init__(self, *args, loan=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.loan = loan
        self.fields['notes'].required = False
        if loan:
            existing = loan.guarantors.values_list('guarantor_id', flat=True)
            qs = Member.objects.exclude(pk__in=existing)
            if loan.member:
                qs = qs.exclude(pk=loan.member_id)
            self.fields['guarantor'].queryset = qs

    def clean(self):
        cleaned = super().clean()
        guarantor = cleaned.get('guarantor')
        amount = cleaned.get('amount_guaranteed')
        if self.loan and guarantor and amount:
            if self.loan.member and guarantor == self.loan.member:
                raise ValidationError("A member cannot guarantee their own loan.")
            if Loan.objects.filter(member=guarantor, status__in=['active', 'late']).exists():
                raise ValidationError(
                    f"{guarantor.name} has an active loan and cannot act as guarantor."
                )
            g_contrib = guarantor.total_contributions() or Decimal('0')
            if amount > g_contrib:
                raise ValidationError(
                    f"{guarantor.name} can only guarantee up to KES {g_contrib:,.2f} (their total contributions)."
                )

            borrower_contrib = Decimal('0')
            if self.loan.member:
                borrower_contrib = self.loan.member.total_contributions() or Decimal('0')
            shortfall = max(self.loan.loan_amount - borrower_contrib, Decimal('0'))
            target = shortfall if self.loan.member else self.loan.loan_amount

            if target <= 0:
                raise ValidationError(
                    "The borrower's contributions fully cover this loan. No guarantor allocation is permitted."
                )

            if amount > target:
                raise ValidationError(
                    f"Guaranteed amount (KES {amount:,.2f}) cannot exceed the required target of KES {target:,.2f}."
                )

            existing_qs = self.loan.guarantors.all()
            if self.instance and self.instance.pk:
                existing_qs = existing_qs.exclude(pk=self.instance.pk)
            existing_guaranteed = existing_qs.aggregate(t=Sum('amount_guaranteed'))['t'] or Decimal('0')

            if (existing_guaranteed + amount) > target:
                remaining_allowed = max(target - existing_guaranteed, Decimal('0'))
                raise ValidationError(
                    f"Total guaranteed amount (KES {(existing_guaranteed + amount):,.2f}) would exceed the required target of KES {target:,.2f}. "
                    f"Maximum additional guarantee allowed is KES {remaining_allowed:,.2f}."
                )
        return cleaned


class LoanAdjustForm(forms.ModelForm):
    """
    Extended form used when editing an existing loan.
    """
    duration_months = forms.ChoiceField(
        choices=DURATION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    interest_rate = forms.DecimalField(
        min_value=0,
        max_value=100,
        decimal_places=2,
        required=False,
        label='Interest Rate (%)',
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'min': '0',
            'max': '100',
            'placeholder': '10.00',
            'id': 'id_interest_rate_pct',
        }),
        help_text='Flat one-off interest charged on the principal (e.g. enter 10 for 10%).',
    )
    late_penalty_months = forms.IntegerField(
        min_value=0,
        required=False,
        initial=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 'step': '1', 'min': '0', 'placeholder': '0'
        }),
        help_text="Number of overdue months penalty has been applied.",
    )

    class Meta:
        model = Loan
        fields = [
            'member', 'non_member', 'borrower_type',
            'loan_amount', 'loan_type', 'interest_rate', 'duration_months', 'date_taken',
            'due_date', 'amount_paid', 'status', 'notes',
            'fund_source', 'fund_source_bank', 'fund_source_label',
        ]
        widgets = {
            'member': forms.Select(attrs={'class': 'form-select'}),
            'non_member': forms.Select(attrs={'class': 'form-select'}),
            'borrower_type': forms.Select(attrs={'class': 'form-select'}),
            'loan_amount': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '100', 'placeholder': '0.00'
            }),
            'loan_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_loan_type'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'date_taken': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'amount_paid': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'
            }),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'fund_source': forms.Select(attrs={'class': 'form-select', 'id': 'id_fund_source'}),
            'fund_source_bank': forms.Select(attrs={'class': 'form-select', 'id': 'id_fund_source_bank'}),
            'fund_source_label': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'e.g. Donor Fund, External Partner',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            if self.instance.loan_type == 'emergency' or (self.instance.product and (self.instance.product.is_emergency or self.instance.product.interest_type == 'emergency')):
                self.initial['interest_rate'] = 0.0
                self.initial['loan_type'] = 'emergency'
            elif self.instance.interest_rate is not None:
                self.initial['interest_rate'] = float(self.instance.interest_rate) * 100
        self.fields['non_member'].required = False
        self.fields['member'].required = False

    def clean_duration_months(self):
        return int(self.cleaned_data['duration_months'])

    def clean_interest_rate(self):
        pct = self.cleaned_data.get('interest_rate')
        if pct is None:
            return Decimal('0.0000')
        if pct < 0:
            raise forms.ValidationError("Interest rate must be 0 or greater.")
        return (Decimal(str(pct)) / Decimal('100')).quantize(Decimal('0.0001'))

    def clean_loan_amount(self):
        amount = self.cleaned_data.get('loan_amount')
        if amount is None or amount <= 0:
            raise ValidationError("Loan amount must be greater than zero.")
        return amount

    def clean_amount_paid(self):
        amount = self.cleaned_data.get('amount_paid')
        if amount is None or amount < 0:
            raise ValidationError("Amount paid cannot be negative.")
        return amount

    def clean_late_penalty_months(self):
        val = self.cleaned_data.get('late_penalty_months')
        return val if val is not None else 0

    def clean(self):
        cleaned = super().clean()
        loan_type = cleaned.get('loan_type')
        if loan_type == 'emergency':
            cleaned['interest_rate'] = Decimal('0.00')
        elif cleaned.get('interest_rate') is None:
            raise ValidationError("Please enter an Interest Rate.")
        return cleaned


class CollateralForm(forms.ModelForm):
    class Meta:
        model = Collateral
        fields = ['description', 'estimated_value', 'document']
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Title Deed, Vehicle'}),
            'estimated_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '100', 'placeholder': '0.00'}),
            'document': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }


class LoanApplicationForm(forms.ModelForm):
    duration_months = forms.ChoiceField(
        choices=DURATION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = LoanApplication
        fields = ['member', 'loan_amount', 'duration_months', 'reason', 'notes']
        widgets = {
            'member': forms.Select(attrs={'class': 'form-select'}),
            'loan_amount': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '100', 'placeholder': '0.00'
            }),
            'reason': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Explain why the member needs this loan…'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
                'placeholder': 'Optional notes…'
            }),
        }

    def clean_duration_months(self):
        return int(self.cleaned_data['duration_months'])

    def clean_loan_amount(self):
        amount = self.cleaned_data.get('loan_amount')
        if amount is None or amount <= Decimal('0.00'):
            raise ValidationError("Loan amount must be greater than zero.")
        return amount

    def clean(self):
        cleaned = super().clean()
        member = cleaned.get('member')
        if member and not self.instance.pk:
            if Loan.objects.filter(member=member, status__in=['active', 'late']).exists():
                raise ValidationError(
                    f"{member.name} currently has an active or late loan. "
                    "Existing loans must be cleared before applying for a new loan."
                )
        return cleaned


class LoanApplicationReviewForm(forms.Form):
    ACTION_CHOICES = [
        ('approve', 'Approve & Issue Loan'),
        ('reject',  'Reject Application'),
    ]
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input action-radio'})
    )
    date_taken = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    fund_source = forms.ChoiceField(
        choices=Loan.FUND_SOURCE_CHOICES,
        required=False,
        initial='group_funds',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_fund_source'})
    )
    fund_source_bank = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_fund_source_bank'})
    )
    fund_source_label = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Donor Fund'})
    )
    review_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Reason or feedback…'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            from bank_accounts.models import BankAccount
            self.fields['fund_source_bank'].queryset = BankAccount.objects.filter(is_active=True, fund_type=BankAccount.FUND_TYPE_GENERAL).order_by('bank_name')
        except Exception:
            pass

    def clean(self):
        cleaned = super().clean()
        action = cleaned.get('action')
        date_taken = cleaned.get('date_taken')
        review_notes = cleaned.get('review_notes')

        if action == 'approve':
            if not date_taken:
                self.add_error('date_taken', 'Date loan taken is required for approval.')
        elif action == 'reject':
            if not review_notes:
                self.add_error('review_notes', 'Please provide a reason for rejecting the application.')
        return cleaned



class LoanProductForm(forms.ModelForm):
    class Meta:
        model = LoanProduct
        fields = [
            'name', 'description', 'interest_type', 'interest_frequency',
            'interest_rate', 'duration_months', 'min_amount', 'max_amount',
            'is_emergency', 'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'e.g. Emergency Loan'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Brief description of this loan product…'
            }),
            'interest_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_interest_type'}),
            'interest_frequency': forms.Select(attrs={'class': 'form-select'}),
            'interest_rate': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100',
                'placeholder': '0.00 for interest-free'
            }),
            'duration_months': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '1', 'min': '0',
                'placeholder': '0 = no default (agreed at time of issue)'
            }),
            'min_amount': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '100', 'min': '0', 'placeholder': '0.00'
            }),
            'max_amount': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '100', 'min': '0', 'placeholder': '0 = no limit'
            }),
            'is_emergency': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned = super().clean()
        min_amt = cleaned.get('min_amount', 0)
        max_amt = cleaned.get('max_amount', 0)
        if max_amt and min_amt and max_amt < min_amt:
            raise forms.ValidationError('Maximum amount must be greater than or equal to minimum amount.')
        if cleaned.get('interest_type') == 'emergency':
            cleaned['interest_rate'] = Decimal('0.00')
            cleaned['is_emergency'] = True
        return cleaned


class NonMemberApplicantForm(forms.ModelForm):
    """Form to register a new non-member loan applicant."""

    class Meta:
        model = NonMemberApplicant
        fields = [
            'full_name', 'phone', 'id_number', 'email', 'address', 'id_document',
            'employer', 'monthly_income', 'reason_for_loan',
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full legal name'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+254 7XX XXX XXX'}),
            'id_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'National ID / Passport No.'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@example.com'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Physical / postal address'}),
            'id_document': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'employer': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Employer or business name'}),
            'monthly_income': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '100', 'min': '0', 'placeholder': '0.00'
            }),
            'reason_for_loan': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'e.g. Business expansion, medical, school fees…'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = False
        self.fields['address'].required = False
        self.fields['id_document'].required = False
        self.fields['employer'].required = False
        self.fields['reason_for_loan'].required = False


class NonMemberQualifyForm(forms.ModelForm):
    """Used by admin/treasurer to set qualification status and add notes."""

    class Meta:
        model = NonMemberApplicant
        fields = ['qualification_status', 'qualification_notes']
        widgets = {
            'qualification_status': forms.Select(attrs={'class': 'form-select'}),
            'qualification_notes': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 4,
                'placeholder': 'Describe the assessment outcome, any conditions, concerns, etc.',
            }),
        }

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get('qualification_status')
        notes = cleaned.get('qualification_notes', '').strip()
        if status == 'disqualified' and not notes:
            raise ValidationError('Please provide notes explaining why this applicant was disqualified.')
        return cleaned


class LoanRestructureRequestForm(forms.ModelForm):
    new_term_months = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=60,
        label='New Term (Months)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 6', 'id': 'id_new_term_months'}),
        help_text='Required for Term Extension, Rate Adjustment, and Consolidation.'
    )
    new_rate = forms.DecimalField(
        required=False,
        min_value=Decimal('0.00'),
        max_value=Decimal('100.00'),
        decimal_places=2,
        label='New Interest Rate (%)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g. 5.00', 'id': 'id_new_rate'}),
        help_text='Leave empty to retain the current loan rate.'
    )
    moratorium_months = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=12,
        label='Moratorium Period (Months)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 2', 'id': 'id_moratorium_months'}),
        help_text='Freeze duration before regular payments resume.'
    )
    accrue_interest = forms.BooleanField(
        required=False,
        label='Accrue interest during freeze?',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_accrue_interest'}),
        help_text='Check if interest should continue to accumulate during the moratorium period.'
    )
    remaining_months = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=60,
        label='Post-Moratorium Repayment Months',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 4', 'id': 'id_remaining_months'}),
        help_text='Repayment window once the moratorium period ends.'
    )
    consolidated_loans = forms.ModelMultipleChoiceField(
        queryset=Loan.objects.none(),
        required=False,
        label='Additional Loans to Consolidate',
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'id': 'id_consolidated_loans'}),
        help_text='Select other active loans for this member to merge into this restructure.'
    )

    class Meta:
        model = LoanRestructure
        fields = ['restructure_type', 'reason']
        widgets = {
            'restructure_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_restructure_type'}),
            'reason': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Explain why the member is unable to meet the original repayment schedule and the proposed relief...',
                'id': 'id_reason'
            }),
        }

    def __init__(self, *args, loan=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.loan = loan or getattr(self.instance, 'loan', None)
        if self.loan:
            if self.loan.member:
                self.fields['consolidated_loans'].queryset = Loan.objects.filter(
                    member=self.loan.member,
                    status__in=['active', 'late']
                ).exclude(pk=self.loan.pk)
            elif self.loan.non_member:
                self.fields['consolidated_loans'].queryset = Loan.objects.filter(
                    non_member=self.loan.non_member,
                    status__in=['active', 'late']
                ).exclude(pk=self.loan.pk)

    def clean(self):
        cleaned_data = super().clean()
        if not self.loan:
            raise ValidationError("A loan must be specified for the restructure request.")

        if self.loan.status in ('cleared', 'written_off'):
            raise ValidationError(f"Cannot restructure a loan that is already {self.loan.get_status_display().lower()}.")

        if self.loan.balance <= Decimal('0.00'):
            raise ValidationError("Cannot restructure a loan with zero outstanding balance.")

        from loans.restructuring import check_max_restructures_limit
        check_max_restructures_limit(self.loan)

        rtype = cleaned_data.get('restructure_type')
        if rtype == 'TERM_EXTENSION' and not cleaned_data.get('new_term_months'):
            self.add_error('new_term_months', 'Please specify the new repayment duration in months.')

        if rtype == 'MORATORIUM':
            if not cleaned_data.get('moratorium_months'):
                self.add_error('moratorium_months', 'Please specify the number of freeze months.')
            if not cleaned_data.get('remaining_months'):
                cleaned_data['remaining_months'] = self.loan.duration_months

        if rtype == 'CONSOLIDATION':
            if not cleaned_data.get('consolidated_loans'):
                self.add_error('consolidated_loans', 'Please select at least one additional loan to consolidate.')
            if not cleaned_data.get('new_term_months'):
                self.add_error('new_term_months', 'Please specify the new consolidated term duration.')

        return cleaned_data


class LoanRestructureRejectForm(forms.Form):
    rejection_reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 3,
            'placeholder': 'Explain why this restructure request is rejected...',
            'id': 'id_rejection_reason'
        }),
        required=True,
        label='Reason for Rejection'
    )

