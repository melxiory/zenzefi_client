# ui/icons.py
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt

def get_tray_icon(running=False):
    """Возвращает иконку для трея"""
    pixmap = QPixmap(16, 16)
    if running:
        pixmap.fill(Qt.green)  # Зеленая когда запущено
    else:
        pixmap.fill(Qt.red)    # Красная когда остановлено
    return QIcon(pixmap)