"""任务模型"""

from typing import Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..process.base import AbstractProcess


class Task:
    """任务类"""
    _next_id = 1  # 类变量，用于生成唯一ID

    # 阶段定义
    STAGE_ANALYSIS = 0    # 需求分析
    STAGE_TASK = 1        # 任务拆分
    STAGE_DEVELOP = 2     # 开发自测
    STAGE_COMPLETE = 3    # 任务完成

    STAGE_NAMES = ["需求分析", "任务拆分", "开发自测", "任务完成"]

    def __init__(
        self,
        name: str,
        stage: int = 0,
        task_id: int = None,
        work_directory: str = "",
        model: str = "glm-5",
        env: dict = None,
        on_log: Callable[[str, str, str], None] = None
    ):
        """
        初始化任务

        Args:
            name: 任务名称
            stage: 当前阶段 (0-4)
            task_id: 任务ID，如果不提供则自动生成
            work_directory: 工作目录
            model: 使用的模型名称
            env: 环境变量配置
            on_log: 日志回调函数 (icon, tag, message)
        """
        self.id = task_id if task_id is not None else Task._next_id
        self.name = name
        self.stage = stage
        self.work_directory = work_directory
        self._model = model
        self._env = env
        self._on_log = on_log
        self._process: Optional['AbstractProcess'] = None  # 关联的流程对象

        # 更新下一个ID
        if self.id >= Task._next_id:
            Task._next_id = self.id + 1

    @property
    def stage_name(self) -> str:
        """获取当前阶段名称"""
        if 0 <= self.stage < len(self.STAGE_NAMES):
            return self.STAGE_NAMES[self.stage]
        return "未知"

    @property
    def process(self) -> Optional['AbstractProcess']:
        """获取关联的流程对象"""
        return self._process

    def _create_process_by_stage(self) -> Optional['AbstractProcess']:
        """根据当前阶段创建对应的流程对象"""
        if self.stage == self.STAGE_ANALYSIS:
            from ..process.analysis import Analysis
            return Analysis(
                work_directory=self.work_directory,
                task_name=self.name,
                on_log=self._on_log
            )
        elif self.stage == self.STAGE_TASK:
            from ..process.devtask import DevTask
            return DevTask(
                work_directory=self.work_directory,
                task_name=self.name,
                on_log=self._on_log
            )
        elif self.stage == self.STAGE_DEVELOP:
            from ..process.develop import Develop
            return Develop(
                work_directory=self.work_directory,
                task_name=self.name,
                on_log=self._on_log
            )
        return None

    async def get_or_create_process(self, work_directory: str = None) -> Optional['AbstractProcess']:
        """
        获取或创建流程对象

        根据当前阶段创建对应的流程对象

        Args:
            work_directory: 工作目录，如果不提供则使用实例的工作目录

        Returns:
            流程对象
        """
        if work_directory:
            self.work_directory = work_directory

        if self._process is None:
            self._process = self._create_process_by_stage()
            if self._process:
                await self._process.start()

        return self._process

    async def clear_process(self):
        """清除关联的流程对象"""
        if self._process is not None:
            await self._process.close()
            self._process = None

    async def next_stage(self) -> bool:
        """
        切换到下一阶段

        Returns:
            是否成功切换
        """
        # 检查是否已经是最后阶段
        if self.stage >= self.STAGE_COMPLETE:
            if self._on_log:
                self._on_log("⚠️", "[Task]", "已经是最后阶段，无法继续推进")
            return False

        # 关闭当前流程
        await self.clear_process()

        # 推进到下一阶段
        old_stage = self.stage
        self.stage += 1

        if self._on_log:
            self._on_log("➡️", "[Task]", f"阶段切换: {self.STAGE_NAMES[old_stage]} -> {self.stage_name}")

        # 创建下一阶段的流程并启动
        self._process = self._create_process_by_stage()
        if self._process:
            await self._process.start()

        return True

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "stage": self.stage,
            "work_directory": self.work_directory
        }

    @staticmethod
    def from_dict(data: dict) -> 'Task':
        """从字典反序列化"""
        return Task(
            name=data.get("name", ""),
            stage=data.get("stage", 0),
            task_id=data.get("id"),
            work_directory=data.get("work_directory", "")
        )

    @staticmethod
    def reset_id_counter():
        """重置ID计数器"""
        Task._next_id = 1

    def __repr__(self):
        return f"Task(id={self.id}, name='{self.name}', stage={self.stage})"
