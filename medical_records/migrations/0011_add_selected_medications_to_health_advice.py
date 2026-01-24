# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('medical_records', '0010_medication_medicationrecord'),
    ]

    operations = [
        migrations.AddField(
            model_name='healthadvice',
            name='selected_medications',
            field=models.TextField(blank=True, null=True, verbose_name='选中的药单ID列表（JSON格式）'),
        ),
    ]
