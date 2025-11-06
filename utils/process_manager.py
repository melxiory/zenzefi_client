# utils/process_manager.py
import psutil
import logging
import ctypes
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class ProcessManager:
    def __init__(self):
        self.is_admin = self._check_admin_rights()

    def _check_admin_rights(self) -> bool:
        """Проверяет, запущено ли приложение с правами администратора"""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    def get_process_info(self, process_name: str) -> List[Dict]:
        """Возвращает информацию о всех процессах с указанным именем"""
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'username', 'exe', 'cmdline']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == process_name.lower():
                    process_info = {
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'username': proc.info.get('username', 'N/A'),
                        'exe': proc.info.get('exe', 'N/A'),
                        'cmdline': proc.info.get('cmdline', []),
                        'is_our_process': self._is_our_process(proc),
                        'can_manage': self._can_manage_process(proc)
                    }
                    processes.append(process_info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return processes

    def _is_our_process(self, process) -> bool:
        """Проверяет, является ли процесс нашим (запущен из нашей папки)"""
        try:
            if hasattr(process, 'exe') and process.exe():
                exe_path = Path(process.exe())
                # Проверяем по имени процесса (Python или наш EXE)
                return 'python' in process.name().lower() or 'zenzefi' in process.name().lower()
            return False
        except (psutil.AccessDenied, AttributeError):
            return False

    def _can_manage_process(self, process) -> bool:
        """Проверяет, можем ли мы управлять процессом"""
        if self.is_admin:
            return True  # С правами админа можем управлять любыми процессами

        # Без прав админа можем управлять только нашими процессами
        return self._is_our_process(process)

    def terminate_process(self, pid: int, force: bool = False) -> bool:
        """Завершает процесс по PID"""
        try:
            process = psutil.Process(pid)

            if not self._can_manage_process(process):
                logger.warning(f"🚫 Нет прав для завершения процесса PID: {pid}")
                return False

            if force:
                process.kill()
            else:
                process.terminate()

            process.wait(timeout=3)
            logger.info(f"✅ Процесс PID: {pid} {'принудительно ' if force else ''}завершен")
            return True

        except psutil.NoSuchProcess:
            logger.info(f"⚠️ Процесс PID: {pid} уже завершен")
            return True
        except psutil.AccessDenied:
            logger.error(f"❌ Отказано в доступе к процессу PID: {pid}")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка завершения процесса PID: {pid}: {e}")
            return False

    def terminate_processes_by_name(self, process_name: str, force: bool = False) -> int:
        """Завершает все процессы с указанным именем"""
        processes = self.get_process_info(process_name)
        terminated_count = 0

        for proc_info in processes:
            if self.terminate_process(proc_info['pid'], force):
                terminated_count += 1

        return terminated_count

    def is_process_running(self, process_name: str) -> bool:
        """Проверяет, запущен ли процесс"""
        return len(self.get_process_info(process_name)) > 0

    def get_admin_status(self) -> Dict:
        """Возвращает информацию о правах доступа"""
        return {
            'is_admin': self.is_admin,
            'message': 'С правами администратора' if self.is_admin else 'Без прав администратора'
        }

    def kill_process_on_port(self, port: int) -> bool:
        """
        Завершает процесс, занимающий указанный порт

        Args:
            port: Номер порта

        Returns:
            bool: True если процесс был успешно завершен
        """
        from .port_utils import get_process_using_port

        process_info = get_process_using_port(port)
        if not process_info:
            logger.warning(f"⚠️ Процесс на порту {port} не найден")
            return False

        pid = process_info.get('pid')
        if not pid:
            logger.error(f"❌ Не удалось получить PID процесса на порту {port}")
            return False

        logger.info(
            f"🔄 Attempting to terminate process on port {port}:\n"
            f"   PID: {pid}\n"
            f"   Name: {process_info.get('name')}\n"
            f"   User: {process_info.get('username', 'N/A')}"
        )

        # Пытаемся завершить процесс (сначала мягко, потом принудительно)
        if self.terminate_process(pid, force=False):
            return True

        # Если мягкое завершение не сработало, пробуем принудительно
        logger.warning(f"⚠️ Soft termination failed, trying force kill for PID {pid}")
        return self.terminate_process(pid, force=True)


# Синглтон для глобального доступа
_process_manager = None


def get_process_manager() -> ProcessManager:
    """Возвращает глобальный экземпляр ProcessManager"""
    global _process_manager
    if _process_manager is None:
        _process_manager = ProcessManager()
    return _process_manager