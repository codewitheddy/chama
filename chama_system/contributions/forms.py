from django import forms
from django.core.exceptions import ValidationError
from .models import Contribution
from members.models import Member
from utils.payment_type_mixin import PaymentTypeFormMixin


class ContributionForm(PaymentTypeFormMixin, forms.ModelForm):
    class Meta:
        model = Contribution
        fields = ['member', 'amount', 'date', 'payment_type', 'mpesa_code']
        widgets = {
            'member': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only active members can receive contributions
        self.fields['member'].queryset = Member.objects.filter(is_active=True).order_by('name')
        self._add_payment_type_widgets()

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is None or amount <= 0:
            raise ValidationError('Contribution amount must be greater than zero.')
        return amount

    def clean(self):
        cleaned = super().clean()
        # Block contributions for inactive/exited members
        member = cleaned.get('member')
        if member and not member.is_active:
            raise ValidationError(
                f'{member.name} is no longer an active member and cannot receive contributions.'
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
