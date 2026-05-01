from django import forms
from django.core.exceptions import ValidationError
from .models import Penalty
from utils.payment_type_mixin import PaymentTypeFormMixin


class PenaltyForm(PaymentTypeFormMixin, forms.ModelForm):
    class Meta:
        model = Penalty
        fields = ['member', 'reason', 'payment_type', 'mpesa_code', 'amount', 'date']
        widgets = {
            'member': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reason': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Late arrival, Missing meeting...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._add_payment_type_widgets()

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is None or amount <= 0:
            raise ValidationError('Penalty amount must be greater than zero.')
        return amount

    def clean(self):
        cleaned = super().clean()
        return self.clean_payment_type_fields()
