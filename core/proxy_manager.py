import threading
import time
import os
import signal
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class ProxyManager:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.process = None
        self.is_running = False
        self.proxy_thread = None

    def start_proxy(self):
        """Запуск прокси-сервера"""
        if self.is_running:
            logger.warning("Прокси уже запущен")
            return False

        try:
            # Получаем конфигурацию
            local_port = self.config_manager.get('local_port', 61000)
            remote_url = self.config_manager.get('remote_url', 'https://zenzefi.melxiory.ru')
            cert_path = self.config_manager.get('certificate_path', 'melxiory.pem')

            # Проверяем необходимые файлы
            if not self._check_required_files(cert_path):
                return False

            # Запускаем прокси в отдельном процессе
            self.proxy_thread = threading.Thread(
                target=self._run_proxy_process,
                args=(local_port, remote_url, cert_path),
                daemon=True
            )
            self.proxy_thread.start()

            # Ждем немного для инициализации
            time.sleep(2)

            # Проверяем что процесс запустился
            if self._is_port_open(local_port):
                self.is_running = True
                logger.info(f"Прокси запущен на порту {local_port}")
                return True
            else:
                logger.error("Прокси не запустился")
                return False

        except Exception as e:
            logger.error(f"Ошибка запуска прокси: {e}")
            return False

    def stop_proxy(self):
        """Остановка прокси-сервера"""
        if not self.is_running:
            return True

        try:
            if self.process:
                # Отправляем сигнал завершения
                if os.name == 'nt':  # Windows
                    self.process.terminate()
                else:  # Unix/Linux
                    os.kill(self.process.pid, signal.SIGTERM)

                # Ждем завершения
                self.process.wait(timeout=10)

            self.is_running = False
            self.process = None
            logger.info("Прокси остановлен")
            return True

        except Exception as e:
            logger.error(f"Ошибка остановки прокси: {e}")
            # Пытаемся принудительно завершить
            try:
                if self.process:
                    self.process.kill()
            except:
                pass
            finally:
                self.is_running = False
                self.process = None
            return False

    def get_status(self):
        """Получение статуса прокси"""
        return {
            'running': self.is_running,
            'port': self.config_manager.get('local_port', 61000),
            'url': self.config_manager.get('remote_url', 'https://zenzefi.melxiory.ru'),
            'certificate': self.config_manager.get('certificate_path', 'melxiory.pem')
        }

    def _run_proxy_process(self, local_port, remote_url, cert_path):
        """Запускает процесс прокси в отдельном потоке"""
        try:
            # Импортируем здесь чтобы избежать circular imports
            from ..proxy.proxy_server import run_proxy_server

            # Запускаем прокси-сервер
            run_proxy_server(local_port, remote_url, cert_path)

        except Exception as e:
            logger.error(f"Ошибка в процессе прокси: {e}")
            self.is_running = False

    def _check_required_files(self, cert_path):
        """Проверяет наличие необходимых файлов"""
        required_files = [
            cert_path,
            'fake.crt',
            'fake.key'
        ]

        missing_files = []
        for file_path in required_files:
            if not Path(file_path).exists():
                missing_files.append(file_path)

        if missing_files:
            logger.error(f"Отсутствуют необходимые файлы: {missing_files}")
            return False

        return True

    def _is_port_open(self, port):
        """Проверяет, открыт ли порт"""
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(('127.0.0.1', port))
                return result == 0
        except:
            return False

    def restart_proxy(self):
        """Перезапуск прокси"""
        self.stop_proxy()
        time.sleep(1)
        return self.start_proxy()

    def update_config(self, new_config):
        """Обновление конфигурации с перезапуском прокси"""
        was_running = self.is_running

        if was_running:
            self.stop_proxy()

        # Обновляем конфигурацию
        for key, value in new_config.items():
            self.config_manager.set(key, value)

        if was_running:
            return self.start_proxy()

        return True