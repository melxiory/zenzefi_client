# proxy_manager.py
import asyncio
import ssl
import re
import logging
import time
import threading
from pathlib import Path
from aiohttp import web, ClientSession, WSMsgType
import aiohttp
from utils.process_manager import get_process_manager
from utils.port_utils import check_port_availability, get_process_using_port
from core.config_manager import get_app_data_dir
import sys

logger = logging.getLogger(__name__)


class ZenzefiProxy:
    def __init__(self):
        self.upstream_url = "https://zenzefi.melxiory.ru"
        self.local_url = "https://127.0.0.1:61000"
        self.ssl_context = None

    async def handle_http(self, request):
        """Обработка HTTP/HTTPS запросов"""
        try:
            body = await request.read()

            # Подготовка заголовков
            headers = {}
            for key, value in request.headers.items():
                key_lower = key.lower()
                if key_lower not in ['host', 'connection', 'content-length', 'transfer-encoding']:
                    headers[key] = value

            header_host = self.upstream_url.replace('https://', '')
            headers.update({
                "Host": f"{header_host}",
                "X-Real-IP": request.remote,
                "X-Forwarded-For": request.remote,
                "X-Forwarded-Proto": "https"
            })

            upstream_url = f"{self.upstream_url}{request.path_qs}"

            cookie_jar = aiohttp.CookieJar()
            for name, value in request.cookies.items():
                cookie_jar.update_cookies({name: value})

            async with ClientSession(
                    connector=aiohttp.TCPConnector(ssl=False),
                    cookie_jar=cookie_jar
            ) as session:
                async with session.request(
                        method=request.method,
                        url=upstream_url,
                        headers=headers,
                        data=body,
                        allow_redirects=False,
                        timeout=aiohttp.ClientTimeout(total=30)
                ) as upstream_response:

                    response_headers = {}
                    for key, value in upstream_response.headers.items():
                        key_lower = key.lower()

                        if key_lower in ['content-encoding', 'transfer-encoding', 'connection', 'keep-alive']:
                            continue

                        if key_lower == 'access-control-allow-origin':
                            value = self.local_url

                        if key_lower == 'location':
                            value = value.replace(self.upstream_url, self.local_url)

                        response_headers[key] = value

                    response_headers.update({
                        'Access-Control-Allow-Origin': self.local_url,
                        'Access-Control-Allow-Credentials': 'true',
                        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                        'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With'
                    })

                    content = await upstream_response.read()
                    content_type = upstream_response.headers.get('content-type', '').lower()

                    if any(x in content_type for x in ['text/', 'javascript', 'json']):
                        try:
                            content_str = content.decode('utf-8')
                            content_str = self.fix_content(content_str, content_type)
                            content = content_str.encode('utf-8')
                        except:
                            pass

                    return web.Response(
                        body=content,
                        status=upstream_response.status,
                        headers=response_headers
                    )

        except Exception as e:
            logger.error(f"❌ HTTP Error: {e}")
            return web.Response(text=f"Proxy error: {str(e)}", status=500)

    async def handle_websocket(self, request):
        """Обработка WebSocket соединений"""
        ws_local = web.WebSocketResponse()
        await ws_local.prepare(request)

        logger.debug(f"🔌 WebSocket: {request.path}")

        try:
            upstream_ws_url = f"wss://zenzefi.melxiory.ru{request.path_qs}"

            headers = {
                "Host": "zenzefi.melxiory.ru",
                "Origin": self.upstream_url,
                "X-Real-IP": request.remote,
                "X-Forwarded-For": request.remote
            }

            if 'Cookie' in request.headers:
                headers['Cookie'] = request.headers['Cookie']
            if 'Authorization' in request.headers:
                headers['Authorization'] = request.headers['Authorization']

            for key in ['User-Agent', 'Accept', 'Accept-Language', 'Sec-WebSocket-Protocol']:
                if key in request.headers:
                    headers[key] = request.headers[key]

            cookie_jar = aiohttp.CookieJar()
            for name, value in request.cookies.items():
                cookie_jar.update_cookies({name: value})

            async with ClientSession(
                    connector=aiohttp.TCPConnector(ssl=False),
                    cookie_jar=cookie_jar
            ) as session:
                async with session.ws_connect(
                        upstream_ws_url,
                        headers=headers,
                        ssl=False
                ) as ws_upstream:

                    async def forward_to_upstream():
                        async for msg in ws_local:
                            if msg.type == WSMsgType.TEXT:
                                await ws_upstream.send_str(msg.data)
                            elif msg.type == WSMsgType.BINARY:
                                await ws_upstream.send_bytes(msg.data)
                            elif msg.type == WSMsgType.CLOSE:
                                await ws_upstream.close()
                                break

                    async def forward_to_local():
                        async for msg in ws_upstream:
                            if msg.type == WSMsgType.TEXT:
                                await ws_local.send_str(msg.data)
                            elif msg.type == WSMsgType.BINARY:
                                await ws_local.send_bytes(msg.data)
                            elif msg.type == WSMsgType.CLOSE:
                                await ws_local.close()
                                break

                    await asyncio.gather(
                        forward_to_upstream(),
                        forward_to_local(),
                        return_exceptions=True
                    )

        except Exception as e:
            logger.error(f"❌ WebSocket Error: {e}")
        finally:
            if not ws_local.closed:
                await ws_local.close()

        return ws_local

    def fix_content(self, content, content_type):
        """Исправляет контент для работы через прокси"""
        content = content.replace(self.upstream_url, self.local_url)
        content = content.replace('//zenzefi.melxiory.ru', '//127.0.0.1:61000')

        content = content.replace('wss://zenzefi.melxiory.ru', 'wss://127.0.0.1:61000')
        content = content.replace('ws://zenzefi.melxiory.ru', 'wss://127.0.0.1:61000')

        if 'text/html' in content_type:
            content = re.sub(
                r'(href|src|action)=["\'](/[^"\']*)["\']',
                r'\1="https://127.0.0.1:61000\2"',
                content
            )
        elif 'text/css' in content_type:
            content = re.sub(
                r'url\(["\']?(/[^)"\']*)["\']?\)',
                r'url(https://127.0.0.1:61000\1)',
                content
            )

        return content

    async def router(self, request):
        """Маршрутизация между HTTP и WebSocket"""
        if request.headers.get('Upgrade', '').lower() == 'websocket':
            return await self.handle_websocket(request)
        else:
            return await self.handle_http(request)


class ProxyManager:
    def __init__(self):
        self.is_running = False
        self.process_manager = get_process_manager()
        self.remote_url = ""
        self.local_port = 61000
        self.proxy = None
        self.runner = None
        self.site = None
        self.loop = None
        self.thread = None
        self.app_name = "Zenzefi Proxy"

    def start(self, local_port=61000, remote_url="https://zenzefi.melxiory.ru"):
        """Запуск прокси сервера"""
        if self.is_running:
            logger.warning("⚠️ Прокси уже запущен")
            return False

        try:
            # Улучшенная проверка порта
            port_available, port_message = check_port_availability(local_port)

            # Если порт занят, проверяем не нашим ли приложением
            if not port_available and self.is_port_in_use_by_us(local_port):
                logger.info("⚠️ Порт занят нашим приложением, пытаемся перезапустить...")
                self.stop()
                time.sleep(2)
                port_available, port_message = check_port_availability(local_port)

            if not port_available:
                process_info = get_process_using_port(local_port)
                if process_info:
                    logger.warning(f"⚠️ {port_message}")

                    # Пытаемся завершить процесс, занимающий порт
                    if self.process_manager.terminate_process(process_info['pid']):
                        logger.info(f"✅ Процесс завершен, проверяем порт снова...")
                        time.sleep(2)
                        port_available, port_message = check_port_availability(local_port)

                # Если порт все еще занят
                if not port_available:
                    error_msg = f"Не удалось освободить порт {local_port}. {port_message}"
                    logger.error(f"❌ {error_msg}")

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

            # Запускаем прокси сервер
            self.remote_url = remote_url
            self.local_port = local_port

            logger.info("🚀 Запускаем прокси сервер...")

            # Создаем новый event loop в отдельном потоке
            self.thread = threading.Thread(target=self._run_server, daemon=True)
            self.thread.start()

            # Ждем немного, чтобы сервер успел запуститься
            time.sleep(3)

            if self.is_running:
                logger.info(f"✅ Прокси запущен на https://127.0.0.1:{local_port}")
                logger.info(f"🌐 Проксируется на: {remote_url}")
                return True
            else:
                logger.error("❌ Прокси не запустился")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка запуска прокси: {e}")
            return False

    def _run_server(self):
        """Запускает сервер в отдельном event loop"""
        try:
            # Создаем новый event loop для этого потока
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            # Запускаем сервер
            self.loop.run_until_complete(self._start_server())

            # Запускаем event loop
            self.loop.run_forever()

        except Exception as e:
            logger.error(f"❌ Ошибка в event loop: {e}")
            self.is_running = False
        finally:
            if self.loop:
                self.loop.close()

    async def _start_server(self):
        """Асинхронный запуск сервера"""
        try:
            # Получаем путь к сертификатам
            app_data_dir = get_app_data_dir()
            certs_dir = app_data_dir / "certificates"
            cert_path = certs_dir / "fake.crt"
            key_path = certs_dir / "fake.key"

            # Создаем SSL контекст
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))

            # Создаем прокси
            self.proxy = ZenzefiProxy()
            self.proxy.upstream_url = self.remote_url
            self.proxy.local_url = f"https://127.0.0.1:{self.local_port}"

            # Создаем приложение
            app = web.Application()
            app.router.add_route('*', '/{path:.*}', self.proxy.router)

            # Создаем runner
            self.runner = web.AppRunner(app, access_log=None)
            await self.runner.setup()

            # Создаем site
            self.site = web.TCPSite(
                self.runner,
                host='127.0.0.1',
                port=self.local_port,
                ssl_context=ssl_context,
            )

            await self.site.start()
            self.is_running = True
            logger.info(f"✅ Сервер успешно запущен на порту {self.local_port}")

        except Exception as e:
            logger.error(f"❌ Ошибка запуска сервера: {e}")
            self.is_running = False

    def stop(self):
        """Остановка прокси сервера"""
        try:
            logger.info("🛑 Останавливаем прокси сервер...")

            self.is_running = False

            # Останавливаем aiohttp сервер
            if self.loop and self.loop.is_running():
                # Запускаем остановку в event loop
                asyncio.run_coroutine_threadsafe(self._stop_server(), self.loop)
                time.sleep(2)

                # Останавливаем event loop
                self.loop.call_soon_threadsafe(self.loop.stop)

            # Ждем завершения потока
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=5)

            logger.info("✅ Прокси сервер остановлен")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка остановки прокси: {e}")
            return False

    async def _stop_server(self):
        """Асинхронная остановка сервера"""
        try:
            if self.site:
                await self.site.stop()
            if self.runner:
                await self.runner.cleanup()
            logger.debug("✅ Сервер успешно остановлен")
        except Exception as e:
            logger.error(f"❌ Ошибка при остановке сервера: {e}")

    def get_status(self):
        """Возвращает статус прокси"""
        port_available, port_message = check_port_availability(self.local_port)
        port_used_by_us = self.is_port_in_use_by_us(self.local_port) if not port_available else False

        status = {
            'running': self.is_running,
            'port_available': port_available,
            'port_used_by_us': port_used_by_us,
            'port': self.local_port,
            'url': self.remote_url,
            'is_admin': self.process_manager.is_admin
        }

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

        try:
            process = psutil.Process(process_info['pid'])
            exe_path = Path(process.exe())

            # Проверяем что это Python процесс
            is_python = 'python' in process_info['name'].lower()

            # Если это наш EXE файл
            if getattr(sys, 'frozen', False):
                current_exe = Path(sys.executable)
                is_our_path = exe_path == current_exe
            else:
                # В dev режиме проверяем по имени процесса
                is_our_path = is_python

            logger.debug(f"Проверка процесса: {process_info['name']}, PID: {process_info['pid']}")
            logger.debug(f"Путь: {exe_path}, наш процесс: {is_our_path}")

            return is_python and is_our_path

        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError) as e:
            logger.debug(f"Не удалось проверить процесс на порту {port}: {e}")
            return False


# Синглтон для глобального доступа
_proxy_manager = None


def get_proxy_manager() -> ProxyManager:
    """Возвращает глобальный экземпляр ProxyManager"""
    global _proxy_manager
    if _proxy_manager is None:
        _proxy_manager = ProxyManager()
    return _proxy_manager
