import subprocess
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class NginxManager:
    def __init__(self):
        self.process = None
        self.is_running = False
        self.nginx_dir = Path("nginx").absolute()

    def start(self, local_port=61000, remote_url="https://zenzefi.melxiory.ru"):
        """Запуск nginx прокси"""
        if self.is_running:
            logger.warning("Nginx уже запущен")
            return False

        try:
            # Проверяем что nginx существует
            nginx_exe = self.nginx_dir / "nginx.exe"
            if not nginx_exe.exists():
                logger.error(f"nginx.exe не найден в {self.nginx_dir}")
                return False

            # Убедимся что старый nginx полностью остановлен
            self._force_stop_nginx()

            # Генерируем кастомный конфиг
            self._generate_custom_config(local_port, remote_url)

            # Запускаем nginx
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
            # Graceful shutdown
            if self.process:
                try:
                    nginx_exe = self.nginx_dir / "nginx.exe"
                    subprocess.run(
                        [str(nginx_exe), "-s", "quit"],
                        cwd=str(self.nginx_dir),
                        capture_output=True,
                        timeout=5,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    self.process.terminate()
                    self.process.wait(timeout=5)
                except:
                    pass

            # Принудительная остановка
            self._force_stop_nginx()

            self.is_running = False
            self.process = None
            logger.info("✅ Nginx остановлен")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка остановки nginx: {e}")
            return False

    def _force_stop_nginx(self):
        """Принудительная остановка всех процессов nginx"""
        try:
            # Используем taskkill для Windows
            subprocess.run(
                ["taskkill", "/f", "/im", "nginx.exe"],
                capture_output=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            # Ждем немного
            time.sleep(2)

        except Exception as e:
            logger.warning(f"Предупреждение при остановке nginx: {e}")

    def _generate_custom_config(self, local_port, remote_url):
        """Создает полный nginx.conf без клиентского сертификата"""
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

    # Zenzefi Proxy Configuration
    server {{
        listen       {local_port} ssl;
        server_name  127.0.0.1;

        # Self-signed сертификаты для localhost
        ssl_certificate      ../fake.crt;
        ssl_certificate_key  ../fake.key;

        ssl_protocols       TLSv1.2 TLSv1.3;
        ssl_ciphers         HIGH:!aNULL:!MD5;

        # Таймауты
        proxy_connect_timeout 30s;
        proxy_send_timeout    30s;
        proxy_read_timeout    30s;

        # Буферизация
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;

        location / {{
            proxy_pass {remote_url};

            # Заголовки
            proxy_set_header Host zenzefi.melxiory.ru;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            # SSL настройки для upstream
            proxy_ssl_verify off;
            proxy_ssl_server_name on;

            # Клиентский сертификат УБРАН
        }}
    }}
}}
'''
        # Заменяем основной конфиг
        conf_dir = self.nginx_dir / "conf"
        main_conf_path = conf_dir / "nginx.conf"
        main_conf_path.write_text(full_config, encoding='utf-8')
        logger.info(f"📁 Основной nginx.conf перезаписан")

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
        """Возвращает статус nginx"""
        return {
            'running': self.is_running,
            'port': 61000,
            'url': 'https://zenzefi.melxiory.ru'
        }

    def restart(self):
        """Перезапуск nginx"""
        self.stop()
        time.sleep(3)
        return self.start()