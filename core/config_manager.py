import json
import sys
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional
import os

logger = logging.getLogger(__name__)


def get_app_data_dir():
    """Возвращает путь для хранения данных приложения"""
    if getattr(sys, 'frozen', False):
        # В portable режиме используем _MEIPASS для временных файлов
        if hasattr(sys, '_MEIPASS'):
            # Для рабочих файлов (конфиги, логи, сертификаты) используем AppData
            if os.name == 'nt':  # Windows
                appdata_dir = Path(os.getenv('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
                app_data_dir = appdata_dir / 'Zenzefi'
            else:  # Linux/Mac
                app_data_dir = Path.home() / '.config' / 'zenzefi'
        else:
            # Dev режим
            app_data_dir = Path(__file__).parent.parent / 'app_data'
    else:
        # Dev режим
        app_data_dir = Path(__file__).parent.parent / 'app_data'

    app_data_dir.mkdir(parents=True, exist_ok=True)
    return app_data_dir


class ConfigManager:
    def __init__(self):
        self.config_path = self._get_config_path()
        self.config = self._load_config()

    def _get_config_path(self) -> Path:
        """Возвращает путь к файлу конфигурации"""
        config_dir = get_app_data_dir()

        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / 'config.json'

    def _get_default_config(self) -> dict:
        """Возвращает конфигурацию по умолчанию"""
        return {
            'proxy': {
                'enabled': False,
                'local_port': 61000,
                'remote_url': '',
                'backend_url': 'http://localhost:8000',  # Backend server URL
            },

            'application': {
                'auto_start': False,
                'minimize_to_tray': True,
                'start_minimized': False,
                'single_instance': True,
                'show_already_running_message': True,
                'theme': 'dark'
            },

            'ui': {
                'window_width': 800,
                'window_height': 600,
                'window_x': None,  # Позиция окна X (None = center)
                'window_y': None,  # Позиция окна Y (None = center)
            }
        }

    def _load_config(self) -> Dict[str, Any]:
        """Загружает конфигурацию из файла"""
        default_config = self._get_default_config()

        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    # Объединяем с дефолтными значениями
                    return self._deep_merge(default_config, loaded_config)
        except Exception as e:
            logger.error(f"Ошибка загрузки конфига: {e}")

        return default_config

    def _deep_merge(self, base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
        """Рекурсивное объединение словарей"""
        result = base.copy()

        for key, value in update.items():
            if (key in result and
                    isinstance(result[key], dict) and
                    isinstance(value, dict)):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def save(self) -> bool:
        """Сохраняет конфигурацию в файл"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            logger.info("Конфигурация сохранена")
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения конфига: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """Получает значение по ключу (dot notation)"""
        try:
            keys = key.split('.')
            value = self.config

            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default

            return value
        except:
            return default

    def set(self, key: str, value: Any, save: bool = False) -> bool:
        """Устанавливает значение по ключу (dot notation)"""
        try:
            keys = key.split('.')
            config_ref = self.config

            for k in keys[:-1]:
                if k not in config_ref or not isinstance(config_ref[k], dict):
                    config_ref[k] = {}
                config_ref = config_ref[k]

            config_ref[keys[-1]] = value

            if save:
                return self.save()
            return True
        except Exception as e:
            logger.error(f"Ошибка установки значения {key}: {e}")
            return False

    def get_proxy_config(self) -> Dict[str, Any]:
        """Возвращает настройки прокси"""
        return self.get('proxy', {})

    def set_proxy_config(self, config: Dict[str, Any], save: bool = True) -> bool:
        """Устанавливает настройки прокси"""
        return self.set('proxy', config, save)

    def get_app_config(self) -> Dict[str, Any]:
        """Возвращает настройки приложения"""
        return self.get('application', {})

    def reset_to_defaults(self) -> bool:
        """Сбрасывает настройки к значениям по умолчанию"""
        self.config = self._get_default_config()
        return self.save()



# Синглтон для глобального доступа
_config_instance = None


def get_config() -> ConfigManager:
    """Возвращает глобальный экземпляр ConfigManager"""
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigManager()
    return _config_instance