# main.py
import sys
import logging
from PySide6.QtWidgets import QApplication, QMessageBox
from ui.icons import get_icon_manager


def setup_logging():
    """Настраивает логирование ДО всех операций"""
    from core.config_manager import get_app_data_dir
    app_data_dir = get_app_data_dir()
    logs_dir = app_data_dir / "logs"
    logs_dir.mkdir(exist_ok=True)

    log_file = logs_dir / "zenzefi_client.log"

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding='utf-8')
        ]
    )


# НАСТРАИВАЕМ ЛОГИРОВАНИЕ САМЫМ ПЕРВЫМ ДЕЛОМ
setup_logging()
logger = logging.getLogger(__name__)


def setup_exception_handler():
    """Настраивает глобальный обработчик исключений"""

    def exception_handler(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logger.critical("Необработанное исключение:",
                        exc_info=(exc_type, exc_value, exc_traceback))

        try:
            app = QApplication.instance()
            if app:
                QMessageBox.critical(
                    None,
                    "Критическая ошибка",
                    f"Произошла критическая ошибка:\n{exc_value}\n\n"
                    "Подробности в лог-файле."
                )
        except:
            pass

    sys.excepthook = exception_handler


def main():
    """Основная функция приложения"""
    logger.info("🔍 Проверка единственного экземпляра...")

    # Проверяем единственный экземпляр
    from utils.single_instance import get_single_instance

    instance_lock = get_single_instance()

    if not instance_lock.lock():
        show_already_running_message()
        return 1

    app = None
    try:
        # Создаем приложение
        app = QApplication(sys.argv)
        app.setApplicationName("Zenzefi Client")
        app.setApplicationVersion("1.0.0")
        app.setQuitOnLastWindowClosed(False)

        # Настраиваем обработчик исключений
        setup_exception_handler()

        logger.info("🚀 Запуск Zenzefi Client")

        # Инициализация менеджеров
        from core.proxy_manager import get_proxy_manager
        from core.certificate_manager import CertificateManager

        # Проверяем сертификаты
        cert_manager = CertificateManager()
        if not cert_manager.ensure_certificates_exist():
            logger.error("❌ Не удалось создать сертификаты")
            QMessageBox.critical(
                None,
                "Ошибка",
                "Не удалось создать SSL сертификаты. Приложение будет закрыто."
            )
            instance_lock.unlock()
            return 1

        # Создаем менеджер прокси
        proxy_manager = get_proxy_manager()

        # Создаем и показываем главное окно или трей
        from core.config_manager import get_config
        config = get_config()
        start_minimized = config.get('application.start_minimized', False)

        main_window = None
        if not start_minimized:
            from ui.main_window import MainWindow
            main_window = MainWindow(proxy_manager)
            main_window.show()

        # Создаем иконку в трее
        from ui.tray_icon import TrayIcon
        tray_icon = TrayIcon(app, proxy_manager)
        tray_icon.main_window = main_window
        tray_icon.show()

        logger.info("✅ Приложение запущено успешно")

        # Обработчик завершения приложения
        def cleanup():
            logger.info("🛑 Завершение работы приложения")
            try:
                proxy_manager.stop()
            except Exception as e:
                logger.error(f"Ошибка при остановке прокси: {e}")

            # Освобождаем блокировку приложения
            instance_lock.unlock()

        app.aboutToQuit.connect(cleanup)

        # Запускаем главный цикл
        return_code = app.exec()

        return return_code

    except Exception as e:
        logger.critical(f"Критическая ошибка при запуске: {e}")

        # Освобождаем блокировку при ошибке
        if instance_lock:
            instance_lock.unlock()

        if app:
            QMessageBox.critical(
                None,
                "Ошибка запуска",
                f"Не удалось запустить приложение:\n{e}"
            )
        return 1


def show_already_running_message():
    """Показывает сообщение о том, что приложение уже запущено"""
    try:
        # Создаем временное приложение только для показа сообщения
        temp_app = QApplication([])
        icon_manager = get_icon_manager()
        temp_app.setWindowIcon(icon_manager.get_icon("window_img.png"))
        QMessageBox.information(
            None,
            "Zenzefi Client",
            "Приложение уже запущено.\n\n"
            "Проверьте системный трей."
        )
        temp_app.quit()
    except Exception as e:
        print(f"Ошибка при показе сообщения: {e}")

    logger.info("⚠️ Попытка запуска второго экземпляра - завершение")


if __name__ == "__main__":
    sys.exit(main())