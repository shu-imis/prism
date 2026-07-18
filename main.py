"""Prism 应用入口

启动 PySide6 应用，加载全局样式，显示主窗口。
"""
import os
import re
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中（支持直接从仓库目录运行）
_APP_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# PyInstaller 冻结后资源文件位于 sys._MEIPASS，开发时位于源码目录
_IS_FROZEN = getattr(sys, "frozen", False)
_RESOURCE_ROOT = Path(sys._MEIPASS) if _IS_FROZEN else _APP_ROOT


def _load_env() -> None:
    """加载 .env（如果存在）。

    开发时取项目根目录；冻结后按「用户数据目录 → exe 同目录 → 当前
    工作目录」顺序查找并加载首个 .env，方便最终用户自行提供 API Key。
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    candidates = [_RESOURCE_ROOT / ".env"]
    if _IS_FROZEN:
        # 用户数据目录与 config._default_db_path 同一约定；config 在 import
        # 时即读取环境变量，须在 .env 加载完成后才能引入，故此处不复用它
        if sys.platform == "darwin":
            _data_dir = Path.home() / "Library" / "Application Support" / "Prism"
        elif sys.platform == "win32":
            _appdata = os.getenv("APPDATA")
            _data_dir = (Path(_appdata) if _appdata else Path.home() / "AppData" / "Roaming") / "Prism"
        else:
            _data_dir = Path.home() / ".local" / "share" / "Prism"
        candidates += [
            _data_dir / ".env",
            Path(sys.executable).resolve().parent / ".env",
            Path.cwd() / ".env",
        ]
    for env_path in candidates:
        if env_path.exists():
            load_dotenv(env_path)
            break


_load_env()

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QIcon

from ui.main_window import MainWindow
from db.database import Database

# 版本号从 __init__.py 读取：冻结时该文件由 prism.spec 打入 bundle，
# 且仓库根目录自身在 PyInstaller 下无法作为 prism 包 import
_m = re.search(
    r'__version__\s*=\s*["\']([^"\']+)["\']',
    (_RESOURCE_ROOT / "__init__.py").read_text(encoding="utf-8"),
)
__version__ = _m.group(1) if _m else "0.0.0"

def main():
    # 高 DPI 支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Prism")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Prism")

    # 应用图标（Dock / 任务栏）
    _icon_path = _RESOURCE_ROOT / "assets" / "icons" / "icon.png"
    if _icon_path.exists():
        app.setWindowIcon(QIcon(str(_icon_path)))

    # 加载项目自带字体
    _fonts_dir = _RESOURCE_ROOT / "assets" / "fonts"
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
