from django.db import migrations, models
import django.db.models.deletion
import django.core.validators
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('loans', '0011_add_loan_type_monthly_installment'),
    ]

    operations = [
        # 1. Create LoanProduct table
        migrations.CreateModel(
            name='LoanProduct',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, unique=True)),
                ('description', models.TextField(blank=True)),
                ('interest_type', models.CharField(
                    max_length=30,
                    choices=[
                        ('flat',               'Flat Rate'),
                        ('reducing_emi',       'Reducing Balance – Equal Installments (EMI)'),
                        ('reducing_principal', 'Reducing Balance – Equal Principal'),
                    ],
                    default='flat',
                )),
                ('interest_frequency', models.CharField(
                    max_length=10,
                    choices=[
                        ('daily',   'Daily'),
                        ('weekly',  'Weekly'),
                        ('monthly', 'Monthly'),
                        ('yearly',  'Yearly'),
                    ],
                    default='monthly',
                )),
                ('interest_rate', models.DecimalField(
                    max_digits=6, decimal_places=2,
                    validators=[django.core.validators.MinValueValidator(Decimal('0.00'))],
                    help_text='Enter as a percentage, e.g. 10 for 10%.',
                )),
                ('duration_months', models.PositiveIntegerField(
                    default=0,
                    help_text='Default repayment period in months. 0 = no default.',
                )),
                ('min_amount', models.DecimalField(
                    max_digits=12, decimal_places=2, default=Decimal('0.00'),
                    validators=[django.core.validators.MinValueValidator(Decimal('0.00'))],
                )),
                ('max_amount', models.DecimalField(
                    max_digits=12, decimal_places=2, default=Decimal('0.00'),
                    validators=[django.core.validators.MinValueValidator(Decimal('0.00'))],
                    help_text='0 = no upper limit.',
                )),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['name']},
        ),

        # 2. Add product FK to Loan
        migrations.AddField(
            model_name='loan',
            name='product',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='loans',
                to='loans.loanproduct',
            ),
        ),

        # 3. Add reducing_principal choice to loan_type
        migrations.AlterField(
            model_name='loan',
            name='loan_type',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('flat',               'Flat Rate'),
                    ('reducing',           'Reducing Balance (EMI)'),
                    ('reducing_principal', 'Reducing Balance (Equal Principal)'),
                ],
                default='flat',
            ),
        ),
    ]
