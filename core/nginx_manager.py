# nginx_manager.py
import subprocess
import time
import logging
from pathlib import Path
from utils.process_manager import get_process_manager
from utils.port_utils import check_port_availability, get_process_using_port

logger = logging.getLogger(__name__)


class NginxManager:
    def __init__(self):
        self.process = None
        self.is_running = False
        self.nginx_dir = Path("nginx").absolute()
        self.process_manager = get_process_manager()
        self.remote_url = ""
        self.local_port = 61000

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

            # Останавливаем все наши nginx процессы
            logger.info("🛑 Останавливаем все nginx процессы...")
            terminated_count = self.process_manager.terminate_all_nginx()
            logger.info(f"✅ Завершено процессов nginx: {terminated_count}")
            time.sleep(2)

            # Проверяем доступность порта
            port_available, port_message = check_port_availability(local_port)

            if not port_available:
                # Порт занят - пытаемся завершить процесс
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

                    # Здесь можно показать сообщение пользователю через UI
                    logger.error(user_msg)
                    return False

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
        """Остановка nginx"""
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

    def _generate_custom_config(self, local_port, remote_url):
        """Создает nginx config"""
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

        ssl_certificate      ../fake.crt;
        ssl_certificate_key  ../fake.key;

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
            proxy_set_header Host zenzefi.melxiory.ru;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_ssl_verify off;
            proxy_ssl_server_name on;
        }}
    }}
}}
'''
        conf_dir = self.nginx_dir / "conf"
        main_conf_path = conf_dir / "nginx.conf"
        main_conf_path.write_text(full_config, encoding='utf-8')
        logger.info(f"📁 Конфиг nginx обновлен")

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

        status = {
            'running': self.is_running,
            'port_available': port_available,
            'port': self.local_port,
            'url': self.remote_url,
            'is_admin': self.process_manager.is_admin
        }

        # Добавляем сообщение только если оно есть
        if port_message:
            status['port_message'] = port_message

        return status

    def restart(self):
        """Перезапуск nginx"""
        if self.stop():
            time.sleep(3)
            return self.start()
        return False