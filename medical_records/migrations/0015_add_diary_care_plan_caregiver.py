from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import datetime


class Migration(migrations.Migration):

    dependencies = [
        ('medical_records', '0014_eventtemplate'),
    ]

    operations = [
        migrations.CreateModel(
            name='SymptomEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('entry_date', models.DateField(default=datetime.date.today, verbose_name='日期')),
                ('symptom', models.CharField(max_length=200, verbose_name='症状')),
                ('severity', models.IntegerField(choices=[(1, '轻微'), (2, '轻度'), (3, '中度'), (4, '严重'), (5, '非常严重')], default=3, verbose_name='严重程度')),
                ('notes', models.TextField(blank=True, null=True, verbose_name='备注')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('related_checkup', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='medical_records.healthcheckup', verbose_name='关联体检')),
                ('related_medication', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='medical_records.medication', verbose_name='关联药单')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL, verbose_name='用户')),
            ],
            options={
                'verbose_name': '症状日志',
                'verbose_name_plural': '症状日志',
                'ordering': ['-entry_date', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='VitalEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('entry_date', models.DateField(default=datetime.date.today, verbose_name='日期')),
                ('vital_type', models.CharField(choices=[('blood_pressure', '血压'), ('heart_rate', '心率'), ('weight', '体重'), ('temperature', '体温'), ('blood_sugar', '血糖'), ('oxygen', '血氧'), ('other', '其他')], max_length=50, verbose_name='体征类型')),
                ('value', models.CharField(max_length=100, verbose_name='数值')),
                ('unit', models.CharField(blank=True, max_length=20, null=True, verbose_name='单位')),
                ('notes', models.TextField(blank=True, null=True, verbose_name='备注')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('related_checkup', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='medical_records.healthcheckup', verbose_name='关联体检')),
                ('related_medication', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='medical_records.medication', verbose_name='关联药单')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL, verbose_name='用户')),
            ],
            options={
                'verbose_name': '体征日志',
                'verbose_name_plural': '体征日志',
                'ordering': ['-entry_date', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='CarePlan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200, verbose_name='计划标题')),
                ('description', models.TextField(blank=True, null=True, verbose_name='计划描述')),
                ('is_active', models.BooleanField(default=True, verbose_name='是否启用')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL, verbose_name='用户')),
            ],
            options={
                'verbose_name': '健康管理计划',
                'verbose_name_plural': '健康管理计划',
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='CareGoal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200, verbose_name='目标标题')),
                ('target_value', models.CharField(blank=True, max_length=100, null=True, verbose_name='目标值')),
                ('unit', models.CharField(blank=True, max_length=20, null=True, verbose_name='单位')),
                ('due_date', models.DateField(blank=True, null=True, verbose_name='目标日期')),
                ('status', models.CharField(choices=[('active', '进行中'), ('completed', '已完成'), ('paused', '已暂停')], default='active', max_length=20, verbose_name='状态')),
                ('progress_percent', models.IntegerField(default=0, verbose_name='进度百分比')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='goals', to='medical_records.careplan', verbose_name='所属计划')),
            ],
            options={
                'verbose_name': '健康目标',
                'verbose_name_plural': '健康目标',
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='CareAction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200, verbose_name='行动')),
                ('frequency', models.CharField(blank=True, max_length=50, null=True, verbose_name='频率')),
                ('status', models.CharField(choices=[('pending', '待完成'), ('done', '已完成')], default='pending', max_length=20, verbose_name='状态')),
                ('suggested_by_ai', models.BooleanField(default=False, verbose_name='AI建议')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('goal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='actions', to='medical_records.caregoal', verbose_name='所属目标')),
            ],
            options={
                'verbose_name': '健康行动',
                'verbose_name_plural': '健康行动',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='CaregiverAccess',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('relationship', models.CharField(blank=True, max_length=50, null=True, verbose_name='关系')),
                ('can_view_records', models.BooleanField(default=True, verbose_name='可查看体检报告')),
                ('can_view_medications', models.BooleanField(default=True, verbose_name='可查看药单')),
                ('can_view_events', models.BooleanField(default=False, verbose_name='可查看事件')),
                ('can_view_diary', models.BooleanField(default=False, verbose_name='可查看日志')),
                ('can_manage_medications', models.BooleanField(default=False, verbose_name='可管理药单')),
                ('is_active', models.BooleanField(default=True, verbose_name='是否有效')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('caregiver', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='caregiver_accesses', to=settings.AUTH_USER_MODEL, verbose_name='照护者')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='caregiver_links', to=settings.AUTH_USER_MODEL, verbose_name='授权人')),
            ],
            options={
                'verbose_name': '照护者授权',
                'verbose_name_plural': '照护者授权',
            },
        ),
        migrations.AddConstraint(
            model_name='caregiveraccess',
            constraint=models.UniqueConstraint(fields=('owner', 'caregiver'), name='unique_caregiver_access'),
        ),
    ]
