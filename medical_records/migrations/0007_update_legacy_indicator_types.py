# Generated manually to update legacy indicator types in database

from django.db import migrations


def update_legacy_indicator_types(apps, schema_editor):
    """更新数据库中的旧指标类型代码到新代码"""
    HealthIndicator = apps.get_model('medical_records', 'HealthIndicator')

    # 旧类型到新类型的映射（与services.py中的映射保持一致）
    type_mapping = {
        'physical_exam': 'general_exam',      # 体格检查 → 一般检查
        'ultrasound_exam': 'ultrasound',      # 超声检查 → 超声检查
        'urine_exam': 'urine',                # 尿液检查 → 尿液检查
        'eye_exam': 'special_organs',         # 眼科检查 → 专科检查
        'imaging_exam': 'CT_MRI',             # 影像学检查 → CT和MRI（简化处理）
        'thyroid_function': 'thyroid',        # 甲状腺功能 → 甲状腺
        'diagnosis': 'pathology',             # 病症诊断 → 病理检查
        'symptoms': 'other',                  # 症状描述 → 其他检查
        'other_exam': 'other',                # 其他检查 → 其他检查
    }

    # 更新所有指标的类型
    for old_type, new_type in type_mapping.items():
        count = HealthIndicator.objects.filter(indicator_type=old_type).update(indicator_type=new_type)
        if count > 0:
            print(f"[数据迁移] 将 {count} 个指标从 '{old_type}' 更新为 '{new_type}'")


class Migration(migrations.Migration):

    dependencies = [
        ('medical_records', '0006_alter_healthindicator_indicator_type_and_more'),
    ]

    operations = [
        migrations.RunPython(update_legacy_indicator_types),
    ]
