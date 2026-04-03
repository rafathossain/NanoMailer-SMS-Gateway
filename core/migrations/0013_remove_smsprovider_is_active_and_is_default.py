# Remove is_active and is_default fields from SMSProvider

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_remove_defaultrate_default_rates'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='smsprovider',
            name='is_active',
        ),
        migrations.RemoveField(
            model_name='smsprovider',
            name='is_default',
        ),
    ]
