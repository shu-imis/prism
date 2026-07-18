# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 构建脚本。

macOS 生成 dist/Prism.app，Windows 生成 dist/Prism/（onedir，含 Prism.exe）。
用法：pyinstaller prism.spec --noconfirm
"""
import re
import sys
from pathlib import Path

ROOT = Path(SPECPATH)
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

_version_m = re.search(
    r'__version__\s*=\s*["\']([^"\']+)["\']',
    (ROOT / "__init__.py").read_text(encoding="utf-8"),
)
VERSION = _version_m.group(1) if _version_m else "0.0.0"

a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    datas=[
        ("assets", "assets"),
        # 冻结后 main.py 从此文件读取版本号（prism 包在冻结时不可解析）
        ("__init__.py", "."),
    ],
    hiddenimports=[],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="prism",
    console=False,
    icon=["assets/icons/icon.ico"] if IS_WIN else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="Prism",
)

if IS_MAC:
    app = BUNDLE(
        coll,
        name="Prism.app",
        icon="assets/icons/icon.icns",
        bundle_identifier="com.prism.app",
        version=VERSION,
        info_plist={
            "CFBundleName": "Prism",
            "CFBundleDisplayName": "Prism",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
        },
    )
