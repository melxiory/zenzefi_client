# ui/health_indicator.py

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer, Signal
import asyncio
import logging

logger = logging.getLogger(__name__)


class HealthIndicator(QWidget):
    """
    Виджет индикатора состояния backend сервера

    Отображает текущий health status из /health endpoint:
    - healthy (зеленый) - все сервисы работают
    - degraded (желтый) - некоторые сервисы недоступны (не критично)
    - unhealthy (красный) - критические сервисы недоступны
    - unreachable (серый) - backend сервер недоступен
    """

    # Сигнал для обновления из async контекста
    health_updated = Signal(dict)

    def __init__(self, proxy_manager, parent=None):
        super().__init__(parent)
        self.proxy_manager = proxy_manager
        self._init_ui()
        self._setup_timer()

        # Подключаем сигнал для thread-safe обновления
        self.health_updated.connect(self._update_ui)

        # Проверяем сразу при запуске, если backend URL уже настроен
        if self.proxy_manager.backend_url:
            logger.info(f"Initial health check for configured backend: {self.proxy_manager.backend_url}")
            self._check_health()

    def _init_ui(self):
        """Инициализация UI"""
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Индикатор (цветная точка)
        self.indicator_label = QLabel("●")  # Unicode U+25CF
        self.indicator_label.setObjectName("healthIndicator")

        # Текстовый статус
        self.status_label = QLabel("Checking...")
        self.status_label.setObjectName("healthStatusText")

        layout.addWidget(self.indicator_label)
        layout.addWidget(self.status_label)
        layout.addStretch()

        self.setLayout(layout)

        # Начальное состояние (серый, не проверен)
        self._update_style('unreachable', None)

    def _setup_timer(self):
        """Настройка таймера для периодической проверки каждые 60 секунд"""
        self.health_timer = QTimer(self)
        self.health_timer.timeout.connect(self._check_health)
        self.health_timer.start(60000)  # 60 секунд
        logger.info("Health check timer started (60s interval)")

    def _check_health(self):
        """Проверяет health backend сервера (асинхронно)"""
        # Запускаем async проверку в event loop proxy manager'а
        if self.proxy_manager.loop and self.proxy_manager.loop.is_running():
            # Proxy запущен, используем его event loop
            future = asyncio.run_coroutine_threadsafe(
                self.proxy_manager.check_backend_health(),
                self.proxy_manager.loop
            )
            # Обрабатываем результат в отдельном потоке
            future.add_done_callback(lambda f: self._on_health_checked(f.result()))
        else:
            # Proxy не запущен, создаем временный event loop
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(self.proxy_manager.check_backend_health())
                loop.close()
                self._on_health_checked(result)
            except Exception as e:
                logger.error(f"Failed to check health: {e}")
                self._on_health_checked({
                    'status': 'unreachable',
                    'timestamp': None,
                    'error': str(e)
                })

    def _on_health_checked(self, health_data):
        """Callback после проверки health (thread-safe)"""
        # Используем сигнал для thread-safe обновления UI
        self.health_updated.emit(health_data)

    def _update_ui(self, health_data):
        """Обновляет UI на основе health данных (вызывается в GUI потоке)"""
        status = health_data.get('status', 'unreachable')
        timestamp = health_data.get('timestamp')
        error = health_data.get('error')

        self._update_style(status, error)
        logger.debug(f"Health status updated: {status} (timestamp: {timestamp})")

    def _update_style(self, status, error=None):
        """Обновляет визуальное отображение на основе статуса"""
        # Цвета и тексты для разных статусов
        STATUS_CONFIG = {
            'healthy': {
                'color': '#00C853',  # Зеленый
                'text': 'Backend: Healthy',
                'tooltip': 'All backend services are operational'
            },
            'degraded': {
                'color': '#FFD600',  # Желтый
                'text': 'Backend: Degraded',
                'tooltip': 'Some non-critical services are down'
            },
            'unhealthy': {
                'color': '#D50000',  # Красный
                'text': 'Backend: Unhealthy',
                'tooltip': 'Critical backend services are down'
            },
            'unreachable': {
                'color': '#757575',  # Серый
                'text': 'Backend: Unreachable',
                'tooltip': 'Cannot connect to backend server'
            }
        }

        config = STATUS_CONFIG.get(status, STATUS_CONFIG['unreachable'])

        # Обновляем индикатор
        self.indicator_label.setStyleSheet(f"color: {config['color']}; font-size: 16px;")

        # Обновляем текст
        self.status_label.setText(config['text'])

        # Обновляем tooltip
        tooltip = config['tooltip']
        if error:
            tooltip += f"\n\nError: {error}"
        self.setToolTip(tooltip)

    def check_now(self):
        """
        Немедленная проверка health (публичный метод)

        Используется для:
        - Проверки при запуске приложения
        - Проверки после изменения backend URL
        """
        logger.info("Manual health check triggered")
        self._check_health()

    def update_backend_url(self, backend_url):
        """
        Обновляет backend URL и немедленно проверяет health

        Args:
            backend_url: Новый URL backend сервера
        """
        self.proxy_manager.backend_url = backend_url
        logger.info(f"Backend URL updated to: {backend_url}")
        self.check_now()

    def stop_timer(self):
        """Останавливает таймер проверки (для cleanup)"""
        if hasattr(self, 'health_timer') and self.health_timer.isActive():
            self.health_timer.stop()
            logger.info("Health check timer stopped")
