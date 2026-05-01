from django import forms
from django.core.exceptions import ValidationError
from .models import Loan, Collateral, LoanGuarantor
from members.models import Member


DURATION_CHOICES = [(i, f"{i} month{'s' if i > 1 else ''}") for i in range(1, 25)]


class LoanForm(forms.ModelForm):
    duration_months = forms.ChoiceField(
        choices=DURATION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_duration_months'})
    )

    class Meta:
        model = Loan
        fields = ['member', 'loan_amount', 'duration_months', 'date_taken', 'notes']
        widgets = {
            'member': forms.Select(attrs={'class': 'form-select'}),
            'loan_amount': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '100',
                'id': 'id_loan_amount', 'placeholder': '0.00'
            }),
            'date_taken': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean_duration_months(self):
        return int(self.cleaned_data['duration_months'])

    def clean_loan_amount(self):
        amount = self.cleaned_data.get('loan_amount')
        if amount is None or amount <= 0:
            raise ValidationError("Loan amount must be greater than zero.")
        return amount

    def clean(self):
        cleaned = super().clean()
        member = cleaned.get('member')
        if member and not self.instance.pk:
            if Loan.objects.filter(member=member, status__in=['active', 'late']).exists():
                raise ValidationError(
                    f"{member.name} already has an active loan. "
                    "It must be cleared before issuing a new one."
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
            # exclude the borrower and existing guarantors from choices
            existing = loan.guarantors.values_list('guarantor_id', flat=True)
            self.fields['guarantor'].queryset = Member.objects.exclude(
                pk=loan.member_id
            ).exclude(pk__in=existing)

    def clean(self):
        cleaned = super().clean()
        guarantor = cleaned.get('guarantor')
        amount = cleaned.get('amount_guaranteed')
        if self.loan and guarantor and amount:
            if guarantor == self.loan.member:
                raise ValidationError("A member cannot guarantee their own loan.")
            # check guarantor doesn't have an active/late loan themselves
            if Loan.objects.filter(member=guarantor, status__in=['active', 'late']).exists():
                raise ValidationError(
                    f"{guarantor.name} has an active loan and cannot act as guarantor."
                )
        return cleaned


class LoanAdjustForm(forms.ModelForm):
    """
    Extended form used when editing an existing loan.
    Exposes all financially relevant fields so historical/cleared loans
    can be corrected to match the new interest formula.
    """
    duration_months = forms.ChoiceField(
        choices=DURATION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    # Expose penalty months so historical loans can be corrected manually.
    # editable=False on the model field means we must declare it explicitly here.
    late_penalty_months = forms.IntegerField(
        min_value=0,
        required=False,
        initial=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 'step': '1', 'min': '0', 'placeholder': '0'
        }),
        help_text="Number of overdue months penalty has been applied (each = 10% of principal).",
    )

    class Meta:
        model = Loan
        fields = [
            'member', 'loan_amount', 'duration_months', 'date_taken',
            'due_date', 'amount_paid', 'status', 'notes',
        ]
        widgets = {
            'member': forms.Select(attrs={'class': 'form-select'}),
            'loan_amount': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '100', 'placeholder': '0.00'
            }),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'date_taken': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'amount_paid': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'
            }),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean_duration_months(self):
        return int(self.cleaned_data['duration_months'])

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


class CollateralForm(forms.ModelForm):
    class Meta:
        model = Collateral
        fields = ['description', 'estimated_value', 'document']
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Title Deed, Vehicle'}),
            'estimated_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '100', 'placeholder': '0.00'}),
            'document': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }
