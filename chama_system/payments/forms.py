from django import forms
from django.core.exceptions import ValidationError
from .models import Payment
from loans.models import Loan


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['loan', 'amount', 'date', 'notes']
        widgets = {
            'loan': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
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
        if loan_id:
            try:
                self.fields['loan'].initial = Loan.objects.get(pk=loan_id)
            except Loan.DoesNotExist:
                pass

    def clean(self):
        cleaned = super().clean()
        loan = cleaned.get('loan')
        amount = cleaned.get('amount')
        if loan and amount is not None:
            if amount <= 0:
                raise ValidationError("Payment amount must be greater than zero.")
            if amount > loan.balance:
                raise ValidationError(
                    f"KES {amount} exceeds the remaining balance of KES {loan.balance}."
                )
        return cleaned
