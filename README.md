# Local AI Chat

Локальный AI-чат для домашней сети. На этапе 0.2 реализованы Ollama, один временный чат с потоковым ответом, dev proxy, production-раздача frontend через FastAPI и базовая документация.

## Текущий стек

- Backend: Python, FastAPI, httpx, python-dotenv
- Frontend: Vue 3, Vite, JavaScript, Composition API, обычный CSS
- Модель: Ollama
- Будущая база: SQLite, пока не подключена

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
- `backend/app/models/` - Pydantic-схемы.
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
- [`backend/app/models/chat.py`](./backend/app/models/chat.py) - валидация запроса чата.
- [`backend/app/routers/health.py`](./backend/app/routers/health.py) - `GET /api/health`.
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
OLLAMA_MODEL=VladimirGav/gemma4-26b-16GB-VRAM:latest
SERVE_FRONTEND=true
FRONTEND_DIST_PATH=frontend/dist
VITE_API_BASE_URL=/api
VITE_API_PROXY_TARGET=http://127.0.0.1:8000
```

## Ollama

Запусти Ollama отдельно и при необходимости подтяни модель:

```powershell
ollama pull VladimirGav/gemma4-26b-16GB-VRAM:latest
```

Используется REST API Ollama:

- `GET /api/tags`
- `POST /api/chat`

## Запуск backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

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

## Открытие с телефона

1. ПК и телефон должны быть в одной локальной сети.
2. Открой в браузере телефона IPv4-адрес ПК, например `http://192.168.1.25:8000`.
3. В dev-режиме может понадобиться разрешить порты `5173` и `8000` в Windows Firewall.

## Режимы чата

- `Instant` - обычный ответ Ollama.
- `Thinking` - ответ с `think: true`.

## Важные ограничения этапа

- История не сохраняется после обновления страницы.
- Нет SQLite, нескольких чатов, поиска, xAI, DuckDuckGo, авторизации, Markdown и WebSocket.
- Backend не хранит постоянную историю.
- Frontend отправляет только историю текущей страницы.

## Проверка

Основной health endpoint:

- `GET /api/health`

