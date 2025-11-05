from ui.theme_manager import get_theme_manager

def get_stylesheet():
    """Возвращает актуальные стили для текущей темы"""
    theme_manager = get_theme_manager()
    return theme_manager.get_stylesheet()