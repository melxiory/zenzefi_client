# ui/tray_icon.py
import logging
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QMessageBox
from PySide6.QtGui import QIcon, QAction, QPixmap
from PySide6.QtCore import QTimer, Qt
from ui.icons import get_icon_manager
from ui.colors import COLORS

logger = logging.getLogger(__name__)


class TrayIcon(QSystemTrayIcon):
    def __init__(self, app, proxy_manager):
        super().__init__()
        self.app = app
        self.proxy_manager = proxy_manager
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

        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(theme_action)
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
            icon_manager = get_icon_manager()

            if self.proxy_manager.is_running:
                self.setIcon(icon_manager.get_icon("green_system_trie.png"))
                proxy_status = "Запущен"
                tooltip = (f"Zenzefi Client - {proxy_status}\n"
                          f"Прокси: https://127.0.0.1:61000")
            else:
                self.setIcon(icon_manager.get_icon("red_system_trie.png"))
                proxy_status = "Остановлен"
                tooltip = f"Zenzefi Client - {proxy_status}"

            self.setToolTip(tooltip)
        except Exception as e:
            logger.error(f"Ошибка обновления статуса: {e}")

    def show_main_window(self):
        """Показывает главное окно"""
        if not self.main_window:
            from ui.main_window import MainWindow
            self.main_window = MainWindow(self.proxy_manager)
            self.main_window.apply_theme()  # Применяем тему при lazy loading
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

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
        msg_box.setText('Вы уверены, что хотите выйти? Прокси будет остановлен.')
        msg_box.setIcon(QMessageBox.Question)

        # Добавляем кнопки
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)

        # Показываем диалог и возвращаем результат
        reply = msg_box.exec()



        if reply == QMessageBox.Yes:
            try:
                self.proxy_manager.stop()
                logger.info("Приложение завершено")
            except Exception as e:
                logger.error(f"Ошибка при остановке прокси: {e}")

            self.app.quit()

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