import asyncio
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QGroupBox,
    QGridLayout, QListWidget, QListWidgetItem,
    QInputDialog, QMessageBox, QTextBrowser
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QTextCursor
import threading
from typing import Callable, Optional
import html

from ..model import Task, Storage


class AsyncSignals(QObject):
    """用于从异步线程发信号到主线程"""
    success = pyqtSignal(str)
    error = pyqtSignal(str)


class AsyncLoopThread(QThread):
    """保持事件循环运行的线程"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loop = None
        self._ready = threading.Event()

    def run(self):
        """运行事件循环"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()

    def get_loop(self):
        """获取事件循环（阻塞直到就绪）"""
        self._ready.wait()
        return self._loop

    def submit_coro(self, coro, on_success: Optional[Callable] = None, on_error: Optional[Callable] = None):
        """提交协程到事件循环执行"""
        if self._loop is None:
            return

        # 创建信号对象用于回调
        signals = AsyncSignals()
        if on_success:
            signals.success.connect(on_success)
        if on_error:
            signals.error.connect(on_error)

        async def wrapped():
            try:
                result = await coro
                if on_success:
                    signals.success.emit(result or "")
            except Exception as e:
                if on_error:
                    signals.error.emit(str(e))

        asyncio.run_coroutine_threadsafe(wrapped(), self._loop)

    def stop(self):
        """停止事件循环"""
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)


class MainWindow(QMainWindow):
    """主窗口"""

    # 配置文件路径
    CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
    STORAGE_FILE = CONFIG_DIR / "local_storage.json"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Multi-Agent 工作台")
        self.setMinimumSize(1000, 600)

        # 当前选中的任务ID
        self.current_task_id: int = -1

        # 当前任务的流程对象
        self._current_process = None

        # 存储管理器
        self.storage = Storage(self.STORAGE_FILE)
        self.storage.load()

        # 异步事件循环线程（共享同一个事件循环）
        self._async_thread = AsyncLoopThread()
        self._async_thread.start()

        # 进程是否就绪
        self._process_ready = False

        # 初始化界面
        self._init_ui()

        # 刷新任务列表
        self._refresh_task_list()

    def _init_ui(self):
        """初始化界面"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # 1. 工作目录选择区域
        dir_group = QGroupBox("工作目录")
        dir_layout = QHBoxLayout(dir_group)

        self.dir_edit = QLineEdit()
        self.dir_edit.setPlaceholderText("请选择工作目录...")
        self.dir_edit.setReadOnly(True)
        self.dir_edit.setText(self.storage.work_directory)
        dir_layout.addWidget(self.dir_edit)

        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.setFixedWidth(80)
        self.browse_btn.clicked.connect(self._browse_directory)
        dir_layout.addWidget(self.browse_btn)

        main_layout.addWidget(dir_group)

        # 2. 主内容区域（左侧列表 + 右侧工作区）
        content_layout = QHBoxLayout()
        content_layout.setSpacing(15)

        # 2.1 左侧列表
        left_group = QGroupBox("任务列表")
        left_layout = QVBoxLayout(left_group)

        self.task_list = QListWidget()
        self.task_list.currentRowChanged.connect(self._on_task_selected)
        left_layout.addWidget(self.task_list)

        # 添加任务按钮
        btn_layout = QHBoxLayout()
        self.add_task_btn = QPushButton("添加任务")
        self.add_task_btn.clicked.connect(self._add_task)
        btn_layout.addWidget(self.add_task_btn)

        self.del_task_btn = QPushButton("删除任务")
        self.del_task_btn.clicked.connect(self._delete_task)
        btn_layout.addWidget(self.del_task_btn)

        left_layout.addLayout(btn_layout)
        content_layout.addWidget(left_group, 1)

        # 2.2 右侧工作区（工作阶段 + 聊天对话框）
        right_group = QGroupBox("工作区")
        right_layout = QVBoxLayout(right_group)
        right_layout.setSpacing(15)

        # 2.2.1 工作阶段区域
        stages_container = QWidget()
        stages_container_layout = QHBoxLayout(stages_container)
        stages_container_layout.setContentsMargins(0, 0, 0, 0)
        stages_container_layout.setSpacing(10)

        # 阶段显示区域
        stages_widget = QWidget()
        stages_layout = QGridLayout(stages_widget)
        stages_layout.setSpacing(10)
        stages_layout.setContentsMargins(0, 0, 0, 0)

        self.stage_labels = []
        self.stage_indicators = []

        for i, stage in enumerate(Storage.WORK_STAGES):
            # 阶段指示器（圆形）
            indicator = QLabel(str(i + 1))
            indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
            indicator.setFixedSize(36, 36)
            indicator.setStyleSheet("""
                QLabel {
                    background-color: #e0e0e0;
                    border-radius: 18px;
                    font-size: 14px;
                    font-weight: bold;
                    color: #666;
                }
            """)
            stages_layout.addWidget(indicator, 0, i, alignment=Qt.AlignmentFlag.AlignCenter)
            self.stage_indicators.append(indicator)

            # 阶段名称
            label = QLabel(stage)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            stages_layout.addWidget(label, 1, i, alignment=Qt.AlignmentFlag.AlignCenter)
            self.stage_labels.append(label)

            # 添加箭头（除了最后一个）
            if i < len(Storage.WORK_STAGES) - 1:
                arrow = QLabel("→")
                arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
                arrow.setStyleSheet("font-size: 18px; color: #999;")
                stages_layout.addWidget(arrow, 0, i + 1, 2, 1)

        # 设置列拉伸因子使布局均匀
        for i in range(len(Storage.WORK_STAGES) * 2 - 1):
            stages_layout.setColumnStretch(i, 1)

        stages_container_layout.addWidget(stages_widget, 1)

        # 本阶段任务完成按钮
        self.complete_stage_btn = QPushButton("本阶段任务完成")
        self.complete_stage_btn.setFixedHeight(36)
        self.complete_stage_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                padding: 0 15px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
            QPushButton:pressed {
                background-color: #b71c1c;
            }
            QPushButton:disabled {
                background-color: #ffcdd2;
                color: #999;
            }
        """)
        self.complete_stage_btn.clicked.connect(self._complete_current_stage)
        stages_container_layout.addWidget(self.complete_stage_btn)

        right_layout.addWidget(stages_container)

        # 2.2.2 聊天对话框区域
        chat_group = QGroupBox("对话")
        chat_layout = QVBoxLayout(chat_group)

        # 聊天记录显示区
        self.chat_display = QTextBrowser()
        self.chat_display.setOpenExternalLinks(True)
        chat_layout.addWidget(self.chat_display)

        # 输入区域
        input_layout = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("输入消息...")
        self.chat_input.returnPressed.connect(self._send_message)
        input_layout.addWidget(self.chat_input)

        self.send_btn = QPushButton("发送")
        self.send_btn.setFixedWidth(80)
        self.send_btn.clicked.connect(self._send_message)
        self.send_btn.setEnabled(False)  # 初始禁用
        input_layout.addWidget(self.send_btn)

        chat_layout.addLayout(input_layout)
        right_layout.addWidget(chat_group, 1)

        content_layout.addWidget(right_group, 3)

        main_layout.addLayout(content_layout, 1)

        # 初始化阶段显示
        self._update_stage_display(-1)

        # 初始禁用输入框
        self.chat_input.setEnabled(False)

    def _refresh_task_list(self):
        """刷新任务列表显示"""
        # 保存当前选中的任务ID
        current_id = self.current_task_id

        self.task_list.clear()
        sorted_tasks = self.storage.get_sorted_tasks()
        target_row = -1

        for row, task in enumerate(sorted_tasks):
            stage_name = Storage.WORK_STAGES[task.stage] if 0 <= task.stage < len(Storage.WORK_STAGES) else "未知"
            item = QListWidgetItem(f"#{task.id:03d} [{stage_name}] {task.name}")
            item.setData(Qt.ItemDataRole.UserRole, task.id)  # 存储任务ID
            self.task_list.addItem(item)

            # 记录需要选中的行
            if task.id == current_id:
                target_row = row

        # 恢复选中状态
        if target_row >= 0:
            self.task_list.setCurrentRow(target_row)

    def _add_task(self):
        """添加新任务"""
        text, ok = QInputDialog.getText(
            self,
            "添加任务",
            "请输入任务名称:"
        )
        if ok and text.strip():
            self.storage.add_task(name=text.strip())
            self._refresh_task_list()
            # 选中新添加的任务
            self.task_list.setCurrentRow(self.task_list.count() - 1)

    def _delete_task(self):
        """删除选中的任务"""
        row = self.task_list.currentRow()
        if row < 0:
            QMessageBox.warning(self, "警告", "请先选择一个任务!")
            return

        item = self.task_list.item(row)
        task_id = item.data(Qt.ItemDataRole.UserRole)
        task = self.storage.get_task_by_id(task_id)

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除任务 \"{task.name}\" 吗?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # 如果有正在运行的流程，先关闭
            if self._current_process and self.current_task_id == task_id:
                async def do_close_and_delete():
                    await self._current_process.close()
                    return task_id

                def on_close_success(tid: int):
                    self._current_process = None
                    self.storage.delete_task(int(tid))
                    self._refresh_task_list()
                    self.current_task_id = -1
                    self._update_stage_display(-1)

                self._run_async(do_close_and_delete(), on_success=on_close_success)
            else:
                self.storage.delete_task(task_id)
                self._refresh_task_list()
                self.current_task_id = -1
                self._update_stage_display(-1)

    def _browse_directory(self):
        """浏览选择目录"""
        directory = QFileDialog.getExistingDirectory(
            self,
            "选择工作目录",
            self.storage.work_directory or "",
            QFileDialog.Option.ShowDirsOnly
        )
        if directory:
            self.dir_edit.setText(directory)
            self.storage.set_work_directory(directory)

    def _on_task_selected(self, row: int):
        """任务选中事件"""
        if row < 0:
            self.current_task_id = -1
            self._update_stage_display(-1)
            self._process_ready = False
            self.chat_input.setEnabled(False)
            self.send_btn.setEnabled(False)
            return

        item = self.task_list.item(row)
        if item:
            task_id = item.data(Qt.ItemDataRole.UserRole)

            # 如果切换到不同任务，重置状态
            if task_id != self.current_task_id:
                self._process_ready = False
                self._current_process = None

            self.current_task_id = task_id
            task = self.storage.get_task_by_id(task_id)
            if task:
                self._update_stage_display(task.stage)

                # 非完成阶段，启动对应流程
                if task.stage < Task.STAGE_COMPLETE:
                    self._start_process(task)
                else:
                    self._clear_chat_display()
                    self.chat_input.setEnabled(False)
                    self.send_btn.setEnabled(False)

    def _start_process(self, task: Task):
        """启动当前阶段的流程"""
        stage_name = Storage.WORK_STAGES[task.stage]
        self._clear_chat_display()
        self._append_log("🚀", "[System]", f"启动{stage_name}: {task.name}")

        # 禁用输入直到启动完成
        self._process_ready = False
        self.chat_input.setEnabled(False)
        self.send_btn.setEnabled(False)

        async def do_start():
            # 获取或创建流程对象（异步）
            process = await task.get_or_create_process(self.storage.work_directory)
            if process is None:
                return None
            # 设置日志回调
            process._on_log = self._append_log
            self._current_process = process
            return f"{stage_name}已启动"

        self._run_async(do_start(), on_success=self._on_process_started)

    def _on_process_started(self, result: str):
        """流程启动成功回调"""
        if result is None:
            self._append_log("⚠️", "[System]", "无法创建流程对象")
            self.chat_input.setEnabled(True)
            self.send_btn.setEnabled(True)
            return

        self._append_log("✅", "[System]", result)

        # 启用输入
        self._process_ready = True
        self.chat_input.setEnabled(True)
        self.send_btn.setEnabled(True)

        # 如果流程有默认输入内容，填充到输入框
        if self._current_process and hasattr(self._current_process, 'get_default_input'):
            default_text = self._current_process.get_default_input()
            if default_text:
                self.chat_input.setText(default_text)

    def _send_message(self):
        """发送消息"""
        text = self.chat_input.text().strip()
        if not text:
            return

        if not self._process_ready:
            QMessageBox.warning(self, "提示", "请等待 Analysis 启动完成")
            return

        # 显示用户消息
        self._append_log("💬", "[我]", text)
        self.chat_input.clear()

        # 如果有 Analysis 流程，发送消息
        if self._current_process:
            async def do_chat():
                await self._current_process.chat(text)
                return "消息已发送"

            self._run_async(do_chat(), on_success=self._on_chat_success)

    def _on_chat_success(self, result: str):
        """聊天消息发送成功回调"""
        pass  # 日志会在 chat 过程中通过回调显示

    def _complete_current_stage(self):
        """完成当前阶段，推进到下一阶段"""
        if self.current_task_id < 0:
            QMessageBox.warning(self, "警告", "请先选择一个任务!")
            return

        task = self.storage.get_task_by_id(self.current_task_id)
        if not task:
            return

        current_stage = task.stage
        current_stage_name = Storage.WORK_STAGES[current_stage]

        # 检查是否已是最后阶段
        if current_stage >= len(Storage.WORK_STAGES) - 1:
            QMessageBox.information(self, "提示", f"任务 \"{task.name}\" 已完成所有阶段!")
            return

        # 确认推进阶段
        next_stage = current_stage + 1
        next_stage_name = Storage.WORK_STAGES[next_stage]

        reply = QMessageBox.question(
            self,
            "确认完成",
            f"确定要将任务 \"{task.name}\" 从 [{current_stage_name}] 推进到 [{next_stage_name}] 吗?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # 如果有流程，先关闭
        if self._current_process:
            self._append_log("🔄", "[System]", "正在关闭当前流程...")

            async def do_close():
                await self._current_process.close()
                await task.clear_process()
                return "流程已关闭"

            def on_close_success(result: str):
                self._append_log("✅", "[System]", result)
                self._current_process = None
                self._advance_stage(task, next_stage, next_stage_name)

            self._run_async(do_close(), on_success=on_close_success)
        else:
            self._advance_stage(task, next_stage, next_stage_name)

    def _advance_stage(self, task: Task, next_stage: int, next_stage_name: str):
        """推进到下一阶段"""
        self.storage.update_task_stage(self.current_task_id, next_stage)
        self._refresh_task_list()
        self._update_stage_display(next_stage)

        self._append_log("✅", "[System]", f"已推进到阶段: {next_stage_name}")

        # 如果到达最后阶段，提示任务完成
        if next_stage == len(Storage.WORK_STAGES) - 1:
            QMessageBox.information(self, "恭喜", f"任务 \"{task.name}\" 已完成所有阶段!")
        else:
            # 自动启动下一阶段流程
            self._start_process(task)

    def _run_async(self, coro, on_success=None, on_error=None):
        """运行异步任务（使用共享事件循环）"""
        if on_error is None:
            on_error = lambda err: self._append_log("❌", "[Error]", err)

        self._async_thread.submit_coro(coro, on_success, on_error)

    def _append_log(self, icon: str, tag: str, message: str):
        """追加日志到聊天显示区"""
        # 根据 tag 确定消息颜色
        if "[我]" in tag:
            color = "#1976d2"
        elif "[Assistant]" in tag:
            color = "#2196f3"
        elif "[Error]" in tag:
            color = "#f44336"
        else:
            color = "#ff9800"

        # 转义 HTML 特殊字符
        escaped_message = html.escape(message).replace("\n", "<br>")

        # 构建消息 HTML
        msg_html = f"""
        <div style="margin-bottom: 10px;">
            <div style="font-weight: 600; color: {color}; margin-bottom: 4px;">
                {icon} {tag}
            </div>
            <div style="color: #333; white-space: pre-wrap;">
                {escaped_message}
            </div>
        </div>
        """

        # 追加到 QTextBrowser
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(msg_html)

        # 滚动到底部
        self.chat_display.verticalScrollBar().setValue(
            self.chat_display.verticalScrollBar().maximum()
        )

    def _clear_chat_display(self):
        """清空聊天显示区"""
        self.chat_display.clear()

    def _update_stage_display(self, current_stage: int):
        """更新阶段显示样式"""
        for i, indicator in enumerate(self.stage_indicators):
            if current_stage < 0:
                # 没有选中任务，全部显示灰色
                indicator.setStyleSheet("""
                    QLabel {
                        background-color: #e0e0e0;
                        border-radius: 18px;
                        font-size: 14px;
                        font-weight: bold;
                        color: #666;
                    }
                """)
            elif i < current_stage:
                # 已完成阶段 - 绿色
                indicator.setStyleSheet("""
                    QLabel {
                        background-color: #4caf50;
                        border-radius: 18px;
                        font-size: 14px;
                        font-weight: bold;
                        color: white;
                    }
                """)
            elif i == current_stage:
                # 当前阶段 - 蓝色
                indicator.setStyleSheet("""
                    QLabel {
                        background-color: #2196f3;
                        border-radius: 18px;
                        font-size: 14px;
                        font-weight: bold;
                        color: white;
                    }
                """)
            else:
                # 未完成阶段 - 灰色
                indicator.setStyleSheet("""
                    QLabel {
                        background-color: #e0e0e0;
                        border-radius: 18px;
                        font-size: 14px;
                        font-weight: bold;
                        color: #666;
                    }
                """)

    def get_work_directory(self) -> str:
        """获取当前选择的工作目录"""
        return self.storage.work_directory

    def closeEvent(self, event):
        """窗口关闭事件"""
        # 关闭当前流程
        if self._current_process:
            async def do_close():
                await self._current_process.close()

            # 使用共享事件循环执行关闭
            future = asyncio.run_coroutine_threadsafe(
                do_close(),
                self._async_thread.get_loop()
            )
            try:
                future.result(timeout=5.0)
            except Exception:
                pass

        # 停止异步事件循环线程
        self._async_thread.stop()
        self._async_thread.wait(3000)

        event.accept()
