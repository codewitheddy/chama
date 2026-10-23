from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('loans', '0012_loanproduct_loan_product'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Create NonMemberApplicant table
        migrations.CreateModel(
            name='NonMemberApplicant',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name', models.CharField(max_length=200)),
                ('phone', models.CharField(max_length=20, unique=True)),
                ('id_number', models.CharField(blank=True, help_text='National ID or Passport number.', max_length=50)),
                ('email', models.EmailField(blank=True)),
                ('address', models.CharField(blank=True, max_length=300)),
                ('id_document', models.FileField(
                    blank=True, null=True,
                    upload_to='non_members/id_docs/',
                    validators=[django.core.validators.FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png'])],
                    help_text='National ID, passport scan, or any official ID document.',
                )),
                ('employer', models.CharField(blank=True, help_text='Current employer or business name.', max_length=200)),
                ('monthly_income', models.DecimalField(
                    decimal_places=2, default=Decimal('0.00'), max_digits=12,
                    validators=[django.core.validators.MinValueValidator(Decimal('0.00'))],
                    help_text='Estimated monthly income (KES).',
                )),
                ('reason_for_loan', models.TextField(blank=True, help_text='Purpose of the loan.')),
                ('qualification_status', models.CharField(
                    choices=[('pending', 'Pending Review'), ('qualified', 'Qualified'), ('disqualified', 'Disqualified')],
                    default='pending', max_length=20,
                )),
                ('qualification_notes', models.TextField(blank=True, help_text='Admin notes on the qualification assessment.')),
                ('qualified_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='qualified_non_members',
                    to=settings.AUTH_USER_MODEL,
                    help_text='Admin/treasurer who assessed this applicant.',
                )),
                ('qualified_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['-created_at']},
        ),

        # 2. Add borrower_type field to Loan
        migrations.AddField(
            model_name='loan',
            name='borrower_type',
            field=models.CharField(
                choices=[('member', 'Member'), ('non_member', 'Non-Member')],
                default='member', max_length=15,
            ),
        ),

        # 3. Make Loan.member nullable
        migrations.AlterField(
            model_name='loan',
            name='member',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to='members.member',
            ),
        ),

        # 4. Add Loan.non_member FK
        migrations.AddField(
            model_name='loan',
            name='non_member',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='loans',
                to='loans.nonmemberapplicant',
                help_text='Set when issuing a loan to a non-member applicant.',
            ),
        ),
    ]
