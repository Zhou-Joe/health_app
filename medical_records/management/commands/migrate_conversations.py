from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta
from medical_records.models import HealthAdvice, Conversation


class Command(BaseCommand):
    help = '将历史HealthAdvice记录迁移到新的Conversation模型'

    def handle(self, *args, **options):
        self.stdout.write("开始迁移历史对话记录...")

        # 获取所有没有关联对话的HealthAdvice记录，按用户和时间分组
        unlinked_advices = HealthAdvice.objects.filter(conversation__isnull=True).order_by('user', 'created_at')

        # 按用户分组
        users_advices = {}
        for advice in unlinked_advices:
            if advice.user_id not in users_advices:
                users_advices[advice.user_id] = []
            users_advices[advice.user_id].append(advice)

        created_conversations = 0
        migrated_advices = 0

        # 为每个用户创建对话
        for user_id, advices in users_advices.items():
            self.stdout.write(f"处理用户 {user_id} 的 {len(advices)} 条记录...")

            # 按日期分组，一天内的对话归为一个对话
            conversations = {}
            for advice in advices:
                date_key = advice.created_at.date()
                if date_key not in conversations:
                    conversations[date_key] = []
                conversations[date_key].append(advice)

            # 为每天的对话创建Conversation记录
            for date, day_advices in conversations.items():
                # 生成对话标题
                if len(day_advices) == 1:
                    title = f"健康咨询: {day_advices[0].question[:30]}{'...' if len(day_advices[0].question) > 30 else ''}"
                else:
                    title = f"健康咨询 ({date.strftime('%m-%d')})"

                # 创建对话
                conversation = Conversation.objects.create(
                    user=day_advices[0].user,
                    title=title,
                    created_at=day_advices[0].created_at,
                    updated_at=day_advices[-1].created_at,
                    is_active=True
                )

                # 将当天的所有Advice关联到这个对话
                for advice in day_advices:
                    advice.conversation = conversation
                    advice.save(update_fields=['conversation'])

                self.stdout.write(f"  - 创建对话: {title} (包含 {len(day_advices)} 条消息)")
                created_conversations += 1
                migrated_advices += len(day_advices)

        self.stdout.write(self.style.SUCCESS(
            f"迁移完成！创建了 {created_conversations} 个对话，迁移了 {migrated_advices} 条记录"
        ))