# API Usage Examples - Zenzefi Client Proxy

## Endpoint: `/api/v1/proxy/`

Desktop Client проксирует этот endpoint по-разному в зависимости от типа запроса.

---

## 🌐 Для браузера (HTML auth страница)

### Автоматическая аутентификация при запуске прокси

```
https://127.0.0.1:61000/api/v1/proxy?token=YOUR_ACCESS_TOKEN
```

**Что происходит:**
1. Desktop Client открывает эту ссылку в браузере при запуске
2. Показывается красивая HTML страница аутентификации
3. JavaScript отправляет токен на backend `/api/v1/proxy/authenticate`
4. Backend устанавливает HTTP-only cookie
5. Автоматический редирект на приложение через 2 секунды

**Заголовки (автоматически от браузера):**
```
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
```

---

## 📡 Для API клиентов (JSON ответ)

### ❌ НЕПРАВИЛЬНО (получите HTML вместо JSON):

```javascript
// НЕ ДЕЛАЙТЕ ТАК!
const response = await fetch('http://127.0.0.1:8000/api/v1/proxy/');
const data = await response.json(); // ❌ Ошибка! Вернется HTML auth страница
```

### ✅ ПРАВИЛЬНО - Вариант 1: Используйте `/status` endpoint

```javascript
// Проверка статуса аутентификации
const response = await fetch('http://127.0.0.1:8000/api/v1/proxy/status', {
    credentials: 'include'  // Важно! Отправляет cookie
});

const data = await response.json();
console.log(data);
// {
//   "authenticated": true,
//   "authenticated_via": "cookie",
//   "user_id": "123",
//   "expires_at": "2025-10-27T12:00:00Z",
//   "time_remaining_seconds": 3600
// }
```

### ✅ ПРАВИЛЬНО - Вариант 2: Укажите `Accept: application/json`

```javascript
// Запрос к корневому endpoint с правильным заголовком
const response = await fetch('http://127.0.0.1:8000/api/v1/proxy/', {
    headers: {
        'Accept': 'application/json'
    },
    credentials: 'include'
});

const data = await response.json();
// Backend вернет JSON (Desktop Client проксирует запрос как есть)
```

---

## 🔐 Процесс cookie аутентификации

### Шаг 1: Установить cookie

```javascript
const response = await fetch('http://127.0.0.1:8000/api/v1/proxy/authenticate', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        token: 'YOUR_ACCESS_TOKEN'
    }),
    credentials: 'include'  // КРИТИЧНО! Без этого cookie не установится
});

if (response.ok) {
    const data = await response.json();
    console.log('Authenticated:', data);
    // {
    //   "user_id": "123",
    //   "expires_at": "2025-10-27T12:00:00Z",
    //   "authenticated_via": "cookie"
    // }
}
```

### Шаг 2: Все последующие запросы автоматически включают cookie

```javascript
// Cookie отправляется автоматически!
const response = await fetch('http://127.0.0.1:8000/api/v1/proxy/some-endpoint', {
    credentials: 'include'  // Важно указать
});

// Статические файлы также работают автоматически
<link rel="stylesheet" href="http://127.0.0.1:8000/api/v1/proxy/static/css/main.css">
<script src="http://127.0.0.1:8000/api/v1/proxy/static/js/app.js"></script>
// ✅ Cookie отправляется браузером автоматически, нет ошибок MIME type!
```

### Шаг 3: Logout (удалить cookie)

```javascript
const response = await fetch('http://127.0.0.1:8000/api/v1/proxy/logout', {
    method: 'DELETE',
    credentials: 'include'
});

if (response.ok) {
    console.log('Logged out successfully');
}
```

---

## 🔍 Логика маршрутизации Desktop Client

Desktop Client анализирует запросы к `/api/v1/proxy/` и решает:

| Условие | Действие |
|---------|----------|
| `?token=...` в URL | ➡️ Показать HTML auth страницу |
| `Accept: text/html` (браузер) | ➡️ Показать HTML auth страницу |
| `Accept: application/json` (API) | ➡️ Проксировать на backend → JSON |
| Без заголовка Accept | ➡️ Проксировать на backend |

---

## 💡 Best Practices

### ✅ DO:
- Всегда используйте `credentials: 'include'` для cookie
- Для API запросов указывайте `Accept: application/json`
- Используйте `/status` для проверки аутентификации
- Используйте `/authenticate` для установки cookie
- Используйте `/logout` для удаления cookie

### ❌ DON'T:
- НЕ запрашивайте `/api/v1/proxy/` без заголовка Accept, ожидая JSON
- НЕ забывайте `credentials: 'include'` - без этого cookie не работают
- НЕ используйте X-Access-Token header - это устаревший метод

---

## 🐛 Troubleshooting

### Проблема: Получаю HTML вместо JSON на `/api/v1/proxy/`

**Решение:**
```javascript
// Добавьте заголовок Accept
fetch('/api/v1/proxy/', {
    headers: { 'Accept': 'application/json' },
    credentials: 'include'
})

// ИЛИ используйте специальный endpoint
fetch('/api/v1/proxy/status', {
    credentials: 'include'
})
```

### Проблема: Cookie не отправляется

**Решение:**
```javascript
// Убедитесь, что указали credentials: 'include'
fetch(url, {
    credentials: 'include'  // ← ОБЯЗАТЕЛЬНО!
})
```

### Проблема: Static файлы возвращают 401 или HTML

**Причина:** Cookie не установлен или истек

**Решение:**
1. Сначала аутентифицируйтесь через `/authenticate`
2. Убедитесь, что cookie не истек (проверьте `/status`)
3. При необходимости повторно аутентифицируйтесь

---

## 📊 Сравнение: До и После

### ❌ СТАРЫЙ метод (header-based, НЕ работает):

```javascript
fetch('/api/v1/proxy/static/css/main.css', {
    headers: {
        'X-Access-Token': 'your_token'
    }
})
// ❌ Статические файлы из <link> и <script> НЕ РАБОТАЮТ
// ❌ MIME type errors
```

### ✅ НОВЫЙ метод (cookie-based, РАБОТАЕТ):

```javascript
// 1. Один раз установить cookie
await fetch('/api/v1/proxy/authenticate', {
    method: 'POST',
    body: JSON.stringify({ token: 'your_token' }),
    credentials: 'include'
});

// 2. Все запросы работают автоматически
<link rel="stylesheet" href="/api/v1/proxy/static/css/main.css">
// ✅ Cookie отправляется автоматически
// ✅ MIME type правильный
// ✅ Файлы загружаются без ошибок
```

---

**Вопросы?** Проверьте [CLIENT_COOKIE_AUTH_MIGRATION.md](./CLIENT_COOKIE_AUTH_MIGRATION.md) для деталей миграции.
