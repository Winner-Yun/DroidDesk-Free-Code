# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.hooks import copy_metadata

datas = [('E:/WorkSmart/DroidDesk/src/droiddesk/resources', 'resources'), ('E:/WorkSmart/DroidDesk/src/droiddesk/resources', 'droiddesk/resources'), ('E:/WorkSmart/DroidDesk/src/droiddesk/reports/templates', 'droiddesk/reports/templates')]
binaries = []
hiddenimports = []
datas += collect_data_files('androguard')
datas += copy_metadata('androguard')
hiddenimports += collect_submodules('androguard.core')
hiddenimports += collect_submodules('androguard.decompiler')
tmp_ret = collect_all('pyaxmlparser')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('PySide6')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('jinja2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['E:/WorkSmart/DroidDesk/src/droiddesk/__main__.py'],
    pathex=['E:/WorkSmart/DroidDesk/src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['androguard.pentest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='droiddesk',
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
    icon=['E:/WorkSmart/DroidDesk/src/droiddesk/resources/icons/droiddesk.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='droiddesk',
)
