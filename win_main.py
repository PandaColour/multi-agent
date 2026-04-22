import sys
import os

# 高 DPI 支持（PyQt6 方式，必须在 import PyQt6.QtWidgets 之前设置）
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"

from PyQt6.QtWidgets import QApplication
from src.qt.main_window import MainWindow


def main():
    """应用程序入口"""
    app = QApplication(sys.argv)

    # 设置应用程序样式
    app.setStyle("Fusion")

    # 创建并显示主窗口
    window = MainWindow()
    window.show()

    # 运行事件循环
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
