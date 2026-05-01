from django.db import models, transaction
from django.core.validators import MinValueValidator
from decimal import Decimal
from members.models import Member


class MeetingPenaltyRule(models.Model):
    """Configurable penalty types — admin can add/edit/delete these."""
    name = models.CharField(max_length=100, unique=True)
    default_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} (KES {self.default_amount})"


class Meeting(models.Model):
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('held', 'Held'),
        ('cancelled', 'Cancelled'),
    ]
    date = models.DateField()
    venue = models.CharField(max_length=200, blank=True)
    agenda = models.TextField(blank=True)
    minutes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"Meeting — {self.date}"

    @property
    def total_penalties(self):
        from django.db.models import Sum
        return self.penalties.aggregate(t=Sum('amount'))['t'] or 0

    @property
    def attendance_summary(self):
        from django.db.models import Count
        counts = {
            row['status']: row['count']
            for row in self.attendance.values('status').annotate(count=Count('pk'))
        }
        return {
            'present':           counts.get('present', 0),
            'late':              counts.get('late', 0),
            'absent_apology':    counts.get('absent_apology', 0),
            'absent_no_apology': counts.get('absent_no_apology', 0),
            'total':             sum(counts.values()),
        }

    def auto_populate_attendance(self):
        """Pre-populate all current members as 'present'. Call after meeting creation."""
        with transaction.atomic():
            existing = set(self.attendance.values_list('member_id', flat=True))
            new_records = [
                MeetingAttendance(meeting=self, member=m, status='present')
                for m in Member.objects.exclude(pk__in=existing)
            ]
            if new_records:
                MeetingAttendance.objects.bulk_create(new_records, ignore_conflicts=True)
        return len(new_records)


class MeetingAttendance(models.Model):
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('late', 'Late'),
        ('absent_apology', 'Absent with Apology'),
        ('absent_no_apology', 'Absent without Apology'),
    ]
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='attendance')
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='meeting_attendance')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='present')

    class Meta:
        unique_together = ('meeting', 'member')
        ordering = ['member__name']

    def __str__(self):
        return f"{self.member.name} — {self.get_status_display()} @ {self.meeting.date}"


class MeetingPenalty(models.Model):
    """A penalty issued during a meeting. Also creates a Penalty record for income tracking."""
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='penalties')
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='meeting_penalties')
    rule = models.ForeignKey(MeetingPenaltyRule, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    reason = models.CharField(max_length=255)
    penalty_record = models.OneToOneField(
        'penalties.Penalty', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='meeting_penalty'
    )

    class Meta:
        ordering = ['member__name']

    def save(self, *args, **kwargs):
        from penalties.models import Penalty
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            # create the income-tracking Penalty record
            p = Penalty.objects.create(
                member=self.member,
                amount=self.amount,
                date=self.meeting.date,
                reason=f"[Meeting {self.meeting.date}] {self.reason}",
            )
            MeetingPenalty.objects.filter(pk=self.pk).update(penalty_record=p)

    def delete(self, *args, **kwargs):
        # cascade-delete the linked Penalty record too
        if self.penalty_record_id:
            from penalties.models import Penalty
            Penalty.objects.filter(pk=self.penalty_record_id).delete()
        super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.member.name} — KES {self.amount} ({self.reason})"
