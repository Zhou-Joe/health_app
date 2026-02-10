from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from medical_records.models import HealthEvent


class Command(BaseCommand):
    help = '自动聚类用户的健康记录为事件'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=str,
            help='指定用户名，如果不指定则为所有用户聚类'
        )
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='时间阈值（天），默认7天'
        )
        parser.add_argument(
            '--clear-auto',
            action='store_true',
            help='清除之前自动生成的事件'
        )

    def handle(self, *args, **options):
        username = options.get('user')
        days_threshold = options.get('days', 7)
        clear_auto = options.get('clear_auto', False)

        # 如果指定了清除自动生成的事件
        if clear_auto:
            count = HealthEvent.objects.filter(is_auto_generated=True).count()
            HealthEvent.objects.filter(is_auto_generated=True).delete()
            self.stdout.write(
                self.style.WARNING(f'已清除 {count} 个自动生成的事件')
            )

        # 获取目标用户
        if username:
            try:
                users = [User.objects.get(username=username)]
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'用户 "{username}" 不存在')
                )
                return
        else:
            users = User.objects.all()

        # 执行聚类
        total_events = 0
        for user in users:
            events_created = HealthEvent.auto_cluster_user_records(user, days_threshold)
            total_events += events_created

            if events_created > 0:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'用户 {user.username}: 创建了 {events_created} 个事件'
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\n完成！共为 {len(users)} 个用户聚类，创建了 {total_events} 个事件'
            )
        )
