"""本地存储管理"""

import json
import os
from pathlib import Path
from typing import Optional
from .task import Task


class Storage:
    """本地存储管理类"""

    # 工作阶段定义
    WORK_STAGES = ["需求分析", "任务拆分", "开发自测", "任务完成"]

    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.work_directory: str = ""
        self.tasks: list[Task] = []

        # 确保存储目录存在
        self._ensure_storage()

    def _ensure_storage(self):
        """确保存储文件存在"""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.storage_path.exists():
            self.save()

    def load(self):
        """加载数据"""
        try:
            if self.storage_path.exists():
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                self.work_directory = data.get("work_directory", "")
                self.tasks = [Task.from_dict(t) for t in data.get("tasks", [])]

        except Exception as e:
            print(f"加载配置失败: {e}")

    def save(self):
        """保存数据"""
        try:
            data = {
                "work_directory": self.work_directory,
                "tasks": [t.to_dict() for t in self.tasks]
            }

            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)

        except Exception as e:
            print(f"保存配置失败: {e}")

    def add_task(self, name: str, stage: int = 0) -> Task:
        """添加任务"""
        task = Task(name, stage)
        self.tasks.append(task)
        self.save()
        return task

    def delete_task(self, task_id: int) -> bool:
        """删除任务"""
        for i, task in enumerate(self.tasks):
            if task.id == task_id:
                self.tasks.pop(i)
                self.save()
                return True
        return False

    def get_task_by_id(self, task_id: int) -> Optional[Task]:
        """根据ID获取任务"""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def get_sorted_tasks(self) -> list[Task]:
        """获取按ID排序的任务列表"""
        return sorted(self.tasks, key=lambda t: t.id)

    def set_work_directory(self, path: str):
        """设置工作目录"""
        self.work_directory = path
        self.save()

    def update_task_stage(self, task_id: int, stage: int):
        """更新任务阶段"""
        task = self.get_task_by_id(task_id)
        if task and 0 <= stage < len(self.WORK_STAGES):
            task.stage = stage
            self.save()

    def task_name_exists(self, name: str) -> bool:
        """检查任务名是否已存在"""
        return any(t.name == name for t in self.tasks)
