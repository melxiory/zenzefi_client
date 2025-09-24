# ui/tray_icon.py
import logging
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QMessageBox
from PySide6.QtGui import QIcon, QAction, QPixmap
from PySide6.QtCore import QTimer, Qt
from ui.icons import get_icon_manager
from ui.colors import COLORS

logger = logging.getLogger(__name__)


class TrayIcon(QSystemTrayIcon):
    def __init__(self, app, nginx_manager):
        super().__init__()
        self.app = app
        self.nginx_manager = nginx_manager
        self.main_window = None

        self.setup_ui()
        self.setup_timer()

    def setup_ui(self):
        icon_manager = get_icon_manager()

        # Устанавливаем красную иконку по умолчанию
        self.setIcon(icon_manager.get_icon("red_system_trie.png"))
        self.setToolTip("Zenzefi Client - Прокси сервер (Остановлен)")

        # Создаем контекстное меню
        menu = QMenu()

        # Действия меню
        show_action = QAction("Показать окно", self)
        show_action.triggered.connect(self.show_main_window)

        start_action = QAction("Запуск Nginx", self)
        start_action.triggered.connect(self.start_nginx)

        stop_action = QAction("Остановка Nginx", self)
        stop_action.triggered.connect(self.stop_nginx)

        restart_action = QAction("Перезапуск Nginx", self)
        restart_action.triggered.connect(self.restart_nginx)

        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(start_action)
        menu.addAction(stop_action)
        menu.addAction(restart_action)
        menu.addSeparator()

        exit_action = QAction("Выход", self)
        exit_action.triggered.connect(self.exit_app)
        menu.addAction(exit_action)

        self.setContextMenu(menu)
        self.activated.connect(self.on_tray_activated)

    def setup_timer(self):
        """Настраивает таймер для обновления статуса"""
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(10000)

    def update_status(self):
        """Обновляет статус в трее"""
        try:
            status = self.nginx_manager.get_status()
            icon_manager = get_icon_manager()

            if status['running']:
                self.setIcon(icon_manager.get_icon("green_system_trie.png"))
                tooltip = "Zenzefi Client - Запущен"
            else:
                self.setIcon(icon_manager.get_icon("red_system_trie.png"))
                tooltip = "Zenzefi Client - Остановлен"

            self.setToolTip(tooltip)
        except Exception as e:
            logger.error(f"Ошибка обновления статуса: {e}")

    def show_main_window(self):
        """Показывает главное окно"""
        if not self.main_window:
            from ui.main_window import MainWindow
            self.main_window = MainWindow(self.nginx_manager)
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def start_nginx(self):
        """Запускает nginx из трея"""
        try:
            from core.config_manager import get_config
            config = get_config()
            remote_url = config.get('proxy.remote_url', 'https://zenzefi.melxiory.ru')

            success = self.nginx_manager.start(61000, remote_url)
            if success:
                self.showMessage("Zenzefi Client", "Nginx успешно запущен",
                                 QSystemTrayIcon.Information, 3000)
                logger.info("Nginx запущен из трея")
            else:
                self.showMessage("Zenzefi Client", "Ошибка запуска Nginx",
                                 QSystemTrayIcon.Critical, 5000)
                logger.error("Ошибка запуска Nginx из трея")
        except Exception as e:
            logger.error(f"Ошибка запуска nginx из трея: {e}")
            self.showMessage("Zenzefi Client", f"Ошибка: {e}",
                             QSystemTrayIcon.Critical, 5000)

    def stop_nginx(self):
        """Останавливает nginx из трея"""
        try:
            success = self.nginx_manager.stop()
            if success:
                self.showMessage("Zenzefi Client", "Nginx успешно остановлен",
                                 QSystemTrayIcon.Information, 3000)
                logger.info("Nginx остановлен из трея")
            else:
                self.showMessage("Zenzefi Client", "Ошибка остановки Nginx",
                                 QSystemTrayIcon.Critical, 5000)
                logger.error("Ошибка остановки Nginx из трея")
        except Exception as e:
            logger.error(f"Ошибка остановки nginx из трея: {e}")
            self.showMessage("Zenzefi Client", f"Ошибка: {e}",
                             QSystemTrayIcon.Critical, 5000)

    def restart_nginx(self):
        """Перезапускает nginx из трея"""
        try:
            # Получаем URL из конфигурации
            from core.config_manager import get_config
            config = get_config()
            remote_url = config.get('proxy.remote_url', 'https://zenzefi.melxiory.ru')

            success = self.nginx_manager.restart()
            if success:
                self.showMessage("Zenzefi Client", "Nginx успешно перезапущен",
                                 QSystemTrayIcon.Information, 3000)
                logger.info("Nginx перезапущен из трея")
            else:
                self.showMessage("Zenzefi Client", "Ошибка перезапуска Nginx",
                                 QSystemTrayIcon.Critical, 5000)
                logger.error("Ошибка перезапуска Nginx из трея")
        except Exception as e:
            logger.error(f"Ошибка перезапуска nginx из трея: {e}")
            self.showMessage("Zenzefi Client", f"Ошибка: {e}",
                             QSystemTrayIcon.Critical, 5000)

    def on_tray_activated(self, reason):
        """Обрабатывает активацию иконки в трее"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_main_window()

    def exit_app(self):
        """Выход из приложения"""
        reply = QMessageBox.question(None, 'Подтверждение выхода',
                                     'Вы уверены, что хотите выйти? Nginx будет остановлен.',
                                     QMessageBox.Yes | QMessageBox.No,
                                     QMessageBox.No)

        if reply == QMessageBox.Yes:
            try:
                self.nginx_manager.stop()
                logger.info("Приложение завершено")
            except Exception as e:
                logger.error(f"Ошибка при остановке nginx: {e}")

            self.app.quit()
