"""Prism 应用入口

启动 PySide6 应用，加载全局样式，显示主窗口。
"""
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中（支持 prism.xxx 绝对导入）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 加载 .env（如果存在）
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ImportError:
        pass

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from prism.ui.main_window import MainWindow
from prism.db.database import Database


def main():
    # 高 DPI 支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Prism")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("Prism")

    # 初始化数据库
    try:
        db = Database()
        db.migrate()
    except Exception as e:
        print(f"[Prism] 数据库初始化失败: {e}")

    # 启动主窗口
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
