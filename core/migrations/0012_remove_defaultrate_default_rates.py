# Remove default_masking_rate and default_non_masking_rate fields

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_refactor_defaultrate'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='defaultrate',
            name='default_masking_rate',
        ),
        migrations.RemoveField(
            model_name='defaultrate',
            name='default_non_masking_rate',
        ),
    ]
