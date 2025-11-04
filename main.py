# main.py
import sys
import logging
from PySide6.QtWidgets import QApplication, QMessageBox
from ui.icons import get_icon_manager


def setup_logging():
    """Настраивает логирование ДО всех операций с ротацией"""
    from core.config_manager import get_app_data_dir
    from logging.handlers import RotatingFileHandler

    app_data_dir = get_app_data_dir()
    logs_dir = app_data_dir / "logs"
    logs_dir.mkdir(exist_ok=True)

    log_file = logs_dir / "zenzefi_client.log"

    # Ротирующий обработчик: макс 5MB, 5 резервных копий
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    )

    logging.basicConfig(
        level=logging.INFO,
        handlers=[console_handler, file_handler]
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
    splash = None
    startup_thread = None

    try:
        # Создаем приложение
        app = QApplication(sys.argv)
        app.setApplicationName("Zenzefi Client")
        app.setApplicationVersion("1.0.0")
        app.setQuitOnLastWindowClosed(False)

        # Настраиваем обработчик исключений
        setup_exception_handler()

        logger.info("🚀 Запуск Zenzefi Client")

        # Показываем splash screen
        from ui.splash_screen import SplashScreen
        splash = SplashScreen()
        splash.show()
        app.processEvents()  # Обновляем GUI

        # Запускаем асинхронную инициализацию
        from core.startup_manager import StartupThread
        startup_thread = StartupThread()

        # Контейнер для результатов
        init_results = {'success': False, 'error': None, 'objects': None}

        def on_progress(message, progress):
            """Обработчик прогресса инициализации"""
            splash.showMessage(message, progress)
            app.processEvents()

        def on_finished(success, error_message):
            """Обработчик завершения инициализации"""
            logger.info(f"📥 Получен сигнал завершения: success={success}, error='{error_message}'")
            init_results['success'] = success
            init_results['error'] = error_message
            if success:
                init_results['objects'] = startup_thread.get_results()
                logger.info(f"📦 Результаты инициализации: {init_results['objects']}")

        startup_thread.progress_signal.connect(on_progress)
        startup_thread.finished_signal.connect(on_finished)
        startup_thread.start()

        # Ждем завершения инициализации с обработкой событий Qt
        logger.info("⏳ Ожидание завершения потока инициализации...")
        while startup_thread.isRunning():
            app.processEvents()  # Обрабатываем сигналы Qt
            startup_thread.wait(10)  # Ждем 10ms

        # Еще раз обрабатываем события чтобы все сигналы дошли
        app.processEvents()
        logger.info(f"✅ Поток завершен. Результаты: success={init_results['success']}, error={init_results['error']}, objects={init_results['objects']}")

        # Проверяем результат
        if not init_results['success']:
            if splash:
                splash.close()
            error_msg = init_results['error'] or "Неизвестная ошибка инициализации"
            logger.error(f"❌ {error_msg}")
            QMessageBox.critical(
                None,
                "Ошибка инициализации",
                error_msg
            )
            instance_lock.unlock()
            return 1

        # Получаем инициализированные объекты
        if not init_results['objects']:
            if splash:
                splash.close()
            error_msg = "Не удалось инициализировать компоненты приложения"
            logger.error(f"❌ {error_msg}")
            QMessageBox.critical(
                None,
                "Ошибка инициализации",
                error_msg
            )
            instance_lock.unlock()
            return 1

        proxy_manager = init_results['objects'].get('proxy_manager')
        if not proxy_manager:
            if splash:
                splash.close()
            error_msg = "Не удалось инициализировать ProxyManager"
            logger.error(f"❌ {error_msg}")
            QMessageBox.critical(
                None,
                "Ошибка инициализации",
                error_msg
            )
            instance_lock.unlock()
            return 1

        # Загружаем конфигурацию
        splash.showMessage("Загрузка конфигурации...", 90)
        app.processEvents()

        from core.config_manager import get_config
        config = get_config()
        start_minimized = config.get('application.start_minimized', False)

        # Создаем иконку в трее
        splash.showMessage("Создание системного трея...", 95)
        app.processEvents()

        from ui.tray_icon import TrayIcon
        tray_icon = TrayIcon(app, proxy_manager)
        tray_icon.show()

        # MainWindow создается только если не запущен в свернутом виде
        # или при клике на трее (lazy loading)
        if not start_minimized:
            splash.showMessage("Загрузка главного окна...", 98)
            app.processEvents()

            from ui.main_window import MainWindow
            main_window = MainWindow(proxy_manager)
            main_window.apply_theme()  # Применяем тему ДО show()
            main_window.show()
            tray_icon.main_window = main_window
        else:
            logger.info("🚀 Запуск в свернутом режиме, окно будет создано по требованию")

        # Закрываем splash screen
        splash.showMessage("Готово!", 100)
        app.processEvents()

        splash.finish(tray_icon if start_minimized else main_window)

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