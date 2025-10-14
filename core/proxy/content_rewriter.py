# core/proxy/content_rewriter.py
"""Модуль для перезаписи URL в контенте"""

import re
import logging
import hashlib
from typing import Optional

logger = logging.getLogger(__name__)


class ContentRewriter:
    """Класс для перезаписи URL в HTML/CSS/JS контенте"""

    # Предкомпилированные регулярные выражения
    _HTML_ATTR_PATTERN = re.compile(r'(href|src|action)=["\'](/[^"\']*)["\']')
    _CSS_URL_PATTERN = re.compile(r'url\(["\']?(/[^)"\']*)["\']?\)')

    def __init__(self, upstream_url: str, local_url: str, cache_manager=None):
        """
        Инициализация ContentRewriter

        Args:
            upstream_url: URL upstream сервера (например, https://zenzefi.melxiory.ru)
            local_url: Локальный URL прокси (например, https://127.0.0.1:61000)
            cache_manager: Опциональный менеджер кэша для кэширования результатов
        """
        self.upstream_url = upstream_url
        self.local_url = local_url
        self.cache_manager = cache_manager

        # Извлекаем хост из upstream URL
        self.upstream_host = upstream_url.replace('https://', '').replace('http://', '')

        logger.debug(f"ContentRewriter: {upstream_url} → {local_url}")

    def rewrite(self, content: str, content_type: str) -> str:
        """
        Перезаписывает URL в контенте

        Args:
            content: Контент для обработки
            content_type: MIME type контента

        Returns:
            str: Обработанный контент с перезаписанными URL
        """
        # Проверяем кэш если доступен
        if self.cache_manager:
            cache_key = self._generate_cache_key(content, content_type)
            cached = self.cache_manager.get(f"rewrite_{cache_key}")
            if cached:
                logger.debug(f"ContentRewriter: cache hit for {content_type}")
                return cached[0].decode('utf-8')

        # Простые замены строк (самый быстрый способ)
        content = content.replace(self.upstream_url, self.local_url)
        content = content.replace(f'//{self.upstream_host}', f'//{self.local_url.replace("https://", "")}')

        # WebSocket URL замены
        content = content.replace(f'wss://{self.upstream_host}', f'wss://127.0.0.1:61000')
        content = content.replace(f'ws://{self.upstream_host}', f'wss://127.0.0.1:61000')

        # Regex замены для специфичных типов контента
        if 'text/html' in content_type:
            content = self._rewrite_html(content)
        elif 'text/css' in content_type:
            content = self._rewrite_css(content)

        # Кэшируем результат (только небольшие файлы)
        if self.cache_manager and len(content) < 102400:  # < 100KB
            cache_key = self._generate_cache_key(content, content_type)
            self.cache_manager.put(f"rewrite_{cache_key}", (content.encode('utf-8'), {}, 200))

        return content

    def _rewrite_html(self, content: str) -> str:
        """
        Перезаписывает URL в HTML контенте

        Args:
            content: HTML контент

        Returns:
            str: Обработанный HTML
        """
        # Замена атрибутов href, src, action с относительными путями
        content = self._HTML_ATTR_PATTERN.sub(
            rf'\1="{self.local_url}\2"',
            content
        )
        return content

    def _rewrite_css(self, content: str) -> str:
        """
        Перезаписывает URL в CSS контенте

        Args:
            content: CSS контент

        Returns:
            str: Обработанный CSS
        """
        # Замена url() с относительными путями
        content = self._CSS_URL_PATTERN.sub(
            rf'url({self.local_url}\1)',
            content
        )
        return content

    def _generate_cache_key(self, content: str, content_type: str) -> str:
        """
        Генерация ключа кэша для результата перезаписи

        Args:
            content: Контент
            content_type: MIME type

        Returns:
            str: MD5 хеш ключа
        """
        # Для небольших файлов используем полный хеш, для больших - первые 1KB + длина
        if len(content) < 10240:  # 10KB
            return hashlib.md5(f"{content}{content_type}".encode()).hexdigest()
        else:
            return hashlib.md5(f"{content[:1024]}{len(content)}{content_type}".encode()).hexdigest()

    def set_urls(self, upstream_url: str, local_url: str):
        """
        Обновляет URL для перезаписи

        Args:
            upstream_url: Новый upstream URL
            local_url: Новый локальный URL
        """
        self.upstream_url = upstream_url
        self.local_url = local_url
        self.upstream_host = upstream_url.replace('https://', '').replace('http://', '')
        logger.info(f"ContentRewriter URLs updated: {upstream_url} → {local_url}")