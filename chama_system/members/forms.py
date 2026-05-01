from django import forms
from django.core.exceptions import ValidationError
from .models import Member


class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = ['name', 'phone', 'registration_fee', 'date_joined']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'registration_fee': forms.NumberInput(attrs={'class': 'form-control'}),
            'date_joined': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def clean_registration_fee(self):
        fee = self.cleaned_data.get('registration_fee')
        if fee is not None and fee < 0:
            raise ValidationError('Registration fee cannot be negative.')
        return fee
