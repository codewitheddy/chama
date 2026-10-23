from django.db import models
from django.conf import settings


class AuditLog(models.Model):
    ACTION_CREATE = 'create'
    ACTION_UPDATE = 'update'
    ACTION_DELETE = 'delete'
    ACTION_CHOICES = [
        (ACTION_CREATE, 'Create'),
        (ACTION_UPDATE, 'Update'),
        (ACTION_DELETE, 'Delete'),
    ]

    # Who & when
    user        = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='audit_logs',
    )
    timestamp   = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address  = models.GenericIPAddressField(null=True, blank=True)

    # What
    action      = models.CharField(max_length=10, choices=ACTION_CHOICES, db_index=True)
    app_label   = models.CharField(max_length=50, db_index=True)
    model_name  = models.CharField(max_length=100, db_index=True)
    object_id   = models.CharField(max_length=50)
    object_repr = models.CharField(max_length=300)  # str(instance) at time of action

    # Change detail
    changes     = models.JSONField(
        default=dict, blank=True,
        help_text='For updates: {"field": ["old_value", "new_value"], ...}. '
                  'For creates: {"field": ["", "new_value"], ...}. '
                  'For deletes: {"field": ["old_value", ""], ...}.',
    )

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        indexes = [
            models.Index(fields=['app_label', 'model_name']),
            models.Index(fields=['user', 'timestamp']),
        ]

    def __str__(self):
        user_str = self.user.username if self.user else 'system'
        return f'{self.get_action_display()} {self.model_name} #{self.object_id} by {user_str}'

    @property
    def action_css(self):
        return {
            'create': 'success',
            'update': 'warning',
            'delete': 'danger',
        }.get(self.action, 'secondary')

    @property
    def action_icon(self):
        return {
            'create': 'bi-plus-circle',
            'update': 'bi-pencil',
            'delete': 'bi-trash',
        }.get(self.action, 'bi-circle')
