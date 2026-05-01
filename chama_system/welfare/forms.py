from django import forms
from django.core.exceptions import ValidationError
from .models import (
    WelfareContributionRate, WelfareContribution,
    WelfareEvent, WelfareDisbursement, WelfareSupportContribution,
)


class WelfareContributionRateForm(forms.ModelForm):
    class Meta:
        model = WelfareContributionRate
        fields = ['amount', 'effective_date']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'effective_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is None or amount <= 0:
            raise ValidationError('Monthly contribution rate must be greater than zero.')
        return amount


class WelfareContributionForm(forms.ModelForm):
    class Meta:
        model = WelfareContribution
        fields = ['member', 'amount', 'date']
        widgets = {
            'member': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is None or amount <= 0:
            raise ValidationError('Contribution amount must be greater than zero.')
        return amount

    def clean(self):
        cleaned = super().clean()
        amount = cleaned.get('amount')
        date = cleaned.get('date')
        if amount and date:
            rate = WelfareContributionRate.rate_for_period(date.year, date.month)
            if rate is not None and amount != rate.amount:
                raise ValidationError(
                    f'The welfare contribution for {date.strftime("%B %Y")} must be exactly '
                    f'KES {rate.amount:,.2f} (the current monthly rate). '
                    f'You entered KES {amount:,.2f}.'
                )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.month = instance.date.month
        instance.year = instance.date.year
        if commit:
            instance.save()
        return instance


class WelfareEventForm(forms.ModelForm):
    class Meta:
        model = WelfareEvent
        fields = ['beneficiary', 'description', 'date_opened']
        widgets = {
            'beneficiary': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'date_opened': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }


class WelfareDisbursementForm(forms.ModelForm):
    class Meta:
        model = WelfareDisbursement
        fields = ['amount', 'date', 'notes']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, welfare_balance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._welfare_balance = welfare_balance

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is None or amount <= 0:
            raise ValidationError('Disbursement amount must be greater than zero.')
        # When editing, exclude the current disbursement's amount from the balance check
        available = self._welfare_balance
        if available is not None:
            if self.instance and self.instance.pk:
                available = available + self.instance.amount
            if amount > available:
                raise ValidationError(
                    f'Disbursement amount exceeds the available welfare balance '
                    f'of KES {available:,.2f}.'
                )
        return amount


class WelfareSupportContributionForm(forms.ModelForm):
    class Meta:
        model = WelfareSupportContribution
        fields = ['contributor', 'amount', 'date']
        widgets = {
            'contributor': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, event=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._event = event
        if event:
            # Exclude the beneficiary from the contributor dropdown
            self.fields['contributor'].queryset = (
                self.fields['contributor'].queryset.exclude(pk=event.beneficiary_id)
            )

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is None or amount <= 0:
            raise ValidationError('Support contribution amount must be greater than zero.')
        return amount

    def clean(self):
        cleaned = super().clean()
        contributor = cleaned.get('contributor')
        if self._event and contributor and contributor == self._event.beneficiary:
            raise ValidationError(
                'A beneficiary cannot contribute to their own welfare event.'
            )
        return cleaned
