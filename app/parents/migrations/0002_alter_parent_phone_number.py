# Generated by Django 5.1.9 on 2025-05-25 04:37

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('parents', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='parent',
            name='phone_number',
            field=models.CharField(blank=True, help_text='Contact phone number', max_length=20, validators=[django.core.validators.RegexValidator(message='Please enter a valid phone number (10-20 characters, may include +, spaces, hyphens, parentheses, or dots)', regex='^[\\+]?[\\d\\s\\-\\(\\)\\.]{10,20}$')], verbose_name='phone number'),
        ),
    ]
