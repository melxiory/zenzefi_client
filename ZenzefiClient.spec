# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('resources', 'resources')],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'cryptography',
        'psutil',
        'aiohttp',
        'asyncio'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Исключаем ненужные модули для уменьшения размера
    excludes=[
        'tkinter',           # GUI библиотека (не используется)
        'matplotlib',        # Графики (не используется)
        'numpy',             # Математика (не используется)
        'scipy',             # Научные вычисления (не используется)
        'pandas',            # Анализ данных (не используется)
        'PIL',               # Обработка изображений (не используется)
        'IPython',           # Интерактивный Python (не используется)
        'jupyter',           # Jupyter notebooks (не используется)
        'sphinx',            # Документация (не используется)
        'unittest',          # Тесты (не нужны в продакшене)
        'pytest',            # Тесты (не нужны в продакшене)
        'setuptools',        # Установка пакетов (не нужна в продакшене)
        'distutils',         # Установка пакетов (не нужна в продакшене)
        # 'email' - НУЖЕН для cryptography (X.509 certificates)
        # 'html' - может использоваться aiohttp
        # 'xml.etree' - может использоваться cryptography/ssl
        'pydoc',             # Документация (не нужна в продакшене)
    ],
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
    name='ZenzefiClient',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,  # Strip не работает на Windows (требует GNU binutils)
    upx=True,  # UPX сжатие (уменьшение размера на 30-50%)
    upx_exclude=[
        # Исключаем DLL которые могут не работать после сжатия
        'vcruntime140.dll',
        'python3.dll',
        'python313.dll',
        # Исключаем Qt платформенные плагины
        'qwindows.dll',
        'qoffscreen.dll',
    ],
    runtime_tmpdir=None,
    console=False,  # Без консоли (GUI приложение)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='resources/window_img.ico',
    version='version.txt',
    manifest='manifest.xml',
    # Дополнительные оптимизации
    uac_admin=False,  # Не требуем права администратора
    uac_uiaccess=False,
)