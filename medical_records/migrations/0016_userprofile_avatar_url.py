from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('medical_records', '0015_add_diary_care_plan_caregiver'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='avatar_url',
            field=models.URLField(blank=True, max_length=500, null=True, verbose_name='头像URL'),
        ),
    ]
