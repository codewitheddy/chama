from django import forms
import bleach
from .models import Meeting, MeetingAttendance, MeetingPenalty, MeetingPenaltyRule
from members.models import Member


from django.utils import timezone

ALLOWED_MINUTES_TAGS = [
    'p', 'br', 'strong', 'em', 'u', 's', 'blockquote',
    'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span',
    'div', 'hr', 'a', 'sub', 'sup', 'code', 'pre',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
]
ALLOWED_MINUTES_ATTRIBUTES = {
    'span': ['style', 'class', 'contenteditable'],
    'p': ['style', 'class'],
    'div': ['style', 'class', 'contenteditable'],
    'a': ['href', 'title', 'target', 'rel'],
    'table': ['style', 'class', 'width', 'border', 'cellpadding', 'cellspacing', 'contenteditable'],
    'tr': ['style', 'class', 'contenteditable'],
    'th': ['style', 'class', 'colspan', 'rowspan', 'width', 'contenteditable'],
    'td': ['style', 'class', 'colspan', 'rowspan', 'width', 'contenteditable'],
    'strong': ['style', 'class'],
    'li': ['data-list', 'style', 'class'],
    'h1': ['style', 'class'],
    'h2': ['style', 'class'],
    'h3': ['style', 'class'],
    'h4': ['style', 'class'],
}
ALLOWED_MINUTES_STYLES = [
    'color', 'background-color', 'background', 'text-align', 'font-weight', 'font-style',
    'text-decoration', 'width', 'border', 'border-collapse', 'padding', 'margin', 'font-size',
    'user-select', '-webkit-user-select', 'border-radius', 'display', 'align-items', 'gap',
]


try:
    from bleach.css_sanitizer import CSSSanitizer
    _css_sanitizer = CSSSanitizer(allowed_css_properties=ALLOWED_MINUTES_STYLES)
except (ImportError, AttributeError):
    _css_sanitizer = None


def sanitize_minutes(minutes):
    if not minutes:
        return ''
    kwargs = {
        'tags': ALLOWED_MINUTES_TAGS,
        'attributes': ALLOWED_MINUTES_ATTRIBUTES,
        'strip': True,
    }
    if _css_sanitizer:
        kwargs['css_sanitizer'] = _css_sanitizer
    return bleach.clean(minutes, **kwargs)


class MeetingForm(forms.ModelForm):
    date = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        help_text='Date when the meeting is scheduled.'
    )

    class Meta:
        model = Meeting
        fields = ['date', 'venue', 'agenda', 'status', 'minutes']
        widgets = {
            'date':    forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'venue':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': "e.g. Community Hall, Nairobi or Chairman's Residence"}),
            'agenda':  forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Enter meeting agenda items, e.g.:\n1. Opening prayer & remarks\n2. Review of previous minutes\n3. Contributions collection\n4. Loan applications & approvals\n5. AOB & adjournment'}),
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

    def clean_minutes(self):
        minutes = self.cleaned_data.get('minutes', '')
        return sanitize_minutes(minutes)


class MeetingMinutesForm(forms.ModelForm):
    """Minutes-only form used when a meeting is held."""
    class Meta:
        model = Meeting
        fields = ['minutes']
        widgets = {
            'minutes': forms.Textarea(attrs={'class': 'form-control', 'rows': 6}),
        }

    def clean_minutes(self):
        minutes = self.cleaned_data.get('minutes', '')
        return sanitize_minutes(minutes)


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
