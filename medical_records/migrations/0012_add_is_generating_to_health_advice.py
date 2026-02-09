# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('medical_records', '0011_add_selected_medications_to_health_advice'),
    ]

    operations = [
        migrations.AddField(
            model_name='healthadvice',
            name='is_generating',
            field=models.BooleanField(default=False, verbose_name='是否正在生成'),
        ),
    ]
