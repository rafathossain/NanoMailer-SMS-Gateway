# Generated manually to refactor DefaultRate model

from django.db import migrations, models


def migrate_operator_rates(apps, schema_editor):
    """Migrate old flat JSON structure to new nested JSON structure."""
    DefaultRate = apps.get_model('core', 'DefaultRate')
    
    try:
        instance = DefaultRate.objects.get(pk=1)
    except DefaultRate.DoesNotExist:
        return
    
    # At this point, 'credentials' has been renamed to 'operator_rates'
    # But the data is still in the old flat format
    old_data = instance.operator_rates or {}
    new_operator_rates = {}
    
    # Mapping from old keys to new structure
    # Old: {"gp_masking": 0.30, "gp_non_masking": 0.25, ...}
    # New: {"gp": {"masking": 0.30, "non_masking": 0.25}, ...}
    
    operators = ['gp', 'bl', 'robi', 'airtel', 'teletalk']
    
    for op in operators:
        op_data = {}
        old_masking_key = f'{op}_masking'
        old_non_masking_key = f'{op}_non_masking'
        
        if old_masking_key in old_data:
            op_data['masking'] = old_data[old_masking_key]
        if old_non_masking_key in old_data:
            op_data['non_masking'] = old_data[old_non_masking_key]
        
        if op_data:
            new_operator_rates[op] = op_data
    
    # Only update if we found data to migrate
    if new_operator_rates:
        instance.operator_rates = new_operator_rates
        instance.save(update_fields=['operator_rates'])


def reverse_migrate_operator_rates(apps, schema_editor):
    """Reverse migration: convert nested JSON back to flat structure."""
    DefaultRate = apps.get_model('core', 'DefaultRate')
    
    try:
        instance = DefaultRate.objects.get(pk=1)
    except DefaultRate.DoesNotExist:
        return
    
    # At this point, 'operator_rates' will be renamed back to 'credentials' on reverse
    old_operator_rates = instance.operator_rates or {}
    old_credentials = {}
    
    for op, rates in old_operator_rates.items():
        if 'masking' in rates:
            old_credentials[f'{op}_masking'] = rates['masking']
        if 'non_masking' in rates:
            old_credentials[f'{op}_non_masking'] = rates['non_masking']
    
    if old_credentials:
        instance.operator_rates = old_credentials
        instance.save(update_fields=['operator_rates'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_profile_address_profile_bio_profile_company_name_and_more'),
    ]

    operations = [
        # Step 1: Rename masking_rate to default_masking_rate
        migrations.RenameField(
            model_name='defaultrate',
            old_name='masking_rate',
            new_name='default_masking_rate',
        ),
        # Step 2: Rename non_masking_rate to default_non_masking_rate
        migrations.RenameField(
            model_name='defaultrate',
            old_name='non_masking_rate',
            new_name='default_non_masking_rate',
        ),
        # Step 3: Rename credentials to operator_rates
        migrations.RenameField(
            model_name='defaultrate',
            old_name='credentials',
            new_name='operator_rates',
        ),
        # Step 4: Update help_text for operator_rates
        migrations.AlterField(
            model_name='defaultrate',
            name='operator_rates',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Operator-specific SMS rates. Format: {"gp": {"masking": 0.30, "non_masking": 0.25}, ...}'
            ),
        ),
        # Step 5: Run data migration to convert JSON structure
        migrations.RunPython(
            migrate_operator_rates,
            reverse_migrate_operator_rates
        ),
    ]
