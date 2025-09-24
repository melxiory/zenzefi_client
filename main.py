# main.py
import sys
import logging
from pathlib import Path
from PySide6.QtWidgets import QApplication
from core.certificate_manager import CertificateManager
from core.nginx_manager import NginxManager
from ui.tray_icon import TrayIcon
from PySide6.QtGui import QIcon
from ui.icons import get_icon_manager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('zenzefi_client.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

def ensure_certificates():
    """Проверяет и создает сертификаты при необходимости"""
    try:
        nginx_dir = Path("nginx").absolute()
        cert_manager = CertificateManager(nginx_dir)
        if cert_manager.ensure_certificates_exist():
            logger.info("✅ Сертификаты готовы")
        else:
            logger.error("❌ Ошибка создания сертификатов")
            return False
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации сертификатов: {e}")
        return False

def main():
    # Создаем приложение
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Устанавливаем иконку приложения
    icon_manager = get_icon_manager()
    app.setWindowIcon(icon_manager.get_icon("window_img.png"))

    # Проверяем сертификаты
    if not ensure_certificates():
        print("❌ Ошибка инициализации сертификатов. Проверьте логи.")
        return 1

    # Создаем единый экземпляр NginxManager
    nginx_manager = NginxManager()

    # Создаем иконку в трее
    tray_icon = TrayIcon(app, nginx_manager)
    tray_icon.show()

    # Показываем главное окно при запуске (опционально)
    if len(sys.argv) > 1 and sys.argv[1] == '--show':
        tray_icon.show_main_window()

    logger.info("✅ Zenzefi Client запущен")

    # Запускаем приложение
    try:
        return app.exec()
    except Exception as e:
        logger.error(f"❌ Ошибка приложения: {e}")
        return 1
    finally:
        # Гарантируем остановку nginx при выходе
        try:
            nginx_manager.stop()
        except:
            pass

if __name__ == "__main__":
    sys.exit(main())