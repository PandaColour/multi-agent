"""开发自测流程 - 读取 task-split.md，将各模块任务分发给子代理执行开发和自测"""

import json
import asyncio
from pathlib import Path

from .base import AbstractProcess
from ..subagent.subagent_manager import SubagentManager


class Develop(AbstractProcess):
    """开发自测流程

    启动后自动：
    1. 读取 task-split.md
    2. 逐个将任务发送给对应 subagent 执行开发和自测
    3. 收集各模块开发报告，汇总写入 develop-report.md
    """

    PROMPT_FILE = Path(__file__).parent.parent.parent / "prompts" / "develop.md"
    MEMORY_PATH = Path(__file__).parent.parent.parent / "memory" / "develop"
    RESULT_PATH = Path(__file__).parent.parent.parent

    # 开发自测时的最大交互轮数（开发需要充足空间）
    _DEVELOP_MAX_TURNS = 40
    # subagent 之间的请求间隔（秒）
    _DEVELOP_INTERVAL_SECONDS = 10

    # 开发任务 prompt 模板
    _DEVELOP_PROMPT_TEMPLATE = """请完成以下开发任务，包括编码和自测：

{module} 模块的开发任务：
{task}

要求：
1. 先阅读相关代码了解现状，再开始修改
2. 遵循项目现有的代码风格和规范
3. 编写/更新单元测试
4. 运行测试验证（如果有 pom.xml：mvn test；有 build.gradle：./gradlew test）
5. 输出完成摘要：修改的文件列表、测试结果、关键实现决策"""

    def __init__(
        self,
        work_directory: str,
        task_name: str,
        on_log: callable = None
    ):
        super().__init__(work_directory=work_directory, on_log=on_log)
        self._task_name = task_name
        self._result_file = self.RESULT_PATH / task_name / "develop-report.md"
        self._task_file = self.RESULT_PATH / task_name / "task-split.md"
        self._subagent_manager = SubagentManager()
        self._reports: dict[str, str] = {}

    def _load_prompt_template(self) -> str:
        if self.PROMPT_FILE.exists():
            content = self.PROMPT_FILE.read_text(encoding="utf-8")
            return content
        return ""

    def build_system_prompt(self) -> str:
        prompt_template = self._load_prompt_template()
        system_prompt = prompt_template.replace("{{DEVELOP_OUTPUT_FILE}}", str(self._result_file))
        system_prompt = system_prompt.replace("{{MEMORY_PATH}}", str(self.MEMORY_PATH))
        return system_prompt

    def get_default_input(self) -> str:
        """获取输入框默认内容"""
        if self._task_file.exists():
            return "开始开发"
        return f"任务拆分文件 {self._task_file} 不存在，请先完成任务拆分阶段"

    # ── chat 重写：第一次自动触发开发分发 ────────────────────────────────────

    async def chat(self, context: str) -> None:
        """第一次调用时直接分发开发任务给 subagent，跳过主代理"""
        if not hasattr(self, '_dev_triggered'):
            self._dev_triggered = True
            await self._auto_develop()
        else:
            await super().chat(context)

    # ── close 覆写：确保子代理连接被清理 ─────────────────────────────────────

    async def close(self) -> None:
        """关闭流程，断开所有子代理连接"""
        await self._subagent_manager.disconnect_all()
        await super().close()

    # ── 自动开发流程 ────────────────────────────────────────────────────────

    async def _auto_develop(self) -> None:
        """读取 task-split.md，逐个将任务发给 subagent 执行开发和自测"""
        self._log("📋", "[Develop]", "开始开发阶段…")

        # 解析 task-split.md
        tasks = self._parse_task_split(self._task_file)
        if not tasks:
            self._log("⚠️", "[Develop]", "task-split.md 为空或不存在，请在对话中手动指定任务")
            return

        # 按模块分组
        module_tasks: dict[str, str] = {}
        for item in tasks:
            module = item.get("module", "")
            task_content = item.get("task", "")
            if module in module_tasks:
                module_tasks[module] += "\n" + task_content
            else:
                module_tasks[module] = task_content

        self._log("🛠️", "[Develop]", f"共 {len(module_tasks)} 个模块需要开发")

        # 逐个模块分发开发任务
        for i, (module, task_desc) in enumerate(module_tasks.items()):
            if i > 0:
                self._log("⏳", "[Develop]", f"等待 {self._DEVELOP_INTERVAL_SECONDS}s 后继续…")
                await asyncio.sleep(self._DEVELOP_INTERVAL_SECONDS)

            dev_prompt = self._DEVELOP_PROMPT_TEMPLATE.format(
                module=module,
                task=task_desc,
            )
            self._log("🛠️", "[Develop]", f"正在向 {module} 发送开发任务…")

            try:
                report = await self._subagent_manager.query(
                    name=module,
                    prompt=dev_prompt,
                    max_turns=self._DEVELOP_MAX_TURNS,
                    on_log=self._log,
                )
                self._reports[module] = report
                self._log("✅", "[Develop]", f"{module} 开发完成")

            except ValueError as e:
                self._log("⚠️", "[Develop]", str(e))
                self._reports[module] = f"[跳过] {e}"
            except Exception as e:
                self._log("❌", "[Develop]", f"{module} 开发失败: {e}")
                self._reports[module] = f"[开发失败] {e}"

        # 汇总写入 develop-report.md
        await self._write_report()

        # 开发完成，断开所有子代理连接
        await self._subagent_manager.disconnect_all()

        self._log("✅", "[Develop]", "开发阶段全部完成，请查看 develop-report.md")

    async def _write_report(self) -> None:
        """汇总各模块开发报告写入文件"""
        parts = ["# 开发报告\n"]
        for module, report in self._reports.items():
            parts.append(f"## {module}\n\n{report}\n")
        content = "\n".join(parts)

        # 确保目录存在
        self._result_file.parent.mkdir(parents=True, exist_ok=True)
        self._result_file.write_text(content, encoding="utf-8")
        self._log("📄", "[Develop]", f"开发报告已写入 {self._result_file}")

    def _parse_task_split(self, path: Path) -> list[dict]:
        """解析 task-split.md"""
        try:
            content = path.read_text(encoding="utf-8").strip()
            return json.loads(content)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            self._log("❌", "[Develop]", f"解析失败: {e}")
            return []
