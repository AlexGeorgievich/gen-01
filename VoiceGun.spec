# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, copy_metadata


datas = [
    ("assets/gpt01.svg", "assets"),
    ("docs/USER_GUIDE_EN.md", "docs"),
    ("docs/USER_GUIDE_RU.md", "docs"),
]
binaries = []
hiddenimports = [
    "gruut_lang_en",
    "gruut_lang_fr",
    "gruut_lang_es",
    "gruut_lang_de",
    "gruut_lang_it",
]

for package in (
    "gruut",
    "gruut_lang_en",
    "gruut_lang_fr",
    "gruut_lang_es",
    "gruut_lang_de",
    "gruut_lang_it",
    "pykakasi",
):
    for source, destination in collect_data_files(package):
        # VoiceGun uses gruut's native lexicon/G2P model. The duplicate eSpeak
        # databases are not selected by the application and add about 70 MB.
        if "espeak" not in Path(source).parts:
            datas.append((source, destination))

for distribution in ("deep-translator", "edge-tts", "gruut", "pykakasi"):
    datas += copy_metadata(distribution)

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VoiceGun",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/gpt01.ico",
    version="windows_version_info.txt",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VoiceGun",
)
