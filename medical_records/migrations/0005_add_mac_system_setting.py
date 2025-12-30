from django.db import migrations


def add_mac_system_setting(apps, schema_editor):
    SystemSettings = apps.get_model('medical_records', 'SystemSettings')
    
    SystemSettings.objects.update_or_create(
        key='is_mac_system',
        defaults={
            'name': 'Mac系统',
            'value': 'false',
            'description': '如果MinerU服务运行在Mac系统上，请设置为true。VLM模式将使用vlm-mlx-engine后端',
            'is_active': True
        }
    )


class Migration(migrations.Migration):

    dependencies = [
        ('medical_records', '0004_alter_healthindicator_indicator_type_and_more'),
    ]

    operations = [
        migrations.RunPython(add_mac_system_setting),
    ]
