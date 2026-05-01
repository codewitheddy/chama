"""
Reusable model mixin and form mixin for payment_type / mpesa_code fields.
Import into any model or form that records a financial transaction.
"""
import re
from django.db import models
from django import forms
from django.core.exceptions import ValidationError


PAYMENT_TYPE_CHOICES = [
    ('cash',  'Cash'),
    ('mpesa', 'M-Pesa'),
]


# ── Model mixin ───────────────────────────────────────────────────

class PaymentTypeMixin(models.Model):
    """
    Abstract model mixin — adds payment_type and mpesa_code to any model.
    Usage:
        class MyModel(PaymentTypeMixin, models.Model):
            ...
    """
    payment_type = models.CharField(
        max_length=10,
        choices=PAYMENT_TYPE_CHOICES,
        default='cash',
    )
    mpesa_code = models.CharField(
        max_length=20,
        blank=True,
        help_text='M-Pesa confirmation code (required for M-Pesa payments).',
    )

    class Meta:
        abstract = True


# ── Form mixin ────────────────────────────────────────────────────

class PaymentTypeFormMixin:
    """
    Form mixin — adds payment_type radio buttons and mpesa_code field,
    with conditional server-side validation.

    Usage:
        class MyForm(PaymentTypeFormMixin, forms.ModelForm):
            ...
    """

    def _add_payment_type_widgets(self):
        """Call from __init__ after super().__init__() to set up widgets."""
        self.fields['payment_type'].widget = forms.RadioSelect(
            attrs={'class': 'payment-type-radio'}
        )
        self.fields['mpesa_code'].required = False
        self.fields['mpesa_code'].label = 'M-Pesa Confirmation Code'
        self.fields['mpesa_code'].widget = forms.TextInput(attrs={
            'class': 'form-control text-uppercase',
            'placeholder': 'e.g. QHX4Y2Z1AB',
            'maxlength': '20',
            'autocomplete': 'off',
        })

    def clean_payment_type_fields(self):
        """
        Call from clean() to validate mpesa_code when payment_type == 'mpesa'.
        Returns cleaned_data with mpesa_code normalised.
        """
        cleaned = self.cleaned_data
        payment_type = cleaned.get('payment_type')
        mpesa_code = cleaned.get('mpesa_code', '').strip()

        if payment_type == 'mpesa':
            if not mpesa_code:
                self.add_error('mpesa_code', 'M-Pesa confirmation code is required.')
            elif not re.match(r'^[A-Za-z0-9]{6,20}$', mpesa_code):
                self.add_error(
                    'mpesa_code',
                    'Enter a valid M-Pesa code (letters and numbers only, 6–20 characters).'
                )
            else:
                cleaned['mpesa_code'] = mpesa_code.upper()
        else:
            cleaned['mpesa_code'] = ''

        return cleaned
