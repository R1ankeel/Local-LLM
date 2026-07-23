# Local AI Chat

Локальный AI-чат для домашней сети. На этапе 0.5 добавлены production SPA fallback для `/login` и `/chat/:chatId`, мобильный drawer со списком чатов и глобальная активная модель Ollama для всего backend.

## Текущий стек

- Backend: Python, FastAPI, httpx, python-dotenv, SQLModel, SQLite
- Frontend: Vue 3, Vite, JavaScript, Composition API, обычный CSS
- Модель: Ollama
- База: SQLite

## Структура проекта

```text
.
├── ARCHITECTURE.md
├── README.md
├── .env.example
├── .gitignore
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── clients/
│       ├── core/
│       ├── models/
│       ├── routers/
│       └── main.py
└── frontend/
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── api/
        ├── assets/
        ├── components/
        ├── composables/
        ├── layouts/
        ├── router/
        └── views/
```

## Назначение папок

- `backend/` - backend приложения.
- `backend/app/routers/` - HTTP endpoints.
- `backend/app/clients/` - внешние клиенты, сейчас Ollama.
- `backend/app/core/` - конфигурация и общие настройки.
- `backend/app/models/` - Pydantic-схемы и SQLModel-таблицы.
- `frontend/` - Vue-приложение.
- `frontend/src/components/` - UI-компоненты чата.
- `frontend/src/composables/` - логика потокового чата и health-check.
- `frontend/src/layouts/` - общий макет страницы.
- `frontend/src/views/` - корневой экран.
- `frontend/src/api/` - HTTP helpers.
- `frontend/src/router/` - Vue Router.
- `frontend/src/assets/` - стили.

## Назначение файлов

- [`ARCHITECTURE.md`](./ARCHITECTURE.md) - короткие правила архитектуры и ограничения этапа.
- [`README.md`](./README.md) - запуск и сборка проекта.
- [`.env.example`](./.env.example) - пример переменных окружения.
- [`.gitignore`](./.gitignore) - исключения для Git.
- [`backend/requirements.txt`](./backend/requirements.txt) - зависимости backend.
- [`backend/app/main.py`](./backend/app/main.py) - FastAPI-приложение, роуты и раздача production frontend.
- [`backend/app/core/config.py`](./backend/app/core/config.py) - чтение `.env`.
- [`backend/app/clients/ollama.py`](./backend/app/clients/ollama.py) - минимальный клиент Ollama на `httpx`.
- [`backend/app/models/chat.py`](./backend/app/models/chat.py) - таблицы `chats` и `messages`, а также схемы запросов чата.
- [`backend/app/models/ollama.py`](./backend/app/models/ollama.py) - схемы ответа `/api/models`.
- [`backend/app/routers/health.py`](./backend/app/routers/health.py) - `GET /api/health`.
- [`backend/app/routers/chats.py`](./backend/app/routers/chats.py) - CRUD чатов.
- [`backend/app/routers/models.py`](./backend/app/routers/models.py) - `GET /api/models`.
- [`backend/app/routers/chat.py`](./backend/app/routers/chat.py) - `POST /api/chat` с NDJSON-потоком.
- [`frontend/package.json`](./frontend/package.json) - зависимости и скрипты frontend.
- [`frontend/vite.config.js`](./frontend/vite.config.js) - dev proxy на backend.
- [`frontend/src/main.js`](./frontend/src/main.js) - точка входа Vue.
- [`frontend/src/App.vue`](./frontend/src/App.vue) - корневой Vue-компонент.
- [`frontend/src/router/index.js`](./frontend/src/router/index.js) - маршрутизация.
- [`frontend/src/views/HomeView.vue`](./frontend/src/views/HomeView.vue) - экран с чат-интерфейсом.
- [`frontend/src/components/ChatView.vue`](./frontend/src/components/ChatView.vue) - сборка экрана чата.
- [`frontend/src/components/MessageList.vue`](./frontend/src/components/MessageList.vue) - область сообщений.
- [`frontend/src/components/ChatComposer.vue`](./frontend/src/components/ChatComposer.vue) - поле ввода, режимы и кнопки.
- [`frontend/src/composables/useHealth.js`](./frontend/src/composables/useHealth.js) - загрузка health endpoint.
- [`frontend/src/composables/useChatStream.js`](./frontend/src/composables/useChatStream.js) - потоковый запрос, NDJSON и отмена.
- [`frontend/src/api/http.js`](./frontend/src/api/http.js) - базовые HTTP helpers.
- [`frontend/src/layouts/MainLayout.vue`](./frontend/src/layouts/MainLayout.vue) - общий макет страницы.
- [`frontend/src/components/AppHeader.vue`](./frontend/src/components/AppHeader.vue) - заголовок и статусы.
- [`frontend/src/assets/base.css`](./frontend/src/assets/base.css) - адаптивные стили.

## Переменные окружения

Используй `.env` на основе `.env.example`.

```env
APP_HOST=0.0.0.0
APP_PORT=8000
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_DEFAULT_MODEL=VladimirGav/gemma4-26b-16GB-VRAM:latest
SERVE_FRONTEND=true
FRONTEND_DIST_PATH=frontend/dist
DATABASE_PATH=backend/data/local_llm.sqlite3
SESSION_COOKIE_NAME=local_llm_session
SESSION_TTL_DAYS=7
VITE_API_BASE_URL=/api
VITE_API_PROXY_TARGET=http://127.0.0.1:8000
```

## Auth и SQLite

- SQLite база хранится в `backend/data/local_llm.sqlite3` по умолчанию.
- Cookie сессии называется `local_llm_session`.
- Cookie выставляется как `HttpOnly`, `SameSite=Lax`, без `Secure`, чтобы работать по локальному HTTP с ПК и телефона в одной сети.
- Пароли хранятся только в виде `pbkdf2_sha256`-хеша.

## Chats и messages

В базе есть четыре таблицы:

- `users`
- `sessions`
- `chats`
- `messages`

`chats`:

- `id`
- `user_id`
- `model`
- `title`
- `created_at`
- `updated_at`

`messages`:

- `id`
- `chat_id`
- `role`
- `content`
- `created_at`

## Локальная сеть

### Dev-режим

- Frontend Vite слушает `0.0.0.0:5173`.
- Backend FastAPI слушает `0.0.0.0:8000`.
- На телефоне открывай IPv4 активного Wi-Fi или Ethernet адаптера ПК, например `http://192.168.0.71:5173`.
- `localhost` на телефоне использовать нельзя.
- Адрес ПК можно посмотреть через `ipconfig`.
- Обычно не нужно использовать WSL, Hyper-V, VPN или виртуальные адаптеры.
- Оба устройства должны быть в одной локальной сети.
- Гостевая Wi-Fi-сеть и client isolation могут блокировать соединение.
- Windows Firewall может попросить разрешить входящие TCP-подключения на `5173` и `8000`.
- Приложение не меняет Firewall автоматически.

### Production

- После `npm run build` frontend раздаётся FastAPI с одного origin на порту `8000`.

## Ollama

Запусти Ollama отдельно и при необходимости подтяни модель:

```powershell
ollama pull VladimirGav/gemma4-26b-16GB-VRAM:latest
```

Используется REST API Ollama:

- `GET /api/tags`
- `POST /api/chat`

Backend также отдаёт нормализованный список моделей через `GET /api/models`.

Для ограниченной VRAM дополнительно рекомендуются настройки Ollama:

```env
OLLAMA_MAX_LOADED_MODELS=1
OLLAMA_NUM_PARALLEL=1
```

Эти значения помогают не держать много моделей в памяти одновременно, но они не заменяют серверный lock и явную выгрузку модели.

## Запуск backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Создание первого локального пользователя

Из папки `backend/`:

```powershell
python -m app.scripts.create_user --username admin --password "strong-password"
```

Команда создаёт запись в SQLite и сохраняет пароль только в виде хеша.

## Запуск frontend

```powershell
cd frontend
npm install
npm run dev
```

Dev-адреса:

- Frontend: `http://localhost:5173`
- Backend: `http://127.0.0.1:8000`
- Health: `http://127.0.0.1:8000/api/health`

## Production-сборка

```powershell
cd frontend
npm run build
```

После сборки frontend окажется в `frontend/dist`.

## Запуск production

```powershell
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Если `frontend/dist` существует, FastAPI раздает собранный frontend с того же origin.

## Маршруты чатов

- `GET /api/chats` - список чатов текущего пользователя.
- `POST /api/chats` - создать новый чат.
- `GET /api/chats/{chat_id}` - получить чат вместе с сообщениями.
- `DELETE /api/chats/{chat_id}` - удалить чат.
- `GET /api/models` - список установленных моделей Ollama для текущего пользователя.
- `POST /api/chat` - отправить сообщение в конкретный чат с глобальной активной моделью.

Для `POST /api/chat` frontend передаёт:

- `chat_id`
- `content`
- `mode`

Модель в запросе на генерацию не передаётся: backend берёт её из глобальной серверной настройки.

Ответ остаётся NDJSON-потоком с событиями:

- `type=content`
- `type=done`
- `type=error`

## Модели Ollama

- Текущая активная модель задаётся через `OLLAMA_DEFAULT_MODEL`.
- `GET /api/models` возвращает `active_model` и список установленных моделей.
- Обычный пользователь только видит активную модель.
- Backend уже содержит отдельный сервис для будущего admin endpoint, но сам endpoint в рамках этого этапа не добавлен.
- Если админский переход модели будет запрошен во время активной генерации, сервис вернёт контролируемую ошибку `409`, чтобы не менять модель посреди запроса.
- Смена модели в сервисе идёт через явную выгрузку старой модели (`keep_alive: 0`), проверку `/api/ps`, затем предварительную загрузку новой (`keep_alive: -1`).
- Если Ollama недоступна, `GET /api/models` и создание сообщения возвращают контролируемую ошибку, а сохранённые чаты и история остаются доступными.

## Миграция SQLite

- При старте backend создаёт отсутствующие таблицы через SQLModel.
- Существующие пользователи, сессии, чаты и сообщения сохраняются.
- Таблица `chats` не получает отдельную колонку для модели.

## SPA fallback

Production backend теперь отдаёт `index.html` для прямых заходов на:

- `/`
- `/login`
- `/chat/3`

Это нужно для обновления страницы, прямых ссылок и открытия чата на другом устройстве без `404 Not Found`.

## Режимы чата

- `Instant` - обычный ответ Ollama.
- `Thinking` - ответ с `think: true`.

## Вход и выход

- Вход: `POST /api/auth/login` принимает `username` и `password`, возвращает пользователя и устанавливает HttpOnly cookie.
- Текущий пользователь: `GET /api/auth/me`.
- Выход: `POST /api/auth/logout` удаляет серверную сессию и очищает cookie.
- Без действующей сессии `GET /api/chats` и `POST /api/chat` возвращают `401`.

## Важные ограничения этапа

- История теперь сохраняется в SQLite между обновлениями страницы.
- Нет памяти отдельных вкладок, системных промптов, суммаризации контекста, ролей и административной панели.
- Нет публичной регистрации.
- Нет следующих этапов roadmap.

## Проверка

Основные проверки:

- `GET /api/auth/me` без cookie возвращает `401`
- `GET /api/models` без cookie возвращает `401`
- `POST /api/auth/login` с неверным паролем не создаёт сессию
- `POST /api/auth/login` с верным паролем устанавливает HttpOnly cookie
- `GET /api/auth/me` после входа возвращает пользователя
- `GET /api/chats` без cookie возвращает `401`
- `POST /api/chats` создаёт чат только для текущего пользователя
- `POST /api/chat` без cookie возвращает `401`
- `POST /api/chat` с cookie сохраняет user/assistant messages и продолжает стримить NDJSON по частям
- `POST /api/chat` использует глобальную активную модель backend
- `POST /api/auth/logout` инвалидирует старую сессию
- `DELETE /api/chats/{chat_id}` удаляет чат и его сообщения
- `GET /api/models` с cookie возвращает `active_model` и список моделей Ollama
- недоступность Ollama не ломает просмотр сохранённых чатов
- Прямые URL `/login` и `/chat/:chatId` в production должны открываться без `404`

Команды проверки:

```powershell
cd frontend
npm run build

cd ..\backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Для проверки входа с ПК и телефона:

1. Запусти backend на `0.0.0.0:8000`.
2. Открой приложение с ПК по `http://127.0.0.1:8000`.
3. Открой то же приложение с телефона по локальному IP ПК, например `http://192.168.0.71:8000`.
4. Войди под созданным локальным пользователем на обоих устройствах.

Фронтенд роуты:

- `/login`
- `/`
- `/chat/:chatId`

UI:

- На desktop список чатов виден рядом с текущим чатом.
- На mobile список чатов открывается как drawer поверх контента.
