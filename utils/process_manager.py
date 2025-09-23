# utils/process_manager.py
import time
import psutil
import subprocess
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
                # Проверяем, находится ли процесс в нашей папке nginx
                nginx_dir = Path("nginx").absolute()
                return nginx_dir in exe_path.parents
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

    def terminate_all_nginx(self) -> int:
        """Завершает все процессы nginx с многоуровневой стратегией"""
        logger.info(f"🔧 Запуск остановки nginx процессов (админ: {self.is_admin})")

        # Шаг 1: Graceful shutdown через nginx команду
        graceful_stopped = self._graceful_nginx_shutdown()
        if graceful_stopped:
            return graceful_stopped

        # Шаг 2: Обычное завершение процессов
        processes = self.get_process_info("nginx.exe")
        terminated_count = 0

        for proc_info in processes:
            if proc_info['can_manage']:
                if self.terminate_process(proc_info['pid'], force=False):
                    terminated_count += 1

        # Шаг 3: Если процессы остались, принудительное завершение
        if terminated_count < len([p for p in processes if p['can_manage']]):
            time.sleep(2)
            remaining_processes = self.get_process_info("nginx.exe")
            for proc_info in remaining_processes:
                if proc_info['can_manage']:
                    if self.terminate_process(proc_info['pid'], force=True):
                        terminated_count += 1

        # Шаг 4: Используем taskkill для надежности
        self._use_taskkill()

        return terminated_count

    def _graceful_nginx_shutdown(self) -> int:
        """Пытается graceful shutdown через nginx -s quit"""
        try:
            nginx_dir = Path("nginx").absolute()
            nginx_exe = nginx_dir / "nginx.exe"

            if nginx_exe.exists():
                result = subprocess.run(
                    [str(nginx_exe), "-s", "quit"],
                    cwd=str(nginx_dir),
                    capture_output=True,
                    timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                if result.returncode == 0:
                    logger.info("✅ Graceful shutdown nginx выполнен")
                    return 1
        except Exception as e:
            logger.debug(f"Graceful shutdown не удался: {e}")

        return 0

    def _use_taskkill(self):
        """Использует taskkill для завершения процессов"""
        try:
            if self.is_admin:
                # С правами админа - принудительно завершаем все
                subprocess.run(
                    ["taskkill", "/f", "/im", "nginx.exe"],
                    capture_output=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                # Без прав админа - пытаемся завершить нормально
                subprocess.run(
                    ["taskkill", "/im", "nginx.exe"],
                    capture_output=True,
                    timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
        except Exception as e:
            logger.debug(f"Ошибка taskkill: {e}")

    def is_process_running(self, process_name: str) -> bool:
        """Проверяет, запущен ли процесс"""
        return len(self.get_process_info(process_name)) > 0

    def get_admin_status(self) -> Dict:
        """Возвращает информацию о правах доступа"""
        return {
            'is_admin': self.is_admin,
            'message': 'С правами администратора' if self.is_admin else 'Без прав администратора'
        }


# Синглтон для глобального доступа
_process_manager = None


def get_process_manager() -> ProcessManager:
    """Возвращает глобальный экземпляр ProcessManager"""
    global _process_manager
    if _process_manager is None:
        _process_manager = ProcessManager()
    return _process_manager