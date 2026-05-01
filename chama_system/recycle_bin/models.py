from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class DeletedRecord(models.Model):
    """
    Stores a soft-deleted record as a JSON snapshot.
    Records are permanently purged after RETENTION_DAYS.
    """
    RETENTION_DAYS = 30

    app_label   = models.CharField(max_length=100)
    model_name  = models.CharField(max_length=100)
    object_id   = models.CharField(max_length=50)
    object_repr = models.CharField(max_length=300)   # human-readable label
    data        = models.JSONField()                  # full serialized object
    delete_reason = models.TextField()
    deleted_by  = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name='deleted_records'
    )
    deleted_at  = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-deleted_at']
        verbose_name = 'Deleted Record'
        verbose_name_plural = 'Deleted Records'

    def __str__(self):
        return f"{self.model_name} #{self.object_id} — {self.object_repr}"

    @property
    def expires_at(self):
        from datetime import timedelta
        return self.deleted_at + timedelta(days=self.RETENTION_DAYS)

    @property
    def days_remaining(self):
        delta = self.expires_at - timezone.now()
        return max(delta.days, 0)

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at
