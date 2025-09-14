#!/usr/bin/env python3
"""
Тестирование NginxManager
"""

import logging
import time
from core.nginx_manager import NginxManager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def main():
    print("🧪 Тестирование NginxManager")
    print("=" * 50)

    # Создаем менеджер
    manager = NginxManager()

    try:
        # Запускаем nginx
        print("🚀 Запускаем nginx...")
        if manager.start():
            print("✅ Nginx успешно запущен!")
            print("🌐 Откройте: https://127.0.0.1:61000")
            print("⏹️  Нажмите Enter для остановки...")

            # Ждем остановки
            input()

        else:
            print("❌ Не удалось запустить nginx")

    except KeyboardInterrupt:
        print("\n🛑 Остановка по Ctrl+C")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Останавливаем nginx
        print("⏹️  Останавливаем nginx...")
        manager.stop()


if __name__ == "__main__":
    main()