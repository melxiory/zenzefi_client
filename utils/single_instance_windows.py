# utils/single_instance_windows.py
import logging
import sys
import os
from ctypes import wintypes, windll, byref

logger = logging.getLogger(__name__)


class SingleInstance:
    """
    Класс для обеспечения единственного экземпляра приложения на Windows
    Использует именованные мьютексы
    """

    def __init__(self, mutex_name="ZenzefiClient_SingleInstance_Mutex"):
        self.mutex_name = mutex_name
        self.mutex_handle = None
        self.locked = False

    def lock(self):
        """Захватывает мьютекс"""
        try:
            # Создаем именованный мьютекс
            self.mutex_handle = windll.kernel32.CreateMutexW(
                None,  # Атрибуты безопасности
                wintypes.BOOL(False),  # Не владеем изначально
                self.mutex_name  # Имя мьютекса
            )

            if not self.mutex_handle:
                logger.error("❌ Не удалось создать мьютекс")
                return False

            # Проверяем, не существует ли уже мьютекс
            last_error = windll.kernel32.GetLastError()

            if last_error == 183:  # ERROR_ALREADY_EXISTS
                logger.warning(f"⚠️ Приложение уже запущено (мьютекс {self.mutex_name} существует)")
                windll.kernel32.CloseHandle(self.mutex_handle)
                self.mutex_handle = None
                return False
            else:
                self.locked = True
                logger.info(f"✅ Мьютекс создан: {self.mutex_name}")
                return True

        except Exception as e:
            logger.error(f"❌ Ошибка создания мьютекса: {e}")
            return False

    def unlock(self):
        """Освобождает мьютекс"""
        if self.mutex_handle:
            try:
                windll.kernel32.CloseHandle(self.mutex_handle)
                logger.debug(f"🔓 Мьютекс освобожден: {self.mutex_name}")
            except Exception as e:
                logger.debug(f"Ошибка при освобождении мьютекса: {e}")
            finally:
                self.mutex_handle = None
                self.locked = False


def get_single_instance():
    """Возвращает механизм блокировки для Windows"""
    return SingleInstance()