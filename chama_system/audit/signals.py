"""
Signal handlers that write an AuditLog entry on every save/delete
for the financial models we care about.

Models tracked:
  - Contribution, Loan, Payment, Penalty
  - WelfareContribution, WelfareDisbursement, WelfareSupportContribution, WelfareExternalSupport
  - YearEndWithdrawal, MemberInterestShare
  - Member (member roster changes)
  - Meeting, MeetingAttendance, MeetingPenalty
"""
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.apps import apps

from audit.middleware import get_current_user, get_current_ip

# ---------------------------------------------------------------------------
# The models we want to audit (app_label, model_name)
# ---------------------------------------------------------------------------
TRACKED_MODELS = {
    ('contributions',  'contribution'),
    ('loans',          'loan'),
    ('payments',       'payment'),
    ('penalties',      'penalty'),
    ('members',        'member'),
    ('members',        'memberexit'),
    ('members',        'registrationfeepayment'),
    ('welfare',        'welfarecontribution'),
    ('welfare',        'welfarecontributionrate'),
    ('welfare',        'welfaredisbursement'),
    ('welfare',        'welfaresupportcontribution'),
    ('welfare',        'welfareexternalsupport'),
    ('yearend',        'yearendwithdrawal'),
    ('meetings',       'meeting'),
    ('expenses',       'expense'),
    ('investments',    'investment'),
    ('investments',    'investmentreturn'),
    ('investments',    'investmentwithdrawal'),
    ('bank_accounts',  'bankbalance'),
}

# Fields to skip when building a change dict (internal / noisy)
_SKIP_FIELDS = {'id', 'created_at', 'updated_at'}


def _model_key(instance):
    meta = instance._meta
    return (meta.app_label, meta.model_name)


def _is_tracked(instance):
    return _model_key(instance) in TRACKED_MODELS


def _field_values(instance):
    """Return {field_name: str(value)} for all concrete fields."""
    data = {}
    for field in instance._meta.concrete_fields:
        if field.name in _SKIP_FIELDS:
            continue
        try:
            value = field.value_from_object(instance)
            data[field.name] = str(value) if value is not None else ''
        except Exception:
            pass
    return data


# Store pre-save snapshots in a thread-local dict keyed by (model, pk)
import threading
_snapshots = threading.local()


def _get_snapshots():
    if not hasattr(_snapshots, 'data'):
        _snapshots.data = {}
    return _snapshots.data


@receiver(pre_save)
def capture_pre_save_snapshot(sender, instance, **kwargs):
    if not _is_tracked(instance):
        return
    if instance.pk:
        try:
            old = sender.objects.get(pk=instance.pk)
            _get_snapshots()[(_model_key(instance), instance.pk)] = _field_values(old)
        except sender.DoesNotExist:
            pass


@receiver(post_save)
def log_save(sender, instance, created, **kwargs):
    if not _is_tracked(instance):
        return

    from audit.models import AuditLog

    key = (_model_key(instance), instance.pk)
    snapshots = _get_snapshots()
    old_data = snapshots.pop(key, {})
    new_data = _field_values(instance)

    if created:
        # Record initial field values as creates
        changes = {k: ['', v] for k, v in new_data.items() if v != ''}
        action = AuditLog.ACTION_CREATE
    else:
        # Only record fields that actually changed
        changes = {}
        all_keys = set(old_data) | set(new_data)
        for k in all_keys:
            if k in _SKIP_FIELDS:
                continue
            old_v = old_data.get(k, '')
            new_v = new_data.get(k, '')
            if old_v != new_v:
                changes[k] = [old_v, new_v]
        if not changes:
            return  # nothing actually changed — skip
        action = AuditLog.ACTION_UPDATE

    meta = instance._meta
    AuditLog.objects.create(
        user        = get_current_user(),
        ip_address  = get_current_ip(),
        action      = action,
        app_label   = meta.app_label,
        model_name  = meta.model_name,
        object_id   = str(instance.pk),
        object_repr = str(instance)[:300],
        changes     = changes,
    )


@receiver(post_delete)
def log_delete(sender, instance, **kwargs):
    if not _is_tracked(instance):
        return

    from audit.models import AuditLog

    old_data = _field_values(instance)
    changes = {k: [v, ''] for k, v in old_data.items() if v != ''}

    meta = instance._meta
    try:
        object_repr = str(instance)[:300]
    except Exception:
        object_repr = f"{meta.verbose_name} #{getattr(instance, 'pk', '')}"

    AuditLog.objects.create(
        user        = get_current_user(),
        ip_address  = get_current_ip(),
        action      = AuditLog.ACTION_DELETE,
        app_label   = meta.app_label,
        model_name  = meta.model_name,
        object_id   = str(instance.pk),
        object_repr = object_repr,
        changes     = changes,
    )

