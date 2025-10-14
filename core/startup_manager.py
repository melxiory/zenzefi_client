# core/startup_manager.py
import logging
import threading
from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)


class StartupThread(QThread):
    """Поток для асинхронной инициализации приложения"""
    progress_signal = Signal(str, int)  # message, progress
    finished_signal = Signal(bool, str)  # success, error_message

    def __init__(self):
        super().__init__()
        self.certificate_manager = None
        self.proxy_manager = None

    def run(self):
        """Выполняет инициализацию в фоновом потоке"""
        try:
            logger.info("📋 Начало инициализации в фоновом потоке")

            # Шаг 1: Проверка и создание сертификатов (30%)
            self.progress_signal.emit("Проверка SSL сертификатов...", 10)
            logger.debug("Импорт CertificateManager...")

            from core.certificate_manager import CertificateManager
            logger.debug("CertificateManager импортирован успешно")

            self.certificate_manager = CertificateManager()
            logger.debug("CertificateManager создан")

            logger.debug("Проверка существования сертификатов...")
            if not self.certificate_manager.ensure_certificates_exist():
                error_msg = "Не удалось создать SSL сертификаты"
                logger.error(f"❌ {error_msg}")
                self.finished_signal.emit(False, error_msg)
                return

            logger.info("✅ SSL сертификаты проверены")
            self.progress_signal.emit("SSL сертификаты готовы", 40)

            # Шаг 2: Инициализация менеджера прокси (20%)
            self.progress_signal.emit("Инициализация прокси менеджера...", 50)
            logger.debug("Импорт ProxyManager...")

            from core.proxy_manager import get_proxy_manager
            logger.debug("get_proxy_manager импортирован успешно")

            self.proxy_manager = get_proxy_manager()
            logger.debug(f"ProxyManager создан: {self.proxy_manager}")

            if not self.proxy_manager:
                error_msg = "get_proxy_manager() вернул None"
                logger.error(f"❌ {error_msg}")
                self.finished_signal.emit(False, error_msg)
                return

            logger.info("✅ ProxyManager инициализирован")
            self.progress_signal.emit("Прокси менеджер готов", 70)

            # Шаг 3: Проверка портов (необязательно, быстрая проверка)
            self.progress_signal.emit("Проверка доступности портов...", 80)
            logger.debug("Импорт port_utils...")

            from utils.port_utils import check_port_availability
            logger.debug("Проверка порта 61000...")

            port_available, _ = check_port_availability(61000)
            if port_available:
                logger.info("✅ Порт 61000 доступен")
            else:
                logger.warning("⚠️ Порт 61000 занят, потребуется освобождение при запуске")

            self.progress_signal.emit("Инициализация завершена", 100)
            logger.info("✅ Инициализация завершена успешно")

            # Небольшая задержка чтобы все сигналы успели обработаться
            import time
            time.sleep(0.1)

            # Успех
            logger.info("📤 Отправка сигнала успешного завершения")
            self.finished_signal.emit(True, "")
            logger.info("📤 Сигнал отправлен")

        except Exception as e:
            error_msg = f"Ошибка инициализации: {e}"
            logger.error(error_msg, exc_info=True)
            self.finished_signal.emit(False, error_msg)

    def get_results(self):
        """Возвращает инициализированные объекты"""
        return {
            'certificate_manager': self.certificate_manager,
            'proxy_manager': self.proxy_manager
        }