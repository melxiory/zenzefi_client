# proxy_manager.py
import asyncio
import ssl
import logging
import time
import threading
import sys
from aiohttp import web, ClientSession, TCPConnector, ClientTimeout, ClientConnectorError, ServerTimeoutError
from utils.process_manager import get_process_manager
from utils.port_utils import check_port_availability, get_process_using_port
from core.config_manager import get_app_data_dir

logger = logging.getLogger(__name__)


class ZenzefiProxy:
    def __init__(self, backend_url, proxy_manager=None):
        """
        Args:
            backend_url: URL backend сервера для проксирования
            proxy_manager: Ссылка на ProxyManager (для доступа к токену)
        """
        self.backend_url = backend_url
        self.proxy_manager = proxy_manager  # Для доступа к current_token

        # Connection pool для переиспользования соединений
        self.connector = None
        self.session = None

        # Семафор для ограничения одновременных соединений к backend
        self.connection_semaphore = asyncio.Semaphore(50)

        # Статистика производительности
        self.stats = {
            'total_requests': 0,
            'total_responses': 0,
            'active_connections': 0,
            'errors': 0
        }

    async def initialize(self):
        """Инициализация connection pool для backend"""
        if self.connector is None:
            # Настройка connection pooling для backend (127.0.0.1:8000)
            self.connector = TCPConnector(
                ssl=False,  # Backend на localhost без SSL
                limit=100,  # Максимум 100 одновременных соединений
                limit_per_host=50,  # Максимум 50 на хост (backend)
                ttl_dns_cache=300,  # DNS кэш на 5 минут
                keepalive_timeout=60,  # Keep-alive 60 секунд
                force_close=False,  # Переиспользуем соединения
                enable_cleanup_closed=True  # Автоочистка закрытых соединений
            )

        if self.session is None:
            self.session = ClientSession(
                connector=self.connector,
                timeout=ClientTimeout(total=90, connect=10)  # 90s total, 10s connect
            )

    async def cleanup(self):
        """Очистка ресурсов"""
        if self.session:
            await self.session.close()
            self.session = None
        if self.connector:
            await self.connector.close()
            self.connector = None

    async def handle_http(self, request):
        """Обработка HTTP/HTTPS запросов через backend proxy"""
        self.stats['total_requests'] += 1
        self.stats['active_connections'] += 1

        try:
            # ВСЕ запросы идут через backend с X-Access-Token header
            return await self._proxy_to_backend(request)

        except Exception as e:
            self.stats['errors'] += 1
            self.stats['active_connections'] -= 1
            logger.error(f"❌ HTTP Error: {e}")
            return web.Response(text=f"Proxy error: {str(e)}", status=500)

    async def _proxy_to_backend(self, request):
        """
        Проксирует ВСЕ запросы на backend с X-Access-Token header

        Backend отвечает за:
        - Валидацию X-Access-Token
        - Проксирование на Zenzefi Server
        """
        backend_url = self.backend_url

        # Используем семафор для ограничения одновременных соединений
        async with self.connection_semaphore:
            try:
                # Читаем тело запроса
                body = await request.read()

                # Подготовка заголовков
                headers = {}
                for key, value in request.headers.items():
                    key_lower = key.lower()
                    if key_lower not in ['host', 'connection', 'content-length', 'transfer-encoding']:
                        headers[key] = value

                # Добавляем X-Access-Token из ProxyManager
                if self.proxy_manager and self.proxy_manager.current_token:
                    headers['X-Access-Token'] = self.proxy_manager.current_token
                    logger.debug(
                        f"🔑 Added X-Access-Token for request\n"
                        f"   Path: {request.path}\n"
                        f"   Method: {request.method}"
                    )
                else:
                    logger.warning(
                        f"⚠️ No token available for request!\n"
                        f"   Path: {request.path}\n"
                        f"   → Request will likely fail with 401"
                    )

                # Добавляем X-Device-ID header (для device conflict detection)
                if self.proxy_manager and self.proxy_manager.device_id:
                    headers['X-Device-ID'] = self.proxy_manager.device_id
                    logger.debug(f"🔑 Added X-Device-ID: {self.proxy_manager.device_id}")
                else:
                    # КРИТИЧЕСКАЯ ОШИБКА: Без device_id запрос не должен отправляться
                    logger.error(
                        f"❌ CRITICAL: No device_id available - aborting request\n"
                        f"   Path: {request.path}\n"
                        f"   This should never happen - device_id must be generated on proxy start"
                    )
                    # Возвращаем 500 ошибку клиенту
                    return web.Response(
                        status=500,
                        text="Internal error: Device ID not initialized. Please restart the application.",
                        content_type="text/plain"
                    )

                # Формируем URL на backend с префиксом /api/v1/proxy
                upstream_url = f"{backend_url.rstrip('/')}/api/v1/proxy{request.path_qs}"
                logger.debug(f"🔐 Proxying to backend: {upstream_url}")

                # Используем переиспользуемую сессию
                await self.initialize()

                async with self.session.request(
                    method=request.method,
                    url=upstream_url,
                    headers=headers,
                    data=body,
                    allow_redirects=False
                ) as upstream_response:

                    # Читаем ответ
                    content = await upstream_response.read()

                    # Копируем заголовки ответа
                    response_headers = {}

                    for key, value in upstream_response.headers.items():
                        key_lower = key.lower()

                        # Пропускаем некоторые заголовки
                        if key_lower in ['content-encoding', 'transfer-encoding', 'connection', 'keep-alive']:
                            continue

                        response_headers[key] = value

                    # Добавляем CORS headers для локального proxy
                    response_headers.update({
                        'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Credentials': 'true',
                        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                        'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With, X-Access-Token'
                    })

                    # Убираем charset из Content-Type если он есть (aiohttp не принимает)
                    if 'Content-Type' in response_headers or 'content-type' in response_headers:
                        content_type_key = 'Content-Type' if 'Content-Type' in response_headers else 'content-type'
                        content_type_value = response_headers[content_type_key]
                        if '; charset=' in content_type_value:
                            response_headers[content_type_key] = content_type_value.split('; charset=')[0]

                    self.stats['total_responses'] += 1
                    self.stats['active_connections'] -= 1

                    logger.debug(f"Backend response: {upstream_response.status}")

                    # Создаем response
                    response = web.Response(
                        body=content,
                        status=upstream_response.status,
                        headers=response_headers
                    )

                    return response

            except ClientConnectorError as e:
                self.stats['errors'] += 1
                self.stats['active_connections'] -= 1
                logger.error(f"❌ Backend недоступен: {e}")

                return web.Response(
                    text=(
                        "❌ Backend сервер недоступен!\n\n"
                        "Пожалуйста, запустите backend сервер:\n"
                        "poetry run uvicorn app.main:app --reload\n\n"
                        f"Детали: {str(e)}"
                    ),
                    status=502,
                    content_type="text/plain; charset=utf-8"
                )

            except ServerTimeoutError as e:
                self.stats['errors'] += 1
                self.stats['active_connections'] -= 1
                logger.error(f"❌ Таймаут соединения с backend: {e}")

                return web.Response(
                    text=(
                        "❌ Таймаут соединения с backend сервером!\n\n"
                        "Backend слишком долго отвечает. Проверьте:\n"
                        "- Backend сервер запущен и отвечает\n"
                        "- Нет проблем с сетью\n\n"
                        f"Детали: {str(e)}"
                    ),
                    status=504,
                    content_type="text/plain; charset=utf-8"
                )

            except Exception as e:
                self.stats['errors'] += 1
                self.stats['active_connections'] -= 1
                logger.error(f"❌ Ошибка проксирования на backend: {e}", exc_info=True)

                return web.Response(
                    text=f"❌ Ошибка проксирования:\n\n{str(e)}",
                    status=502,
                    content_type="text/plain; charset=utf-8"
                )

    async def router(self, request):
        """Маршрутизация всех запросов через backend proxy"""
        return await self.handle_http(request)

    def get_full_stats(self):
        """Получить полную статистику прокси"""
        return {
            'requests': self.stats['total_requests'],
            'responses': self.stats['total_responses'],
            'active': self.stats['active_connections'],
            'errors': self.stats['errors']
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

        # Security: tokens and device ID in memory only
        self.current_token = None    # Access token (RAM only)
        self.backend_url = None       # Backend URL (RAM only)
        self.token_expires_at = None  # Token expiration time (ISO 8601 string, RAM only)
        self.device_id = None          # Device ID (hardware fingerprint, RAM only)

        # Error tracking
        self.last_error_type = None  # Тип последней ошибки: 'backend', 'token', 'port', 'unknown'
        self.last_error_details = None  # Детали последней ошибки

    def start(self, backend_url, token=None):
        """
        Запуск прокси сервера с токеном для backend

        Args:
            backend_url: URL backend сервера
            token: Access token для аутентификации (НЕ сохраняется на диск)

        Returns:
            bool: True если успешно запущен
        """
        if self.is_running:
            logger.warning("⚠️ Прокси уже запущен")
            return False

        if not token:
            logger.error("❌ Token is required to start proxy")
            return False

        if not backend_url:
            logger.error("❌ Backend URL is required")
            return False

        # Generate Device ID (CRITICAL - before saving token)
        try:
            from core.device_id import generate_device_id
            self.device_id = generate_device_id()
        except Exception as e:
            # СТРОГИЙ РЕЖИМ: Без device_id не запускаем proxy
            self.last_error_type = "device_id_generation_failed"
            self.last_error_details = str(e)
            logger.error(
                f"❌ Failed to generate Device ID - proxy start aborted\n"
                f"   Error: {e}\n"
                f"   Proxy will NOT start without valid Device ID"
            )
            return False

        # Сохраняем в память (НЕ на диск!)
        self.current_token = token
        self.backend_url = backend_url

        logger.debug(
            f"🔐 Security context prepared:\n"
            f"   Token length: {len(token)} chars\n"
            f"   Backend URL: {backend_url}\n"
            f"   Device ID: {self.device_id}"
        )

        # Проверка порта
        local_port = 61000  # Фиксированный порт
        self.local_port = local_port

        port_available, port_message = check_port_availability(local_port)
        if not port_available:
            logger.warning(f"⚠️ {port_message}")

            process_info = get_process_using_port(local_port)
            if process_info:
                logger.info(
                    f"📌 Процесс на порту {local_port}:\n"
                    f"   PID: {process_info.get('pid')}\n"
                    f"   Name: {process_info.get('name')}\n"
                    f"   User: {process_info.get('username', 'N/A')}"
                )

                # Пытаемся убить процесс
                pm = get_process_manager()
                if pm.kill_process_on_port(local_port):
                    logger.info(f"✅ Процесс на порту {local_port} завершен, повторная проверка порта...")

                    # Даем небольшую задержку для освобождения порта
                    time.sleep(0.5)

                    # Проверяем, что порт действительно освободился
                    port_available, port_message = check_port_availability(local_port)
                    if not port_available:
                        logger.error(f"❌ Порт {local_port} все еще занят после завершения процесса")
                        self.last_error_type = 'port'
                        self.last_error_details = f"Не удалось освободить порт {local_port}: {port_message}"
                        return False

                    logger.info(f"✅ Порт {local_port} успешно освобожден")
                else:
                    logger.error(f"❌ Не удалось завершить процесс на порту {local_port}")
                    self.last_error_type = 'port'
                    self.last_error_details = f"Порт {local_port} занят процессом {process_info.get('name')} (PID: {process_info.get('pid')}). Требуются права администратора для завершения процесса."
                    return False
            else:
                logger.error(f"❌ Порт {local_port} занят неизвестным процессом")
                self.last_error_type = 'port'
                self.last_error_details = f"Порт {local_port} занят неизвестным процессом. Не удалось определить процесс."
                return False

        try:
            # Создаём event loop для потока
            self.loop = asyncio.new_event_loop()

            # Запускаем сервер в отдельном потоке
            self.thread = threading.Thread(
                target=self._run_server,
                daemon=True
            )
            self.thread.start()

            # Ждём запуска (максимум 5 секунд)
            for _ in range(50):
                if self.is_running:
                    break
                time.sleep(0.1)

            if not self.is_running:
                logger.error("❌ Прокси не запустился за отведенное время")
                return False

            logger.info(f"✅ Proxy server started on https://127.0.0.1:{local_port}")

            # Проверяем статус токена на backend
            logger.info("🔐 Checking token status with backend...")
            token_valid = self._check_token_status()

            if not token_valid:
                logger.warning("⚠️ Token validation failed, but proxy is running")
                # Не останавливаем прокси - пользователь может исправить токен

            return True

        except Exception as e:
            logger.error(f"❌ Failed to start proxy: {e}")
            self.stop()
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

            # Создаем прокси с передачей backend_url и ссылки на self
            self.proxy = ZenzefiProxy(
                backend_url=self.backend_url,
                proxy_manager=self  # Передаем ссылку для доступа к токену
            )

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

    def _check_token_status(self):
        """
        Проверяет статус токена на backend через GET /api/v1/proxy/status

        Returns:
            bool: True если токен валиден
        """
        if not self.current_token or not self.backend_url:
            logger.error("❌ No token or backend URL for status check")
            return False

        try:
            import requests

            status_url = f"{self.backend_url.rstrip('/')}/api/v1/proxy/status"

            logger.info(f"🔐 Checking token status: {status_url}")
            logger.debug(f"   Token length: {len(self.current_token)} chars")

            # GET запрос с X-Access-Token header
            response = requests.get(
                status_url,
                headers={"X-Access-Token": self.current_token},
                timeout=10,
                proxies={"http": None, "https": None}  # Отключаем системный прокси для localhost
            )

            if response.status_code == 200:
                data = response.json()

                # Сохраняем время истечения токена
                self.token_expires_at = data.get('expires_at')

                logger.info(
                    f"✅ Token is valid!\n"
                    f"   User ID: {data.get('user_id')}\n"
                    f"   Token ID: {data.get('token_id')}\n"
                    f"   Activated: {data.get('is_activated')}\n"
                    f"   Expires: {data.get('expires_at')}\n"
                    f"   Status: {data.get('status')}"
                )

                return True
            else:
                logger.error(
                    f"❌ Token validation failed!\n"
                    f"   Status: {response.status_code}\n"
                    f"   Response: {response.text}"
                )
                self.last_error_type = 'token'
                self.last_error_details = f"Invalid access token (HTTP {response.status_code})"
                return False

        except requests.ConnectionError as e:
            logger.error(
                f"❌ Cannot connect to backend server!\n"
                f"   URL: {status_url}\n"
                f"   Error: {e}\n"
                f"   → Is backend running?"
            )
            self.last_error_type = 'backend'
            self.last_error_details = "Cannot connect to backend server"
            return False
        except requests.Timeout:
            logger.error(f"❌ Status check request timed out (>10s)")
            self.last_error_type = 'backend'
            self.last_error_details = "Backend connection timeout"
            return False
        except requests.RequestException as e:
            logger.error(f"❌ Status check request error: {e}")
            self.last_error_type = 'backend'
            self.last_error_details = str(e)
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected status check error: {e}")
            logger.exception("Full traceback:")
            self.last_error_type = 'unknown'
            self.last_error_details = str(e)
            return False

    def refresh_token_status(self):
        """
        Публичный метод для обновления статуса токена (используется из UI)

        Обновляет self.token_expires_at если токен активирован.
        Можно вызывать периодически для обновления UI после активации токена.

        Returns:
            bool: True если токен валиден и статус обновлен
        """
        if not self.is_running:
            logger.debug("Proxy not running, skipping token status refresh")
            return False

        return self._check_token_status()

    def stop(self):
        """Остановка прокси сервера"""
        if not self.is_running:
            logger.warning("⚠️ Прокси не запущен")
            return

        try:
            logger.info("🛑 Stopping proxy...")

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

            # ОЧИСТКА ДАННЫХ ИЗ ПАМЯТИ (критично для безопасности)
            self.current_token = None
            self.token_expires_at = None
            self.device_id = None
            # backend_url НЕ очищаем - нужен для health monitoring

            logger.info("🧹 Security cleanup: token, device_id, and expiration cleared from memory (backend_url preserved for health checks)")

            # Логируем статистику
            if self.proxy:
                stats = self.proxy.get_full_stats()
                logger.info(
                    f"📊 Session statistics:\n"
                    f"   Total requests: {stats.get('requests', 0)}\n"
                    f"   Total responses: {stats.get('responses', 0)}\n"
                    f"   Errors: {stats.get('errors', 0)}\n"
                    f"   Active connections: {stats.get('active', 0)}"
                )

            logger.info("✅ Proxy stopped and cleaned up successfully")

        except Exception as e:
            logger.error(f"❌ Error stopping proxy: {e}")
            logger.exception("Full traceback:")

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

        # Добавляем статистику прокси
        if self.proxy and self.is_running:
            status['proxy_stats'] = self.proxy.get_full_stats()

        return status

    def get_proxy_stats(self):
        """Получить детальную статистику прокси"""
        if self.proxy and self.is_running:
            return self.proxy.get_full_stats()
        return None

    async def check_backend_health(self):
        """
        Проверяет состояние backend сервера через /health endpoint

        Returns:
            dict: {
                'status': 'healthy'|'degraded'|'unhealthy'|'unreachable',
                'timestamp': str or None,
                'error': str or None
            }
        """
        if not self.backend_url:
            return {
                'status': 'unreachable',
                'timestamp': None,
                'error': 'Backend URL not configured'
            }

        health_url = f"{self.backend_url}/health"

        try:
            # Используем отдельную сессию для health check
            async with ClientSession(timeout=ClientTimeout(total=5)) as session:
                async with session.get(health_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            'status': data.get('status', 'unknown'),
                            'timestamp': data.get('timestamp'),
                            'error': None
                        }
                    else:
                        return {
                            'status': 'unreachable',
                            'timestamp': None,
                            'error': f'HTTP {response.status}'
                        }
        except (ClientConnectorError, asyncio.TimeoutError) as e:
            logger.debug(f"Backend health check failed: {e}")
            return {
                'status': 'unreachable',
                'timestamp': None,
                'error': 'Connection failed'
            }
        except Exception as e:
            logger.error(f"Unexpected error in health check: {e}")
            return {
                'status': 'unreachable',
                'timestamp': None,
                'error': str(e)
            }

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
