from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('loans', '0006_add_late_penalty_fields'),
        ('members', '0004_member_is_active'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='LoanApplication',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('loan_amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('duration_months', models.PositiveIntegerField(default=1)),
                ('reason', models.TextField(help_text='Why the member needs this loan.')),
                ('notes', models.TextField(blank=True)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('approved', 'Approved'),
                        ('rejected', 'Rejected'),
                    ],
                    default='pending',
                    max_length=20,
                )),
                ('review_notes', models.TextField(blank=True, help_text='Treasurer notes on approval or rejection.')),
                ('applied_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('member', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='loan_applications',
                    to='members.member',
                )),
                ('applied_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='loan_applications_submitted',
                    to='auth.user',
                )),
                ('reviewed_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='loan_applications_reviewed',
                    to='auth.user',
                )),
                ('loan', models.OneToOneField(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='application',
                    to='loans.loan',
                )),
            ],
            options={
                'ordering': ['-applied_at'],
            },
        ),
    ]
