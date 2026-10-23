from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from django.utils import timezone
from .models import YearEndWithdrawal, MemberInterestShare, YearEndMemberStatus


class YearEndWithdrawalForm(forms.ModelForm):
    include_loan_interest = forms.BooleanField(
        required=False,
        initial=True,
        label='Include Loan Interest',
        help_text='Interest earned and collected from member loans.',
    )
    include_penalties = forms.BooleanField(
        required=False,
        initial=True,
        label='Include Penalties & Fines',
        help_text='Late attendance, meeting absent & loan default fines paid.',
    )
    include_other_income = forms.BooleanField(
        required=False,
        initial=False,
        label='Include Other / Miscellaneous Income',
        help_text='External income, grants & bank interest (uncheck to accumulate for next year).',
    )
    include_registration_fees = forms.BooleanField(
        required=False,
        initial=False,
        label='Include Registration Fees',
        help_text='Member entrance fees (uncheck to accumulate in Registration Fee Fund).',
    )
    include_investment_returns = forms.BooleanField(
        required=False,
        initial=True,
        label='Include Investment Returns',
        help_text='Dividends & income received from group investment projects.',
    )
    deduct_expenses = forms.BooleanField(
        required=False,
        initial=True,
        label='Deduct Group Fund Expenses',
        help_text='Subtract operational expenses paid from group funds from the profit pool.',
    )

    class Meta:
        model = YearEndWithdrawal
        fields = [
            'financial_year',
            'date',
            'include_loan_interest',
            'include_penalties',
            'include_other_income',
            'include_registration_fees',
            'include_investment_returns',
            'deduct_expenses',
            'notes',
        ]
        widgets = {
            'financial_year': forms.NumberInput(attrs={'class': 'form-control'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Optional notes regarding this annual distribution event...'}),
            'include_loan_interest': forms.CheckboxInput(attrs={'class': 'form-check-input revenue-stream-checkbox', 'data-stream': 'loan_interest'}),
            'include_penalties': forms.CheckboxInput(attrs={'class': 'form-check-input revenue-stream-checkbox', 'data-stream': 'penalties'}),
            'include_other_income': forms.CheckboxInput(attrs={'class': 'form-check-input revenue-stream-checkbox', 'data-stream': 'other_income'}),
            'include_registration_fees': forms.CheckboxInput(attrs={'class': 'form-check-input revenue-stream-checkbox', 'data-stream': 'registration_fees'}),
            'include_investment_returns': forms.CheckboxInput(attrs={'class': 'form-check-input revenue-stream-checkbox', 'data-stream': 'investment_returns'}),
            'deduct_expenses': forms.CheckboxInput(attrs={'class': 'form-check-input revenue-stream-checkbox', 'data-stream': 'expenses'}),
        }

    def clean_financial_year(self):
        year = self.cleaned_data.get('financial_year')
        if year:
            qs = YearEndWithdrawal.objects.filter(financial_year=year)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    f'A year-end withdrawal for {year} has already been recorded.'
                )
        return year


# Inline formset — one row per member for interest share amounts
MemberInterestShareFormSet = inlineformset_factory(
    YearEndWithdrawal,
    MemberInterestShare,
    fields=['member', 'amount'],
    extra=0,
    can_delete=False,
    widgets={
        'member': forms.Select(attrs={'class': 'form-select form-select-sm'}),
        'amount': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01'}),
    },
)

# Inline formset — one row per member for continuing/exiting status
YearEndMemberStatusFormSet = inlineformset_factory(
    YearEndWithdrawal,
    YearEndMemberStatus,
    fields=['member', 'status'],
    extra=0,
    can_delete=False,
    widgets={
        'member': forms.Select(attrs={'class': 'form-select form-select-sm'}),
        'status': forms.Select(attrs={'class': 'form-select form-select-sm'}),
    },
)
