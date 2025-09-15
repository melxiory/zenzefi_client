#!/usr/bin/env python3
"""
Тестирование ConfigManager + NginxManager
"""

import logging
import time
from pathlib import Path
from core.config_manager import get_config
from core.nginx_manager import NginxManager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_config_manager():
    """Тестирование ConfigManager"""
    print("🧪 Тестирование ConfigManager")
    print("=" * 50)

    config = get_config()

    # 1. Показываем текущие настройки
    print("📋 Текущие настройки:")
    print(f"   Порт: {config.get('proxy.local_port')}")
    print(f"   URL: {config.get('proxy.remote_url')}")
    print(f"   Автозапуск: {config.get('application.auto_start')}")

    # 2. Валидация настроек
    print("\n🔍 Валидация настроек:")
    is_valid, message = config.validate_proxy_config()
    print(f"   {message}")


    # 4. Сохраняем настройки
    if config.save():
        print("   ✅ Настройки сохранены")
    else:
        print("   ❌ Ошибка сохранения настроек")
        return False

    return True


def test_nginx_manager():
    """Тестирование NginxManager"""
    print("\n🚀 Тестирование NginxManager")
    print("=" * 50)

    config = get_config()
    manager = NginxManager()

    # Получаем настройки из конфига
    local_port = config.get('proxy.local_port', 61000)
    remote_url = config.get('proxy.remote_url', 'https://zenzefi.melxiory.ru')

    print(f"📍 Настройки из конфига:")
    print(f"   Локальный порт: {local_port}")
    print(f"   Удаленный URL: {remote_url}")

    # Запускаем nginx
    print(f"\n🔄 Запуск nginx...")
    if manager.start(local_port, remote_url):
        print("✅ Nginx успешно запущен!")
        print(f"🌐 Откройте: https://127.0.0.1:{local_port}")

        # Добавляем в историю
        config.add_connection_history(True, "Успешный тестовый запуск")

        # Ждем
        print("⏳ Nginx работает 10 секунд...")
        time.sleep(100)

        # Останавливаем
        print("\n🛑 Останавливаем nginx...")
        manager.stop()

        return True
    else:
        print("❌ Не удалось запустить nginx")
        config.add_connection_history(False, "Ошибка запуска nginx")
        return False


def show_history():
    """Показывает историю подключений"""
    print("\n📊 История подключений:")
    print("=" * 50)

    config = get_config()
    history = config.get('history.connection_history', [])

    if not history:
        print("   История пуста")
        return

    for i, entry in enumerate(history[:5]):  # Последние 5 записей
        from datetime import datetime
        timestamp = datetime.fromtimestamp(entry['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
        status = "✅" if entry['success'] else "❌"
        print(f"   {i + 1}. {timestamp} {status} {entry['message']}")


def main():
    """Основная функция тестирования"""
    print("🧪 Комплексное тестирование ConfigManager + NginxManager")
    print("=" * 60)

    try:
        # Тестируем ConfigManager
        if not test_config_manager():
            return

        # Тестируем NginxManager
        test_nginx_manager()

        # Показываем историю
        show_history()

        # Сохраняем финальные настройки
        config = get_config()
        config.set('application.last_test', time.time())
        config.save()

        print("\n" + "=" * 60)
        print("🎉 Тестирование завершено!")
        print("📁 Конфиг сохранен в:", get_config().config_path)

    except KeyboardInterrupt:
        print("\n🛑 Остановка по Ctrl+C")
        # Останавливаем nginx если был запущен
        manager = NginxManager()
        manager.stop()
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()