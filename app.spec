# -*- mode: python ; coding: utf-8 -*-
# Generated via: pyinstaller --onefile --windowed --noupx --add-data=data:data main.py
# Final spec: pathex=['src'], datas=[('data','data')], hiddenimports=['openlapexe.*'], console=False, upx=False, onefile
# Entry: main.py (src版フルGUI App2+VehicleEditor47+TrackView2+DragView+SimulateView2 4タブ統合)
# Fallback: app.py shim retained for backward compatibility
# Verification: python -m py_compile app.spec && (pyinstaller app.spec || spec検証)

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['src'],
    binaries=[],
    datas=[('data', 'data')],
    hiddenimports=['openlapexe.*','PIL','PIL.Image','PIL.ImageTk'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='app',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    windowed=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    onefile=True,
)
