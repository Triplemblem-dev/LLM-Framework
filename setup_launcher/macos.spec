# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("generated/integrity.json", "setup_launcher/generated")],
    hiddenimports=[],
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
    name="LLM-Framework-Setup",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="universal2",
    codesign_identity=None,
    entitlements_file=None,
)
collection = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="LLM-Framework-Setup",
)
app = BUNDLE(
    collection,
    name="LLM-Framework-Setup.app",
    icon=None,
    bundle_identifier="org.llmframework.setup",
    info_plist={
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "1",
        "NSHighResolutionCapable": True,
    },
)
