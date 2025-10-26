# 🖥️ Desktop Client: Миграция на Cookie-Based Authentication

## Описание изменений

**Цель:**
Интегрировать Desktop Client (zenzefi_client) с новым cookie-based authentication backend.

**Что меняется:**
1. При входе клиент отправляет токен на backend `/authenticate` endpoint
2. Backend устанавливает HTTP-only cookie
3. Все последующие запросы автоматически содержат cookie
4. JavaScript перехватчики больше не нужны (или упрощены)

---

## 📋 План изменений

1. ✅ Создать authentication flow при запуске прокси
2. ✅ Добавить HTML страницу для установки cookie
3. ✅ Упростить/удалить JavaScript перехватчики
4. ✅ Обновить UI для отображения статуса cookie
5. ✅ Добавить logout функционал

---

## 🔧 Шаг 1: Создание Auth Manager

### Новый файл: `core/auth_manager.py`

```python
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
```

---

## 🔧 Шаг 2: Модификация ZenzefiProxy

### Файл: `core/proxy_manager.py`

**Добавить в начало файла:**

```python
from core.auth_manager import get_auth_manager
```

**Добавить в класс `ZenzefiProxy` новый метод:**

```python
class ZenzefiProxy:
    def __init__(self, local_port, remote_url):
        # ... существующий __init__ код ...
        
        # Добавить auth manager
        self.auth_manager = get_auth_manager(backend_url=remote_url)
        self.access_token = None
    
    async def handle_http(self, request):
        """Handle HTTP requests"""
        
        # Специальная обработка для auth страницы
        if request.path == '/api/v1/proxy' or request.path == '/api/v1/proxy/':
            return await self._serve_auth_page(request)
        
        # ... остальной существующий код handle_http ...
    
    async def _serve_auth_page(self, request):
        """
        Служебная страница для первоначальной аутентификации
        
        Эта страница:
        1. Читает токен из sessionStorage
        2. Отправляет его на backend /authenticate endpoint
        3. Backend устанавливает cookie
        4. Перенаправляет на реальное приложение
        """
        
        # Проверяем есть ли уже токен в query параметрах
        query = request.query
        token = query.get('token', None)
        
        html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Zenzefi Authentication</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    margin: 0;
                    color: white;
                }}
                .container {{
                    background: rgba(255, 255, 255, 0.1);
                    backdrop-filter: blur(10px);
                    padding: 40px;
                    border-radius: 20px;
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
                    text-align: center;
                    max-width: 500px;
                }}
                .spinner {{
                    border: 4px solid rgba(255, 255, 255, 0.3);
                    border-radius: 50%;
                    border-top: 4px solid white;
                    width: 50px;
                    height: 50px;
                    animation: spin 1s linear infinite;
                    margin: 20px auto;
                }}
                @keyframes spin {{
                    0% {{ transform: rotate(0deg); }}
                    100% {{ transform: rotate(360deg); }}
                }}
                .message {{
                    font-size: 18px;
                    margin: 20px 0;
                }}
                .error {{
                    background: rgba(220, 38, 38, 0.8);
                    padding: 15px;
                    border-radius: 10px;
                    margin-top: 20px;
                }}
                .success {{
                    background: rgba(34, 197, 94, 0.8);
                    padding: 15px;
                    border-radius: 10px;
                    margin-top: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🔐 Zenzefi Authentication</h1>
                <div class="spinner" id="spinner"></div>
                <div class="message" id="message">Authenticating...</div>
            </div>
            
            <script>
                const backendUrl = '{self.remote_url}';
                const token = '{token}' || sessionStorage.getItem('zenzefi_token');
                
                async function authenticate() {{
                    const spinner = document.getElementById('spinner');
                    const message = document.getElementById('message');
                    
                    if (!token) {{
                        spinner.style.display = 'none';
                        message.innerHTML = '<div class="error">❌ No token found!<br>Please enter token in the application.</div>';
                        return;
                    }}
                    
                    try {{
                        // Отправляем токен на backend для установки cookie
                        const response = await fetch(`${{backendUrl}}/api/v1/proxy/authenticate`, {{
                            method: 'POST',
                            headers: {{
                                'Content-Type': 'application/json',
                            }},
                            body: JSON.stringify({{ token: token }}),
                            credentials: 'include'  // Важно для cookie
                        }});
                        
                        if (response.ok) {{
                            const data = await response.json();
                            
                            spinner.style.display = 'none';
                            message.innerHTML = `
                                <div class="success">
                                    ✅ Authentication successful!<br>
                                    <small>User ID: ${{data.user_id}}</small><br>
                                    <small>Expires: ${{new Date(data.expires_at).toLocaleString()}}</small><br>
                                    <br>
                                    Redirecting...
                                </div>
                            `;
                            
                            // Перенаправляем на основное приложение через 2 секунды
                            setTimeout(() => {{
                                window.location.href = '{self.remote_url}/';
                            }}, 2000);
                            
                        }} else {{
                            const errorData = await response.json();
                            
                            spinner.style.display = 'none';
                            message.innerHTML = `
                                <div class="error">
                                    ❌ Authentication failed!<br>
                                    <small>${{errorData.detail || 'Unknown error'}}</small>
                                </div>
                            `;
                        }}
                        
                    }} catch (error) {{
                        spinner.style.display = 'none';
                        message.innerHTML = `
                            <div class="error">
                                ❌ Network error!<br>
                                <small>${{error.message}}</small><br>
                                <small>Is backend running at ${{backendUrl}}?</small>
                            </div>
                        `;
                        console.error('Authentication error:', error);
                    }}
                }}
                
                // Запускаем аутентификацию при загрузке
                authenticate();
            </script>
        </body>
        </html>
        """
        
        return web.Response(
            text=html,
            content_type='text/html',
            headers={
                'Cache-Control': 'no-store, no-cache, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        )
```

---

## 🔧 Шаг 3: Обновление ProxyManager

### Файл: `core/proxy_manager.py`

**В методе `start()` добавить сохранение токена:**

```python
class ProxyManager:
    def start(self, local_port=61000, remote_url="https://zenzefi.melxiory.ru", access_token=None):
        """Запуск прокси сервера"""
        
        if self.is_running:
            logger.warning("⚠️ Прокси уже запущен")
            return False
        
        try:
            # ... существующий код проверки порта ...
            
            self.remote_url = remote_url
            self.local_port = local_port
            
            # Сохраняем токен для последующей аутентификации
            if access_token:
                logger.info("🔑 Access token provided, will authenticate on first request")
                # Токен будет использован ZenzefiProxy при первом обращении
            
            # ... остальной существующий код запуска ...
```

---

## 🔧 Шаг 4: Упрощение/Удаление JavaScript перехватчиков

**Cookie работают автоматически, поэтому сложные перехватчики НЕ НУЖНЫ!**

### Опция 1: Удалить перехватчики полностью

Если весь функционал перенесён на cookie, можно удалить:
- `static/zenzefi_proxy.js` (или упростить)
- Вызовы перехватчиков из HTML

### Опция 2: Упростить для логирования

Оставить минимальный скрипт только для debug:

```javascript
// Упрощённый static/zenzefi_proxy.js
(function() {
    'use strict';
    
    console.log('[Zenzefi Proxy] Cookie-based authentication active');
    console.log('[Zenzefi Proxy] No request interceptors needed - cookies work automatically!');
    
    // Опционально: проверка статуса
    fetch('/api/v1/proxy/status', {
        credentials: 'include'  // Включить отправку cookie
    })
    .then(response => response.json())
    .then(data => {
        console.log('[Zenzefi Proxy] Auth status:', data);
        console.log('[Zenzefi Proxy] Authenticated via:', data.authenticated_via);
    })
    .catch(error => {
        console.error('[Zenzefi Proxy] Status check failed:', error);
    });
    
})();
```

---

## 🔧 Шаг 5: Обновление UI

### Файл: `ui/main_window.py`

**Добавить методы для работы с cookie auth:**

```python
from core.auth_manager import get_auth_manager
import asyncio
import webbrowser

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # ... существующий код ...
        
        self.auth_manager = get_auth_manager()
        
    def on_start_proxy_clicked(self):
        """Обработка нажатия кнопки запуска прокси"""
        
        # Получаем токен из UI
        access_token = self.token_input.text().strip()
        
        if not access_token:
            QMessageBox.warning(
                self, 
                "No Token", 
                "Please enter an access token"
            )
            return
        
        # Сохраняем токен в sessionStorage браузера (для совместимости)
        # или просто передаём в URL
        
        # Запускаем прокси
        config = get_config()
        local_port = config.get('proxy.local_port', 61000)
        remote_url = config.get('proxy.remote_url', 'http://localhost:8000')
        
        success = self.proxy_manager.start(
            local_port=local_port,
            remote_url=remote_url,
            access_token=access_token
        )
        
        if success:
            # Открываем браузер на auth странице с токеном
            auth_url = f"https://127.0.0.1:{local_port}/api/v1/proxy?token={access_token}"
            webbrowser.open(auth_url)
            
            logger.info(f"✅ Прокси запущен, открыт браузер для аутентификации")
            
            # Запускаем асинхронную проверку статуса
            asyncio.create_task(self.check_auth_status())
    
    async def check_auth_status(self):
        """Проверить статус аутентификации"""
        await asyncio.sleep(5)  # Подождать пока пользователь аутентифицируется
        
        success, status_data = await self.auth_manager.check_status()
        
        if success:
            logger.info(f"✅ Authenticated: {status_data}")
            
            # Обновить UI для отображения статуса
            self.update_auth_status_ui(status_data)
        else:
            logger.warning("⚠️ Authentication check failed")
    
    def update_auth_status_ui(self, status_data):
        """Обновить UI с информацией об аутентификации"""
        # Добавить labels для отображения:
        # - Authenticated via: cookie/header
        # - User ID
        # - Time remaining
        # - Expires at
        
        if hasattr(self, 'auth_status_label'):
            auth_via = status_data.get('authenticated_via', 'unknown')
            time_remaining = status_data.get('time_remaining_seconds', 0)
            
            hours = time_remaining // 3600
            minutes = (time_remaining % 3600) // 60
            
            self.auth_status_label.setText(
                f"✅ Authenticated via {auth_via} | "
                f"Time remaining: {hours}h {minutes}m"
            )
```

---

## 🔧 Шаг 6: Добавить Logout функционал

### Файл: `ui/main_window.py`

**Добавить кнопку и обработчик logout:**

```python
def setup_ui(self):
    # ... существующий UI код ...
    
    # Добавить кнопку logout
    self.logout_button = QPushButton("🚪 Logout", self)
    self.logout_button.clicked.connect(self.on_logout_clicked)
    # Добавить в layout...

def on_logout_clicked(self):
    """Обработка нажатия кнопки logout"""
    
    reply = QMessageBox.question(
        self,
        'Confirm Logout',
        'Are you sure you want to logout? This will delete the authentication cookie.',
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No
    )
    
    if reply == QMessageBox.Yes:
        # Асинхронный logout
        asyncio.create_task(self.perform_logout())

async def perform_logout(self):
    """Выполнить logout"""
    
    success = await self.auth_manager.logout()
    
    if success:
        logger.info("✅ Logged out successfully")
        
        # Обновить UI
        if hasattr(self, 'auth_status_label'):
            self.auth_status_label.setText("Not authenticated")
        
        QMessageBox.information(
            self,
            "Logged Out",
            "You have been logged out successfully."
        )
    else:
        logger.error("❌ Logout failed")
        
        QMessageBox.warning(
            self,
            "Logout Failed",
            "Failed to logout. Please try again."
        )
```

---

## 🧪 Шаг 7: Тестирование

### 7.1. Запуск клиента

```bash
# В директории zenzefi_client
python main.py
```

### 7.2. Проверка auth flow

1. **Введите access token** в UI
2. **Нажмите "Start Proxy"**
3. **Браузер откроется** на `https://127.0.0.1:61000/api/v1/proxy?token=...`
4. **Проверьте в DevTools:**
   - Application → Cookies → должна быть `zenzefi_access_token`
   - Console → логи аутентификации
5. **Перенаправление** на основное приложение через 2 секунды
6. **Все статические файлы** (CSS/JS/images) должны загружаться ✅

### 7.3. Проверка cookie в браузере

**Chrome DevTools:**
1. F12 → Application → Cookies
2. Выбрать `https://127.0.0.1:61000`
3. Найти `zenzefi_access_token`
4. Проверить атрибуты:
   - ✅ HttpOnly: true
   - ✅ Secure: true
   - ✅ SameSite: None
   - ✅ Path: /api/v1/proxy

### 7.4. Проверка статуса

```python
# В Python console или через UI
import asyncio
from core.auth_manager import get_auth_manager

auth_manager = get_auth_manager("http://localhost:8000")

# Проверить статус
success, data = asyncio.run(auth_manager.check_status())
print(f"Success: {success}")
print(f"Data: {data}")
```

---

## 📝 Шаг 8: Обновление конфигурации

### Файл: `app_data/config.json`

**Добавить настройки backend:**

```json
{
  "application": {
    "theme": "dark",
    "language": "ru"
  },
  "proxy": {
    "local_port": 61000,
    "remote_url": "http://localhost:8000",
    "backend_url": "http://localhost:8000"
  },
  "auth": {
    "auto_authenticate": true,
    "save_token": false
  }
}
```

---

## ✅ Чеклист финальной проверки

Перед релизом проверьте:

- [ ] ✅ `core/auth_manager.py` создан и работает
- [ ] ✅ `ZenzefiProxy._serve_auth_page()` добавлен
- [ ] ✅ UI обновлён для отображения auth статуса
- [ ] ✅ Logout функционал работает
- [ ] ✅ Cookie устанавливается в браузере
- [ ] ✅ Статические файлы загружаются без ошибок
- [ ] ✅ JavaScript перехватчики удалены/упрощены
- [ ] ✅ Тестирование пройдено

---

## 🐛 Troubleshooting

### Проблема: Auth страница не открывается

**Причина:** Прокси не запущен или порт занят

**Решение:**
```bash
# Проверить что прокси запущен
netstat -ano | findstr :61000

# Проверить логи
# В app_data/logs/zenzefi_client.log
```

### Проблема: Cookie не устанавливается

**Причина:** Backend недоступен или CORS настроен неправильно

**Решение:**
```bash
# Проверить доступность backend
curl http://localhost:8000/health

# Проверить CORS headers
curl -v -X POST http://localhost:8000/api/v1/proxy/authenticate \
  -H "Content-Type: application/json" \
  -H "Origin: https://127.0.0.1:61000" \
  -d '{"token": "test"}'
  
# Должны быть headers:
# Access-Control-Allow-Origin: https://127.0.0.1:61000
# Access-Control-Allow-Credentials: true
```

### Проблема: Редирект не работает после auth

**Причина:** Неправильный URL в JavaScript

**Решение:**
Проверить в `_serve_auth_page()`:
```python
window.location.href = '{self.remote_url}/';  # Должен быть правильный URL
```

### Проблема: "Mixed Content" ошибка в Chrome

**Причина:** HTTP backend + HTTPS frontend

**Решение:**
- Либо оба HTTP: `http://localhost:8000` + `http://127.0.0.1:61000`
- Либо оба HTTPS: `https://backend.com:8000` + `https://127.0.0.1:61000`

### Проблема: Cookie не отправляется с fetch()

**Причина:** Забыли `credentials: 'include'`

**Решение:**
```javascript
fetch(url, {
  credentials: 'include'  // ← ОБЯЗАТЕЛЬНО
})
```

---

## 📊 До и После

### До (Header-based):

```
1. User enters token
2. Token saved in sessionStorage
3. JavaScript intercepts ALL requests
4. JavaScript adds X-Access-Token header
5. ❌ <link>/<script> tags DON'T work
6. ❌ Static files return 401 HTML
7. ❌ MIME type errors
```

### После (Cookie-based):

```
1. User enters token
2. Token sent to backend /authenticate
3. Backend validates & sets cookie
4. ✅ Cookie automatically sent with ALL requests
5. ✅ <link>/<script> tags work perfectly
6. ✅ Static files load correctly
7. ✅ No MIME type errors
```

---

## 🎉 Результат

Desktop Client теперь:
- ✅ Автоматически аутентифицируется при запуске
- ✅ Использует безопасные HTTP-only cookies
- ✅ Загружает все статические файлы без ошибок
- ✅ Имеет UI для отображения auth статуса
- ✅ Поддерживает logout
- ✅ Не требует сложных JavaScript перехватчиков

**Следующий шаг:** Production deployment с SSL сертификатами
