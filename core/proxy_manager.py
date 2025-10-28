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
    def __init__(self):
        self.upstream_url = "https://zenzefi.melxiory.ru"
        # Local URL БЕЗ префикса - чистый URL для браузера
        # Backend получит запросы с префиксом /api/v1/proxy (добавляется при проксировании)
        self.local_url = "https://127.0.0.1:61000"

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
                timeout=ClientTimeout(total=30, connect=5)
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
            # ВСЕ запросы идут через backend!
            # Backend отвечает за:
            # - Аутентификацию (включая показ auth страницы если нужно)
            # - Валидацию cookie
            # - Проксирование на Zenzefi
            # - Content rewriting
            return await self._proxy_to_backend(request)

        except Exception as e:
            self.stats['errors'] += 1
            self.stats['active_connections'] -= 1
            logger.error(f"❌ HTTP Error: {e}")
            return web.Response(text=f"Proxy error: {str(e)}", status=500)

    async def _proxy_to_backend(self, request):
        """
        Проксирует ВСЕ запросы на backend (127.0.0.1:8000)

        Backend отвечает за:
        - Валидацию cookie аутентификации
        - Проксирование на Zenzefi Server
        - Content rewriting
        """
        backend_url = "http://127.0.0.1:8000"

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

                # Передаем local_url в backend для правильного content rewriting
                # Backend должен переписывать URL на этот адрес (БЕЗ префикса /api/v1/proxy)
                headers['X-Local-Url'] = self.local_url

                # Копируем cookies от браузера
                cookies = {}
                for name, value in request.cookies.items():
                    cookies[name] = value
                    logger.debug(f"Forwarding cookie to backend: {name}={value[:20]}...")

                # Формируем URL на backend с префиксом /api/v1/proxy
                # Браузер видит чистый URL, но backend получает с префиксом
                upstream_url = f"{backend_url}/api/v1/proxy{request.path_qs}"
                logger.debug(f"🔐 Proxying to backend: {upstream_url}")

                # Используем переиспользуемую сессию
                await self.initialize()

                async with self.session.request(
                    method=request.method,
                    url=upstream_url,
                    headers=headers,
                    data=body,
                    cookies=cookies,
                    allow_redirects=False
                ) as upstream_response:

                    # Читаем ответ
                    content = await upstream_response.read()

                    # Копируем заголовки ответа
                    response_headers = {}
                    backend_cookies = []  # Собираем Set-Cookie заголовки от backend

                    for key, value in upstream_response.headers.items():
                        key_lower = key.lower()

                        # Пропускаем некоторые заголовки
                        if key_lower in ['content-encoding', 'transfer-encoding', 'connection', 'keep-alive']:
                            continue

                        # Специальная обработка Set-Cookie - НЕ копируем напрямую
                        if key_lower == 'set-cookie':
                            logger.info(f"Backend Set-Cookie: {value[:80]}...")
                            backend_cookies.append(value)
                            continue  # НЕ добавляем в response_headers

                        response_headers[key] = value

                    # Добавляем CORS headers для локального proxy
                    response_headers.update({
                        'Access-Control-Allow-Origin': self.local_url,
                        'Access-Control-Allow-Credentials': 'true',
                        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                        'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With'
                    })

                    self.stats['total_responses'] += 1
                    self.stats['active_connections'] -= 1

                    logger.debug(f"Backend response: {upstream_response.status}")

                    # Создаем response
                    response = web.Response(
                        body=content,
                        status=upstream_response.status,
                        headers=response_headers
                    )

                    # Переустанавливаем cookies от backend для локального прокси домена
                    for cookie_header in backend_cookies:
                        try:
                            # Парсим Set-Cookie заголовок от backend
                            # Формат: name=value; Max-Age=123; Path=/; HttpOnly; Secure; SameSite=lax
                            parts = cookie_header.split(';')
                            if not parts:
                                continue

                            # Первая часть - name=value
                            name_value = parts[0].strip()
                            if '=' not in name_value:
                                continue

                            cookie_name, cookie_value = name_value.split('=', 1)

                            # Парсим дополнительные атрибуты
                            max_age = None
                            path = '/'
                            httponly = False
                            secure = False
                            samesite = None

                            for part in parts[1:]:
                                part = part.strip().lower()
                                if part.startswith('max-age='):
                                    try:
                                        max_age = int(part.split('=', 1)[1])
                                    except:
                                        pass
                                elif part.startswith('path='):
                                    path = part.split('=', 1)[1]
                                elif part == 'httponly':
                                    httponly = True
                                elif part == 'secure':
                                    secure = True
                                elif part.startswith('samesite='):
                                    samesite = part.split('=', 1)[1]

                            # Устанавливаем cookie для локального прокси (127.0.0.1:61000)
                            # ВАЖНО: НЕ используем Secure для localhost (HTTPS на самоподписанном сертификате)
                            response.set_cookie(
                                name=cookie_name,
                                value=cookie_value,
                                max_age=max_age,
                                path=path,
                                httponly=httponly,
                                secure=False,  # Localhost с самоподписанным сертификатом
                                samesite=samesite if samesite else 'Lax'
                            )

                            logger.info(f"Cookie set for local proxy: {cookie_name}, max_age={max_age}, path={path}")

                        except Exception as e:
                            logger.error(f"Failed to parse Set-Cookie: {cookie_header[:50]}... Error: {e}")

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
        # Все запросы (HTTP/HTTPS) идут через handle_http → backend
        # Backend отвечает за валидацию, проксирование и content rewriting
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
            # Local URL БЕЗ префикса - для чистых URL в браузере
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

            # Логируем статистику перед остановкой
            if self.proxy:
                stats = self.proxy.get_full_stats()
                logger.info(f"📊 Статистика прокси: {stats}")

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

        # Добавляем статистику прокси
        if self.proxy and self.is_running:
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