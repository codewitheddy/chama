from django import forms
from .models import Meeting, MeetingAttendance, MeetingPenalty, MeetingPenaltyRule
from members.models import Member


class MeetingForm(forms.ModelForm):
    class Meta:
        model = Meeting
        fields = ['date', 'venue', 'agenda', 'status', 'minutes']
        widgets = {
            'date':    forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'venue':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Chairman\'s house'}),
            'agenda':  forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'minutes': forms.Textarea(attrs={'class': 'form-control', 'rows': 6}),
            'status':  forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # once a meeting is held, lock the status field to 'held' only
        if self.instance and self.instance.pk and self.instance.status == 'held':
            self.fields['status'].choices = [('held', 'Held')]
            self.fields['status'].widget.attrs['disabled'] = True

    def clean_status(self):
        # disabled fields are not submitted — fall back to instance value
        if self.instance and self.instance.pk and self.instance.status == 'held':
            return 'held'
        return self.cleaned_data.get('status')


class MeetingMinutesForm(forms.ModelForm):
    """Minutes-only form used when a meeting is held."""
    class Meta:
        model = Meeting
        fields = ['minutes']
        widgets = {
            'minutes': forms.Textarea(attrs={'class': 'form-control', 'rows': 6}),
        }


class MeetingPenaltyForm(forms.ModelForm):
    class Meta:
        model = MeetingPenalty
        fields = ['member', 'rule', 'amount', 'reason']
        widgets = {
            'member': forms.Select(attrs={'class': 'form-select'}),
            'rule':   forms.Select(attrs={'class': 'form-select', 'id': 'id_rule'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '50'}),
            'reason': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, meeting=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.meeting = meeting
        self.fields['rule'].required = False
        self.fields['rule'].empty_label = '— Custom reason —'


class MeetingPenaltyRuleForm(forms.ModelForm):
    class Meta:
        model = MeetingPenaltyRule
        fields = ['name', 'default_amount', 'description']
        widgets = {
            'name':           forms.TextInput(attrs={'class': 'form-control'}),
            'default_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '50'}),
            'description':    forms.TextInput(attrs={'class': 'form-control'}),
        }
