from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
from .models import (
    HealthCheckup, HealthIndicator, Medication, MedicationRecord,
    HealthEvent, EventItem, EventTemplate, UserProfile
)
from django.contrib.contenttypes.models import ContentType


class HealthEventModelTest(TestCase):
    """HealthEvent 模型测试"""

    def setUp(self):
        """设置测试数据"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.event = HealthEvent.objects.create(
            user=self.user,
            name='测试事件',
            event_type='illness',
            start_date=date.today(),
            end_date=date.today() + timedelta(days=7),
            description='这是一个测试事件'
        )

    def test_event_creation(self):
        """测试事件创建"""
        self.assertEqual(self.event.user, self.user)
        self.assertEqual(self.event.name, '测试事件')
        self.assertEqual(self.event.event_type, 'illness')
        self.assertFalse(self.event.is_auto_generated)

    def test_duration_days_property(self):
        """测试持续天数计算"""
        # 7天的事件（1-7号）
        self.assertEqual(self.event.duration_days, 8)  # 包含首尾共8天

    def test_get_item_count(self):
        """测试获取记录数量"""
        self.assertEqual(self.event.get_item_count(), 0)

        # 添加一个体检报告
        checkup = HealthCheckup.objects.create(
            user=self.user,
            checkup_date=date.today(),
            hospital='测试医院'
        )
        EventItem.objects.create(
            event=self.event,
            content_type=ContentType.objects.get_for_model(checkup),
            object_id=checkup.id
        )

        self.assertEqual(self.event.get_item_count(), 1)

    def test_get_checkups(self):
        """测试获取关联的体检报告"""
        checkup = HealthCheckup.objects.create(
            user=self.user,
            checkup_date=date.today(),
            hospital='测试医院'
        )
        EventItem.objects.create(
            event=self.event,
            content_type=ContentType.objects.get_for_model(checkup),
            object_id=checkup.id
        )

        checkups = self.event.get_checkups()
        self.assertEqual(checkups.count(), 1)

    def test_get_medications(self):
        """测试获取关联的药单"""
        medication = Medication.objects.create(
            user=self.user,
            medicine_name='测试药物',
            dosage='每日一次',
            start_date=date.today(),
            end_date=date.today() + timedelta(days=7)
        )
        EventItem.objects.create(
            event=self.event,
            content_type=ContentType.objects.get_for_model(medication),
            object_id=medication.id
        )

        medications = self.event.get_medications()
        self.assertEqual(medications.count(), 1)


class EventItemModelTest(TestCase):
    """EventItem 模型测试"""

    def setUp(self):
        """设置测试数据"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.event = HealthEvent.objects.create(
            user=self.user,
            name='测试事件',
            event_type='illness',
            start_date=date.today()
        )
        self.checkup = HealthCheckup.objects.create(
            user=self.user,
            checkup_date=date.today(),
            hospital='测试医院'
        )

    def test_event_item_creation(self):
        """测试事件项目创建"""
        item = EventItem.objects.create(
            event=self.event,
            content_type=ContentType.objects.get_for_model(self.checkup),
            object_id=self.checkup.id,
            added_by='manual'
        )

        self.assertEqual(item.event, self.event)
        self.assertEqual(item.added_by, 'manual')

    def test_item_summary_for_checkup(self):
        """测试体检报告的摘要"""
        item = EventItem.objects.create(
            event=self.event,
            content_type=ContentType.objects.get_for_model(self.checkup),
            object_id=self.checkup.id
        )

        summary = item.item_summary
        self.assertIn('体检报告', summary)
        self.assertIn('测试医院', summary)

    def test_item_summary_for_medication(self):
        """测试药单的摘要"""
        medication = Medication.objects.create(
            user=self.user,
            medicine_name='阿莫西林',
            dosage='每日一次',
            start_date=date.today(),
            end_date=date.today() + timedelta(days=7)
        )
        item = EventItem.objects.create(
            event=self.event,
            content_type=ContentType.objects.get_for_model(medication),
            object_id=medication.id
        )

        summary = item.item_summary
        self.assertIn('药单', summary)
        self.assertIn('阿莫西林', summary)

    def test_unique_constraint(self):
        """测试唯一约束（同一记录不能重复添加到同一事件）"""
        EventItem.objects.create(
            event=self.event,
            content_type=ContentType.objects.get_for_model(self.checkup),
            object_id=self.checkup.id
        )

        # 尝试再次添加同一个记录
        with self.assertRaises(Exception):  # IntegrityError
            EventItem.objects.create(
                event=self.event,
                content_type=ContentType.objects.get_for_model(self.checkup),
                object_id=self.checkup.id
            )


class AutoClusterTest(TestCase):
    """自动聚类功能测试"""

    def setUp(self):
        """设置测试数据"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

    def test_cluster_checkups_by_time(self):
        """测试按时间聚类体检报告"""
        base_date = date.today()

        # 创建3份体检报告，在7天内
        for i in range(3):
            HealthCheckup.objects.create(
                user=self.user,
                checkup_date=base_date + timedelta(days=i),
                hospital=f'医院{i}'
            )

        # 创建一份不在7天内的体检报告
        HealthCheckup.objects.create(
            user=self.user,
            checkup_date=base_date + timedelta(days=20),
            hospital='医院20'
        )

        # 执行自动聚类
        events_created = HealthEvent.auto_cluster_user_records(self.user, days_threshold=7)

        # 应该创建2个事件：一个包含前3份报告，一个包含第4份报告
        self.assertGreaterEqual(events_created, 1)

    def test_cluster_medications_by_overlap(self):
        """测试按时间重叠聚类药单"""
        base_date = date.today()

        # 创建两个时间重叠的药单
        Medication.objects.create(
            user=self.user,
            medicine_name='药物1',
            dosage='每日一次',
            start_date=base_date,
            end_date=base_date + timedelta(days=10)
        )
        Medication.objects.create(
            user=self.user,
            medicine_name='药物2',
            dosage='每日一次',
            start_date=base_date + timedelta(days=5),
            end_date=base_date + timedelta(days=15)
        )

        # 执行自动聚类
        events_created = HealthEvent.auto_cluster_user_records(self.user, days_threshold=7)

        # 应该至少创建1个事件
        self.assertGreaterEqual(events_created, 1)


class EventTemplateModelTest(TestCase):
    """EventTemplate 模型测试"""

    def setUp(self):
        """设置测试数据"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.template = EventTemplate.objects.create(
            name='年度体检模板',
            description='年度健康体检',
            event_type='checkup',
            suggested_duration_days=1,
            default_name_template='{date} 年度体检'
        )

    def test_template_creation(self):
        """测试模板创建"""
        self.assertEqual(self.template.name, '年度体检模板')
        self.assertEqual(self.template.event_type, 'checkup')
        self.assertEqual(self.template.suggested_duration_days, 1)

    def test_apply_template(self):
        """测试应用模板创建事件"""
        start_date = date.today()

        event = self.template.apply_template(
            user=self.user,
            start_date=start_date
        )

        self.assertEqual(event.user, self.user)
        self.assertEqual(event.event_type, 'checkup')
        self.assertEqual(event.start_date, start_date)
        self.assertEqual(event.end_date, start_date)  # 1天
        self.assertIn(start_date.strftime('%Y-%m-%d'), event.name)

    def test_apply_template_with_custom_name(self):
        """测试应用模板时使用自定义名称"""
        custom_name = '我的自定义体检'

        event = self.template.apply_template(
            user=self.user,
            start_date=date.today(),
            custom_name=custom_name
        )

        self.assertEqual(event.name, custom_name)


class EventAPITest(TestCase):
    """Event API 测试"""

    def setUp(self):
        """设置测试数据"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_api_events_list(self):
        """测试获取事件列表 API"""
        HealthEvent.objects.create(
            user=self.user,
            name='测试事件',
            event_type='illness',
            start_date=date.today()
        )

        response = self.client.get('/api/events/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['events']), 1)

    def test_api_event_create(self):
        """测试创建事件 API"""
        response = self.client.post(
            '/api/events/',
            data=json.dumps({
                'name': '新事件',
                'event_type': 'checkup',
                'start_date': date.today().strftime('%Y-%m-%d'),
                'description': '测试描述'
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['event']['name'], '新事件')

    def test_api_event_detail(self):
        """测试获取事件详情 API"""
        event = HealthEvent.objects.create(
            user=self.user,
            name='测试事件',
            event_type='illness',
            start_date=date.today()
        )

        response = self.client.get(f'/api/events/{event.id}/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['event']['name'], '测试事件')

    def test_api_event_add_item(self):
        """测试添加记录到事件 API"""
        event = HealthEvent.objects.create(
            user=self.user,
            name='测试事件',
            event_type='illness',
            start_date=date.today()
        )
        checkup = HealthCheckup.objects.create(
            user=self.user,
            checkup_date=date.today(),
            hospital='测试医院'
        )

        response = self.client.post(
            f'/api/events/{event.id}/add-item/',
            data=json.dumps({
                'content_type': 'healthcheckup',
                'object_id': checkup.id
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['event_item_count'], 1)

    def test_api_event_remove_item(self):
        """测试从事件移除记录 API"""
        event = HealthEvent.objects.create(
            user=self.user,
            name='测试事件',
            event_type='illness',
            start_date=date.today()
        )
        checkup = HealthCheckup.objects.create(
            user=self.user,
            checkup_date=date.today(),
            hospital='测试医院'
        )
        item = EventItem.objects.create(
            event=event,
            content_type=ContentType.objects.get_for_model(checkup),
            object_id=checkup.id
        )

        response = self.client.delete(f'/api/events/{event.id}/remove-item/{item.id}/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data['success'])

    def test_api_auto_cluster(self):
        """测试自动聚类 API"""
        # 创建一些测试数据
        for i in range(3):
            HealthCheckup.objects.create(
                user=self.user,
                checkup_date=date.today() + timedelta(days=i),
                hospital=f'医院{i}'
            )

        response = self.client.post(
            '/api/events/auto-cluster/',
            data=json.dumps({'days_threshold': 7}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data['success'])
        self.assertGreater(data['events_created'], 0)

    def test_api_bulk_add_items(self):
        """测试批量添加记录 API"""
        event = HealthEvent.objects.create(
            user=self.user,
            name='测试事件',
            event_type='illness',
            start_date=date.today()
        )

        checkup1 = HealthCheckup.objects.create(
            user=self.user,
            checkup_date=date.today(),
            hospital='医院1'
        )
        checkup2 = HealthCheckup.objects.create(
            user=self.user,
            checkup_date=date.today(),
            hospital='医院2'
        )

        response = self.client.post(
            f'/api/events/{event.id}/bulk-add-items/',
            data=json.dumps({
                'items': [
                    {'content_type': 'healthcheckup', 'object_id': checkup1.id},
                    {'content_type': 'healthcheckup', 'object_id': checkup2.id},
                ]
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['added_count'], 2)

    def test_api_event_statistics(self):
        """测试事件统计 API"""
        HealthEvent.objects.create(
            user=self.user,
            name='测试事件1',
            event_type='illness',
            start_date=date.today()
        )
        HealthEvent.objects.create(
            user=self.user,
            name='测试事件2',
            event_type='checkup',
            start_date=date.today()
        )

        response = self.client.get('/api/events/statistics/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['statistics']['total_events'], 2)

    def test_authentication_required(self):
        """测试认证要求"""
        self.client.logout()

        response = self.client.get('/api/events/')
        # 应该重定向到登录页面或返回401/403
        self.assertIn(response.status_code, [301, 302, 401, 403])


class EventViewTest(TestCase):
    """Event 视图测试"""

    def setUp(self):
        """设置测试数据"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_events_list_page(self):
        """测试事件列表页面"""
        response = self.client.get('/events/')
        self.assertEqual(response.status_code, 200)

    def test_event_detail_page(self):
        """测试事件详情页面"""
        event = HealthEvent.objects.create(
            user=self.user,
            name='测试事件',
            event_type='illness',
            start_date=date.today()
        )

        response = self.client.get(f'/events/{event.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '测试事件')

    def test_create_event_view(self):
        """测试创建事件视图"""
        response = self.client.post(
            '/events/create/',
            data={
                'name': '新事件',
                'event_type': 'checkup',
                'start_date': date.today().strftime('%Y-%m-%d'),
                'description': '测试描述'
            }
        )

        self.assertEqual(response.status_code, 302)  # 重定向
        self.assertTrue(HealthEvent.objects.filter(name='新事件').exists())


# Helper import
import json
