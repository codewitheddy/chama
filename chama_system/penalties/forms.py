from django import forms
from django.core.exceptions import ValidationError
from .models import Penalty


class PenaltyForm(forms.ModelForm):
    class Meta:
        model = Penalty
        fields = ['member', 'amount', 'date', 'reason']
        widgets = {
            'member': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reason': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Late arrival, Missing meeting...'}),
        }

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is None or amount <= 0:
            raise ValidationError('Penalty amount must be greater than zero.')
        return amount
