from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from django.utils import timezone
from .models import YearEndWithdrawal, MemberInterestShare, YearEndMemberStatus


class YearEndWithdrawalForm(forms.ModelForm):
    class Meta:
        model = YearEndWithdrawal
        fields = ['financial_year', 'date', 'notes']
        widgets = {
            'financial_year': forms.NumberInput(attrs={'class': 'form-control'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean_financial_year(self):
        year = self.cleaned_data.get('financial_year')
        if year:
            qs = YearEndWithdrawal.objects.filter(financial_year=year)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    f'A year-end withdrawal for {year} has already been recorded.'
                )
        return year


# Inline formset — one row per member for interest share amounts
MemberInterestShareFormSet = inlineformset_factory(
    YearEndWithdrawal,
    MemberInterestShare,
    fields=['member', 'amount'],
    extra=0,
    can_delete=False,
    widgets={
        'member': forms.Select(attrs={'class': 'form-select form-select-sm'}),
        'amount': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01'}),
    },
)

# Inline formset — one row per member for continuing/exiting status
YearEndMemberStatusFormSet = inlineformset_factory(
    YearEndWithdrawal,
    YearEndMemberStatus,
    fields=['member', 'status'],
    extra=0,
    can_delete=False,
    widgets={
        'member': forms.Select(attrs={'class': 'form-select form-select-sm'}),
        'status': forms.Select(attrs={'class': 'form-select form-select-sm'}),
    },
)
