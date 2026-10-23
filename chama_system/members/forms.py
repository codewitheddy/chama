from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Member, RegistrationFeePayment, RegistrationFeeRate


class RegistrationFeeRateForm(forms.ModelForm):
    """Form for configuring registration fee rates."""

    class Meta:
        model = RegistrationFeeRate
        fields = ['amount', 'effective_date', 'notes']
        widgets = {
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': '0.00',
            }),
            'effective_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Optional notes on this rate change...',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk and not self.initial.get('effective_date'):
            self.fields['effective_date'].initial = timezone.localdate()

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is None or amount <= 0:
            raise ValidationError('Registration fee rate must be greater than zero.')
        return amount


class RegistrationFeePaymentForm(forms.ModelForm):
    """Form for recording member registration fee payments."""

    class Meta:
        model = RegistrationFeePayment
        fields = ['member', 'amount', 'payment_date', 'payment_method', 'receipt_number', 'notes']
        widgets = {
            'member': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': '0.00',
            }),
            'payment_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'payment_method': forms.Select(attrs={'class': 'form-control'}),
            'receipt_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., RC-2026-001',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Additional notes...',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['receipt_number'].required = False
        self.fields['notes'].required = False


class MemberForm(forms.ModelForm):
    # Registration fee toggle field (not part of the model, but used for workflow)
    registration_fee_paid_toggle = forms.BooleanField(
        required=False,
        label="Has the member paid the registration fee?",
        help_text="Check if the member has already paid the registration fee at signup. If unchecked, you'll be able to add the fee later when they pay.",
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'id': 'regFeeToggle',
        }),
    )

    class Meta:
        model = Member
        fields = [
            'name', 'phone', 'date_joined',
            'photo', 'id_document',
            'next_of_kin_name', 'next_of_kin_phone', 'next_of_kin_relationship',
        ]
        widgets = {
            'name':                    forms.TextInput(attrs={'class': 'form-control'}),
            'phone':                   forms.TextInput(attrs={'class': 'form-control'}),
            'date_joined':             forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'photo':                   forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'id_document':             forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.pdf,image/*'}),
            'next_of_kin_name':        forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full name'}),
            'next_of_kin_phone':       forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 0712 345 678'}),
            'next_of_kin_relationship': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Spouse, Parent, Sibling'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-populate the toggle based on current registration_fee_paid value
        if self.instance and self.instance.pk:
            # On edit: toggle is checked if member has already paid (registration_fee_paid > 0)
            self.fields['registration_fee_paid_toggle'].initial = (
                self.instance.registration_fee_paid and self.instance.registration_fee_paid > 0
            )
        else:
            # On create: default to unchecked
            self.fields['registration_fee_paid_toggle'].initial = False

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo and hasattr(photo, 'size'):
            if photo.size > 5 * 1024 * 1024:
                raise ValidationError('Photo must be smaller than 5 MB.')
        return photo

    def clean_id_document(self):
        doc = self.cleaned_data.get('id_document')
        if doc and hasattr(doc, 'size'):
            if doc.size > 10 * 1024 * 1024:
                raise ValidationError('ID document must be smaller than 10 MB.')
        return doc
