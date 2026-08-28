# -*- mode: python ; coding: utf-8 -*-

import os
import re
from glob import glob


def _app_version():
    # 版本号唯一来源：VersionCheck.APP_VERSION，避免多处手工维护不一致
    spec_dir = os.path.abspath(SPECPATH)
    with open(os.path.join(spec_dir, "VersionCheck.py"), "r", encoding="utf-8") as fh:
        match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', fh.read())
    return match.group(1) if match else "0.0.0"


def _build_version_file():
    version = _app_version()
    parts = [int(p) for p in version.split(".")[:3]]
    parts += [0] * (3 - len(parts))
    quad = tuple(parts + [0])
    out_dir = os.path.join(os.path.abspath(SPECPATH), "build")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "version_info.txt")
    content = (
        "# UTF-8\n"
        "# 由 StockWidget.spec 依据 VersionCheck.APP_VERSION 自动生成，勿手工编辑\n"
        "VSVersionInfo(\n"
        "  ffi=FixedFileInfo(\n"
        f"    filevers={quad},\n"
        f"    prodvers={quad},\n"
        "    mask=0x3f,\n"
        "    flags=0x0,\n"
        "    OS=0x40004,\n"
        "    fileType=0x1,\n"
        "    subtype=0x0,\n"
        "    date=(0, 0)\n"
        "  ),\n"
        "  kids=[\n"
        "    StringFileInfo(\n"
        "      [\n"
        "      StringTable(\n"
        "        u'080404b0',\n"
        "        [StringStruct(u'CompanyName', u'StockWidget'),\n"
        "        StringStruct(u'FileDescription', u'StockWidget 股票看盘浮窗'),\n"
        f"        StringStruct(u'FileVersion', u'{version}'),\n"
        "        StringStruct(u'InternalName', u'StockWidget'),\n"
        "        StringStruct(u'LegalCopyright', u''),\n"
        "        StringStruct(u'OriginalFilename', u'StockWidget.exe'),\n"
        "        StringStruct(u'ProductName', u'StockWidget'),\n"
        f"        StringStruct(u'ProductVersion', u'{version}')])\n"
        "      ]),\n"
        "    VarFileInfo([VarStruct(u'Translation', [2052, 1200])])\n"
        "  ]\n"
        ")\n"
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


_VERSION_FILE = _build_version_file()


def _root_dlls(package_name):
    import importlib.util

    spec = importlib.util.find_spec(package_name)
    if spec is None or not spec.origin:
        return []
    package_dir = os.path.dirname(spec.origin)
    return [(path, package_name) for path in glob(os.path.join(package_dir, "*.dll"))]


_EXTRA_BINARIES = _root_dlls("PySide6") + _root_dlls("shiboken6")
_EXCLUDED_BINARY_NAMES = {"icuuc.dll", "icudt78.dll"}


a = Analysis(
    ['StockWidget.py'],
    pathex=[],
    binaries=_EXTRA_BINARIES,
    datas=[('StockWidget.ico', '.'), ('resources', 'resources')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
a.binaries = [
    entry for entry in a.binaries
    if entry[0].lower() not in _EXCLUDED_BINARY_NAMES
]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='StockWidget',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[
        'PySide6*.dll',
        'Qt6*.dll',
        'shiboken6*.dll',
        '*.pyd',
    ],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['StockWidget.ico'],
    version=_VERSION_FILE,
)
