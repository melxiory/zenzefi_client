# utils/single_instance.py
import logging
import os
import sys

logger = logging.getLogger(__name__)


def get_single_instance():
    """Возвращает подходящий механизм блокировки для текущей ОС"""
    if os.name == 'nt':  # Windows
        try:
            from .single_instance_windows import get_single_instance as windows_getter
            return windows_getter()
        except Exception as e:
            logger.warning(f"Windows мьютекс не доступен, используем файловую блокировку: {e}")

    # Для всех ОС используем файловую блокировку
    from .single_instance_file import get_single_instance as file_getter
    return file_getter()


# Простая функция для быстрой проверки
def is_already_running():
    """Быстрая проверка, запущено ли уже приложение"""
    try:
        instance = get_single_instance()
        # Пытаемся захватить блокировку и сразу освобождаем
        if instance.lock():
            instance.unlock()
            return False  # Не запущено
        else:
            return True  # Уже запущено
    except:
        return False