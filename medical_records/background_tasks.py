"""
后台任务管理模块
支持异步执行长时间运行的任务
"""

import threading
import queue
import time
from datetime import datetime
from typing import Dict, Any, Callable, Optional
import logging

logger = logging.getLogger(__name__)


class BackgroundTaskManager:
    """后台任务管理器"""

    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.task_queue = queue.Queue()
        self.worker_thread = None
        self.running = False

    def start_worker(self):
        """启动工作线程"""
        if self.worker_thread and self.worker_thread.is_alive():
            return

        self.running = True
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()
        logger.info("Background task worker started")

    def _worker(self):
        """工作线程主循环"""
        while self.running:
            try:
                task_id, func, args, kwargs = self.task_queue.get(timeout=1)
                self.tasks[task_id]['status'] = 'processing'
                self.tasks[task_id]['start_time'] = datetime.now().isoformat()

                try:
                    # 执行任务
                    result = func(*args, **kwargs)
                    self.tasks[task_id]['status'] = 'completed'
                    self.tasks[task_id]['result'] = result
                    self.tasks[task_id]['end_time'] = datetime.now().isoformat()
                    logger.info(f"Task {task_id} completed")
                except Exception as e:
                    self.tasks[task_id]['status'] = 'failed'
                    self.tasks[task_id]['error'] = str(e)
                    self.tasks[task_id]['end_time'] = datetime.now().isoformat()
                    logger.error(f"Task {task_id} failed: {e}")

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Worker error: {e}")

    def create_task(self, task_id: str, func: Callable, *args, **kwargs) -> Dict[str, Any]:
        """
        创建新的后台任务

        Args:
            task_id: 任务ID
            func: 要执行的函数
            *args, **kwargs: 函数参数

        Returns:
            任务信息字典
        """
        task = {
            'task_id': task_id,
            'status': 'pending',
            'created_at': datetime.now().isoformat(),
            'progress': 0,
            'message': '任务已创建，等待执行'
        }

        self.tasks[task_id] = task
        self.task_queue.put((task_id, func, args, kwargs))

        # 确保工作线程在运行
        self.start_worker()

        return task

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        return self.tasks.get(task_id)

    def update_task_progress(self, task_id: str, progress: int, message: str):
        """更新任务进度"""
        if task_id in self.tasks:
            self.tasks[task_id]['progress'] = progress
            self.tasks[task_id]['message'] = message

    def complete_task(self, task_id: str, result: Any = None):
        """标记任务完成"""
        if task_id in self.tasks:
            self.tasks[task_id]['status'] = 'completed'
            self.tasks[task_id]['progress'] = 100
            self.tasks[task_id]['result'] = result
            self.tasks[task_id]['end_time'] = datetime.now().isoformat()

    def fail_task(self, task_id: str, error: str):
        """标记任务失败"""
        if task_id in self.tasks:
            self.tasks[task_id]['status'] = 'failed'
            self.tasks[task_id]['error'] = error
            self.tasks[task_id]['end_time'] = datetime.now().isoformat()

    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """清理旧任务"""
        cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)
        to_remove = []

        for task_id, task in self.tasks.items():
            created_time = datetime.fromisoformat(task['created_at'])
            if created_time.timestamp() < cutoff_time:
                to_remove.append(task_id)

        for task_id in to_remove:
            del self.tasks[task_id]

        logger.info(f"Cleaned up {len(to_remove)} old tasks")


# 全局任务管理器实例
task_manager = BackgroundTaskManager()


def run_in_background(task_id: str, func: Callable, *args, **kwargs):
    """
    在后台运行任务的便捷函数

    Args:
        task_id: 任务ID
        func: 要执行的函数
        *args, **kwargs: 函数参数

    Returns:
        任务信息字典
    """
    return task_manager.create_task(task_id, func, *args, **kwargs)
