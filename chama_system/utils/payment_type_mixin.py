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


# ── Cross-model M-Pesa code uniqueness check ──────────────────────

def _mpesa_code_already_used(code, exclude_model=None, exclude_pk=None):
    """
    Check whether an M-Pesa code has already been recorded across ALL
    transaction models.  Returns a human-readable description of the
    duplicate, or None if the code is unused.

    exclude_model / exclude_pk: pass the current model class and instance pk
    when editing an existing record so we don't flag it against itself.
    """
    from payments.models import Payment
    from contributions.models import Contribution
    from penalties.models import Penalty
    from welfare.models import WelfareContribution, WelfareDisbursement, WelfareSupportContribution, WelfareExternalSupport

    checks = [
        (Payment,                    'Loan Payment'),
        (Contribution,               'Contribution'),
        (Penalty,                    'Penalty'),
        (WelfareContribution,        'Welfare Contribution'),
        (WelfareDisbursement,        'Welfare Disbursement'),
        (WelfareSupportContribution, 'Welfare Support Contribution'),
        (WelfareExternalSupport,     'External Welfare Support'),
    ]

    for model_cls, label in checks:
        qs = model_cls.objects.filter(mpesa_code=code)
        # When editing, exclude the record being updated
        if exclude_model is not None and model_cls == exclude_model and exclude_pk:
            qs = qs.exclude(pk=exclude_pk)
        match = qs.select_related('member').first() if hasattr(model_cls, 'member') else qs.first()
        if match:
            member_name = getattr(match, 'member', None)
            member_str = f' for {member_name.name}' if member_name else ''
            return f'Code {code} is already recorded as a {label}{member_str}.'

    return None


# ── Form mixin ────────────────────────────────────────────────────

class PaymentTypeFormMixin:
    """
    Form mixin — adds payment_type radio buttons and mpesa_code field,
    with conditional server-side validation including cross-model
    M-Pesa code uniqueness checking.

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
        Validates mpesa_code when payment_type == 'mpesa':
          1. Required check
          2. Format check (alphanumeric, 6–20 chars)
          3. Cross-model uniqueness check

        Returns cleaned_data with mpesa_code normalised to uppercase.
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
                code = mpesa_code.upper()
                # Cross-model uniqueness — exclude self when editing
                exclude_model = getattr(self, '_meta', None) and getattr(self._meta, 'model', None)
                if hasattr(self, 'instance') and self.instance and self.instance.pk:
                    exclude_model = self.instance.__class__
                    exclude_pk = self.instance.pk
                else:
                    exclude_model = None
                    exclude_pk = None

                duplicate = _mpesa_code_already_used(code, exclude_model, exclude_pk)
                if duplicate:
                    self.add_error('mpesa_code', duplicate)
                else:
                    cleaned['mpesa_code'] = code
        else:
            cleaned['mpesa_code'] = ''

        return cleaned
