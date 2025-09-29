# utils/single_instance_file.py
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class SingleInstance:
    """
    Класс для обеспечения единственного экземпляра приложения
    Использует файловую блокировку
    """

    def __init__(self, lockfile_name="zenzefi_client.lock"):
        from core.config_manager import get_app_data_dir
        app_data_dir = get_app_data_dir()
        self.lockfile = app_data_dir / lockfile_name
        self.lockfile_handle = None
        self.locked = False

    def lock(self):
        """Захватывает файловую блокировку"""
        try:
            # Создаем директорию если нужно
            self.lockfile.parent.mkdir(parents=True, exist_ok=True)

            # Пытаемся создать файл в эксклюзивном режиме
            try:
                self.lockfile_handle = os.open(
                    self.lockfile,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY
                )

                # Записываем PID текущего процесса
                pid = str(os.getpid())
                os.write(self.lockfile_handle, pid.encode())
                os.close(self.lockfile_handle)
                self.lockfile_handle = None

                self.locked = True
                logger.info(f"✅ Файловая блокировка создана: {self.lockfile}")
                return True

            except FileExistsError:
                # Файл уже существует - проверяем, жив ли процесс
                if self._is_process_running():
                    logger.warning(f"⚠️ Приложение уже запущено (файл блокировки {self.lockfile} существует)")
                    return False
                else:
                    # Процесс мертв - удаляем старый файл и пробуем снова
                    try:
                        self.lockfile.unlink()
                        logger.info("🗑️ Удален старый файл блокировки")
                        return self.lock()  # Рекурсивно пробуем снова
                    except:
                        logger.error("❌ Не удалось удалить старый файл блокировки")
                        return False

        except Exception as e:
            logger.error(f"❌ Ошибка файловой блокировки: {e}")
            return False

    def _is_process_running(self):
        """Проверяет, запущен ли процесс, создавший файл блокировки"""
        try:
            if self.lockfile.exists():
                with open(self.lockfile, 'r') as f:
                    pid_str = f.read().strip()
                    if pid_str.isdigit():
                        pid = int(pid_str)
                        import psutil
                        return psutil.pid_exists(pid)
        except:
            pass
        return False

    def unlock(self):
        """Освобождает файловую блокировку"""
        if self.locked and self.lockfile.exists():
            try:
                self.lockfile.unlink()
                logger.debug(f"🔓 Файловая блокировка удалена: {self.lockfile}")
            except Exception as e:
                logger.debug(f"Ошибка при удалении файла блокировки: {e}")
            finally:
                self.locked = False


def get_single_instance():
    """Возвращает механизм файловой блокировки"""
    return SingleInstance()