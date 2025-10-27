# ui/main_window.py
import logging
import threading
from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                               QWidget, QPushButton, QTextEdit, QLineEdit, QLabel,
                               QGroupBox, QStatusBar, QMessageBox)
from PySide6.QtCore import QTimer, QThread, Signal, QObject
from PySide6.QtGui import QTextCursor, QFont

logger = logging.getLogger(__name__)


class LogEmitter(QObject):
    """Объект для эмитации сигналов логов"""
    log_signal = Signal(str)


class LogHandler(logging.Handler):
    """Кастомный обработчик логов для вывода в GUI с debouncing"""

    def __init__(self, log_emitter):
        super().__init__()
        self.log_emitter = log_emitter
        self.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.log_buffer = []
        self.buffer_lock = threading.Lock()
        self.flush_timer = None

    def emit(self, record):
        try:
            msg = self.format(record)
            with self.buffer_lock:
                self.log_buffer.append(msg)
                # Если таймер не запущен, запускаем его
                if self.flush_timer is None:
                    self.flush_timer = threading.Timer(0.2, self.flush_buffer)
                    self.flush_timer.start()
        except Exception as e:
            print(f"Ошибка в LogHandler: {e}")

    def flush_buffer(self):
        """Отправляет накопленные логи пакетом"""
        try:
            with self.buffer_lock:
                if self.log_buffer:
                    # Отправляем все накопленные сообщения одним пакетом
                    combined_msg = '\n'.join(self.log_buffer)
                    self.log_emitter.log_signal.emit(combined_msg)
                    self.log_buffer.clear()
                self.flush_timer = None
        except Exception as e:
            print(f"Ошибка при flush логов: {e}")


class ProxyManagerThread(QThread):
    """Поток для управления прокси"""
    log_signal = Signal(str)
    status_signal = Signal(dict)

    def __init__(self, proxy_manager):
        super().__init__()
        self.proxy_manager = proxy_manager
        self.action = None
        self.remote_url = ""

    def set_action(self, action, remote_url=None):
        self.action = action
        if remote_url:
            self.remote_url = remote_url

    def run(self):
        try:
            if self.action == "start":
                self.start_proxy()
            elif self.action == "stop":
                self.stop_proxy()
            elif self.action == "restart":
                self.restart_proxy()
        except Exception as e:
            self.log_signal.emit(f"❌ Ошибка в потоке: {e}")
            logger.error(f"Ошибка в ProxyManagerThread: {e}", exc_info=True)

    def start_proxy(self):
        try:
            success = self.proxy_manager.start(61000, self.remote_url)
            status = self.proxy_manager.get_status()
            self.status_signal.emit(status)
            if success:
                self.log_signal.emit("✅ Прокси успешно запущен")
            else:
                self.log_signal.emit("❌ Ошибка запуска прокси")
        except Exception as e:
            self.log_signal.emit(f"❌ Ошибка запуска прокси: {e}")
            logger.error(f"Ошибка запуска: {e}", exc_info=True)

    def stop_proxy(self):
        try:
            success = self.proxy_manager.stop()
            status = self.proxy_manager.get_status()
            self.status_signal.emit(status)
            if success:
                self.log_signal.emit("✅ Прокси успешно остановлен")
            else:
                self.log_signal.emit("❌ Ошибка остановки прокси")
        except Exception as e:
            self.log_signal.emit(f"❌ Ошибка остановки прокси: {e}")
            logger.error(f"Ошибка остановки: {e}", exc_info=True)

    def restart_proxy(self):
        try:
            self.stop_proxy()
            if self.remote_url:
                self.start_proxy()
        except Exception as e:
            self.log_signal.emit(f"❌ Ошибка перезапуска прокси: {e}")
            logger.error(f"Ошибка перезапуска: {e}", exc_info=True)


class MainWindow(QMainWindow):
    def __init__(self, proxy_manager):
        super().__init__()
        self.proxy_manager = proxy_manager
        self.proxy_thread = None
        self.current_status = {}

        self.setup_ui()

        # Загружаем конфиг
        from core.config_manager import get_config
        self.config = get_config()

        # Создаем эмиттер для логов
        self.log_emitter = LogEmitter()

        self.setup_logging()
        self.load_config()
        self.update_status()

        # Таймер для обновления статуса
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(5000)

        # Применяем тему ПОСЛЕ создания всех элементов (отложенная загрузка)
        QTimer.singleShot(0, self.apply_theme)

    def setup_ui(self):
        """Настройка пользовательского интерфейса"""
        self.setWindowTitle("Zenzefi Client")
        self.setGeometry(100, 100, 800, 600)

        # Устанавливаем иконку окна
        try:
            from ui.icons import get_icon_manager
            icon_manager = get_icon_manager()
            self.setWindowIcon(icon_manager.get_icon("window_img.png"))
        except Exception as e:
            logger.warning(f"Не удалось загрузить иконку окна: {e}")

        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Группа настроек прокси
        proxy_group = QGroupBox("Настройки прокси")
        proxy_layout = QVBoxLayout(proxy_group)

        # Поле для ввода URL
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("URL для проксирования:"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Введите адрес")
        url_layout.addWidget(self.url_input)
        proxy_layout.addLayout(url_layout)

        # Кнопки управления
        buttons_layout = QHBoxLayout()
        self.start_btn = QPushButton("Запуск прокси")
        self.stop_btn = QPushButton("Остановка прокси")
        self.restart_btn = QPushButton("Перезапуск")

        self.start_btn.clicked.connect(self.start_proxy)
        self.stop_btn.clicked.connect(self.stop_proxy)
        self.restart_btn.clicked.connect(self.restart_proxy)

        buttons_layout.addWidget(self.start_btn)
        buttons_layout.addWidget(self.stop_btn)
        buttons_layout.addWidget(self.restart_btn)
        proxy_layout.addLayout(buttons_layout)

        layout.addWidget(proxy_group)

        # Группа аутентификации
        auth_group = QGroupBox("Аутентификация")
        auth_layout = QVBoxLayout(auth_group)

        # Поле для токена
        token_layout = QHBoxLayout()
        token_layout.addWidget(QLabel("Access Token:"))
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input.setPlaceholderText("Введите токен доступа")
        token_layout.addWidget(self.token_input)
        auth_layout.addLayout(token_layout)

        # Статус токена
        self.token_status_label = QLabel("Статус: ⚠️ Не установлен")
        auth_layout.addWidget(self.token_status_label)

        # Статус backend сервера
        self.auth_status_label = QLabel("Backend: ⚪ Не проверен")
        self.auth_status_label.setStyleSheet("color: #888888;")
        auth_layout.addWidget(self.auth_status_label)

        # Кнопки
        token_buttons_layout = QHBoxLayout()
        self.save_token_btn = QPushButton("Сохранить")
        self.clear_token_btn = QPushButton("Очистить")
        self.toggle_token_visibility_btn = QPushButton("Показать токен")
        self.check_auth_btn = QPushButton("Проверить Backend")
        self.logout_btn = QPushButton("🚪 Logout")

        self.save_token_btn.clicked.connect(self.save_token)
        self.clear_token_btn.clicked.connect(self.clear_token)
        self.toggle_token_visibility_btn.clicked.connect(self.toggle_token_visibility)
        self.check_auth_btn.clicked.connect(self.on_check_auth_clicked)
        self.logout_btn.clicked.connect(self.on_logout_clicked)

        token_buttons_layout.addWidget(self.save_token_btn)
        token_buttons_layout.addWidget(self.clear_token_btn)
        token_buttons_layout.addWidget(self.toggle_token_visibility_btn)
        token_buttons_layout.addWidget(self.check_auth_btn)
        token_buttons_layout.addWidget(self.logout_btn)
        token_buttons_layout.addStretch()
        auth_layout.addLayout(token_buttons_layout)

        layout.addWidget(auth_group)

        # Группа логов
        log_group = QGroupBox("Логирование")
        log_layout = QVBoxLayout(log_group)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier", 10))
        log_layout.addWidget(self.log_text)

        # Кнопки для логов
        log_buttons_layout = QHBoxLayout()
        self.clear_log_btn = QPushButton("Очистить логи")
        self.copy_log_btn = QPushButton("Копировать логи")

        self.clear_log_btn.clicked.connect(self.clear_logs)
        self.copy_log_btn.clicked.connect(self.copy_logs)

        log_buttons_layout.addWidget(self.clear_log_btn)
        log_buttons_layout.addWidget(self.copy_log_btn)
        log_buttons_layout.addStretch()
        log_layout.addLayout(log_buttons_layout)

        layout.addWidget(log_group)

        # Статус бар
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Готов к работе")

        self.update_buttons_state()

    def setup_logging(self):
        """Настраивает логирование в GUI"""
        # Добавляем кастомный обработчик
        self.log_handler = LogHandler(self.log_emitter)
        self.log_handler.setLevel(logging.INFO)

        # Подключаем сигнал к слоту
        self.log_emitter.log_signal.connect(self.add_log_message)

        # Добавляем обработчик в корневой логгер
        root_logger = logging.getLogger()
        root_logger.addHandler(self.log_handler)

        if root_logger.level == logging.NOTSET:
            root_logger.setLevel(logging.INFO)

    def add_log_message(self, message):
        """Добавляет сообщение в лог"""
        try:
            self.log_text.append(message)
            self.log_text.moveCursor(QTextCursor.End)
        except Exception as e:
            print(f"Ошибка добавления лога: {e}")

    def clear_logs(self):
        """Очищает логи"""
        self.log_text.clear()
        logger.info("Логи очищены")

    def copy_logs(self):
        """Копирует логи в буфер обмена"""
        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(self.log_text.toPlainText())
            self.status_bar.showMessage("Логи скопированы в буфер обмена", 3000)
        except Exception as e:
            logger.error(f"Ошибка копирования логов: {e}")

    def load_config(self):
        """Загружает конфигурацию"""
        try:
            remote_url = self.config.get('proxy.remote_url', '')
            if not remote_url:
                remote_url = 'https://zenzefi.melxiory.ru'
            self.url_input.setText(remote_url)

            # Загружаем токен
            token = self.config.get_access_token()
            if token:
                self.token_input.setText(token)
                self.token_status_label.setText("Статус: ✅ Токен установлен")
                self.token_status_label.setStyleSheet("color: #00D4AA;")
            else:
                self.token_status_label.setText("Статус: ⚠️ Не установлен")
                self.token_status_label.setStyleSheet("color: #FFA500;")
        except Exception as e:
            logger.error(f"Ошибка загрузки конфига: {e}")
            self.url_input.setText('https://zenzefi.melxiory.ru')

    def save_config(self):
        """Сохраняет конфигурацию"""
        try:
            remote_url = self.url_input.text().strip()
            if remote_url:
                self.config.set('proxy.remote_url', remote_url)
                self.config.save()
                logger.debug("Конфигурация сохранена")
        except Exception as e:
            logger.error(f"Ошибка сохранения конфига: {e}")

    def save_token(self):
        """Сохраняет токен в конфиг"""
        try:
            token = self.token_input.text().strip()
            if not token:
                self.token_status_label.setText("Статус: ❌ Токен не может быть пустым")
                self.token_status_label.setStyleSheet("color: #E4002B;")
                QMessageBox.warning(self, "Ошибка", "Токен не может быть пустым")
                return

            if self.config.set_access_token(token):
                self.token_status_label.setText("Статус: ✅ Токен сохранён")
                self.token_status_label.setStyleSheet("color: #00D4AA;")
                logger.info("✅ Access token сохранён")
                QMessageBox.information(self, "Успех", "Access token успешно сохранён")
            else:
                self.token_status_label.setText("Статус: ❌ Ошибка сохранения")
                self.token_status_label.setStyleSheet("color: #E4002B;")
                QMessageBox.critical(self, "Ошибка", "Не удалось сохранить токен")
        except Exception as e:
            logger.error(f"Ошибка сохранения токена: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка: {e}")

    def clear_token(self):
        """Очищает токен"""
        try:
            reply = QMessageBox.question(
                self,
                "Подтверждение",
                "Вы уверены, что хотите удалить токен?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                if self.config.clear_access_token():
                    self.token_input.clear()
                    self.token_status_label.setText("Статус: ⚠️ Токен удалён")
                    self.token_status_label.setStyleSheet("color: #FFA500;")
                    logger.info("🗑️ Access token удалён")
                    QMessageBox.information(self, "Успех", "Токен успешно удалён")
                else:
                    QMessageBox.critical(self, "Ошибка", "Не удалось удалить токен")
        except Exception as e:
            logger.error(f"Ошибка удаления токена: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка: {e}")

    def toggle_token_visibility(self):
        """Переключает видимость токена"""
        try:
            if self.token_input.echoMode() == QLineEdit.EchoMode.Password:
                self.token_input.setEchoMode(QLineEdit.EchoMode.Normal)
                self.toggle_token_visibility_btn.setText("Скрыть токен")
            else:
                self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
                self.toggle_token_visibility_btn.setText("Показать токен")
        except Exception as e:
            logger.error(f"Ошибка переключения видимости токена: {e}")

    def on_check_auth_clicked(self):
        """Обработчик кнопки проверки статуса"""
        try:
            # Запускаем проверку в отдельном потоке
            import threading
            thread = threading.Thread(target=self._run_check_auth_status)
            thread.daemon = True
            thread.start()
        except Exception as e:
            logger.error(f"Ошибка при проверке backend: {e}")
            self.auth_status_label.setText("Backend: ❌ Ошибка проверки")
            self.auth_status_label.setStyleSheet("color: #E4002B;")

    def _run_check_auth_status(self):
        """Запускает check_auth_status в новом event loop"""
        import asyncio
        try:
            asyncio.run(self.check_auth_status())
        except Exception as e:
            logger.error(f"Ошибка в _run_check_auth_status: {e}")

    async def check_auth_status(self):
        """Проверить доступность backend сервера (не cookie!)"""
        try:
            import aiohttp
            import asyncio

            # Backend URL
            backend_url = "http://127.0.0.1:8000"

            self.auth_status_label.setText("Backend: 🔄 Проверка...")
            self.auth_status_label.setStyleSheet("color: #FFA500;")

            try:
                # Простая проверка доступности backend (без cookie)
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{backend_url}/health",  # health check endpoint
                        timeout=aiohttp.ClientTimeout(total=5),
                        ssl=False
                    ) as response:
                        if response.status == 200:
                            logger.info("✅ Backend доступен")
                            self.auth_status_label.setText("Backend: ✅ Доступен")
                            self.auth_status_label.setStyleSheet("color: #00A438;")
                        else:
                            logger.warning(f"⚠️ Backend ответил с кодом {response.status}")
                            self.auth_status_label.setText(f"Backend: ⚠️ Код {response.status}")
                            self.auth_status_label.setStyleSheet("color: #FFA500;")

            except aiohttp.ClientConnectorError:
                logger.error("❌ Backend недоступен (не запущен?)")
                self.auth_status_label.setText("Backend: ❌ Недоступен")
                self.auth_status_label.setStyleSheet("color: #E4002B;")
            except asyncio.TimeoutError:
                logger.error("❌ Backend не отвечает (таймаут)")
                self.auth_status_label.setText("Backend: ❌ Таймаут")
                self.auth_status_label.setStyleSheet("color: #E4002B;")

        except Exception as e:
            logger.error(f"Ошибка проверки backend: {e}")
            self.auth_status_label.setText("Backend: ❌ Ошибка")
            self.auth_status_label.setStyleSheet("color: #E4002B;")

    def update_auth_status_ui(self, status_data):
        """DEPRECATED: Больше не используется в новой архитектуре"""
        # Cookie статус проверяется в браузере, не в desktop client
        pass

    def on_logout_clicked(self):
        """Обработка нажатия кнопки logout"""
        try:
            # В новой архитектуре logout делается через браузер
            QMessageBox.information(
                self,
                'Logout через браузер',
                'Для выхода из системы:\n\n'
                '1. Откройте браузер с прокси\n'
                '2. Перейдите на https://127.0.0.1:61000/logout\n'
                '3. Или просто закройте браузер\n\n'
                'Cookie хранится в браузере, не в desktop client.',
                QMessageBox.StandardButton.Ok
            )
            logger.info("ℹ️ Показано сообщение о logout через браузер")
        except Exception as e:
            logger.error(f"Ошибка при показе сообщения о logout: {e}")

    def start_proxy(self):
        """Запускает прокси"""
        # СТРОГАЯ БЛОКИРОВКА: Проверка токена ПЕРЕД запуском
        if not self.config.has_access_token():
            QMessageBox.critical(
                self,
                "Ошибка аутентификации",
                "Access token не настроен.\n\n"
                "Для работы прокси требуется токен доступа.\n"
                "Пожалуйста, введите токен в разделе 'Аутентификация' и нажмите 'Сохранить'."
            )
            logger.warning("⚠️ Попытка запуска прокси без токена")
            return

        remote_url = self.url_input.text().strip()
        if not remote_url:
            QMessageBox.warning(self, "Ошибка", "Введите URL для проксирования")
            return

        if not remote_url.startswith(('http://', 'https://')):
            QMessageBox.warning(self, "Ошибка", "URL должен начинаться с http:// или https://")
            return

        self.save_config()
        # Не открываем браузер автоматически - пользователь откроет сам
        self.start_proxy_thread("start", remote_url)

    def stop_proxy(self):
        """Останавливает прокси"""
        self.start_proxy_thread("stop")

    def restart_proxy(self):
        """Перезапускает прокси"""
        remote_url = self.url_input.text().strip()
        if not remote_url:
            QMessageBox.warning(self, "Ошибка", "Введите URL для проксирования")
            return

        self.save_config()
        self.start_proxy_thread("restart", remote_url)

    def start_proxy_thread(self, action, remote_url=None):
        """Запускает поток управления прокси"""
        if self.proxy_thread and self.proxy_thread.isRunning():
            logger.warning("Поток уже запущен")
            return

        try:
            self.proxy_thread = ProxyManagerThread(self.proxy_manager)
            self.proxy_thread.set_action(action, remote_url)
            self.proxy_thread.log_signal.connect(self.add_log_message)
            self.proxy_thread.status_signal.connect(self.handle_status_update)
            self.proxy_thread.finished.connect(self.thread_finished)
            self.proxy_thread.start()

            self.update_buttons_state(False)
        except Exception as e:
            logger.error(f"Ошибка запуска потока: {e}", exc_info=True)
            self.update_buttons_state(True)

    def thread_finished(self):
        """Вызывается при завершении потока"""
        self.update_buttons_state(True)
        self.update_status()

    def handle_status_update(self, status):
        """Обрабатывает обновление статуса"""
        try:
            self.current_status = status
            self.update_status_display()
            # Браузер пользователь откроет вручную - не открываем автоматически
        except Exception as e:
            logger.error(f"Ошибка обновления статуса: {e}")

    def update_status(self):
        """Обновляет статус"""
        try:
            if not self.proxy_thread or not self.proxy_thread.isRunning():
                status = self.proxy_manager.get_status()
                self.handle_status_update(status)
        except Exception as e:
            logger.error(f"Ошибка обновления статуса: {e}")

    def update_status_display(self):
        """Обновляет отображение статуса"""
        try:
            if not self.current_status:
                return

            status = self.current_status

            # Получаем цвета темы
            try:
                from ui.theme_manager import get_theme_manager
                theme_manager = get_theme_manager()
                colors = theme_manager.get_current_colors()
            except Exception as e:
                logger.warning(f"Не удалось загрузить тему: {e}")
                colors = {
                    'success': '#00D4AA',
                    'error': '#E4002B',
                    'header_bg': '#000000'
                }

            if status.get('running', False):
                status_text = f"✅ Прокси запущен - https://127.0.0.1:{status.get('port', 61000)} → {status.get('url', 'N/A')}"
                text_color = colors['success']
            else:
                status_text = "❌ Прокси остановлен"
                text_color = colors['error']

            # Улучшенная информация о порте
            if not status.get('port_available', True):
                if status.get('port_used_by_us', False):
                    status_text += " | ⚠️ Порт занят нашим приложением"
                    text_color = "#FFA500"
                elif 'port_message' in status:
                    status_text += f" | {status['port_message']}"
                    text_color = "#FFA500"

            # Обновляем статус бар
            self.status_bar.setStyleSheet(f"color: {text_color}; background-color: {colors['header_bg']};")
            self.status_bar.showMessage(status_text)

        except Exception as e:
            logger.error(f"Ошибка отображения статуса: {e}")
            self.status_bar.showMessage("Ошибка статуса")

    def update_buttons_state(self, enabled=True):
        """Обновляет состояние кнопок"""
        try:
            self.start_btn.setEnabled(enabled)
            self.stop_btn.setEnabled(enabled)
            self.restart_btn.setEnabled(enabled)
            self.url_input.setEnabled(enabled)

            if not enabled:
                self.start_btn.setText("Запуск...")
                self.stop_btn.setText("Остановка...")
                self.restart_btn.setText("Перезапуск...")
            else:
                self.start_btn.setText("Запуск прокси")
                self.stop_btn.setText("Остановка прокси")
                self.restart_btn.setText("Перезапуск")
        except Exception as e:
            logger.error(f"Ошибка обновления кнопок: {e}")

    def closeEvent(self, event):
        """Обрабатывает закрытие окна"""
        try:
            if hasattr(self, 'proxy_thread') and self.proxy_thread and self.proxy_thread.isRunning():
                reply = QMessageBox.question(
                    self,
                    'Подтверждение',
                    'Прокси все еще работает. Вы уверены, что хотите выйти?',
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )

                if reply == QMessageBox.Yes:
                    # Останавливаем поток
                    if self.proxy_thread:
                        self.proxy_thread.wait(3000)
                    event.accept()
                else:
                    event.ignore()
            else:
                event.accept()
        except Exception as e:
            logger.error(f"Ошибка при закрытии окна: {e}")
            event.accept()

    def apply_theme(self):
        """Применяет текущую тему Mercedes-Benz"""
        try:
            from ui.theme_manager import get_theme_manager
            theme_manager = get_theme_manager()

            stylesheet = theme_manager.get_stylesheet()
            colors = theme_manager.get_current_colors()

            # Добавляем стиль для заголовка окна
            enhanced_stylesheet = stylesheet + f"""
                QMainWindow {{
                    background-color: {colors['primary_bg']};
                    color: {colors['text_primary']};
                }}
            """

            self.setStyleSheet(enhanced_stylesheet)

            # Настраиваем QTextEdit для логов
            log_style = f"""
                QTextEdit {{
                    background-color: {colors['input_bg']};
                    color: {colors['text_secondary']};
                    border: 1px solid {colors['border_dark']};
                    border-radius: 3px;
                    font-family: 'Courier New', monospace;
                    selection-background-color: {colors['button_active']};
                }}
            """
            self.log_text.setStyleSheet(log_style)

            # Обновляем статус бар если есть статус
            if self.current_status:
                self.update_status_display()

            # Принудительное обновление
            self.update()

        except Exception as e:
            logger.warning(f"Ошибка применения темы: {e}")