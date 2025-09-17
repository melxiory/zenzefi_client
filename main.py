# main.py
import logging
import time
from pathlib import Path
from core.certificate_manager import CertificateManager
from core.nginx_manager import NginxManager
from core.config_manager import get_config

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('test.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)


def test_certificate_manager():
    """Тестирование менеджера сертификатов"""
    print("🔐 Тестирование CertificateManager...")

    nginx_dir = Path("nginx").absolute()
    cert_manager = CertificateManager(nginx_dir)

    # Проверяем существование сертификатов
    if cert_manager.check_certificates_exist():
        print("✅ Сертификаты уже существуют")
        # Показываем информацию о сертификате
        info = cert_manager.get_certificate_info()
        print(f"📄 Информация о сертификате: {info}")
    else:
        print("⚠️ Сертификаты не найдены, генерируем...")
        if cert_manager.generate_self_signed_certificate():
            print("✅ Сертификаты успешно созданы")
        else:
            print("❌ Ошибка создания сертификатов")
            return False

    # Проверяем метод ensure
    if cert_manager.ensure_certificates_exist():
        print("✅ Сертификаты гарантированно существуют")
    else:
        print("❌ Ошибка гарантии существования сертификатов")

    return True


def test_config_manager():
    """Тестирование менеджера конфигурации"""
    print("\n⚙️ Тестирование ConfigManager...")

    config = get_config()

    # Чтение конфигурации
    proxy_config = config.get_proxy_config()
    print(f"📋 Конфигурация прокси: {proxy_config}")

    # Изменение конфигурации
    new_port = 61000
    config.set('proxy.local_port', new_port)
    print(f"🔄 Изменен порт на: {new_port}")

    # Проверка валидации
    is_valid, message = config.validate_proxy_config()
    print(f"✅ Валидация конфигурации: {is_valid} - {message}")

    # Сохранение
    if config.save():
        print("💾 Конфигурация сохранена")
    else:
        print("❌ Ошибка сохранения конфигурации")

    return True


def test_nginx_manager():
    """Тестирование менеджера nginx"""
    print("\n🌐 Тестирование NginxManager...")

    nginx_manager = NginxManager()

    # Проверяем статус
    status = nginx_manager.get_status()
    print(f"📊 Статус nginx: {status}")

    # Запускаем nginx
    print("🚀 Запуск nginx...")
    if nginx_manager.start():
        print("✅ Nginx запущен успешно")

        # Даем время поработать
        time.sleep(5)

        # Проверяем статус после запуска
        status = nginx_manager.get_status()
        print(f"📊 Статус после запуска: {status}")

        # Останавливаем
        print("🛑 Остановка nginx...")
        if nginx_manager.stop():
            print("✅ Nginx остановлен успешно")
        else:
            print("❌ Ошибка остановки nginx")
            return False
    else:
        print("❌ Ошибка запуска nginx")
        return False

    return True


def main():
    """Основная функция тестирования"""
    print("🧪 Запуск тестирования всех модулей Zenzefi Client\n")

    # Тестируем менеджер сертификатов
    if not test_certificate_manager():
        print("❌ Тест CertificateManager не пройден")
        return

    # Тестируем менеджер конфигурации
    if not test_config_manager():
        print("❌ Тест ConfigManager не пройден")
        return

    # Тестируем менеджер nginx
    if not test_nginx_manager():
        print("❌ Тест NginxManager не пройден")
        return

    print("\n🎉 Все тесты пройдены успешно!")


if __name__ == "__main__":
    main()