#!/usr/bin/env python
"""
Оптимизированная сборка ZenzefiClient с дополнительными оптимизациями.

Этот скрипт автоматизирует процесс сборки приложения с максимальной оптимизацией:
- Очистка предыдущих сборок
- Удаление __pycache__ для чистой сборки
- Компиляция .pyc с оптимизацией уровня 2
- Запуск PyInstaller с оптимизированными параметрами
- Вывод статистики размера файлов
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path


def clean_build():
    """Очистка предыдущих сборок и кэшей"""
    print("🧹 Очистка предыдущих сборок...")

    dirs_to_remove = ['build', 'dist', '__pycache__']
    for dir_name in dirs_to_remove:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print(f"   Удалено: {dir_name}/")

    # Рекурсивно удаляем __pycache__ во всех подпапках
    for root, dirs, files in os.walk('.'):
        if '__pycache__' in dirs:
            pycache_path = os.path.join(root, '__pycache__')
            shutil.rmtree(pycache_path)
            print(f"   Удалено: {pycache_path}")

    print("✅ Очистка завершена\n")


def optimize_bytecode():
    """Компиляция Python файлов с оптимизацией уровня 2"""
    print("⚡ Компиляция .pyc файлов с оптимизацией уровня 2...")

    try:
        # -O -O = оптимизация уровня 2 (удаление docstrings и assert)
        subprocess.run([sys.executable, '-OO', '-m', 'compileall', '.'], check=True)
        print("✅ Байткод оптимизирован\n")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Ошибка компиляции байткода: {e}\n")


def build_exe():
    """Запуск PyInstaller с оптимизированными параметрами"""
    print("🔨 Сборка исполняемого файла...")

    try:
        # Запускаем PyInstaller с максимальной оптимизацией
        cmd = [
            'pyinstaller',
            '--clean',           # Очистка перед сборкой
            '--noconfirm',       # Не спрашивать подтверждение
            '--log-level=WARN',  # Только предупреждения и ошибки
            'ZenzefiClient.spec'
        ]

        subprocess.run(cmd, check=True)
        print("✅ Сборка завершена\n")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка сборки: {e}")
        return False


def get_size_mb(file_path):
    """Получить размер файла в МБ"""
    if os.path.exists(file_path):
        size_bytes = os.path.getsize(file_path)
        return size_bytes / (1024 * 1024)
    return 0


def print_statistics():
    """Вывод статистики размера файлов"""
    print("📊 Статистика сборки:")
    print("=" * 50)

    exe_path = Path('dist') / 'ZenzefiClient.exe'

    if exe_path.exists():
        exe_size = get_size_mb(exe_path)
        print(f"📦 ZenzefiClient.exe: {exe_size:.2f} МБ")

        # Проверяем наличие дополнительных файлов в dist/
        dist_path = Path('dist')
        total_size = 0
        file_count = 0

        for file in dist_path.rglob('*'):
            if file.is_file():
                total_size += file.stat().st_size
                file_count += 1

        total_size_mb = total_size / (1024 * 1024)
        print(f"📁 Всего файлов в dist/: {file_count}")
        print(f"💾 Общий размер: {total_size_mb:.2f} МБ")
        print("=" * 50)
        print(f"✅ Сборка готова: {exe_path}")
    else:
        print("❌ Исполняемый файл не найден!")

    print()


def main():
    """Основная функция сборки"""
    print("🚀 Начало оптимизированной сборки ZenzefiClient\n")

    # Проверка наличия spec файла
    if not os.path.exists('ZenzefiClient.spec'):
        print("❌ Файл ZenzefiClient.spec не найден!")
        return 1

    # Шаг 1: Очистка
    clean_build()

    # Шаг 2: Оптимизация байткода
    optimize_bytecode()

    # Шаг 3: Сборка
    if not build_exe():
        return 1

    # Шаг 4: Статистика
    print_statistics()

    print("🎉 Оптимизированная сборка завершена успешно!")
    return 0


if __name__ == '__main__':
    sys.exit(main())