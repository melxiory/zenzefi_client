# core/auth_manager.py
"""
Authentication Manager для работы с cookie-based auth
"""

import aiohttp
import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class AuthManager:
    """Управление аутентификацией с backend"""

    def __init__(self, backend_url: str):
        """
        Инициализация AuthManager

        Args:
            backend_url: URL backend сервера (например, http://localhost:8000)
        """
        self.backend_url = backend_url.rstrip('/')
        self.authenticated = False
        self.auth_data: Optional[Dict[str, Any]] = None

    async def authenticate(self, access_token: str) -> tuple[bool, Optional[str]]:
        """
        Аутентификация с backend и установка cookie

        Args:
            access_token: Access token для аутентификации

        Returns:
            tuple: (успех: bool, ошибка: str или None)
        """
        try:
            auth_url = f"{self.backend_url}/api/v1/proxy/authenticate"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    auth_url,
                    json={"token": access_token},
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=False  # Для локального development
                ) as response:

                    if response.status == 200:
                        self.auth_data = await response.json()
                        self.authenticated = True

                        logger.info(
                            f"✅ Authentication successful: "
                            f"user={self.auth_data.get('user_id')}, "
                            f"expires_at={self.auth_data.get('expires_at')}"
                        )

                        return True, None

                    else:
                        error_data = await response.json()
                        error_msg = error_data.get('detail', f'HTTP {response.status}')

                        logger.error(f"❌ Authentication failed: {error_msg}")

                        return False, error_msg

        except aiohttp.ClientConnectorError as e:
            error_msg = f"Cannot connect to backend: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return False, error_msg

        except aiohttp.ClientError as e:
            error_msg = f"Request error: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return False, error_msg

        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.exception(f"❌ {error_msg}")
            return False, error_msg

    async def check_status(self) -> tuple[bool, Optional[Dict[str, Any]]]:
        """
        Проверить статус аутентификации на backend

        Returns:
            tuple: (успех: bool, данные: dict или None)
        """
        try:
            status_url = f"{self.backend_url}/api/v1/proxy/status"

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    status_url,
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=False
                ) as response:

                    if response.status == 200:
                        data = await response.json()
                        return True, data
                    else:
                        return False, None

        except Exception as e:
            logger.error(f"Failed to check status: {e}")
            return False, None

    async def logout(self) -> bool:
        """
        Logout (удалить cookie на backend)

        Returns:
            bool: Успешность операции
        """
        try:
            logout_url = f"{self.backend_url}/api/v1/proxy/logout"

            async with aiohttp.ClientSession() as session:
                async with session.delete(
                    logout_url,
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=False
                ) as response:

                    if response.status == 200:
                        self.authenticated = False
                        self.auth_data = None
                        logger.info("✅ Logged out successfully")
                        return True
                    else:
                        logger.error(f"❌ Logout failed: HTTP {response.status}")
                        return False

        except Exception as e:
            logger.error(f"Failed to logout: {e}")
            return False

    def is_authenticated(self) -> bool:
        """Проверить локальный статус аутентификации"""
        return self.authenticated

    def get_auth_data(self) -> Optional[Dict[str, Any]]:
        """Получить данные аутентификации"""
        return self.auth_data


# Singleton instance
_auth_manager: Optional[AuthManager] = None


def get_auth_manager(backend_url: str = "http://localhost:8000") -> AuthManager:
    """
    Получить singleton экземпляр AuthManager

    Args:
        backend_url: URL backend сервера

    Returns:
        AuthManager: Singleton instance
    """
    global _auth_manager

    if _auth_manager is None:
        _auth_manager = AuthManager(backend_url)

    return _auth_manager
