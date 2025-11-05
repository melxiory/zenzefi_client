# ui/theme_manager.py
import logging
from ui.colors import COLORS, COLORS_LIGHT

logger = logging.getLogger(__name__)

# Mercedes-Benz Dark Theme
STYLESHEET_DARK = """
/* Mercedes-Benz Dark Theme */
QMainWindow {
    background-color: #1A1A1A;
    color: #FFFFFF;
}

QWidget {
    background-color: #1A1A1A;
    color: #FFFFFF;
}

/* Группы как в Mercedes - с черным заголовком */
QGroupBox {
    color: #FFFFFF;
    font-weight: bold;
    border: 1px solid #404040;
    border-radius: 4px;
    margin-top: 10px;
    padding-top: 10px;
    background-color: #252525;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
    background-color: transparent;
    color: #C8C8C8;
    font-size: 13px;
    font-weight: bold;
    margin-left: 10px;
}

/* Кнопки Mercedes стиль */
QPushButton {
    background-color: #2D2D2D;
    color: #FFFFFF;
    border: 1px solid #404040;
    border-radius: 3px;
    padding: 8px 16px;
    font-weight: bold;
    min-width: 90px;
    font-size: 14px;
}

QPushButton:hover {
    background-color: #00A0E9;
    border: 1px solid #00A0E9;
}

QPushButton:pressed {
    background-color: #0078B6;
    border: 1px solid #0078B6;
}

QPushButton:disabled {
    background-color: #2D2D2D;
    color: #666666;
    border: 1px solid #404040;
}

/* Поля ввода */
QLineEdit {
    background-color: #2D2D2D;
    color: #FFFFFF;
    border: 1px solid #404040;
    border-radius: 3px;
    padding: 6px 8px;
    font-size: 14px;
}

QLineEdit:focus {
    border: 1px solid #00A0E9;
    background-color: #2D2D2D;
}

/* Текстовые поля */
QTextEdit {
    background-color: #2D2D2D;
    color: #C8C8C8;
    border: 1px solid #404040;
    border-radius: 3px;
    font-family: 'Courier New', monospace;
    font-size: 14px;
    padding: 8px;
}

/* Статус бар */
QStatusBar {
    background-color: #000000;
    color: #C8C8C8;
    border-top: 1px solid #404040;
    font-size: 12px;
    padding: 4px;
}

/* Метки */
QLabel {
    color: #C8C8C8;
    font-size: 14px;
    font-weight: normal;
    background-color: #252525;
}

/* Выпадающие списки */
QComboBox {
    background-color: #2D2D2D;
    color: #FFFFFF;
    border: 1px solid #404040;
    border-radius: 3px;
    padding: 5px;
    min-width: 100px;
}

QComboBox::drop-down {
    border: none;
}

QComboBox QAbstractItemView {
    background-color: #2D2D2D;
    color: #FFFFFF;
    border: 1px solid #404040;
    selection-background-color: #00A0E9;
}

/* Скроллбары */
QScrollBar:vertical {
    background-color: #2D2D2D;
    width: 12px;
    border-radius: 6px;
    border: none;
}

QScrollBar::handle:vertical {
    background-color: #404040;
    border-radius: 6px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background-color: #666666;
}

/* Специфические элементы MainWindow */
QLabel#warningLabel {
    color: orange;
    font-size: 10px;
    font-style: italic;
}

QLabel#statusLabel {
    font-weight: bold;
    font-size: 14px;
}

QLabel#statusLabel[status="running"] {
    color: #00FF00;
    font-weight: bold;
}

QLabel#statusLabel[status="stopped"] {
    color: #808080;
    font-weight: bold;
}

QLabel#localUrlLabel {
    font-family: monospace;
    font-size: 14px;
}

QLabel#instructionsLabel {
    color: gray;
    font-size: 10px;
    padding: 10px;
}

/* QMessageBox (всплывающие окна) */
QMessageBox {
    background-color: #1A1A1A;
    color: #FFFFFF;
}

QMessageBox QLabel {
    color: #C8C8C8;
    background-color: #1A1A1A;
    font-size: 13px;
}

QMessageBox QPushButton {
    background-color: #2D2D2D;
    color: #FFFFFF;
    border: 1px solid #404040;
    border-radius: 3px;
    padding: 6px 20px;
    min-width: 80px;
    font-weight: bold;
}

QMessageBox QPushButton:hover {
    background-color: #00A0E9;
    border: 1px solid #00A0E9;
}

QMessageBox QPushButton:pressed {
    background-color: #0078B6;
}

QMessageBox QPushButton:default {
    background-color: #00A0E9;
    border: 2px solid #00C8FF;
}
"""


class ThemeManager:
    def __init__(self):
        # Загружаем тему из конфига
        from core.config_manager import get_config
        config = get_config()
        self.current_theme = config.get('application.theme', 'dark')

    def toggle_theme(self):
        """Переключает между светлой и темной темой"""
        if self.current_theme == "dark":
            self.current_theme = "light"
        else:
            self.current_theme = "dark"

        # Сохраняем в конфиг
        from core.config_manager import get_config
        config = get_config()
        config.set('application.theme', self.current_theme, save=True)

        logger.info(f"🔄 Переключена тема: {self.current_theme}")
        return self.current_theme

    def get_current_colors(self):
        """Возвращает цвета текущей темы"""
        return COLORS_LIGHT if self.current_theme == "light" else COLORS

    def get_stylesheet(self):
        """Возвращает стили для текущей темы"""
        if self.current_theme == "light":
            return self._get_light_stylesheet()
        return STYLESHEET_DARK

    def _get_light_stylesheet(self):
        """Генерирует стили для светлой темы Mercedes"""
        colors = self.get_current_colors()

        return f"""
        /* Mercedes-Benz Light Theme */
        QMainWindow {{
            background-color: {colors['primary_bg']};
            color: {colors['text_primary']};
        }}

        QWidget {{
            background-color: {colors['primary_bg']};
            color: {colors['text_primary']};
        }}

        QGroupBox {{
            color: {colors['text_primary']};
            font-weight: bold;
            border: 1px solid {colors['border_dark']};
            border-radius: 4px;
            margin-top: 10px;
            padding-top: 10px;
            background-color: {colors['card_bg']};
        }}

        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0px 8px;
            background-color: transparent;
            color: {colors['text_secondary']};
            font-size: 13px;
            font-weight: bold;
            margin-left: 10px;
        }}

        QPushButton {{
            background-color: #F8F8F8;
            color: {colors['text_primary']};
            border: 1px solid {colors['border_dark']};
            border-radius: 3px;
            padding: 8px 16px;
            font-weight: bold;
            min-width: 90px;
            font-size: 14px;
        }}

        QPushButton:hover {{
            background-color: {colors['button_active']};
            color: #FFFFFF;
            border: 1px solid {colors['button_active']};
        }}

        QPushButton:pressed {{
            background-color: #0078B6;
            border: 1px solid #0078B6;
        }}

        QLineEdit {{
            background-color: {colors['input_bg']};
            color: {colors['text_primary']};
            border: 1px solid {colors['border_dark']};
            border-radius: 3px;
            padding: 6px 8px;
            font-size: 14px;
        }}

        QLineEdit:focus {{
            border: 1px solid {colors['button_active']};
        }}

        QTextEdit {{
            background-color: {colors['input_bg']};
            color: {colors['text_primary']};
            border: 1px solid {colors['border_dark']};
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            padding: 8px;
        }}

        QStatusBar {{
            background-color: {colors['header_bg']};
            color: #FFFFFF;
            border-top: 1px solid {colors['border_dark']};
            font-size: 12px;
            padding: 4px;
        }}

        QLabel {{
            color: {colors['text_secondary']};
            font-size: 14px;
            font-weight: normal;
            background-color: {colors['card_bg']};
        }}

        /* Специфические элементы MainWindow */
        QLabel#warningLabel {{
            color: orange;
            font-size: 10px;
            font-style: italic;
        }}

        QLabel#statusLabel {{
            font-weight: bold;
            font-size: 14px;
        }}

        QLabel#statusLabel[status="running"] {{
            color: #00AA00;
            font-weight: bold;
        }}

        QLabel#statusLabel[status="stopped"] {{
            color: #666666;
            font-weight: bold;
        }}

        QLabel#localUrlLabel {{
            font-family: monospace;
            font-size: 14px;
        }}

        QLabel#instructionsLabel {{
            color: #666666;
            font-size: 10px;
            padding: 10px;
        }}

        /* QMessageBox (всплывающие окна) */
        QMessageBox {{
            background-color: {colors['primary_bg']};
            color: {colors['text_primary']};
        }}

        QMessageBox QLabel {{
            color: {colors['text_secondary']};
            background-color: {colors['card_bg']};
            font-size: 13px;
        }}

        QMessageBox QPushButton {{
            background-color: #F8F8F8;
            color: {colors['text_primary']};
            border: 1px solid {colors['border_dark']};
            border-radius: 3px;
            padding: 6px 20px;
            min-width: 80px;
            font-weight: bold;
        }}

        QMessageBox QPushButton:hover {{
            background-color: {colors['button_active']};
            color: #FFFFFF;
            border: 1px solid {colors['button_active']};
        }}

        QMessageBox QPushButton:pressed {{
            background-color: #0078B6;
        }}

        QMessageBox QPushButton:default {{
            background-color: {colors['button_active']};
            border: 2px solid #00C8FF;
            color: #FFFFFF;
        }}
        """


# Синглтон
_theme_manager = None


def get_theme_manager():
    global _theme_manager
    if _theme_manager is None:
        _theme_manager = ThemeManager()
    return _theme_manager
