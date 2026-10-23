from django import forms
from django.core.exceptions import ValidationError
from .models import (
    WelfareContributionRate, WelfareContribution,
    WelfareEvent, WelfareDisbursement, WelfareSupportContribution,
    WelfareExternalSupport,
)
from utils.payment_type_mixin import PaymentTypeFormMixin


class WelfareContributionRateForm(forms.ModelForm):
    class Meta:
        model = WelfareContributionRate
        fields = ['amount', 'effective_date']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
            'effective_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk and not self.initial.get('effective_date'):
            from django.utils import timezone
            self.fields['effective_date'].initial = timezone.localdate()

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is None or amount <= 0:
            raise ValidationError('Monthly contribution rate must be greater than zero.')
        return amount


class WelfareContributionForm(PaymentTypeFormMixin, forms.ModelForm):
    class Meta:
        model = WelfareContribution
        fields = ['member', 'amount', 'date', 'payment_type', 'mpesa_code']
        widgets = {
            'member': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._add_payment_type_widgets()

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is None or amount <= 0:
            raise ValidationError('Contribution amount must be greater than zero.')
        return amount

    def clean(self):
        cleaned = super().clean()
        amount = cleaned.get('amount')
        date = cleaned.get('date')
        member = cleaned.get('member')

        if amount and date:
            rate = WelfareContributionRate.rate_for_period(date.year, date.month)
            if rate is not None and amount != rate.amount:
                raise ValidationError(
                    f'The welfare contribution for {date.strftime("%B %Y")} must be exactly '
                    f'KES {rate.amount:,.2f} (the current monthly rate). '
                    f'You entered KES {amount:,.2f}.'
                )

        # Prevent duplicate contribution for the same member/month/year
        if member and date:
            qs = WelfareContribution.objects.filter(
                member=member, month=date.month, year=date.year
            )
            # Exclude current instance when editing
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                from datetime import date as dt
                period = dt(date.year, date.month, 1).strftime('%B %Y')
                raise ValidationError(
                    f'{member.name} has already paid the welfare contribution for {period}.'
                )

        cleaned = self.clean_payment_type_fields()
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


class WelfareDisbursementForm(PaymentTypeFormMixin, forms.ModelForm):
    class Meta:
        model = WelfareDisbursement
        fields = ['amount', 'date', 'payment_type', 'mpesa_code', 'notes']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, welfare_balance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._welfare_balance = welfare_balance
        self._add_payment_type_widgets()

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

    def clean(self):
        cleaned = super().clean()
        return self.clean_payment_type_fields()


class WelfareSupportContributionForm(PaymentTypeFormMixin, forms.ModelForm):
    class Meta:
        model = WelfareSupportContribution
        fields = ['contributor', 'amount', 'date', 'payment_type', 'mpesa_code']
        widgets = {
            'contributor': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, event=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._event = event
        self._add_payment_type_widgets()
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
        return self.clean_payment_type_fields()


class WelfareExternalSupportForm(PaymentTypeFormMixin, forms.ModelForm):
    class Meta:
        model = WelfareExternalSupport
        fields = ['supporter_name', 'supporter_phone', 'amount', 'date',
                  'payment_type', 'mpesa_code', 'notes']
        widgets = {
            'supporter_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. John Kamau',
            }),
            'supporter_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. 0712345678 (optional)',
            }),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Optional note (e.g. neighbour, church, employer)',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._add_payment_type_widgets()

    def clean_supporter_name(self):
        name = self.cleaned_data.get('supporter_name', '').strip()
        if not name:
            raise ValidationError('Supporter name is required.')
        return name

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is None or amount <= 0:
            raise ValidationError('Amount must be greater than zero.')
        return amount

    def clean(self):
        cleaned = super().clean()
        return self.clean_payment_type_fields()
