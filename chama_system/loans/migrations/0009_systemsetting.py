from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('loans', '0008_add_interest_rate_to_loan'),
    ]

    operations = [
        migrations.CreateModel(
            name='SystemSetting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=100, unique=True)),
                ('value', models.CharField(max_length=255)),
                ('label', models.CharField(blank=True, max_length=200)),
                ('help_text', models.CharField(blank=True, max_length=500)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['key'],
            },
        ),
    ]
