# ui/icons.py
from pathlib import Path
from PySide6.QtGui import QIcon, QPixmap, Qt


class IconManager:
    def __init__(self):
        self.resources_dir = Path("resources").absolute()

    def get_icon(self, icon_name):
        """Возвращает иконку по имени файла"""
        icon_path = self.resources_dir / icon_name
        if icon_path.exists():
            return QIcon(str(icon_path))
        else:
            # Fallback - создаем простую иконку если файл не найден
            pixmap = QPixmap(16, 16)
            if "green" in icon_name:
                pixmap.fill(Qt.green)
            elif "red" in icon_name:
                pixmap.fill(Qt.red)
            else:
                pixmap.fill(Qt.blue)
            return QIcon(pixmap)

    def get_pixmap(self, icon_name, size=16):
        """Возвращает QPixmap по имени файла"""
        icon_path = self.resources_dir / icon_name
        if icon_path.exists():
            pixmap = QPixmap(str(icon_path))
            return pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            # Fallback
            pixmap = QPixmap(size, size)
            if "green" in icon_name:
                pixmap.fill(Qt.green)
            elif "red" in icon_name:
                pixmap.fill(Qt.red)
            else:
                pixmap.fill(Qt.blue)
            return pixmap


# Синглтон
_icon_manager = None


def get_icon_manager():
    global _icon_manager
    if _icon_manager is None:
        _icon_manager = IconManager()
    return _icon_manager