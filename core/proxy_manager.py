# proxy_manager.py
import asyncio
import ssl
import re
import logging
import time
import threading
from aiohttp import web, ClientSession, WSMsgType
import aiohttp
from utils.process_manager import get_process_manager
from utils.port_utils import check_port_availability, get_process_using_port
from core.config_manager import get_app_data_dir
import sys
from collections import OrderedDict
from typing import Optional, Tuple
import hashlib

logger = logging.getLogger(__name__)


class LRUCache:
    """Простой LRU кэш для статических ресурсов"""
    def __init__(self, maxsize=100):
        self.cache = OrderedDict()
        self.maxsize = maxsize
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Tuple[bytes, dict, int]]:
        """Получить элемент из кэша"""
        if key in self.cache:
            self.hits += 1
            # Перемещаем в конец (most recently used)
            self.cache.move_to_end(key)
            return self.cache[key]
        self.misses += 1
        return None

    def put(self, key: str, value: Tuple[bytes, dict, int]):
        """Добавить элемент в кэш"""
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.maxsize:
            # Удаляем самый старый элемент
            self.cache.popitem(last=False)

    def clear(self):
        """Очистить кэш"""
        self.cache.clear()
        self.hits = 0
        self.misses = 0

    def get_stats(self):
        """Получить статистику кэша"""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        return {
            'size': len(self.cache),
            'maxsize': self.maxsize,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': f"{hit_rate:.1f}%"
        }


class ZenzefiProxy:
    # Предкомпилированные регулярные выражения
    _HTML_ATTR_PATTERN = re.compile(r'(href|src|action)=["\'](/[^"\']*)["\']')
    _CSS_URL_PATTERN = re.compile(r'url\(["\']?(/[^)"\']*)["\']?\)')

    # Статические расширения для кэширования
    _CACHEABLE_EXTENSIONS = {'.js', '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.woff', '.woff2', '.ttf', '.ico', '.webp'}

    # Размер для streaming (1MB)
    _STREAMING_THRESHOLD = 1024 * 1024

    def __init__(self):
        self.upstream_url = "https://zenzefi.melxiory.ru"
        self.local_url = "https://127.0.0.1:61000"
        self.ssl_context = None

        # Кэш для статических ресурсов
        self.cache = LRUCache(maxsize=100)

        # Connection pool для переиспользования соединений
        self.connector = None
        self.session = None

        # Семафор для ограничения одновременных соединений
        self.connection_semaphore = asyncio.Semaphore(50)

    async def initialize(self):
        """Инициализация connection pool"""
        if self.connector is None:
            # Настройка connection pooling
            self.connector = aiohttp.TCPConnector(
                ssl=False,
                limit=100,  # Максимум 100 одновременных соединений
                limit_per_host=30,  # Максимум 30 на хост
                ttl_dns_cache=300,  # DNS кэш на 5 минут
                keepalive_timeout=60,  # Keep-alive 60 секунд
                enable_cleanup_closed=True
            )

        if self.session is None:
            self.session = ClientSession(
                connector=self.connector,
                timeout=aiohttp.ClientTimeout(total=30, connect=10)
            )

    async def cleanup(self):
        """Очистка ресурсов"""
        if self.session:
            await self.session.close()
            self.session = None
        if self.connector:
            await self.connector.close()
            self.connector = None

    def _get_cache_key(self, path: str, query: str = "") -> str:
        """Генерация ключа кэша"""
        full_path = f"{path}?{query}" if query else path
        return hashlib.md5(full_path.encode()).hexdigest()

    def _is_cacheable(self, path: str, content_type: str) -> bool:
        """Проверка, можно ли кэшировать ресурс"""
        # Проверяем расширение файла
        path_lower = path.lower()
        for ext in self._CACHEABLE_EXTENSIONS:
            if ext in path_lower:
                return True

        # Проверяем content-type
        cacheable_types = ['image/', 'font/', 'text/css', 'application/javascript']
        return any(ct in content_type.lower() for ct in cacheable_types)

    async def handle_http(self, request):
        """Обработка HTTP/HTTPS запросов с кэшированием и streaming"""
        try:
            # Проверяем кэш для статических ресурсов
            cache_key = self._get_cache_key(request.path, request.query_string)

            # Пытаемся получить из кэша (только для GET запросов)
            if request.method == 'GET':
                cached = self.cache.get(cache_key)
                if cached:
                    content, headers, status = cached
                    logger.debug(f"✅ Cache HIT: {request.path}")
                    return web.Response(body=content, status=status, headers=headers)

            # Используем семафор для ограничения одновременных соединений
            async with self.connection_semaphore:
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

                # Используем переиспользуемую сессию
                await self.initialize()

                async with self.session.request(
                        method=request.method,
                        url=upstream_url,
                        headers=headers,
                        data=body,
                        allow_redirects=False
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

                    content_type = upstream_response.headers.get('content-type', '').lower()
                    content_length = int(upstream_response.headers.get('content-length', 0))

                    # Streaming для больших файлов (>1MB)
                    if content_length > self._STREAMING_THRESHOLD:
                        logger.debug(f"🌊 Streaming: {request.path} ({content_length} bytes)")

                        response = web.StreamResponse(
                            status=upstream_response.status,
                            headers=response_headers
                        )
                        await response.prepare(request)

                        async for chunk in upstream_response.content.iter_chunked(8192):
                            await response.write(chunk)

                        await response.write_eof()
                        return response

                    # Обычная загрузка для небольших файлов
                    content = await upstream_response.read()

                    # Обработка текстового контента
                    if any(x in content_type for x in ['text/', 'javascript', 'json']):
                        try:
                            content_str = content.decode('utf-8')
                            content_str = self.fix_content(content_str, content_type)
                            content = content_str.encode('utf-8')
                        except:
                            pass

                    # Кэшируем статические ресурсы
                    if request.method == 'GET' and self._is_cacheable(request.path, content_type):
                        self.cache.put(cache_key, (content, dict(response_headers), upstream_response.status))
                        logger.debug(f"💾 Cached: {request.path}")

                    return web.Response(
                        body=content,
                        status=upstream_response.status,
                        headers=response_headers
                    )

        except Exception as e:
            logger.error(f"❌ HTTP Error: {e}")
            return web.Response(text=f"Proxy error: {str(e)}", status=500)

    async def handle_websocket(self, request):
        """Обработка WebSocket соединений с ограничением"""
        ws_local = web.WebSocketResponse(max_msg_size=10 * 1024 * 1024)  # 10MB лимит
        await ws_local.prepare(request)

        logger.debug(f"🔌 WebSocket: {request.path}")

        try:
            async with self.connection_semaphore:
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

                await self.initialize()

                async with self.session.ws_connect(
                        upstream_ws_url,
                        headers=headers,
                        ssl=False,
                        max_msg_size=10 * 1024 * 1024
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
        """Исправляет контент для работы через прокси (с оптимизированными regex и кэшированием)"""
        # Создаем ключ кэша на основе хеша контента и типа
        # Для небольших файлов (<10KB) используем полный хеш, для больших - первые 1KB
        if len(content) < 10240:
            cache_key = hashlib.md5(f"{content}{content_type}".encode()).hexdigest()
        else:
            cache_key = hashlib.md5(f"{content[:1024]}{len(content)}{content_type}".encode()).hexdigest()

        # Проверяем кэш (используем тот же LRU кэш)
        cached_result = self.cache.get(f"fix_{cache_key}")
        if cached_result:
            # Возвращаем кэшированный результат
            return cached_result[0].decode('utf-8')

        # Простые замены строк
        content = content.replace(self.upstream_url, self.local_url)
        content = content.replace('//zenzefi.melxiory.ru', '//127.0.0.1:61000')
        content = content.replace('wss://zenzefi.melxiory.ru', 'wss://127.0.0.1:61000')
        content = content.replace('ws://zenzefi.melxiory.ru', 'wss://127.0.0.1:61000')

        # Regex замены с предкомпилированными паттернами
        if 'text/html' in content_type:
            content = self._HTML_ATTR_PATTERN.sub(
                r'\1="https://127.0.0.1:61000\2"',
                content
            )
        elif 'text/css' in content_type:
            content = self._CSS_URL_PATTERN.sub(
                r'url(https://127.0.0.1:61000\1)',
                content
            )

        # Кэшируем результат (только для небольших файлов чтобы не перегружать память)
        if len(content) < 102400:  # < 100KB
            self.cache.put(f"fix_{cache_key}", (content.encode('utf-8'), {}, 200))

        return content

    async def router(self, request):
        """Маршрутизация между HTTP и WebSocket"""
        if request.headers.get('Upgrade', '').lower() == 'websocket':
            return await self.handle_websocket(request)
        else:
            return await self.handle_http(request)

    def get_cache_stats(self):
        """Получить статистику кэша"""
        return self.cache.get_stats()


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

            # Инициализируем connection pool
            await self.proxy.initialize()

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
            logger.info(f"📊 Connection pool: лимит={self.proxy.connector.limit}, per_host={self.proxy.connector.limit_per_host}")

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

            # Логируем статистику кэша перед остановкой
            if self.proxy:
                stats = self.proxy.get_cache_stats()
                logger.info(f"📊 Статистика кэша: {stats}")

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
            if self.proxy:
                await self.proxy.cleanup()
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

        # Добавляем статистику кэша
        if self.proxy and self.is_running:
            status['cache_stats'] = self.proxy.get_cache_stats()

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