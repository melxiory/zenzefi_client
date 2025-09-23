# utils/port_utils.py
import socket
import psutil
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)


def is_port_in_use(port: int) -> bool:
    """Проверяет, занят ли порт"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.settimeout(1)
            s.bind(('127.0.0.1', port))
            return False
        except socket.error:
            return True
        finally:
            s.close()


def get_process_using_port(port: int) -> Optional[Dict]:
    """Возвращает информацию о процессе, занимающем порт"""
    try:
        for conn in psutil.net_connections(kind='inet'):
            try:
                if (hasattr(conn, 'laddr') and conn.laddr and
                        hasattr(conn.laddr, 'port') and conn.laddr.port == port and
                        conn.status == 'LISTEN'):

                    process = psutil.Process(conn.pid)
                    if process.is_running():
                        return {
                            'name': process.name(),
                            'pid': process.pid,
                            'username': process.username() if hasattr(process, 'username') else 'N/A'
                        }
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception as e:
        logger.debug(f"Ошибка при поиске процесса на порту {port}: {e}")
    return None


def check_port_availability(port: int) -> tuple[bool, str]:
    """Проверяет доступность порта и возвращает информацию о проблеме"""
    if not is_port_in_use(port):
        return True, "Порт свободен"

    process_info = get_process_using_port(port)
    if process_info:
        message = (
            f"Порт {port} занят процессом {process_info['name']} "
            f"(PID: {process_info['pid']})"
        )
        # Добавляем username если доступен
        if process_info['username'] != 'N/A':
            message += f", пользователь: {process_info['username']}"
        return False, message
    else:
        return False, f"Порт {port} занят"