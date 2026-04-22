"""子代理管理器 - 懒加载模式

配置从 subagent.json 读取，ClaudeSDKClient 在首次 query 时才创建，后续复用。
"""

import json
from pathlib import Path
from typing import Callable, Optional

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
)

from ..process.base import DEFAULT_CLAUDE_ENV,MODEL_NAME

# 项目根目录
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_SUBAGENT_CONFIG_PATH = _PROJECT_ROOT / "config" / "subagent.json"


class SubagentManager:
    """子代理管理器 - 懒加载，首次 query 时才初始化 ClaudeSDKClient"""

    def __init__(self):
        self._clients: dict[str, ClaudeSDKClient] = {}
        self._configs: dict[str, dict] = {}
        self._load_config()

    def _load_config(self) -> None:
        """加载 subagent.json 配置"""
        if not _SUBAGENT_CONFIG_PATH.exists():
            return
        with open(_SUBAGENT_CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
        for item in config.get("subagents", []):
            name = item["name"]
            self._configs[name] = {
                "workspace": item["workspace"],
                "prompt_path": item["prompt_path"],
                "max_turns": None,
            }

    def _build_system_prompt(self, name: str) -> str:
        """根据配置加载 prompt 文件"""
        prompt_path = self._configs[name]["prompt_path"]
        abs_path = _PROJECT_ROOT / prompt_path
        if abs_path.exists():
            return abs_path.read_text(encoding="utf-8")
        return ""

    async def _ensure_client(self, name: str) -> ClaudeSDKClient:
        """懒初始化：首次调用时创建并连接 ClaudeSDKClient，后续复用"""
        if name in self._clients:
            return self._clients[name]

        if name not in self._configs:
            raise ValueError(f"子代理配置不存在: {name}")

        cfg = self._configs[name]
        system_prompt = self._build_system_prompt(name)

        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            cwd=cfg["workspace"],
            permission_mode="bypassPermissions",
            model=MODEL_NAME,
            env=DEFAULT_CLAUDE_ENV,
        )
        if cfg["max_turns"] is not None:
            options.max_turns = cfg["max_turns"]

        client = ClaudeSDKClient(options=options)
        await client.connect()
        self._clients[name] = client
        return client

    async def query(
        self,
        name: str,
        prompt: str,
        max_turns: int = None,
        on_log: Callable[[str, str, str], None] = None,
    ) -> str:
        """向指定子代理发送 query 并收集完整响应

        首次调用时自动初始化 client（懒加载），后续复用同一连接。

        Args:
            name: 子代理名称（必须在 subagent.json 中配置）
            prompt: 发送给子代理的内容
            max_turns: 最大交互轮数，仅首次初始化时生效
            on_log: 日志回调 (icon, tag, message)，用于输出中间 AssistantMessage

        Returns:
            完整的响应文本（优先 ResultMessage.result，为空则拼接所有文本）
        """
        # 记录 max_turns（仅首次初始化时使用）
        if name in self._configs and max_turns is not None:
            if self._configs[name]["max_turns"] is None:
                self._configs[name]["max_turns"] = max_turns

        # 懒初始化
        client = await self._ensure_client(name)

        await client.query(prompt)

        feedback = ""
        text_parts: list[str] = []

        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock) and block.text.strip():
                        text = block.text.strip()
                        text_parts.append(text)
                        if on_log:
                            snippet = text.replace("\n", " ")[:150]
                            on_log("💬", f"[{name}]", snippet)
            elif isinstance(msg, ResultMessage):
                feedback = msg.result or ""

        # 优先 ResultMessage，为空则兜底拼接所有文本
        if not feedback and text_parts:
            feedback = "\n\n".join(text_parts)

        return feedback

    async def disconnect(self, name: str) -> None:
        """断开指定子代理"""
        client = self._clients.pop(name, None)
        if client:
            await client.disconnect()

    async def disconnect_all(self) -> None:
        """断开所有已连接的子代理"""
        for client in self._clients.values():
            await client.disconnect()
        self._clients.clear()

    def list_names(self) -> list[str]:
        """列出所有配置的子代理名称"""
        return list(self._configs.keys())

    def list_connected(self) -> list[str]:
        """列出已连接的子代理名称"""
        return list(self._clients.keys())
