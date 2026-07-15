"""Prism 应用入口

启动 PySide6 应用，加载全局样式，显示主窗口。
"""
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中（支持直接从仓库目录运行）
_APP_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))
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
from PySide6.QtGui import QFontDatabase, QIcon

from ui.main_window import MainWindow
from db.database import Database


def main():
    # 高 DPI 支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Prism")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("Prism")

    # 应用图标（Dock / 任务栏）
    _icon_path = Path(__file__).parent / "assets" / "icons" / "icon.png"
    if _icon_path.exists():
        app.setWindowIcon(QIcon(str(_icon_path)))

    # 加载项目自带字体
    _fonts_dir = Path(__file__).parent / "assets" / "fonts"
    for _f in _fonts_dir.glob("*.ttf"):
        if _f.name.startswith("."):
            continue
        _fid = QFontDatabase.addApplicationFontFromData(_f.read_bytes())
        if _fid >= 0:
            _families = QFontDatabase.applicationFontFamilies(_fid)
            print(f"[Prism] font: {_families[0]}")

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
