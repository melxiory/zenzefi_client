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

        theme_action = QAction("Переключить тему", self)
        theme_action.triggered.connect(self.toggle_theme)

        start_action = QAction("Запуск Nginx", self)
        start_action.triggered.connect(self.start_nginx)

        stop_action = QAction("Остановка Nginx", self)
        stop_action.triggered.connect(self.stop_nginx)

        restart_action = QAction("Перезапуск Nginx", self)
        restart_action.triggered.connect(self.restart_nginx)

        menu.addAction(theme_action)
        menu.addSeparator()
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

            # Получаем статус токена
            from core.config_manager import get_config
            config = get_config()
            token_status = "✅ Настроен" if config.has_access_token() else "❌ Не настроен"

            if status['running']:
                self.setIcon(icon_manager.get_icon("green_system_trie.png"))
                proxy_status = "Запущен"
                tooltip = (f"Zenzefi Client - {proxy_status}\n"
                          f"Прокси: https://127.0.0.1:61000\n"
                          f"Токен: {token_status}")
            else:
                self.setIcon(icon_manager.get_icon("red_system_trie.png"))
                proxy_status = "Остановлен"
                tooltip = (f"Zenzefi Client - {proxy_status}\n"
                          f"Токен: {token_status}")

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

            # СТРОГАЯ БЛОКИРОВКА: Проверка токена перед запуском
            if not config.has_access_token():
                self.showMessage(
                    "Zenzefi Client",
                    "Ошибка: Access token не настроен.\n"
                    "Откройте главное окно и настройте токен.",
                    QSystemTrayIcon.Critical,
                    5000
                )
                logger.warning("⚠️ Попытка запуска прокси из трея без токена")
                return

            remote_url = config.get('proxy.remote_url', 'https://zenzefi.melxiory.ru')

            success = self.nginx_manager.start(61000, remote_url)
            if success:
                self.showMessage("Zenzefi Client",
                                 "Прокси запущен.\n\nОткрываем браузер для аутентификации...",
                                 QSystemTrayIcon.Information, 3000)
                logger.info("Прокси запущен из трея")

                # Открываем браузер для cookie аутентификации
                try:
                    import webbrowser
                    access_token = config.get_access_token()
                    local_port = config.get('proxy.local_port', 61000)
                    auth_url = f"https://127.0.0.1:{local_port}/api/v1/proxy?token={access_token}"
                    webbrowser.open(auth_url)
                    logger.info(f"🌐 Браузер открыт для auth: {auth_url}")
                except Exception as e:
                    logger.error(f"Ошибка открытия браузера: {e}")
            else:
                self.showMessage("Zenzefi Client", "Ошибка запуска прокси",
                                 QSystemTrayIcon.Critical, 5000)
                logger.error("Ошибка запуска прокси из трея")
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
        icon_manager = get_icon_manager()

        # Создаем кастомный QMessageBox
        msg_box = QMessageBox()

        # Устанавливаем иконку окна
        msg_box.setWindowIcon(icon_manager.get_icon("window_img.png"))

        # Настраиваем содержимое
        msg_box.setWindowTitle('Подтверждение выхода')
        msg_box.setText('Вы уверены, что хотите выйти? Nginx будет остановлен.')
        msg_box.setIcon(QMessageBox.Question)

        # Добавляем кнопки
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)

        # Показываем диалог и возвращаем результат
        reply = msg_box.exec()



        if reply == QMessageBox.Yes:
            try:
                self.nginx_manager.stop()
                logger.info("Приложение завершено")
            except Exception as e:
                logger.error(f"Ошибка при остановке nginx: {e}")

            self.app.quit()

    def check_single_instance(self):
        """Проверяет, является ли этот экземпляр единственным"""
        try:
            from utils.single_instance import get_single_instance
            instance_lock = get_single_instance(51000)
            return not instance_lock.check_already_running()
        except Exception as e:
            logger.error(f"Ошибка проверки единственного экземпляра: {e}")
            return True

    def toggle_theme(self):
        """Переключает тему приложения"""
        from ui.theme_manager import get_theme_manager
        theme_manager = get_theme_manager()

        new_theme = theme_manager.toggle_theme()

        # Обновляем стиль главного окна если оно открыто
        if self.main_window:
            self.main_window.apply_theme()

        self.showMessage(
            "Zenzefi Client",
            f"Тема переключена: {'Светлая' if new_theme == 'light' else 'Тёмная'}",
            QSystemTrayIcon.Information,
            2000
        )