"""流程基类"""

import json
import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock, ToolUseBlock
)

# 从 config/config.json 加载模型配置
_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "config.json"
with open(_CONFIG_PATH, encoding="utf-8") as f:
    _cfg = json.load(f)["model"]

MODEL_NAME = _cfg["name"]
DEFAULT_CLAUDE_ENV = {
    "ANTHROPIC_API_KEY": _cfg["api_key"],
    "ANTHROPIC_BASE_URL": _cfg["base_url"],
}




# 命令类型
_CMD_START = "start"
_CMD_CHAT = "chat"
_CMD_CLOSE = "close"


class AbstractProcess(ABC):
    """流程基类

    所有客户端操作通过命令队列在同一个 asyncio task 中执行，
    避免跨 task 使用 ClaudeSDKClient 导致 anyio cancel scope 崩溃。
    """

    def __init__(
        self,
        work_directory: str,
        on_log: callable = None,
    ):
        self._work_directory = work_directory
        self._input_counter = 0  # 用户输入计数器
        self._on_log = on_log  # 日志回调函数

        # 命令队列和 worker task
        self._cmd_queue: Optional[asyncio.Queue] = None
        self._worker_task: Optional[asyncio.Task] = None

    @abstractmethod
    def build_system_prompt(self) -> str:
        return ""

    def _log(self, icon: str, tag: str, message: str):
        """输出日志"""
        if self._on_log:
            self._on_log(icon, tag, message)

    async def _process_response(self) -> None:
        """接收并处理响应"""
        client = self._client
        if client is None:
            return

        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock) and block.text.strip():
                        text = block.text.strip()[0:500]
                        self._log("💬", "[Assistant]", text)
                    if isinstance(block, ToolUseBlock):
                        self._log("🔧", "[Tool]", block.name)
            elif isinstance(msg, ResultMessage):
                result = msg.result or ""
                if result:
                    self._log("✅", "[Result]", result)

    async def _worker(self) -> None:
        """Worker task - 在同一个 async 上下文中处理所有命令"""
        self._client: Optional[ClaudeSDKClient] = None

        while True:
            cmd = await self._cmd_queue.get()

            try:
                if cmd[0] == _CMD_START:
                    system_prompt = self.build_system_prompt()
                    self._client = ClaudeSDKClient(options=ClaudeAgentOptions(
                        system_prompt=system_prompt,
                        cwd=self._work_directory,
                        permission_mode="bypassPermissions",
                        model=MODEL_NAME,
                        env=DEFAULT_CLAUDE_ENV,
                    ))
                    await self._client.connect()
                    future = cmd[1]
                    if future and not future.done():
                        future.set_result("started")

                elif cmd[0] == _CMD_CHAT:
                    context = cmd[1]
                    future = cmd[2]
                    self._input_counter += 1
                    await self._client.query(context)
                    await self._process_response()
                    if future and not future.done():
                        future.set_result("sent")

                elif cmd[0] == _CMD_CLOSE:
                    # 如果用户输入次数大于1，先发送记忆整理提示
                    if self._input_counter > 1:
                        custom_prompt = cmd[2] if len(cmd) > 2 else None
                        memory_prompt = custom_prompt or "结合我们的对话,为了一会更好的完成此类任务,整理你的记忆,允许根据需要增加记忆文件"
                        self._log("📝", "[Memory]", "正在整理记忆...")
                        await self._client.query(memory_prompt)
                        await self._process_response()

                    if self._client:
                        await self._client.disconnect()
                        self._client = None

                    future = cmd[1]
                    if future and not future.done():
                        future.set_result("closed")
                    return  # 退出 worker

            except asyncio.CancelledError:
                # worker 被取消，清理客户端
                self._log("⚠️", "[Worker]", "Worker 被取消")
                if self._client:
                    try:
                        await self._client.disconnect()
                    except Exception:
                        pass
                    self._client = None
                # 设置 future 防止调用方永远等待
                future = None
                if len(cmd) > 1:
                    future = cmd[1] if cmd[0] in (_CMD_START, _CMD_CLOSE) else cmd[2]
                if future and not future.done():
                    future.set_exception(RuntimeError("Worker 被取消"))
                return

            except Exception as e:
                self._log("❌", "[Error]", str(e))
                future = None
                if cmd[0] == _CMD_START:
                    future = cmd[1]
                elif cmd[0] == _CMD_CHAT:
                    future = cmd[2]
                elif cmd[0] == _CMD_CLOSE:
                    future = cmd[1]
                if future and not future.done():
                    future.set_exception(e)
                if cmd[0] == _CMD_CLOSE:
                    return  # 即使出错也要退出 worker

    async def start(self) -> None:
        """启动流程（创建 worker task 并初始化客户端）"""
        loop = asyncio.get_running_loop()
        self._cmd_queue = asyncio.Queue()
        future = loop.create_future()

        # 启动 worker task
        self._worker_task = loop.create_task(self._worker())

        # 发送 start 命令并等待完成
        await self._cmd_queue.put((_CMD_START, future))
        await future

    async def chat(self, context: str) -> None:
        """发送消息并等待响应"""
        if self._cmd_queue is None:
            self._log("⚠️", "[Error]", "客户端未连接，请等待初始化完成")
            return

        loop = asyncio.get_running_loop()
        future = loop.create_future()

        await self._cmd_queue.put((_CMD_CHAT, context, future))

        # 超时保护：CLI 子进程崩溃时 future 可能永远不会 resolve
        try:
            await asyncio.wait_for(future, timeout=600.0)
        except asyncio.TimeoutError:
            self._log("❌", "[Error]", "请求超时（600s），CLI 子进程可能已崩溃")
            raise RuntimeError("Claude CLI 请求超时，请重试")

    async def close(self, memory_prompt: str = None) -> None:
        """关闭流程

        Args:
            memory_prompt: 自定义记忆整理提示词，None 则使用默认提示词
        """
        if self._cmd_queue is None:
            return

        loop = asyncio.get_running_loop()
        future = loop.create_future()

        await self._cmd_queue.put((_CMD_CLOSE, future, memory_prompt))

        # 等待 close 完成，超时则取消 worker
        try:
            await asyncio.wait_for(future, timeout=30.0)
        except asyncio.TimeoutError:
            self._log("⚠️", "[Warning]", "关闭超时，强制终止")

        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        self._worker_task = None
        self._cmd_queue = None
