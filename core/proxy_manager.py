# proxy_manager.py
import asyncio
import ssl
import logging
import time
import threading
from aiohttp import web, ClientSession, WSMsgType
import aiohttp
from utils.process_manager import get_process_manager
from utils.port_utils import check_port_availability, get_process_using_port
from core.config_manager import get_app_data_dir
from core.proxy import CacheManager, ContentRewriter
from core.auth_manager import get_auth_manager
import sys
import gzip
import zlib

logger = logging.getLogger(__name__)


# Алиас для обратной совместимости
LRUCache = CacheManager


class ZenzefiProxy:
    # Размер для streaming (1MB)
    _STREAMING_THRESHOLD = 1024 * 1024

    def __init__(self):
        self.upstream_url = "https://zenzefi.melxiory.ru"
        self.local_url = "https://127.0.0.1:61000"
        self.ssl_context = None

        # Кэш для статических ресурсов
        self.cache = LRUCache(maxsize=100)

        # ContentRewriter для перезаписи URL
        self.content_rewriter = ContentRewriter(
            upstream_url=self.upstream_url,
            local_url=self.local_url,
            cache_manager=self.cache
        )

        # Connection pool для переиспользования соединений
        self.connector = None
        self.session = None

        # Семафор для ограничения одновременных соединений
        self.connection_semaphore = asyncio.Semaphore(50)

        # Request deduplication - словарь активных запросов
        self.pending_requests = {}  # {request_key: (asyncio.Event, result_holder)}

        # Статистика производительности
        self.stats = {
            'total_requests': 0,
            'total_responses': 0,
            'active_connections': 0,
            'compressed_responses': 0,
            'compression_saved_bytes': 0,
            'streamed_responses': 0,
            'errors': 0,
            'websocket_connections': 0,
            'deduplicated_requests': 0
        }

    async def initialize(self):
        """Инициализация connection pool с оптимизацией для keep-alive"""
        if self.connector is None:
            # Настройка connection pooling с максимальной оптимизацией keep-alive
            self.connector = aiohttp.TCPConnector(
                ssl=False,
                limit=100,  # Максимум 100 одновременных соединений
                limit_per_host=30,  # Максимум 30 на хост (оптимально для HTTP/1.1)
                ttl_dns_cache=300,  # DNS кэш на 5 минут
                keepalive_timeout=60,  # Keep-alive 60 секунд
                force_close=False,  # НЕ закрывать соединения после каждого запроса (критично!)
                enable_cleanup_closed=True  # Автоочистка закрытых соединений
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


    def _is_compressible(self, content_type: str) -> bool:
        """Проверка, можно ли сжимать контент"""
        compressible_types = [
            'text/', 'application/json', 'application/javascript',
            'application/xml', 'application/x-javascript'
        ]
        return any(ct in content_type.lower() for ct in compressible_types)

    def _compress_content(self, content: bytes, accept_encoding: str) -> tuple[bytes, str]:
        """Сжимает контент используя gzip или deflate

        Возвращает (сжатый_контент, encoding)
        """
        # Не сжимаем если контент слишком маленький (< 1KB)
        if len(content) < 1024:
            return content, None

        # Определяем предпочитаемый метод сжатия
        accept_encoding_lower = accept_encoding.lower()

        # Предпочитаем gzip как наиболее распространенный
        if 'gzip' in accept_encoding_lower:
            try:
                compressed = gzip.compress(content, compresslevel=6)
                # Проверяем что сжатие дало выгоду
                if len(compressed) < len(content):
                    logger.debug(f"🗜️ gzip: {len(content)} → {len(compressed)} bytes ({len(compressed)/len(content)*100:.1f}%)")
                    return compressed, 'gzip'
            except Exception as e:
                logger.warning(f"Ошибка gzip сжатия: {e}")

        # Fallback на deflate
        elif 'deflate' in accept_encoding_lower:
            try:
                compressed = zlib.compress(content, level=6)
                if len(compressed) < len(content):
                    logger.debug(f"🗜️ deflate: {len(content)} → {len(compressed)} bytes ({len(compressed)/len(content)*100:.1f}%)")
                    return compressed, 'deflate'
            except Exception as e:
                logger.warning(f"Ошибка deflate сжатия: {e}")

        # Не удалось сжать или сжатие не поддерживается
        return content, None

    async def handle_http(self, request):
        """Обработка HTTP/HTTPS запросов с кэшированием и streaming"""
        self.stats['total_requests'] += 1
        self.stats['active_connections'] += 1

        try:
            # Специальная обработка для auth страницы
            # Показываем HTML auth страницу только если:
            # 1. Есть token в query параметрах (прямая ссылка из Desktop Client)
            # 2. ИЛИ браузер запрашивает HTML (Accept: text/html) на корневой путь
            if request.path == '/api/v1/proxy' or request.path == '/api/v1/proxy/':
                # Проверяем наличие token в query
                has_token = 'token' in request.query

                # Проверяем Accept header
                accept_header = request.headers.get('Accept', '')
                wants_html = 'text/html' in accept_header

                # Показываем auth страницу только если есть token ИЛИ браузер просит HTML
                if has_token or (wants_html and not 'application/json' in accept_header):
                    self.stats['active_connections'] -= 1
                    return await self._serve_auth_page(request)

                # Иначе проксируем запрос на backend (для API клиентов, ожидающих JSON)

            # Проверяем кэш для статических ресурсов
            cache_key = self.cache.generate_key(request.path, request.query_string)

            # Пытаемся получить из кэша (только для GET запросов)
            if request.method == 'GET':
                cached = self.cache.get(cache_key)
                if cached:
                    content, headers, status = cached
                    logger.debug(f"✅ Cache HIT: {request.path}")
                    self.stats['total_responses'] += 1
                    self.stats['active_connections'] -= 1
                    return web.Response(body=content, status=status, headers=headers)

                # Request Deduplication: проверяем, есть ли уже активный запрос
                if cache_key in self.pending_requests:
                    logger.debug(f"🔄 Request deduplication: waiting for {request.path}")
                    self.stats['deduplicated_requests'] += 1
                    self.stats['active_connections'] -= 1

                    # Ждём результат активного запроса
                    event, result_holder = self.pending_requests[cache_key]
                    await event.wait()  # Ждём пока первый запрос завершится

                    self.stats['total_responses'] += 1

                    # Проверяем результат и создаём НОВЫЙ Response объект
                    if 'body' in result_holder:
                        # Создаём новый Response с переиспользованием body
                        return web.Response(
                            body=result_holder['body'],
                            status=result_holder['status'],
                            headers=result_holder['headers']
                        )
                    elif 'error' in result_holder:
                        # Первый запрос упал, делаем свой
                        logger.debug(f"⚠️ Original request failed: {result_holder['error']}")
                        # Продолжаем выполнение своего запроса
                    else:
                        # Странная ситуация, делаем свой запрос
                        logger.warning("⚠️ No result in holder, making new request")

            # Создаём Event для дедупликации (только для GET)
            dedup_event = None
            result_holder = {}
            if request.method == 'GET' and cache_key not in self.pending_requests:
                dedup_event = asyncio.Event()
                self.pending_requests[cache_key] = (dedup_event, result_holder)

            # Используем семафор для ограничения одновременных соединений
            async with self.connection_semaphore:
                body = await request.read()

                # Подготовка заголовков
                headers = {}
                for key, value in request.headers.items():
                    key_lower = key.lower()
                    if key_lower not in ['host', 'connection', 'content-length', 'transfer-encoding']:
                        headers[key] = value

                header_host = self.upstream_url.replace('https://', '').replace('http://', '')
                headers.update({
                    "Host": f"{header_host}",
                    "X-Real-IP": request.remote,
                    "X-Forwarded-For": request.remote,
                    "X-Forwarded-Proto": "https"
                })

                upstream_url = f"{self.upstream_url}{request.path_qs}"

                # Копируем cookies от клиента для отправки на backend
                # Это критично для cookie-based аутентификации!
                cookies = {}
                for name, value in request.cookies.items():
                    cookies[name] = value
                    logger.debug(f"🍪 Forwarding cookie: {name}")

                # Используем переиспользуемую сессию
                await self.initialize()

                async with self.session.request(
                        method=request.method,
                        url=upstream_url,
                        headers=headers,
                        data=body,
                        cookies=cookies,  # КРИТИЧНО! Пересылаем cookies на backend
                        allow_redirects=False
                ) as upstream_response:

                    # Обработка ошибки 401 (Unauthorized)
                    if upstream_response.status == 401:
                        logger.error("❌ Unauthorized: Cookie аутентификации недействителен или истёк")
                        self.stats['errors'] += 1
                        self.stats['total_responses'] += 1
                        self.stats['active_connections'] -= 1

                        return web.Response(
                            text="⚠️ Сессия аутентификации истекла.\n\n"
                                 "Пожалуйста, перезапустите прокси для повторной аутентификации.",
                            status=401,
                            content_type="text/plain"
                        )

                    response_headers = {}
                    for key, value in upstream_response.headers.items():
                        key_lower = key.lower()

                        if key_lower in ['content-encoding', 'transfer-encoding', 'connection', 'keep-alive']:
                            continue

                        if key_lower == 'access-control-allow-origin':
                            value = self.local_url

                        if key_lower == 'location':
                            value = value.replace(self.upstream_url, self.local_url)

                        # Специальная обработка Set-Cookie для правильной пересылки
                        if key_lower == 'set-cookie':
                            logger.debug(f"🍪 Forwarding Set-Cookie from backend: {value[:50]}...")

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
                        self.stats['streamed_responses'] += 1

                        response = web.StreamResponse(
                            status=upstream_response.status,
                            headers=response_headers
                        )
                        await response.prepare(request)

                        async for chunk in upstream_response.content.iter_chunked(8192):
                            await response.write(chunk)

                        await response.write_eof()
                        self.stats['total_responses'] += 1
                        self.stats['active_connections'] -= 1
                        return response

                    # Обычная загрузка для небольших файлов
                    content = await upstream_response.read()

                    # Обработка текстового контента
                    if any(x in content_type for x in ['text/', 'javascript', 'json']):
                        try:
                            content_str = content.decode('utf-8')
                            content_str = self.content_rewriter.rewrite(content_str, content_type)
                            content = content_str.encode('utf-8')
                        except:
                            pass

                    # Применяем сжатие если клиент поддерживает и контент подходит
                    original_size = len(content)
                    accept_encoding = request.headers.get('Accept-Encoding', '')
                    if accept_encoding and self._is_compressible(content_type):
                        compressed_content, encoding = self._compress_content(content, accept_encoding)
                        if encoding:
                            saved_bytes = original_size - len(compressed_content)
                            self.stats['compressed_responses'] += 1
                            self.stats['compression_saved_bytes'] += saved_bytes
                            content = compressed_content
                            response_headers['Content-Encoding'] = encoding
                            response_headers['Content-Length'] = str(len(content))

                    # Добавляем явные keep-alive заголовки
                    response_headers['Connection'] = 'keep-alive'
                    response_headers['Keep-Alive'] = 'timeout=60, max=100'

                    # Кэшируем статические ресурсы
                    if request.method == 'GET' and self.cache.is_cacheable(request.path, content_type):
                        self.cache.put(cache_key, (content, dict(response_headers), upstream_response.status))
                        logger.debug(f"💾 Cached: {request.path}")

                    self.stats['total_responses'] += 1
                    self.stats['active_connections'] -= 1

                    # Сохраняем данные для дедупликации ПЕРЕД созданием Response
                    if dedup_event:
                        result_holder['body'] = content
                        result_holder['status'] = upstream_response.status
                        result_holder['headers'] = dict(response_headers)
                        dedup_event.set()  # Уведомляем ждущие запросы
                        # Очищаем через небольшую задержку
                        asyncio.create_task(self._cleanup_pending_request(cache_key))

                    # Создаём Response для текущего запроса
                    return web.Response(
                        body=content,
                        status=upstream_response.status,
                        headers=response_headers
                    )

        except Exception as e:
            self.stats['errors'] += 1
            self.stats['active_connections'] -= 1
            logger.error(f"❌ HTTP Error: {e}")

            # Сохраняем ошибку для дедупликации
            if 'dedup_event' in locals() and dedup_event:
                result_holder['error'] = str(e)
                dedup_event.set()
                asyncio.create_task(self._cleanup_pending_request(cache_key))

            return web.Response(text=f"Proxy error: {str(e)}", status=500)

    async def _serve_auth_page(self, request):
        """
        Служебная страница для первоначальной аутентификации

        Маршрутизация:
        - /api/v1/proxy?token=... → HTML auth страница (этот метод)
        - /api/v1/proxy/ (Accept: text/html) → HTML auth страница (этот метод)
        - /api/v1/proxy/ (Accept: application/json) → проксируется на backend

        Процесс аутентификации:
        1. Читает токен из query параметров или конфига
        2. JavaScript отправляет токен на backend /authenticate endpoint
        3. Backend устанавливает HTTP-only secure cookie
        4. Перенаправляет на реальное приложение
        5. Все последующие запросы автоматически содержат cookie
        """

        # Проверяем есть ли уже токен в query параметрах
        query = request.query
        token = query.get('token', '')

        # Если токена нет в query, попробуем получить из конфига
        if not token:
            from core.config_manager import get_config
            config = get_config()
            token = config.get_access_token() or ''

        html = f"""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Zenzefi Authentication</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    margin: 0;
                    color: white;
                }}
                .container {{
                    background: rgba(255, 255, 255, 0.1);
                    backdrop-filter: blur(10px);
                    padding: 40px;
                    border-radius: 20px;
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
                    text-align: center;
                    max-width: 500px;
                }}
                .spinner {{
                    border: 4px solid rgba(255, 255, 255, 0.3);
                    border-radius: 50%;
                    border-top: 4px solid white;
                    width: 50px;
                    height: 50px;
                    animation: spin 1s linear infinite;
                    margin: 20px auto;
                }}
                @keyframes spin {{
                    0% {{ transform: rotate(0deg); }}
                    100% {{ transform: rotate(360deg); }}
                }}
                .message {{
                    font-size: 18px;
                    margin: 20px 0;
                }}
                .error {{
                    background: rgba(220, 38, 38, 0.8);
                    padding: 15px;
                    border-radius: 10px;
                    margin-top: 20px;
                }}
                .success {{
                    background: rgba(34, 197, 94, 0.8);
                    padding: 15px;
                    border-radius: 10px;
                    margin-top: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🔐 Zenzefi Authentication</h1>
                <div class="spinner" id="spinner"></div>
                <div class="message" id="message">Authenticating...</div>
            </div>

            <script>
                // ВАЖНО: backendUrl должен указывать на локальный backend, а НЕ на Zenzefi Server
                const backendUrl = 'http://127.0.0.1:8000';
                const zenzefiUrl = '{self.upstream_url}';
                const token = '{token}' || sessionStorage.getItem('zenzefi_token');

                async function authenticate() {{
                    const spinner = document.getElementById('spinner');
                    const message = document.getElementById('message');

                    if (!token) {{
                        spinner.style.display = 'none';
                        message.innerHTML = '<div class="error">❌ Токен не найден!<br>Пожалуйста, введите токен в приложении.</div>';
                        return;
                    }}

                    try {{
                        // Отправляем токен на backend для установки cookie
                        const response = await fetch(`${{backendUrl}}/api/v1/proxy/authenticate`, {{
                            method: 'POST',
                            headers: {{
                                'Content-Type': 'application/json',
                            }},
                            body: JSON.stringify({{ token: token }}),
                            credentials: 'include'  // Важно для cookie
                        }});

                        if (response.ok) {{
                            const data = await response.json();

                            spinner.style.display = 'none';
                            message.innerHTML = `
                                <div class="success">
                                    ✅ Аутентификация успешна!<br>
                                    <small>User ID: ${{data.user_id}}</small><br>
                                    <small>Истекает: ${{data.expires_at ? new Date(data.expires_at).toLocaleString() : 'Не активирован'}}</small><br>
                                    <br>
                                    Перенаправление...
                                </div>
                            `;

                            // Перенаправляем на проксированное приложение через 2 секунды
                            setTimeout(() => {{
                                window.location.href = '${{backendUrl}}/api/v1/proxy/';
                            }}, 2000);

                        }} else {{
                            const errorData = await response.json();

                            spinner.style.display = 'none';
                            message.innerHTML = `
                                <div class="error">
                                    ❌ Ошибка аутентификации!<br>
                                    <small>${{errorData.detail || 'Unknown error'}}</small>
                                </div>
                            `;
                        }}

                    }} catch (error) {{
                        spinner.style.display = 'none';
                        message.innerHTML = `
                            <div class="error">
                                ❌ Ошибка сети!<br>
                                <small>${{error.message}}</small><br>
                                <small>Backend доступен на ${{backendUrl}}?</small>
                            </div>
                        `;
                        console.error('Authentication error:', error);
                    }}
                }}

                // Запускаем аутентификацию при загрузке
                authenticate();
            </script>
        </body>
        </html>
        """

        return web.Response(
            text=html,
            content_type='text/html',
            headers={
                'Cache-Control': 'no-store, no-cache, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        )

    async def _cleanup_pending_request(self, cache_key: str, delay: float = 0.1):
        """Очистка завершённого запроса из pending_requests"""
        await asyncio.sleep(delay)
        if cache_key in self.pending_requests:
            del self.pending_requests[cache_key]
            logger.debug(f"🧹 Cleaned up pending request: {cache_key[:16]}...")

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

    async def router(self, request):
        """Маршрутизация между HTTP и WebSocket"""
        if request.headers.get('Upgrade', '').lower() == 'websocket':
            return await self.handle_websocket(request)
        else:
            return await self.handle_http(request)

    def get_cache_stats(self):
        """Получить статистику кэша"""
        return self.cache.get_stats()

    def get_full_stats(self):
        """Получить полную статистику прокси"""
        cache_stats = self.cache.get_stats()

        # Подсчитываем коэффициент сжатия
        compression_ratio = 0
        if self.stats['compressed_responses'] > 0:
            avg_saved = self.stats['compression_saved_bytes'] / self.stats['compressed_responses']
            compression_ratio = f"{avg_saved:.0f}"

        return {
            'requests': self.stats['total_requests'],
            'responses': self.stats['total_responses'],
            'active': self.stats['active_connections'],
            'errors': self.stats['errors'],
            'compressed': self.stats['compressed_responses'],
            'compression_saved': f"{self.stats['compression_saved_bytes'] / 1024:.1f} KB",
            'compression_ratio': compression_ratio,
            'streamed': self.stats['streamed_responses'],
            'websockets': self.stats['websocket_connections'],
            'deduplicated': self.stats['deduplicated_requests'],
            'cache': cache_stats
        }


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

            # Обновляем URL в ContentRewriter
            self.proxy.content_rewriter.set_urls(self.remote_url, self.proxy.local_url)

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
            status['proxy_stats'] = self.proxy.get_full_stats()

        return status

    def get_proxy_stats(self):
        """Получить детальную статистику прокси"""
        if self.proxy and self.is_running:
            return self.proxy.get_full_stats()
        return None

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