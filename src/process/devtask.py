"""任务拆分流程 - 根据需求分析结果拆分为各模块的具体开发任务

流程说明：
  第一次 chat 时自动完成拆分 + 子代理复核：
    1. 调用父类 chat 完成 feature-analysis.md → task-split.md 的拆分
    2. 解析 task-split.md，通过 SubagentManager 找到各模块对应子代理
    3. 将任务发送给子代理复核（不开发）
    4. 收集反馈存入 self._feedbacks，后续可根据反馈重新拆分
"""

import json
import asyncio
from pathlib import Path

from .base import AbstractProcess, _CMD_CHAT
from ..subagent.subagent_manager import SubagentManager


class DevTask(AbstractProcess):
    """任务拆分流程"""

    # Prompt 文件路径
    PROMPT_FILE = Path(__file__).parent.parent.parent / "prompts" / "task.md"
    # 系统记忆路径
    MEMORY_PATH = Path(__file__).parent.parent.parent / "memory" / "task"
    # 结果文件路径
    RESULT_PATH = Path(__file__).parent.parent.parent

    # 子代理复核时的最大交互轮数（需要读代码探索，给足够空间）
    _REVIEW_MAX_TURNS = 15
    # 子代理之间的请求间隔（秒），避免 429 限速
    _REVIEW_INTERVAL_SECONDS = 10

    # 子代理复核 prompt 模板
    _REVIEW_PROMPT_TEMPLATE = """现在先不要改代码，审核以下任务，回复完成任务需要做哪些修改，如果功能已经实现，说明怎么调用，如果评估任务不应该由本模块实现，提出改进意见。

{module} 模块的任务内容：
{task}"""

    # cloudbank-partner 专用复核 prompt（强调机构对接职责）
    _PARTNER_REVIEW_PROMPT = """cloudbank-partner 是机构对接层，继承和扩展核心模块的实现，负责处理特定机构的个性化需求和对接逻辑。

现在先不要改代码，审核以下任务。请重点评估：
1. 核心模块的这些变更是否需要在机构层做适配（覆写、扩展、配置覆盖）
2. 机构层是否需要新增对接代码或调整已有对接逻辑
3. 如果核心模块变更不影响机构层，说明原因
4. 如果评估后认为机构层确实需要改动，指出具体的修改点

其他模块的任务变更摘要：
{task}"""

    def __init__(
        self,
        work_directory: str,
        task_name: str,
        on_log: callable = None
    ):
        super().__init__(work_directory=work_directory, on_log=on_log)
        self._task_name = task_name
        self._result_file = self.RESULT_PATH / task_name / "task-split.md"
        # 上一阶段的需求分析文件
        self._analysis_file = self.RESULT_PATH / task_name / "feature-analysis.md"
        # 子代理管理器
        self._subagent_manager = SubagentManager()
        # 第一次 chat 标记
        self._first_chat_done = False
        # 子代理复核反馈 {模块名: 反馈文本}
        self._feedbacks: dict[str, str] = {}

    def _load_prompt_template(self) -> str:
        if self.PROMPT_FILE.exists():
            content = self.PROMPT_FILE.read_text(encoding="utf-8")
            return content
        return ""

    def build_system_prompt(self) -> str:
        prompt_template = self._load_prompt_template()
        system_prompt = prompt_template.replace("{{TASK_OUTPUT_FILE}}", str(self._result_file))
        system_prompt = system_prompt.replace("{{MEMORY_PATH}}", str(self.MEMORY_PATH))
        return system_prompt

    def get_default_input(self) -> str:
        """获取输入框默认内容"""
        if self._analysis_file.exists():
            return f"现在把 {self._analysis_file.name} 拆分成各模块的任务"
        return f"需求分析文件 {self._analysis_file} 不存在，请先完成需求分析阶段"

    # ── chat 重写：第一次自动触发子代理复核 ──────────────────────────────────

    async def chat(self, context: str) -> None:
        """发送消息并等待响应

        第一次调用时：先完成拆分，再自动触发子代理复核。
        后续调用：正常对话（用于用户根据反馈调整任务等）。
        """
        # 调用父类 chat 完成任务拆分
        await super().chat(context)

        # 仅第一次 chat 后自动触发子代理复核
        if not self._first_chat_done:
            self._first_chat_done = True
            await self._auto_review()

    # ── close 覆写：关闭时发送任务拆分阶段的记忆整理 ──────────────────────────

    async def close(self) -> None:
        """关闭流程，发送任务拆分阶段记忆整理后断开"""
        # 断开所有子代理连接
        await self._subagent_manager.disconnect_all()

        # 传递阶段特定的记忆整理提示词，由父类在 _CMD_CLOSE 中执行
        memory_prompt = "任务拆分结束，根据对话整理记忆，将任务拆分过程中发现的系统知识沉淀到记忆文件中"
        await super().close(memory_prompt=memory_prompt)

    # ── 自动复核流程 ────────────────────────────────────────────────────────

    # JSON 解析重试次数
    _JSON_RETRY_MAX = 2

    async def _auto_review(self) -> None:
        """第一次 chat 后自动执行：解析 task-split.md → 逐个分发子代理复核 → 收集反馈

        子代理通过 SubagentManager.query() 懒加载，首次 query 时才初始化，后续复用连接。
        模块之间间隔等待，避免 429 限速。
        """
        self._log("📋", "[Task]", "任务拆分完成，开始自动复核…")

        # 解析 task-split.md，失败则要求重新输出
        tasks = await self._parse_task_split_with_retry()
        if not tasks:
            self._log("⚠️", "[Task]", "task-split.md 多次解析失败，跳过复核")
            return

        # 按模块分组（正常情况每模块只有一条任务）
        module_tasks: dict[str, str] = {}
        for item in tasks:
            module = item.get("module", "")
            task_content = item.get("task", "")
            if module in module_tasks:
                module_tasks[module] += "\n" + task_content
            else:
                module_tasks[module] = task_content

        self._log("🔍", "[复核]", f"共 {len(module_tasks)} 个模块需要复核")

        # 确保 cloudbank-partner 始终参与复核
        self._ensure_partner_task(module_tasks)

        # 逐个模块复核
        for i, (module, task_desc) in enumerate(module_tasks.items()):
            # 非首个模块，等待间隔避免限速
            if i > 0:
                self._log("⏳", "[复核]", f"等待 {self._REVIEW_INTERVAL_SECONDS}s 后继续…")
                await asyncio.sleep(self._REVIEW_INTERVAL_SECONDS)

            # 构造复核 prompt
            if module == "cloudbank-partner":
                review_prompt = self._PARTNER_REVIEW_PROMPT.format(task=task_desc)
            else:
                review_prompt = self._REVIEW_PROMPT_TEMPLATE.format(
                    module=module,
                    task=task_desc,
                )
            self._log("🔍", "[复核]", f"正在向 {module} 发送复核请求…")

            try:
                feedback = await self._subagent_manager.query(
                    name=module,
                    prompt=review_prompt,
                    max_turns=self._REVIEW_MAX_TURNS,
                    on_log=self._log,
                )
                self._feedbacks[module] = feedback
                self._log("✅", "[复核]", f"{module} 复核完成")

            except ValueError as e:
                self._log("⚠️", "[复核]", str(e))
                self._feedbacks[module] = f"[跳过] {e}"
            except Exception as e:
                self._log("❌", "[复核]", f"{module} 复核失败: {e}")
                self._feedbacks[module] = f"[复核失败] {e}"

        # 根据反馈自动重新拆分
        if self._feedbacks:
            await self._refine_task_split()
        else:
            self._log("⚠️", "[Task]", "未收到任何复核反馈，跳过重新拆分")

        # 复核完成，断开所有子代理连接（后续不再需要）
        await self._subagent_manager.disconnect_all()

        self._log("✅", "[Task]", "任务拆分流程全部完成，请查看最终结果")

    # ── 根据反馈重新拆分 ────────────────────────────────────────────────────

    async def _refine_task_split(self) -> None:
        """根据子代理复核反馈，让 ClaudeSDKClient 重新拆分任务"""
        self._log("🔄", "[重新拆分]", "根据复核反馈重新拆分任务…")

        # 拼装反馈内容
        feedback_parts: list[str] = []
        for module, feedback in self._feedbacks.items():
            feedback_parts.append(f"## {module} 复核反馈\n{feedback}")
        feedback_text = "\n\n".join(feedback_parts)

        # 读取当前 task-split.md 内容
        current_split = ""
        if self._result_file.exists():
            current_split = self._result_file.read_text(encoding="utf-8")

        refine_prompt = f"""以下是初步的任务拆分结果（task-split.md）：
{current_split}

以下是各模块子代理的复核反馈：
{feedback_text}

请根据复核反馈重新拆分任务，要求：
1. 每个模块仍然只有一个任务
2. 根据反馈补充遗漏的修改点、修正不准确的地方
3. 如果反馈指出任务不应该由该模块实现，调整到合适的模块
4. 将最终的任务拆分结果写入 {self._result_file}

**格式要求（极其重要）：**
- 文件内容必须是纯 JSON 数组，能直接被 json.loads() 解析
- 不要包含 ```json 或 ``` 等 markdown 标记
- 不要在 JSON 前后添加任何解释性文字
- 不要使用单引号，不要有 trailing comma
- 字符串中的换行用 \\n 表示"""

        # 通过内部 chat 发送，不走用户输入计数
        loop = __import__("asyncio").get_running_loop()
        future = loop.create_future()
        await self._cmd_queue.put((_CMD_CHAT, refine_prompt, future))
        await future

        self._log("✅", "[重新拆分]", "任务重新拆分完成")

    async def _parse_task_split_with_retry(self) -> list[dict]:
        """解析 task-split.md，失败时把错误反馈给 ClaudeSDKClient 要求重新输出

        最多重试 _JSON_RETRY_MAX 次，每次把原始内容和 JSON 错误发给 client 修正。
        """
        # 第一次尝试
        tasks = self._parse_task_split(self._result_file)
        if tasks:
            return tasks

        # 解析失败，进入重试
        for attempt in range(1, self._JSON_RETRY_MAX + 1):
            self._log("🔄", "[Task]", f"JSON 解析失败，第 {attempt} 次要求重新输出…")

            # 读取原始内容和错误
            raw_content = ""
            try:
                raw_content = self._result_file.read_text(encoding="utf-8")
            except FileNotFoundError:
                self._log("❌", "[Task]", "task-split.md 文件不存在")
                return []

            # 尝试获取具体错误信息
            error_msg = ""
            try:
                json.loads(raw_content)
            except json.JSONDecodeError as e:
                error_msg = str(e)

            # 构造修正 prompt
            fix_prompt = f"""你写入的 task-split.md 文件 JSON 格式有误，解析失败。

错误信息：{error_msg}

文件当前内容（前 2000 字符）：
{raw_content[:2000]}

请修正格式后重新写入 {self._result_file}。

**格式要求：**
- 文件内容必须是纯 JSON 数组，能直接被 json.loads() 解析
- 不要包含 ```json 或 ``` 等 markdown 标记
- 不要在 JSON 前后添加任何解释性文字
- 不要使用单引号，不要有 trailing comma
- 字符串中的换行用 \\n 表示"""

            # 通过内部 chat 发送修正请求
            loop = __import__("asyncio").get_running_loop()
            future = loop.create_future()
            await self._cmd_queue.put((_CMD_CHAT, fix_prompt, future))
            await future

            # 重新解析
            tasks = self._parse_task_split(self._result_file)
            if tasks:
                self._log("✅", "[Task]", f"第 {attempt} 次重试解析成功")
                return tasks

        self._log("❌", "[Task]", f"经过 {self._JSON_RETRY_MAX} 次重试仍解析失败")
        return []

    def _parse_task_split(self, path: Path) -> list[dict]:
        """解析 task-split.md 文件（纯 JSON 数组格式）"""
        try:
            content = path.read_text(encoding="utf-8").strip()
            return json.loads(content)
        except json.JSONDecodeError as e:
            self._log("❌", "[Task]", f"JSON 解析失败: {e}")
            return []
        except FileNotFoundError:
            self._log("❌", "[Task]", f"文件不存在: {path}")
            return []

    def get_feedbacks(self) -> dict[str, str]:
        """获取各模块子代理的复核反馈"""
        return self._feedbacks.copy()

    def _ensure_partner_task(self, module_tasks: dict[str, str]) -> None:
        """确保 cloudbank-partner 始终参与复核

        cloudbank-partner 继承核心模块实现机构对接，因此几乎所有核心模块变更
        都需要在 partner 层评估影响。如果 task-split.md 中没有 partner 任务，
        自动从其他模块任务汇总生成一条。
        """
        partner_name = "cloudbank-partner"

        if partner_name in module_tasks:
            return

        # 检查 subagent.json 中是否配置了 cloudbank-partner
        if partner_name not in self._subagent_manager.list_names():
            return

        # 从其他模块的任务汇总生成 partner 的复核内容
        other_tasks = []
        for mod, task in module_tasks.items():
            other_tasks.append(f"[{mod}] {task}")

        partner_task = "以下核心模块有变更，请评估机构对接层是否需要适配：\n"
        partner_task += "\n".join(other_tasks)

        module_tasks[partner_name] = partner_task
        self._log("📌", "[复核]", f"自动补充 {partner_name} 复核任务（继承评估机构对接影响）")
