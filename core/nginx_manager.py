# nginx_manager.py
import subprocess
import time
import logging
import os
import psutil
from pathlib import Path
from utils.process_manager import get_process_manager
from utils.port_utils import check_port_availability, get_process_using_port
import sys

logger = logging.getLogger(__name__)


def ensure_nginx_directories(nginx_dir):
    """Создает необходимые папки для nginx"""
    required_folders = [
        "temp/client_body_temp",
        "temp/proxy_temp",
        "temp/fastcgi_temp",
        "temp/uwsgi_temp",
        "temp/scgi_temp",
    ]

    for folder in required_folders:
        folder_path = nginx_dir / folder
        folder_path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"📁 Создана папка: {folder_path}")


def get_nginx_path():
    """Возвращает путь к nginx с учетом portable режима"""
    if getattr(sys, 'frozen', False):
        # В portable режиме ищем nginx в _MEIPASS
        if hasattr(sys, '_MEIPASS'):
            nginx_dir = Path(sys._MEIPASS) / "nginx"
            if nginx_dir.exists() and (nginx_dir / "nginx.exe").exists():
                return nginx_dir

        # Если в _MEIPASS нет, ищем рядом с EXE
        nginx_dir = Path(sys.executable).parent / "nginx"
        if nginx_dir.exists() and (nginx_dir / "nginx.exe").exists():
            return nginx_dir

        logger.error("❌ nginx не найден")
        return None
    else:
        # Dev режим
        return Path("nginx").absolute()


class NginxManager:
    def __init__(self):
        self.nginx_dir = get_nginx_path()
        if not self.nginx_dir:
            return

        self.process = None
        self.is_running = False
        self.process_manager = get_process_manager()
        self.remote_url = ""
        self.local_port = 61000

        logger.info(f"✅ nginx путь: {self.nginx_dir}")

    def start(self, local_port=61000, remote_url="https://zenzefi.melxiory.ru"):
        """Запуск nginx прокси с фиксированным портом"""
        if self.is_running:
            logger.warning("Nginx уже запущен")
            return False

        try:
            # Проверяем что nginx существует
            nginx_exe = self.nginx_dir / "nginx.exe"
            if not nginx_exe.exists():
                logger.error(f"nginx.exe не найден в {self.nginx_dir}")
                return False

            # Улучшенная проверка порта
            port_available, port_message = check_port_availability(local_port)

            # Если порт занят, проверяем не нашим ли приложением
            if not port_available and self.is_port_in_use_by_us(local_port):
                logger.info("⚠️ Порт занят нашим приложением, пытаемся перезапустить...")
                # Останавливаем наш старый процесс
                self.stop()
                time.sleep(2)
                # Проверяем порт снова
                port_available, port_message = check_port_availability(local_port)

            if not port_available:
                # Остальная логика обработки занятого порта...
                process_info = get_process_using_port(local_port)
                if process_info:
                    logger.warning(f"⚠️ {port_message}")

                    # Пытаемся завершить процесс, занимающий порт
                    if self.process_manager.terminate_process(process_info['pid']):
                        logger.info(f"✅ Процесс завершен, проверяем порт again...")
                        time.sleep(2)
                        port_available, port_message = check_port_availability(local_port)

                # Если порт все еще занят
                if not port_available:
                    error_msg = f"Не удалось освободить порт {local_port}. {port_message}"
                    logger.error(f"❌ {error_msg}")

                    # Формируем сообщение для пользователя
                    if self.process_manager.is_admin:
                        user_msg = (
                            f"❌ Не удалось запустить прокси на порту {local_port}\n\n"
                            f"Причина: {port_message}\n\n"
                            f"📋 Решения:\n"
                            f"• Закройте программу, использующую порт {local_port}\n"
                            f"• Перезагрузите компьютер\n"
                            f"• Проверьте системные службы"
                        )
                    else:
                        user_msg = (
                            f"❌ Не удалось запустить прокси на порту {local_port}\n\n"
                            f"Причина: {port_message}\n\n"
                            f"📋 Решения:\n"
                            f"• Закройте программу, использующую порт {local_port}\n"
                            f"• Запустите приложение с правами администратора\n"
                            f"• Проверьте другие экземпляры программы"
                        )

                    logger.error(user_msg)
                    return False

            # Остальная логика запуска...
            # Генерируем кастомный конфиг
            self._generate_custom_config(local_port, remote_url)
            self.remote_url = remote_url
            self.local_port = local_port

            # Запускаем nginx
            logger.info("🚀 Запускаем nginx...")
            self.process = subprocess.Popen(
                [str(nginx_exe)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.nginx_dir),
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            # Даем время на запуск
            time.sleep(3)

            # Проверяем что запустился
            if self._is_nginx_running():
                self.is_running = True
                logger.info(f"✅ Nginx запущен на https://127.0.0.1:{local_port}")
                logger.info(f"🌐 Проксируется на: {remote_url}")
                return True
            else:
                logger.error("❌ Nginx не запустился")
                # Показываем ошибки если есть
                if self.process.stderr:
                    try:
                        error_output = self.process.stderr.read().decode('utf-8', errors='ignore')
                        if error_output:
                            logger.error(f"Ошибки nginx: {error_output}")
                    except:
                        pass
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка запуска nginx: {e}")
            return False

    def stop(self):
        """Остановка nginx - универсальный метод"""
        # Используем Windows-специфичный метод на Windows
        if os.name == 'nt':
            return self.stop_windows()

        # Для других ОС используем старую логику
        try:
            # Graceful shutdown нашего процесса
            if self.process:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=2)
                except:
                    pass

            # Останавливаем все nginx процессы
            logger.info("🛑 Останавливаем все nginx процессы...")
            terminated_count = self.process_manager.terminate_all_nginx()
            logger.info(f"✅ Завершено процессов nginx: {terminated_count}")

            self.is_running = False
            self.process = None
            logger.info("✅ Nginx остановлен")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка остановки nginx: {e}")
            return False

    def stop_windows(self):
        """Остановка nginx на Windows - улучшенная версия"""
        try:
            # 1. Graceful shutdown через nginx команду
            try:
                nginx_exe = self.nginx_dir / "nginx.exe"
                if nginx_exe.exists():
                    subprocess.run([
                        str(nginx_exe),
                        "-s", "quit"
                    ], timeout=5, capture_output=True, cwd=str(self.nginx_dir))
                    logger.info("✅ Отправлена команда graceful shutdown")
                    time.sleep(2)  # Даем время на завершение
            except subprocess.TimeoutExpired:
                logger.warning("⚠️ Таймаут graceful shutdown")
            except Exception as e:
                logger.debug(f"Graceful shutdown не удался: {e}")

            # 2. Ищем и завершаем ВСЕ процессы nginx от нашего пользователя
            our_nginx_pids = []
            current_user = os.getlogin()

            for proc in psutil.process_iter(['pid', 'name', 'username']):
                try:
                    proc_info = proc.info
                    if (proc_info['name'] and
                            proc_info['name'].lower() == 'nginx.exe' and
                            proc_info['username'] == current_user):  # Только наши процессы
                        our_nginx_pids.append(proc_info['pid'])
                        logger.debug(
                            f"Найден процесс nginx: PID {proc_info['pid']}, пользователь: {proc_info['username']}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # 3. Завершаем наши процессы
            terminated_count = 0
            for pid in our_nginx_pids:
                try:
                    proc = psutil.Process(pid)
                    logger.debug(f"Завершаем процесс nginx PID {pid}")

                    # Сначала пытаемся завершить gracefully
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                        terminated_count += 1
                        continue
                    except psutil.TimeoutExpired:
                        pass

                    # Если не получилось - принудительно
                    try:
                        proc.kill()
                        proc.wait(timeout=1)
                        terminated_count += 1
                    except:
                        pass

                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    logger.debug(f"Процесс {pid} уже завершен или нет доступа: {e}")

            self.is_running = False
            self.process = None

            logger.info(f"✅ Завершено процессов nginx: {terminated_count}")
            if terminated_count > 0:
                time.sleep(1)  # Даем системе время освободить ресурсы

            return True

        except Exception as e:
            logger.error(f"❌ Ошибка остановки nginx на Windows: {e}")
            # Fallback к стандартному методу
            return self._stop_fallback()

    def _stop_fallback(self):
        """Fallback метод остановки"""
        try:
            if self.process:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=2)
                except:
                    try:
                        self.process.kill()
                        self.process.wait(timeout=1)
                    except:
                        pass

            self.is_running = False
            self.process = None
            logger.info("✅ Nginx остановлен (fallback метод)")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка в fallback методе: {e}")
            return False

    def _generate_custom_config(self, local_port, remote_url):
        """Создает nginx config с правильными путями"""
        # Убеждаемся что папки созданы
        ensure_nginx_directories(self.nginx_dir)

        from core.config_manager import get_app_data_dir
        app_data_dir = get_app_data_dir()
        certs_dir = app_data_dir / "certificates"
        certs_dir.mkdir(exist_ok=True)

        cert_path = certs_dir / "fake.crt"
        key_path = certs_dir / "fake.key"

        # Конфиг создаем в папке nginx (в _MEIPASS или рядом с EXE)
        nginx_conf_dir = self.nginx_dir / "conf"
        nginx_conf_dir.mkdir(exist_ok=True)

        full_config = f'''
    worker_processes  1;

    events {{
        worker_connections  1024;
    }}

    http {{
        include       mime.types;
        default_type  application/octet-stream;

        sendfile        on;
        keepalive_timeout  65;

        server {{
            listen       {local_port} ssl;
            server_name  127.0.0.1;

            ssl_certificate      {cert_path};
            ssl_certificate_key  {key_path};

            ssl_protocols       TLSv1.2 TLSv1.3;
            ssl_ciphers         HIGH:!aNULL:!MD5;

            proxy_connect_timeout 30s;
            proxy_send_timeout    30s;
            proxy_read_timeout    30s;

            proxy_buffering on;
            proxy_buffer_size 4k;
            proxy_buffers 8 4k;

            location / {{
                proxy_pass {remote_url};
                proxy_set_header Host {remote_url.split('//')[1]};
                proxy_set_header X-Real-IP $remote_addr;
                proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                proxy_set_header X-Forwarded-Proto $scheme;
                proxy_ssl_verify off;
                proxy_ssl_server_name on;
            }}
        }}
    }}
    '''
        main_conf_path = nginx_conf_dir / "nginx.conf"
        main_conf_path.write_text(full_config, encoding='utf-8')
        logger.info(f"📁 Конфиг создан: {main_conf_path}")

    def _is_nginx_running(self):
        """Проверяет, запущен ли nginx"""
        try:
            result = subprocess.run(
                ["tasklist", "/fi", "imagename eq nginx.exe"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return "nginx.exe" in result.stdout
        except:
            return False

    def get_status(self):
        """Возвращает статус"""
        port_available, port_message = check_port_availability(self.local_port)
        port_used_by_us = self.is_port_in_use_by_us(self.local_port) if not port_available else False

        status = {
            'running': self.is_running,
            'port_available': port_available,
            'port_used_by_us': port_used_by_us,  # ← Новая информация
            'port': self.local_port,
            'url': self.remote_url,
            'is_admin': self.process_manager.is_admin
        }

        # Добавляем сообщение только если оно есть
        if port_message:
            status['port_message'] = port_message
        if port_used_by_us:
            status['port_message'] = "Порт занят нашим приложением (возможно старый процесс)"

        return status

    def is_port_in_use_by_us(self, port: int) -> bool:
        """Проверяет, занят ли порт нашим приложением"""
        from utils.port_utils import get_process_using_port
        import psutil
        from pathlib import Path

        process_info = get_process_using_port(port)
        if not process_info:
            return False

        # Проверяем, что это наш nginx процесс
        if not self.nginx_dir:
            return False

        try:
            process = psutil.Process(process_info['pid'])
            exe_path = Path(process.exe())

            # Проверяем что процесс nginx и находится в нашей папке
            is_nginx = process_info['name'] and 'nginx' in process_info['name'].lower()
            is_our_path = self.nginx_dir in exe_path.parents

            logger.debug(f"Проверка процесса: {process_info['name']}, PID: {process_info['pid']}")
            logger.debug(f"Путь: {exe_path}, наш путь: {is_our_path}")

            return is_nginx and is_our_path

        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError) as e:
            logger.debug(f"Не удалось проверить процесс на порту {port}: {e}")
            return False