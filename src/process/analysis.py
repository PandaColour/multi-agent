"""需求分析流程"""
from abc import ABC


from pathlib import Path

from .base import AbstractProcess


class Analysis(AbstractProcess):
    # Prompt 文件路径
    PROMPT_FILE = Path(__file__).parent.parent.parent / "prompts" / "analysis.md"
    # 系统记忆路径
    MEMORY_PATH = Path(__file__).parent.parent.parent / "memory" / "analysis"
    # 结果文件路径
    RESULT_PATH = Path(__file__).parent.parent.parent

    def __init__(
        self,
        work_directory: str,
        task_name: str,
        on_log: callable = None
    ):
        super().__init__(work_directory=work_directory, on_log=on_log)
        self._task_name = task_name
        self._result_file = self.RESULT_PATH / task_name / "feature-analysis.md"

    def _load_prompt_template(self) -> str:
        if self.PROMPT_FILE.exists():
            content = self.PROMPT_FILE.read_text(encoding="utf-8")
            return content
        return ""

    def build_system_prompt(self) -> str:
        prompt_template = self._load_prompt_template()
        system_prompt = prompt_template.replace("{{ANALYSIS_OUTPUT_FILE}}", str(self._result_file))
        system_prompt = system_prompt.replace("{{MEMORY_PATH}}", str(self.MEMORY_PATH))
        return system_prompt

