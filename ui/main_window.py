# ui/main_window.py - SECURE VERSION (Adapted for PySide6)

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QGroupBox, QFormLayout, QMessageBox
)
from PySide6.QtCore import Qt
import logging

logger = logging.getLogger(__name__)


class MainWindow(QWidget):
    """Главное окно приложения (упрощенное и безопасное)"""

    def __init__(self, proxy_manager):
        super().__init__()
        self.proxy_manager = proxy_manager
        self.health_indicator = None  # Будет создан в _init_ui
        self._init_ui()

    def _init_ui(self):
        """Инициализация UI"""
        self.setWindowTitle("Zenzefi Proxy Client")
        self.setMinimumWidth(500)
        try:
            from ui.icons import get_icon_manager
            icon_manager = get_icon_manager()
            self.setWindowIcon(icon_manager.get_icon("window_img.png"))
        except Exception as e:
            logger.warning(f"Не удалось загрузить иконку окна: {e}")

        # Восстанавливаем размеры и позицию окна из конфига
        self._restore_window_geometry()

        layout = QVBoxLayout()

        # ========== СЕКЦИЯ 1: Configuration ==========
        config_group = QGroupBox("Proxy Configuration")
        config_layout = QFormLayout()

        # Backend URL - восстанавливаем из конфига
        from core.config_manager import get_config
        config = get_config()
        saved_backend_url = config.get('proxy.backend_url', 'http://localhost:8000')

        self.backend_url_input = QLineEdit(saved_backend_url)
        self.backend_url_input.setPlaceholderText("Backend server URL (e.g., http://localhost:8000)")
        self.backend_url_input.textChanged.connect(self._on_backend_url_changed)  # Автосохранение
        config_layout.addRow("Backend Server:", self.backend_url_input)

        # Access Token (НЕ сохраняется, password mode)
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input.setPlaceholderText("Enter access token (not saved)")
        config_layout.addRow("Access Token:", self.token_input)

        # Предупреждение о безопасности
        # warning_label = QLabel("⚠️  Token is NOT saved for security (enter each time)")
        # warning_label.setObjectName("warningLabel")  # Используем object name для стилизации
        # config_layout.addRow("", warning_label)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # ========== СЕКЦИЯ 2: Status ==========
        status_group = QGroupBox("Status")
        status_layout = QFormLayout()

        # Health Indicator - Backend server status
        # Устанавливаем backend_url в ProxyManager перед созданием HealthIndicator
        if saved_backend_url:
            self.proxy_manager.backend_url = saved_backend_url

        from ui.health_indicator import HealthIndicator
        self.health_indicator = HealthIndicator(self.proxy_manager)
        status_layout.addRow("Backend Health:", self.health_indicator)

        self.status_label = QLabel("● Stopped")  # Используем Unicode символ ● (U+25CF)
        self.status_label.setObjectName("statusLabel")  # Используем object name для стилизации
        status_layout.addRow("Proxy Status:", self.status_label)

        # Token expiration time
        self.token_expiration_label = QLabel("—")  # Em dash (U+2014) для "не доступно"
        self.token_expiration_label.setObjectName("tokenExpirationLabel")
        self.token_expiration_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        status_layout.addRow("Token Expires:", self.token_expiration_label)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # ========== СЕКЦИЯ 3: Controls ==========
        controls_layout = QHBoxLayout()

        self.start_btn = QPushButton("Start Proxy")
        self.start_btn.setMinimumHeight(40)
        self.start_btn.clicked.connect(self.on_start_proxy)
        controls_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop Proxy")
        self.stop_btn.setMinimumHeight(40)
        self.stop_btn.clicked.connect(self.on_stop_proxy)
        self.stop_btn.setEnabled(False)
        controls_layout.addWidget(self.stop_btn)

        layout.addLayout(controls_layout)

        # Spacer
        layout.addStretch()

        self.setLayout(layout)

    def on_start_proxy(self):
        """Запуск прокси с валидацией и аутентификацией"""

        # Валидация inputs
        backend_url = self.backend_url_input.text().strip()
        token = self.token_input.text().strip()

        if not backend_url:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Backend URL is required.\n\nPlease enter the URL where your FastAPI backend is running."
            )
            self.backend_url_input.setFocus()
            return

        if not token:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Access Token is required.\n\nPlease enter your access token from /api/v1/tokens/purchase"
            )
            self.token_input.setFocus()
            return

        # Валидация URL формата
        if not backend_url.startswith(('http://', 'https://')):
            QMessageBox.warning(
                self,
                "Validation Error",
                "Backend URL must start with http:// or https://\n\nExample: http://localhost:8000"
            )
            self.backend_url_input.setFocus()
            return

        # Запуск прокси
        try:
            logger.info(f"Starting proxy with backend: {backend_url}")

            success = self.proxy_manager.start(
                backend_url=backend_url,
                token=token
            )

            if success:
                # Обновляем UI
                self.status_label.setText("● Running & Authenticated")  # Используем Unicode символ ● (U+25CF)
                self.status_label.setProperty("status", "running")  # Используем property для стилизации
                self.status_label.style().unpolish(self.status_label)
                self.status_label.style().polish(self.status_label)

                # Обновляем время истечения токена
                self._update_token_expiration()

                self.start_btn.setEnabled(False)
                self.stop_btn.setEnabled(True)
                self.backend_url_input.setEnabled(False)
                self.token_input.setEnabled(False)

                logger.info("✅ Proxy started and authenticated successfully")
            else:
                # Получаем детали ошибки из ProxyManager
                error_type = self.proxy_manager.last_error_type
                error_details = self.proxy_manager.last_error_details

                # Формируем сообщение об ошибке в зависимости от типа
                if error_type == 'backend':
                    error_title = "Backend Connection Error"
                    error_message = (
                        f"<b>Cannot connect to backend server</b><br><br>"
                        f"Backend URL: {backend_url}<br><br>"
                        f"<b>Solutions:</b><br>"
                        f"• Make sure backend server is running<br>"
                        f"• Check that backend URL is correct<br>"
                        f"• Verify firewall/antivirus is not blocking connection"
                    )
                elif error_type == 'token':
                    error_title = "Invalid Access Token"
                    error_message = (
                        f"<b>Access token is invalid or expired</b><br><br>"
                        f"<b>Solutions:</b><br>"
                        f"• Verify you entered the correct token<br>"
                        f"• Purchase a new token from /api/v1/tokens/purchase<br>"
                        f"• Check that token hasn't expired"
                    )
                elif error_type == 'port':
                    error_title = "Port Already in Use"
                    error_message = (
                        f"<b>Port 61000 is already in use</b><br><br>"
                        f"{error_details or 'Port is occupied by another process'}<br><br>"
                        f"<b>Solutions:</b><br>"
                        f"• Run this program as Administrator to automatically free the port<br>"
                        f"• Manually close the application using port 61000<br>"
                        f"• Restart your computer"
                    )
                else:
                    error_title = "Start Failed"
                    error_message = (
                        f"<b>Failed to start proxy</b><br><br>"
                        f"{error_details or 'Unknown error occurred'}<br><br>"
                        f"Check logs for more details"
                    )

                QMessageBox.critical(self, error_title, error_message)
                logger.error(f"❌ Failed to start proxy: {error_type} - {error_details}")

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"<b>Unexpected error starting proxy:</b><br><br>{str(e)}"
            )
            logger.exception("❌ Exception starting proxy")

    def on_stop_proxy(self):
        """Остановка прокси"""
        try:
            logger.info("Stopping proxy...")

            self.proxy_manager.stop()

            # Обновляем UI
            self.status_label.setText("● Stopped")  # Используем Unicode символ ● (U+25CF)
            self.status_label.setProperty("status", "stopped")  # Используем property для стилизации
            self.status_label.style().unpolish(self.status_label)
            self.status_label.style().polish(self.status_label)

            # Очищаем время истечения токена
            self.token_expiration_label.setText("—")

            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.backend_url_input.setEnabled(True)
            self.token_input.setEnabled(True)

            # Очищаем токен для безопасности
            self.token_input.clear()

            logger.info("✅ Proxy stopped successfully")

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"<b>Error stopping proxy:</b><br><br>{str(e)}"
            )
            logger.exception("❌ Exception stopping proxy")

    def _restore_window_geometry(self):
        """Восстанавливает размеры и позицию окна из конфига"""
        from core.config_manager import get_config
        config = get_config()

        width = config.get('ui.window_width', 800)
        height = config.get('ui.window_height', 600)
        x = config.get('ui.window_x')
        y = config.get('ui.window_y')

        self.resize(width, height)

        # Если позиция сохранена, восстанавливаем её
        if x is not None and y is not None:
            self.move(x, y)
        # Иначе центрируем окно
        else:
            from PySide6.QtWidgets import QApplication
            screen = QApplication.primaryScreen().geometry()
            x = (screen.width() - width) // 2
            y = (screen.height() - height) // 2
            self.move(x, y)

        logger.info(f"Восстановлена геометрия окна: {width}x{height} at ({x}, {y})")

    def _save_window_geometry(self):
        """Сохраняет текущие размеры и позицию окна в конфиг"""
        from core.config_manager import get_config
        config = get_config()

        geometry = self.geometry()
        config.set('ui.window_width', geometry.width())
        config.set('ui.window_height', geometry.height())
        config.set('ui.window_x', geometry.x())
        config.set('ui.window_y', geometry.y())
        config.save()

        logger.info(f"Сохранена геометрия окна: {geometry.width()}x{geometry.height()} at ({geometry.x()}, {geometry.y()})")

    def _on_backend_url_changed(self, text):
        """Автосохранение backend URL при изменении и проверка health"""
        # Сохраняем только если URL валиден (не пустой)
        if text.strip():
            from core.config_manager import get_config
            config = get_config()
            config.set('proxy.backend_url', text.strip(), save=True)
            logger.debug(f"Backend URL сохранён: {text.strip()}")

            # Обновляем backend URL в health indicator и запускаем проверку
            if self.health_indicator:
                self.health_indicator.update_backend_url(text.strip())

    def _update_token_expiration(self):
        """Обновляет отображение времени истечения токена"""
        if not self.proxy_manager.token_expires_at:
            self.token_expiration_label.setText("—")
            return

        try:
            from datetime import datetime, timezone

            # Парсим ISO 8601 строку из бекенда
            expires_at_str = self.proxy_manager.token_expires_at

            # Backend возвращает UTC время в формате ISO 8601
            # Например: "2025-11-06T18:30:00.123456" или "2025-11-06T18:30:00"
            # Может быть с/без 'Z' на конце, с/без микросекунд

            # Убираем 'Z' если есть и парсим
            expires_at_str_clean = expires_at_str.replace('Z', '')
            expires_at_naive = datetime.fromisoformat(expires_at_str_clean)

            # ВСЕГДА добавляем timezone=UTC (backend всегда возвращает UTC время)
            expires_at_utc = expires_at_naive.replace(tzinfo=timezone.utc)

            # Конвертируем из UTC в локальное время пользователя
            expires_at_local = expires_at_utc.astimezone()

            # Форматируем для отображения (локальное время)
            formatted = expires_at_local.strftime("%d.%m.%Y %H:%M:%S")

            self.token_expiration_label.setText(formatted)
            logger.debug(f"Token expiration updated: {formatted} (local time, UTC: {expires_at_utc.strftime('%H:%M:%S')})")

        except Exception as e:
            logger.error(f"Failed to parse token expiration: {e}")
            self.token_expiration_label.setText("Invalid format")

    def apply_theme(self):
        """Применяет текущую тему к главному окну"""
        from ui.theme_manager import get_theme_manager
        theme_manager = get_theme_manager()
        stylesheet = theme_manager.get_stylesheet()
        self.setStyleSheet(stylesheet)
        logger.info(f"Применена тема: {theme_manager.current_theme}")

    def closeEvent(self, event):
        """Обработка закрытия окна"""
        # Всегда сохраняем геометрию окна при закрытии
        self._save_window_geometry()

        if self.proxy_manager.is_running:
            reply = QMessageBox.question(
                self,
                "Exit Application",
                "<b>Proxy is currently running.</b><br><br>"
                "Stop proxy and exit application?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                logger.info("Closing application, stopping proxy...")
                self.proxy_manager.stop()
                # Health check таймер останавливается автоматически при выходе
                event.accept()
            else:
                event.ignore()
        else:
            # Просто закрываем окно (таймер продолжает работать в фоне)
            event.accept()
