import os
import subprocess
import time
import logging
from pathlib import Path
import shutil

logger = logging.getLogger(__name__)


class NginxManager:
    def __init__(self):
        self.process = None
        self.is_running = False
        self.nginx_dir = Path("nginx").absolute()

    def start(self, local_port=61000, remote_url="https://zenzefi.melxiory.ru", cert_path="melxiory.pem"):
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

            # Копируем сертификат в папку nginx если нужно
            if cert_path and Path(cert_path).exists():
                cert_dest = self.nginx_dir / "melxiory.pem"
                shutil.copy2(cert_path, cert_dest)
                logger.info(f"📄 Сертификат скопирован: {cert_dest}")

            # Генерируем кастомный конфиг
            self._generate_custom_config(local_port, remote_url)

            # Останавливаем старый nginx если есть
            self.stop()

            # Запускаем nginx
            self.process = subprocess.Popen(
                [str(nginx_exe)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.nginx_dir),  # Рабочая директория = папка nginx
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
            if self.process:
                try:
                    # Graceful shutdown
                    nginx_exe = self.nginx_dir / "nginx.exe"
                    subprocess.run(
                        [str(nginx_exe), "-s", "quit"],
                        cwd=str(self.nginx_dir),
                        capture_output=True,
                        timeout=5,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                except:
                    pass

                self.process.terminate()
                self.process.wait(timeout=5)

            # Дополнительно убиваем все процессы nginx
            subprocess.run(
                ["taskkill", "/f", "/im", "nginx.exe"],
                capture_output=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            self.is_running = False
            self.process = None
            logger.info("✅ Nginx остановлен")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка остановки nginx: {e}")
            return False

    def _generate_custom_config(self, local_port, remote_url):
        """Генерирует кастомный конфиг для прокси"""
        custom_config = f'''
# Zenzefi Proxy Configuration
worker_processes  1;

events {{
    worker_connections  1024;
}}

http {{
    include       mime.types;
    default_type  application/octet-stream;

    sendfile        on;
    keepalive_timeout  65;

    # Прокси сервер для Zenzefi
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
            proxy_ssl_name zenzefi.melxiory.ru;

            # Клиентский сертификат
            proxy_ssl_certificate ../melxiory.pem;
            proxy_ssl_certificate_key ../melxiory.pem;
        }}
    }}
}}
'''
        # Сохраняем конфиг в папку conf
        conf_dir = self.nginx_dir / "conf"
        custom_conf_path = conf_dir / "nginx.conf"
        custom_conf_path.write_text(custom_config, encoding='utf-8')
        logger.info(f"📁 Конфиг создан: {custom_conf_path}")


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
        time.sleep(2)
        return self.start()