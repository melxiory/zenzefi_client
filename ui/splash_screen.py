# ui/splash_screen.py
import logging
from PySide6.QtWidgets import QSplashScreen
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont

logger = logging.getLogger(__name__)


class SplashScreen(QSplashScreen):
    """Экран загрузки с индикатором прогресса в стиле Mercedes-Benz"""

    def __init__(self):
        # Создаем пустой pixmap для фона
        pixmap = QPixmap(500, 300)
        super().__init__(pixmap, Qt.WindowStaysOnTopHint)

        self.progress = 0
        self.message = "Инициализация..."

        # Загружаем цвета темы
        self._load_colors()

    def _load_colors(self):
        """Загружает цвета из текущей темы"""
        try:
            # Сначала пытаемся загрузить тему из конфига
            from core.config_manager import get_config
            config = get_config()
            current_theme = config.get('application.theme', 'dark')

            # Загружаем соответствующие цвета
            from ui.colors import COLORS, COLORS_LIGHT
            if current_theme == 'light':
                self.colors = COLORS_LIGHT
            else:
                self.colors = COLORS

            logger.debug(f"Splash screen загружен с темой: {current_theme}")
        except Exception as e:
            # Fallback на темную тему если не удалось загрузить
            logger.warning(f"Не удалось загрузить тему для splash: {e}")
            from ui.colors import COLORS
            self.colors = COLORS

    def showMessage(self, message, progress=None):
        """Показать сообщение с опциональным прогрессом"""
        self.message = message
        if progress is not None:
            self.progress = progress
        self.repaint()
        logger.debug(f"Splash: {message} ({self.progress}%)")

    def drawContents(self, painter: QPainter):
        """Отрисовка содержимого splash screen в стиле Mercedes-Benz"""
        # Заливаем фон - используем primary_bg вместо header_bg для поддержки светлой темы
        painter.fillRect(0, 0, 500, 300, QColor(self.colors['primary_bg']))

        # Рисуем рамку
        painter.setPen(QColor(self.colors['accent_blue']))
        painter.drawRect(0, 0, 499, 299)

        # === ЗАГОЛОВОК ===
        painter.setPen(QColor(self.colors['text_primary']))
        painter.setFont(QFont("Segoe UI", 24, QFont.Bold))
        painter.drawText(30, 60, "Zenzefi Client")

        # === ПОДЗАГОЛОВОК ===
        painter.setPen(QColor(self.colors['accent_blue']))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(30, 85, "HTTPS Proxy Manager")

        # === ТЕКУЩЕЕ СООБЩЕНИЕ ===
        painter.setFont(QFont("Segoe UI", 10))
        painter.setPen(QColor(self.colors['text_secondary']))
        painter.drawText(30, 130, self.message)

        # === ПРОГРЕСС БАР ===
        bar_x = 30
        bar_y = 160
        bar_width = 440
        bar_height = 24

        # Фон прогресс бара
        painter.setPen(QColor(self.colors['border_dark']))
        painter.setBrush(QColor(self.colors['secondary_bg']))
        painter.drawRect(bar_x, bar_y, bar_width, bar_height)

        # Заполненная часть
        if self.progress > 0:
            fill_width = int((bar_width * self.progress) / 100)
            # Градиент от accent_blue к success
            if self.progress < 100:
                painter.setPen(QColor(self.colors['accent_blue']))
                painter.setBrush(QColor(self.colors['accent_blue']))
            else:
                painter.setPen(QColor(self.colors['success']))
                painter.setBrush(QColor(self.colors['success']))
            painter.drawRect(bar_x, bar_y, fill_width, bar_height)

        # Текст процента (внутри бара)
        painter.setPen(QColor(self.colors['text_primary']))
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        text_rect = painter.boundingRect(bar_x, bar_y, bar_width, bar_height, Qt.AlignCenter, f"{self.progress}%")
        painter.drawText(text_rect, Qt.AlignCenter, f"{self.progress}%")

        # === НИЖНЯЯ ИНФОРМАЦИЯ ===
        # Версия
        painter.setPen(QColor(self.colors['text_secondary']))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(30, 270, "Version 1.0.0")

        # Mercedes-Benz стиль - три звезды
        painter.setPen(QColor(self.colors['accent_silver']))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(420, 270, "★ ★ ★")