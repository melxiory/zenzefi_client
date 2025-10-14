# core/proxy/cache_manager.py
"""Управление кэшем для прокси-сервера"""

import logging
from collections import OrderedDict
from typing import Optional, Tuple
import hashlib

logger = logging.getLogger(__name__)


class CacheManager:
    """Менеджер кэша с LRU политикой вытеснения"""

    def __init__(self, maxsize: int = 100):
        """
        Инициализация кэш-менеджера

        Args:
            maxsize: Максимальное количество элементов в кэше
        """
        self.cache = OrderedDict()
        self.maxsize = maxsize
        self.hits = 0
        self.misses = 0
        logger.debug(f"CacheManager инициализирован: maxsize={maxsize}")

    def get(self, key: str) -> Optional[Tuple[bytes, dict, int]]:
        """
        Получить элемент из кэша

        Args:
            key: Ключ кэша

        Returns:
            Tuple[bytes, dict, int] или None: (content, headers, status) если найдено
        """
        if key in self.cache:
            self.hits += 1
            # Перемещаем в конец (most recently used)
            self.cache.move_to_end(key)
            logger.debug(f"Cache HIT: {key[:16]}...")
            return self.cache[key]

        self.misses += 1
        logger.debug(f"Cache MISS: {key[:16]}...")
        return None

    def put(self, key: str, value: Tuple[bytes, dict, int]):
        """
        Добавить элемент в кэш

        Args:
            key: Ключ кэша
            value: Tuple[bytes, dict, int] - (content, headers, status)
        """
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value

        # Проверяем лимит и вытесняем старый элемент
        if len(self.cache) > self.maxsize:
            evicted_key = self.cache.popitem(last=False)[0]
            logger.debug(f"Cache EVICT: {evicted_key[:16]}...")

    def clear(self):
        """Очистить весь кэш"""
        size_before = len(self.cache)
        self.cache.clear()
        self.hits = 0
        self.misses = 0
        logger.info(f"Cache cleared: {size_before} items removed")

    def get_stats(self) -> dict:
        """
        Получить статистику кэша

        Returns:
            dict: Словарь со статистикой
        """
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0

        return {
            'size': len(self.cache),
            'maxsize': self.maxsize,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': f"{hit_rate:.1f}%",
            'total_requests': total
        }

    def generate_key(self, path: str, query: str = "") -> str:
        """
        Генерация ключа кэша на основе пути и query string

        Args:
            path: URL path
            query: Query string

        Returns:
            str: MD5 хеш ключа
        """
        full_path = f"{path}?{query}" if query else path
        return hashlib.md5(full_path.encode()).hexdigest()

    def is_cacheable(self, path: str, content_type: str) -> bool:
        """
        Проверка, можно ли кэшировать ресурс

        Args:
            path: URL path
            content_type: MIME type

        Returns:
            bool: True если можно кэшировать
        """
        # Кэшируемые расширения
        cacheable_extensions = {
            '.js', '.css', '.png', '.jpg', '.jpeg', '.gif',
            '.svg', '.woff', '.woff2', '.ttf', '.ico', '.webp'
        }

        path_lower = path.lower()
        for ext in cacheable_extensions:
            if ext in path_lower:
                return True

        # Кэшируемые типы контента
        cacheable_types = ['image/', 'font/', 'text/css', 'application/javascript']
        return any(ct in content_type.lower() for ct in cacheable_types)

    def __len__(self) -> int:
        """Возвращает текущий размер кэша"""
        return len(self.cache)

    def __contains__(self, key: str) -> bool:
        """Проверка наличия ключа в кэше"""
        return key in self.cache