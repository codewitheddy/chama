from django import forms
from django.core.exceptions import ValidationError
from .models import Payment
from loans.models import Loan


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['loan', 'amount', 'date', 'payment_type', 'mpesa_code', 'notes']
        widgets = {
            'loan': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'placeholder': '0.00',
            }),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'payment_type': forms.RadioSelect(attrs={'class': 'payment-type-radio'}),
            'mpesa_code': forms.TextInput(attrs={
                'class': 'form-control text-uppercase',
                'placeholder': 'e.g. QHX4Y2Z1AB',
                'maxlength': '20',
                'autocomplete': 'off',
            }),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        loan_id = kwargs.pop('loan_id', None)
        super().__init__(*args, **kwargs)
        self.fields['loan'].queryset = Loan.objects.filter(
            status__in=['active', 'late']
        ).select_related('member')
        self.fields['loan'].label_from_instance = lambda obj: (
            f"{obj.member.name} — KES {obj.loan_amount} (Balance: KES {obj.balance})"
        )
        self.fields['mpesa_code'].required = False
        self.fields['mpesa_code'].label = 'M-Pesa Confirmation Code'
        if loan_id:
            try:
                self.fields['loan'].initial = Loan.objects.get(pk=loan_id)
            except Loan.DoesNotExist:
                pass

    def clean(self):
        cleaned = super().clean()
        loan = cleaned.get('loan')
        amount = cleaned.get('amount')
        payment_type = cleaned.get('payment_type')
        mpesa_code = cleaned.get('mpesa_code', '').strip()

        if loan and amount is not None:
            if amount <= 0:
                raise ValidationError("Payment amount must be greater than zero.")
            if amount > loan.balance:
                raise ValidationError(
                    f"KES {amount} exceeds the remaining balance of KES {loan.balance}."
                )

        if payment_type == 'mpesa':
            if not mpesa_code:
                self.add_error('mpesa_code', 'M-Pesa confirmation code is required.')
            else:
                # Basic sanity: M-Pesa codes are alphanumeric, 8–12 chars
                import re
                if not re.match(r'^[A-Za-z0-9]{6,20}$', mpesa_code):
                    self.add_error(
                        'mpesa_code',
                        'Enter a valid M-Pesa code (letters and numbers only, 6–20 characters).'
                    )
                else:
                    cleaned['mpesa_code'] = mpesa_code.upper()
        else:
            # Cash — clear any stray mpesa_code value
            cleaned['mpesa_code'] = ''

        return cleaned
