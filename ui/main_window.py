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
        warning_label = QLabel("⚠️  Token is NOT saved for security (enter each time)")
        warning_label.setObjectName("warningLabel")  # Используем object name для стилизации
        config_layout.addRow("", warning_label)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # ========== СЕКЦИЯ 2: Status ==========
        status_group = QGroupBox("Status")
        status_layout = QFormLayout()

        self.status_label = QLabel("● Stopped")  # Используем Unicode символ ● (U+25CF)
        self.status_label.setObjectName("statusLabel")  # Используем object name для стилизации
        status_layout.addRow("Proxy Status:", self.status_label)

        self.local_url_label = QLabel("https://127.0.0.1:61000")
        self.local_url_label.setObjectName("localUrlLabel")  # Используем object name для стилизации
        self.local_url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        status_layout.addRow("Local Address:", self.local_url_label)

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

        # ========== СЕКЦИЯ 4: Instructions ==========
        instructions = QLabel(
            "<b>Instructions:</b><br>"
            "1. Enter Backend URL (where FastAPI server runs)<br>"
            "2. Enter Access Token (from <i>/api/v1/tokens/purchase</i>)<br>"
            "3. Click <b>Start Proxy</b><br>"
            "4. Configure your application to use proxy: <code>127.0.0.1:61000</code><br>"
            "5. Applications will authenticate automatically"
        )
        instructions.setObjectName("instructionsLabel")  # Используем object name для стилизации
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

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
                self.start_btn.setEnabled(False)
                self.stop_btn.setEnabled(True)
                self.backend_url_input.setEnabled(False)
                self.token_input.setEnabled(False)

                # Показываем успешное сообщение
                QMessageBox.information(
                    self,
                    "Success",
                    f"<b>Proxy Started Successfully!</b><br><br>"
                    f"<b>Local Proxy:</b> https://127.0.0.1:61000<br>"
                    f"<b>Backend:</b> {backend_url}<br><br>"
                    f"Open your browser and navigate to:<br>"
                    f"<b>https://127.0.0.1:61000/</b><br><br>"
                    f"You may see a certificate warning - click 'Advanced' → 'Proceed'.<br>"
                    f"Cookie will be automatically set on first request!"
                )

                logger.info("✅ Proxy started and authenticated successfully")
            else:
                QMessageBox.critical(
                    self,
                    "Start Failed",
                    "<b>Failed to start proxy.</b><br><br>"
                    "Possible reasons:<br>"
                    "• Backend server is not running<br>"
                    "• Invalid access token<br>"
                    "• Port 61000 is already in use<br><br>"
                    "Check the logs for more details."
                )
                logger.error("❌ Failed to start proxy")

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"<b>Unexpected error starting proxy:</b><br><br>{str(e)}"
            )
            logger.exception("❌ Exception starting proxy")

    def on_stop_proxy(self):
        """Остановка прокси с подтверждением"""

        reply = QMessageBox.question(
            self,
            "Stop Proxy",
            "<b>Stop proxy and logout from backend?</b><br><br>"
            "This will:<br>"
            "• Stop the local proxy server<br>"
            "• Logout from backend (clear session)<br>"
            "• Clear token from memory",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                logger.info("Stopping proxy...")

                self.proxy_manager.stop()

                # Обновляем UI
                self.status_label.setText("● Stopped")  # Используем Unicode символ ● (U+25CF)
                self.status_label.setProperty("status", "stopped")  # Используем property для стилизации
                self.status_label.style().unpolish(self.status_label)
                self.status_label.style().polish(self.status_label)
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
        """Автосохранение backend URL при изменении"""
        # Сохраняем только если URL валиден (не пустой)
        if text.strip():
            from core.config_manager import get_config
            config = get_config()
            config.set('proxy.backend_url', text.strip(), save=True)
            logger.debug(f"Backend URL сохранён: {text.strip()}")

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
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
