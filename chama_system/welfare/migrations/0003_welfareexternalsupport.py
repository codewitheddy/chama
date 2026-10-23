from django.db import migrations, models
import django.core.validators
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('welfare', '0002_add_payment_type_mpesa_code'),
    ]

    operations = [
        migrations.CreateModel(
            name='WelfareExternalSupport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('payment_type', models.CharField(
                    choices=[('cash', 'Cash'), ('mpesa', 'M-Pesa')],
                    default='cash', max_length=10,
                )),
                ('mpesa_code', models.CharField(
                    blank=True, max_length=20,
                    help_text='M-Pesa confirmation code (required for M-Pesa payments).',
                )),
                ('event', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='external_support',
                    to='welfare.welfareevent',
                )),
                ('supporter_name', models.CharField(max_length=200)),
                ('supporter_phone', models.CharField(blank=True, max_length=20)),
                ('amount', models.DecimalField(
                    decimal_places=2, max_digits=10,
                    validators=[django.core.validators.MinValueValidator(Decimal('0.01'))],
                )),
                ('date', models.DateField()),
                ('notes', models.CharField(blank=True, max_length=255)),
            ],
            options={
                'ordering': ['-date'],
            },
        ),
    ]
