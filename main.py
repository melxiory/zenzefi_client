# test_all_modules.py
import logging
import time
from pathlib import Path
from core.certificate_manager import CertificateManager
from core.nginx_manager import NginxManager
from core.config_manager import get_config
from utils.process_manager import get_process_manager
from utils.port_utils import is_port_in_use, get_process_using_port, check_port_availability
import requests

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('test_suite.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)


def test_certificate_manager():
    """Тестирование менеджера сертификатов"""
    print("\n" + "=" * 60)
    print("🔐 ТЕСТИРОВАНИЕ CERTIFICATE MANAGER")
    print("=" * 60)

    nginx_dir = Path("nginx").absolute()
    cert_manager = CertificateManager(nginx_dir)

    # Тест 1: Проверка существования сертификатов
    print("\n1. Проверка существования сертификатов...")
    if cert_manager.check_certificates_exist():
        print("   ✅ Сертификаты уже существуют")
    else:
        print("   ⚠️ Сертификаты не найдены")

    # Тест 2: Генерация сертификатов
    print("\n2. Генерация сертификатов...")
    if cert_manager.generate_self_signed_certificate():
        print("   ✅ Сертификаты успешно созданы")
    else:
        print("   ❌ Ошибка создания сертификатов")
        return False

    # Тест 3: Гарантия существования
    print("\n3. Гарантия существования сертификатов...")
    if cert_manager.ensure_certificates_exist():
        print("   ✅ Сертификаты гарантированно существуют")
    else:
        print("   ❌ Ошибка гарантии существования")
        return False

    # Тест 4: Информация о сертификате
    print("\n4. Информация о сертификате...")
    cert_info = cert_manager.get_certificate_info()
    print(f"   📄 Информация: {cert_info}")

    # Тест 5: Срок действия
    print("\n5. Срок действия сертификата...")
    days_left = cert_manager.get_certificate_days_remaining()
    print(f"   📅 Дней до истечения: {days_left}")

    return True


def test_port_utils():
    """Тестирование утилит для работы с портами"""
    print("\n" + "=" * 60)
    print("🚪 ТЕСТИРОВАНИЕ PORT UTILS")
    print("=" * 60)

    test_port = 61000

    # Тест 1: Проверка порта
    print(f"\n1. Проверка порта {test_port}...")
    port_in_use = is_port_in_use(test_port)
    print(f"   📍 Порт занят: {port_in_use}")

    # Тест 2: Информация о процессе
    print("\n2. Информация о процессе на порту...")
    process_info = get_process_using_port(test_port)
    if process_info:
        print(f"   🔍 Процесс: {process_info}")
    else:
        print("   ℹ️  Процесс не найден или порт свободен")

    # Тест 3: Проверка доступности
    print("\n3. Проверка доступности порта...")
    available, message = check_port_availability(test_port)
    print(f"   📊 Доступен: {available}")
    print(f"   💬 Сообщение: {message}")

    return True


def test_process_manager():
    """Тестирование менеджера процессов"""
    print("\n" + "=" * 60)
    print("⚙️ ТЕСТИРОВАНИЕ PROCESS MANAGER")
    print("=" * 60)

    process_manager = get_process_manager()

    # Тест 1: Права администратора
    print("\n1. Проверка прав администратора...")
    admin_status = process_manager.get_admin_status()
    print(f"   👑 Администратор: {admin_status['is_admin']}")
    print(f"   💬 {admin_status['message']}")

    # Тест 2: Информация о процессах nginx
    print("\n2. Поиск процессов nginx...")
    nginx_processes = process_manager.get_process_info("nginx.exe")
    print(f"   🔍 Найдено процессов: {len(nginx_processes)}")
    for proc in nginx_processes:
        print(f"   • PID: {proc['pid']}, Имя: {proc['name']}, Наш: {proc['is_our_process']}")

    # Тест 3: Проверка запущенных процессов
    print("\n3. Проверка запущенных процессов...")
    is_running = process_manager.is_process_running("nginx.exe")
    print(f"   🚦 Nginx запущен: {is_running}")

    return True


def test_nginx_manager():
    """Тестирование менеджера nginx"""
    print("\n" + "=" * 60)
    print("🌐 ТЕСТИРОВАНИЕ NGINX MANAGER")
    print("=" * 60)

    nginx_manager = NginxManager()

    # Тест 1: Статус перед запуском
    print("\n1. Статус перед запуском...")
    status = nginx_manager.get_status()
    print(f"   📊 Запущен: {status['running']}")
    print(f"   📍 Порт доступен: {status['port_available']}")
    if 'port_message' in status:
        print(f"   💬 Сообщение: {status['port_message']}")

    # Тест 2: Остановка (на всякий случай)
    print("\n2. Предварительная остановка...")
    if nginx_manager.stop():
        print("   ✅ Nginx остановлен")
    else:
        print("   ℹ️ Nginx не был запущен")

    # Тест 3: Запуск nginx
    print("\n3. Запуск nginx...")
    if nginx_manager.start():
        print("   ✅ Nginx успешно запущен")

        # Даем время поработать
        time.sleep(2)

        # Тест 4: Статус после запуска
        print("\n4. Статус после запуска...")
        status = nginx_manager.get_status()
        print(f"   📊 Запущен: {status['running']}")
        print(f"   📍 Порт доступен: {status['port_available']}")

        # Тест 5: Проверка работы порта
        print("\n5. Проверка работы порта...")
        try:
            response = requests.get(f"https://127.0.0.1:61000", verify=False, timeout=5)
            print(f"   🌐 HTTP статус: {response.status_code}")
        except requests.exceptions.SSLError:
            print("   🔒 SSL ошибка (ожидаемо для self-signed cert)")
        except requests.exceptions.ConnectionError:
            print("   ❌ Не удалось подключиться")
        except Exception as e:
            print(f"   ⚠️ Ошибка подключения: {e}")

        # Тест 6: Остановка nginx
        print("\n6. Остановка nginx...")
        if nginx_manager.stop():
            print("   ✅ Nginx успешно остановлен")
        else:
            print("   ❌ Ошибка остановки nginx")
            return False

    else:
        print("   ❌ Ошибка запуска nginx")
        return False

    return True


def test_config_manager():
    """Тестирование менеджера конфигурации"""
    print("\n" + "=" * 60)
    print("⚙️ ТЕСТИРОВАНИЕ CONFIG MANAGER")
    print("=" * 60)

    config = get_config()

    # Тест 1: Чтение конфигурации
    print("\n1. Чтение конфигурации...")
    proxy_config = config.get_proxy_config()
    print(f"   📋 Конфигурация прокси: {proxy_config}")

    # Тест 2: Изменение настроек
    print("\n2. Изменение настроек...")
    new_port = 61001
    config.set('proxy.local_port', new_port, save=False)
    print(f"   🔧 Изменен порт на: {new_port}")

    # Тест 3: Валидация конфигурации
    print("\n3. Валидация конфигурации...")
    is_valid, message = config.validate_proxy_config()
    print(f"   ✅ Валидность: {is_valid}")
    print(f"   💬 Сообщение: {message}")

    # Тест 4: Восстановление настроек
    print("\n4. Восстановление настроек...")
    config.set('proxy.local_port', 61000, save=False)
    print("   🔄 Настройки восстановлены")

    # Тест 5: Сохранение конфигурации
    print("\n5. Сохранение конфигурации...")
    if config.save():
        print("   💾 Конфигурация сохранена")
    else:
        print("   ❌ Ошибка сохранения конфигурации")

    return True


def run_comprehensive_test():
    """Запуск комплексного тестирования"""
    print("🧪 ЗАПУСК КОМПЛЕКСНОГО ТЕСТИРОВАНИЯ")
    print("=" * 60)

    tests = [
        ("Certificate Manager", test_certificate_manager),
        ("Port Utils", test_port_utils),
        ("Process Manager", test_process_manager),
        ("Config Manager", test_config_manager),
        ("Nginx Manager", test_nginx_manager),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            print(f"\n🚀 Запуск теста: {test_name}")
            success = test_func()
            results.append((test_name, success))
            status = "✅ ПРОЙДЕН" if success else "❌ ПРОВАЛЕН"
            print(f"   {status}")
        except Exception as e:
            results.append((test_name, False))
            print(f"   ❌ ОШИБКА: {e}")
            logger.error(f"Ошибка в тесте {test_name}: {e}")

    # Вывод результатов
    print("\n" + "=" * 60)
    print("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
    print("=" * 60)

    passed = 0
    for test_name, success in results:
        status = "✅ ПРОЙДЕН" if success else "❌ ПРОВАЛЕН"
        print(f"{test_name:20} {status}")
        if success:
            passed += 1

    print(f"\n📈 Итого: {passed}/{len(results)} тестов пройдено")

    if passed == len(results):
        print("🎉 Все тесты пройдены успешно!")
        return True
    else:
        print("⚠️  Некоторые тесты не пройдены. Проверьте логи.")
        return False


if __name__ == "__main__":
    # Проверка необходимых зависимостей
    try:
        import psutil
        import cryptography

        print("✅ Все зависимости установлены")
    except ImportError as e:
        print(f"❌ Отсутствует зависимость: {e}")
        print("Установите: pip install psutil cryptography")
        exit(1)

    # Запуск тестов
    success = run_comprehensive_test()

    if success:
        print("\n🎉 Тестирование завершено успешно!")
    else:
        print("\n❌ Тестирование завершено с ошибками!")
        print("Проверьте файл test_suite.log для детальной информации")

    exit(0 if success else 1)