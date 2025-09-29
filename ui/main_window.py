# ui/main_window.py
import logging
from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                               QWidget, QPushButton, QTextEdit, QLineEdit, QLabel,
                               QGroupBox, QStatusBar, QMessageBox)
from PySide6.QtCore import QTimer, QThread, Signal, QObject
from PySide6.QtGui import QTextCursor, QFont
from ui.icons import get_icon_manager
from ui.styles import STYLESHEET
from ui.colors import COLORS

logger = logging.getLogger(__name__)


class LogEmitter(QObject):
    """Объект для эмитации сигналов логов"""
    log_signal = Signal(str)


class LogHandler(logging.Handler):
    """Кастомный обработчик логов для вывода в GUI"""

    def __init__(self, log_emitter):
        super().__init__()
        self.log_emitter = log_emitter
        self.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    def emit(self, record):
        try:
            msg = self.format(record)
            self.log_emitter.log_signal.emit(msg)
        except Exception as e:
            print(f"Ошибка в LogHandler: {e}")


class NginxManagerThread(QThread):
    """Поток для управления nginx"""
    log_signal = Signal(str)
    status_signal = Signal(dict)

    def __init__(self, nginx_manager):
        super().__init__()
        self.nginx_manager = nginx_manager
        self.action = None
        self.remote_url = ""

    def set_action(self, action, remote_url=None):
        self.action = action
        if remote_url:
            self.remote_url = remote_url

    def run(self):
        if self.action == "start":
            self.start_nginx()
        elif self.action == "stop":
            self.stop_nginx()
        elif self.action == "restart":
            self.restart_nginx()

    def start_nginx(self):
        try:
            success = self.nginx_manager.start(61000, self.remote_url)
            status = self.nginx_manager.get_status()
            self.status_signal.emit(status)
            if success:
                self.log_signal.emit("✅ Nginx успешно запущен")
            else:
                self.log_signal.emit("❌ Ошибка запуска Nginx")
        except Exception as e:
            self.log_signal.emit(f"❌ Ошибка запуска Nginx: {e}")

    def stop_nginx(self):
        try:
            success = self.nginx_manager.stop()
            status = self.nginx_manager.get_status()
            self.status_signal.emit(status)
            if success:
                self.log_signal.emit("✅ Nginx успешно остановлен")
            else:
                self.log_signal.emit("❌ Ошибка остановки Nginx")
        except Exception as e:
            self.log_signal.emit(f"❌ Ошибка остановки Nginx: {e}")

    def restart_nginx(self):
        self.stop_nginx()
        self.start_nginx()


class MainWindow(QMainWindow):
    def __init__(self, nginx_manager):
        super().__init__()
        self.nginx_manager = nginx_manager
        self.nginx_thread = None

        self.setup_ui()

        # Устанавливаем стиль
        self.apply_theme()

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

    def setup_ui(self):
        self.setWindowTitle("Zenzefi Client")
        self.setGeometry(100, 100, 800, 600)

        # Устанавливаем иконку окна
        icon_manager = get_icon_manager()
        self.setWindowIcon(icon_manager.get_icon("window_img.png"))

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
        self.start_btn = QPushButton("Запуск Nginx")
        self.stop_btn = QPushButton("Остановка Nginx")
        self.restart_btn = QPushButton("Перезапуск")

        self.start_btn.clicked.connect(self.start_nginx)
        self.stop_btn.clicked.connect(self.stop_nginx)
        self.restart_btn.clicked.connect(self.restart_nginx)

        buttons_layout.addWidget(self.start_btn)
        buttons_layout.addWidget(self.stop_btn)
        buttons_layout.addWidget(self.restart_btn)
        proxy_layout.addLayout(buttons_layout)

        layout.addWidget(proxy_group)

        # Группа логов
        log_group = QGroupBox("Логирование")
        log_layout = QVBoxLayout(log_group)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier", 14))
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
        logging.getLogger().addHandler(self.log_handler)
        logging.getLogger().setLevel(logging.INFO)

    def add_log_message(self, message):
        """Добавляет сообщение в лог"""
        self.log_text.append(message)
        self.log_text.moveCursor(QTextCursor.End)

    def clear_logs(self):
        """Очищает логи"""
        self.log_text.clear()

    def copy_logs(self):
        """Копирует логи в буфер обмена"""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.log_text.toPlainText())
        self.status_bar.showMessage("Логи скопированы в буфер обмена", 3000)

    def load_config(self):
        """Загружает конфигурацию"""
        remote_url = self.config.get('proxy.remote_url', 'Введите адрес')
        self.url_input.setText(remote_url)

    def save_config(self):
        """Сохраняет конфигурацию"""
        try:
            remote_url = self.url_input.text().strip()
            if remote_url:
                self.config.set('proxy.remote_url', remote_url)
                self.config.save()
        except Exception as e:
            logger.error(f"Ошибка сохранения конфига: {e}")

    def start_nginx(self):
        """Запускает nginx"""
        remote_url = self.url_input.text().strip()
        if not remote_url:
            QMessageBox.warning(self, "Ошибка", "Введите URL для проксирования")
            return

        if not remote_url.startswith(('http://', 'https://')):
            QMessageBox.warning(self, "Ошибка", "URL должен начинаться с http:// или https://")
            return

        self.save_config()
        self.start_nginx_thread("start", remote_url)

    def stop_nginx(self):
        """Останавливает nginx"""
        self.start_nginx_thread("stop")

    def restart_nginx(self):
        """Перезапускает nginx"""
        remote_url = self.url_input.text().strip()
        self.save_config()
        self.start_nginx_thread("restart", remote_url)

    def start_nginx_thread(self, action, remote_url=None):
        """Запускает поток управления nginx"""
        if self.nginx_thread and self.nginx_thread.isRunning():
            return

        self.nginx_thread = NginxManagerThread(self.nginx_manager)
        self.nginx_thread.set_action(action, remote_url)
        self.nginx_thread.log_signal.connect(self.add_log_message)
        self.nginx_thread.status_signal.connect(self.handle_status_update)
        self.nginx_thread.finished.connect(self.thread_finished)
        self.nginx_thread.start()

        self.update_buttons_state(False)

    def thread_finished(self):
        """Вызывается при завершении потока"""
        self.update_buttons_state(True)

    def handle_status_update(self, status):
        """Обрабатывает обновление статуса"""
        self.current_status = status
        self.update_status_display()

    def update_status(self):
        """Обновляет статус"""
        if not self.nginx_thread or not self.nginx_thread.isRunning():
            status = self.nginx_manager.get_status()
            self.handle_status_update(status)

    def update_status_display(self):
        """Обновляет отображение статуса"""
        if hasattr(self, 'current_status'):
            status = self.current_status

            from ui.theme_manager import get_theme_manager
            theme_manager = get_theme_manager()
            colors = theme_manager.get_current_colors()

            if status['running']:
                status_text = f"✅ Nginx запущен - https://127.0.0.1:{status['port']} → {status['url']}"
                text_color = colors['success']
            else:
                status_text = "❌ Nginx остановлен"
                text_color = colors['error']

            # Улучшенная информация о порте
            if not status['port_available']:
                if status.get('port_used_by_us', False):
                    status_text += " | ⚠️ Порт занят нашим приложением"
                    text_color = "#FFA500"  # Оранжевый
                elif 'port_message' in status:
                    status_text += f" | {status['port_message']}"
                    text_color = "#FFA500"  # Оранжевый

            # Используем цвет из текущей темы для статус бара
            self.status_bar.setStyleSheet(f"color: {text_color}; background-color: {colors['header_bg']};")
            self.status_bar.showMessage(status_text)

    def update_buttons_state(self, enabled=True):
        """Обновляет состояние кнопок"""
        self.start_btn.setEnabled(enabled)
        self.stop_btn.setEnabled(enabled)
        self.restart_btn.setEnabled(enabled)
        self.url_input.setEnabled(enabled)

        if not enabled:
            self.start_btn.setText("Запуск...")
            self.stop_btn.setText("Остановка...")
        else:
            self.start_btn.setText("Запуск Nginx")
            self.stop_btn.setText("Остановка Nginx")

    def closeEvent(self, event):
        """Обрабатывает закрытие окна"""
        if hasattr(self, 'nginx_thread') and self.nginx_thread and self.nginx_thread.isRunning():
            reply = QMessageBox.question(self, 'Подтверждение',
                                         'Nginx все еще работает. Вы уверены, что хотите выйти?',
                                         QMessageBox.Yes | QMessageBox.No,
                                         QMessageBox.No)

            if reply == QMessageBox.Yes:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def apply_theme(self):
        """Применяет текущую тему Mercedes-Benz"""
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
                    QMainWindow::title {{
                        background-color: {colors['header_bg']};
                        color: {colors['accent_white']};
                    }}
                """

        self.setStyleSheet(enhanced_stylesheet)

        # Настраиваем QTextEdit для логов (специфичные настройки)
        log_style = f"""
            QTextEdit {{
                background-color: {colors['input_bg']};
                color: {colors['text_secondary']};
                border: 1px solid {colors['border_dark']};
                border-radius: 3px;
                font-family: 'Courier New';
                selection-background-color: {colors['button_active']};
            }}
        """
        self.log_text.setStyleSheet(log_style)

        # Обновляем статус бар
        self.update_status_display()

        # Принудительное обновление интерфейса
        self.update()