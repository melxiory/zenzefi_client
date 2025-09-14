import http.server
import ssl
import socketserver
import httpx
import re
from pathlib import Path
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def __init__(self, local_port, remote_url, remote_host, cert_path, *args, **kwargs):
        self.local_port = local_port
        self.remote_url = remote_url
        self.remote_host = remote_host
        self.cert_path = cert_path
        super().__init__(*args, **kwargs)

    def do_GET(self):
        self.proxy_request()

    def do_POST(self):
        self.proxy_request()

    def do_OPTIONS(self):
        self.proxy_request()

    def proxy_request(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length else None

            # Подготавливаем заголовки
            headers = {}
            for key, value in self.headers.items():
                key_lower = key.lower()
                if key_lower not in ['host', 'connection', 'accept-encoding', 'content-length']:
                    headers[key] = value

            headers.update({
                "Host": self.remote_host,
                "X-Real-IP": self.client_address[0],
                "X-Forwarded-For": self.client_address[0],
                "X-Forwarded-Proto": "https"
            })

            if body and 'content-length' not in headers:
                headers['Content-Length'] = str(len(body))

            # Проксируем запрос
            upstream_url = f"{self.remote_url}{self.path}"

            with httpx.Client(
                    verify=False,
                    cert=self.cert_path,
                    timeout=30.0,
                    follow_redirects=False
            ) as client:
                upstream_response = client.request(
                    method=self.command,
                    url=upstream_url,
                    headers=headers,
                    content=body
                )

            # Отправляем ответ
            self.send_response(upstream_response.status_code)

            response_headers = dict(upstream_response.headers)
            for key, value in response_headers.items():
                key_lower = key.lower()

                if key_lower in ['content-encoding', 'transfer-encoding', 'connection', 'keep-alive']:
                    continue

                if key_lower == 'access-control-allow-origin':
                    value = f'https://127.0.0.1:{self.local_port}'

                if key_lower == 'location':
                    value = value.replace(self.remote_host, f'127.0.0.1:{self.local_port}')

                self.send_header(key, value)

            self.end_headers()

            # Обрабатываем контент
            content = upstream_response.content
            content_type = upstream_response.headers.get('content-type', '').lower()

            if any(x in content_type for x in ['text/html', 'text/css', 'javascript', 'json']):
                try:
                    content_str = content.decode('utf-8')
                    content_str = self.fix_content(content_str, content_type)
                    content = content_str.encode('utf-8')
                except:
                    pass

            self.wfile.write(content)

        except Exception as e:
            logger.error(f"Proxy error: {e}")
            self.send_error(500, f"Proxy error: {str(e)}")

    def fix_content(self, content, content_type):
        """Исправляет контент для работы через прокси"""
        content = content.replace(f'https://{self.remote_host}', f'https://127.0.0.1:{self.local_port}')
        content = content.replace(f'http://{self.remote_host}', f'https://127.0.0.1:{self.local_port}')

        if 'text/html' in content_type:
            content = re.sub(
                r'(href|src|action)=["\'](/[^"\']*)["\']',
                rf'\1="https://127.0.0.1:{self.local_port}\2"',
                content
            )

        elif 'text/css' in content_type:
            content = re.sub(
                r'url\(["\']?(/[^)"\']*)["\']?\)',
                rf'url(https://127.0.0.1:{self.local_port}\1)',
                content
            )

        return content

    def log_message(self, format, *args):
        logger.info(f"{self.command} {self.path} -> {args[0] if args else ''}")


def run_proxy_server(local_port, remote_url, cert_path):
    """Запуск прокси-сервера"""
    try:
        # Парсим remote URL чтобы получить host
        parsed_url = urlparse(remote_url)
        remote_host = parsed_url.netloc

        # Настройка логирования
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        # Фабрика для создания обработчиков
        def handler_factory(*args, **kwargs):
            return ProxyHandler(local_port, remote_url, remote_host, cert_path, *args, **kwargs)

        # Настройка сервера
        server_address = ('127.0.0.1', local_port)
        httpd = socketserver.TCPServer(server_address, handler_factory)

        # SSL контекст
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile="fake.crt", keyfile="fake.key")

        # Оборачиваем сокет
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

        logger.info("=" * 60)
        logger.info(f"🚀 Прокси сервер запущен!")
        logger.info(f"📍 Локальный адрес: https://127.0.0.1:{local_port}")
        logger.info(f"🌐 Проксируется на: {remote_url}")
        logger.info(f"🔐 Сертификат: {cert_path}")
        logger.info("=" * 60)
        logger.info("Нажмите Ctrl+C для остановки")
        logger.info("=" * 60)

        httpd.serve_forever()

    except Exception as e:
        logger.error(f"Ошибка запуска прокси сервера: {e}")
        raise