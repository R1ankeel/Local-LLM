# Local AI Chat

Локальный AI-чат для домашней сети. На этапе 0.6 добавлены скрытый базовый system prompt, пользовательские профили поведения, привязка профиля к чату и серверная сборка контекста для Ollama. На этапе 0.7.1 добавлена настраиваемая глубина истории, передаваемой в Ollama. На этапе 0.8.1 добавлена вручную управляемая долговременная память пользователя.

## Текущий стек

- Backend: Python, FastAPI, httpx, python-dotenv, SQLModel, SQLite
- Frontend: Vue 3, Vite, JavaScript, Composition API, обычный CSS
- Модель: Ollama
- База: SQLite
- Правило проекта: пользовательский интерфейс ведётся на русском языке; технические имена API, таблиц и моделей остаются на английском.

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
│       ├── services/
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

## System prompt и профили

На этапе 0.6 есть два разных уровня инструкций:

- скрытый базовый system prompt приложения;
- пользовательский профиль поведения, который выбирается для конкретного чата.

Базовый system prompt:

- живёт только на backend;
- не редактируется обычным пользователем;
- не сохраняется в `messages`;
- не приходит с frontend как источник истины.

Профиль поведения:

- хранится в таблице `behavior_profiles`;
- принадлежит только одному пользователю;
- может редактироваться и удаляться через CRUD API;
- применяется к следующему ответу чата, а не переписывает историю.

Финальный `role=system` собирается на backend как:

- скрытый базовый prompt;
- затем блок `Behavior profile` с инструкциями выбранного профиля;
- затем история текущего чата;
- затем новое сообщение пользователя.

## Таблицы

В базе есть пять таблиц:

- `users`
- `sessions`
- `behavior_profiles`
- `chats`
- `messages`

### `behavior_profiles`

- `id`
- `owner_id`
- `name`
- `description`
- `instructions`
- `is_default`
- `created_at`
- `updated_at`

Требования:

- `name` обязателен и не может быть пустым или состоять только из пробелов;
- `description` может быть пустым;
- `instructions` обязательны и имеют ограничение длины;
- у пользователя может быть только один default-профиль;
- чужие профили не видны и не редактируются.

### `chats`

- `id`
- `user_id`
- `profile_id`
- `title`
- `created_at`
- `updated_at`

### `messages`

- `id`
- `chat_id`
- `role`
- `content`
- `created_at`

Правила для чатов:

- новый чат без `profile_id` получает default-профиль пользователя;
- новый чат может быть создан с явно выбранным собственным профилем;
- существующий чат можно переключить на другой собственный профиль;
- смена профиля не очищает историю и не добавляет служебное сообщение;
- system prompt не сохраняется в `messages`.

## Behavior Profiles API

Авторизованные endpoints:

- `GET /api/profiles`
- `POST /api/profiles`
- `GET /api/profiles/{profile_id}`
- `PATCH /api/profiles/{profile_id}`
- `DELETE /api/profiles/{profile_id}`

Поведение:

- `GET /api/profiles` возвращает только профили текущего пользователя;
- `POST /api/profiles` создаёт новый профиль и может сразу сделать его default;
- `PATCH /api/profiles/{profile_id}` меняет имя, описание, инструкции и default-флаг;
- `DELETE /api/profiles/{profile_id}` возвращает `409`, если профиль ещё используется чатами;
- default-профиль нельзя удалить, пока не назначен другой default.

## Миграция SQLite

При старте backend:

- создаёт отсутствующие таблицы через SQLModel;
- добавляет `behavior_profiles`, если её ещё нет;
- добавляет `chats.profile_id`, если колонка отсутствует;
- не удаляет и не пересоздаёт существующую базу;
- сохраняет пользователей, сессии, чаты и сообщения;
- создаёт default-профиль для каждого пользователя;
- назначает существующим чатам корректный `profile_id`.

Предпочтительное поведение после миграции:

- у каждого существующего пользователя есть профиль `Default assistant`;
- этот профиль является default для пользователя;
- существующие чаты получают этот профиль.

## Auth и SQLite

- SQLite база хранится в `backend/data/local_llm.sqlite3` по умолчанию.
- Cookie сессии называется `local_llm_session`.
- Cookie выставляется как `HttpOnly`, `SameSite=Lax`, без `Secure`, чтобы работать по локальному HTTP с ПК и телефона в одной сети.
- Пароли хранятся только в виде `pbkdf2_sha256`-хеша.

## Маршруты

- `GET /api/chats` - список чатов текущего пользователя.
- `POST /api/chats` - создать новый чат, при необходимости с `profile_id` и `context_message_limit`.
- `GET /api/chats/{chat_id}` - получить чат вместе с сообщениями и глубиной контекста.
- `PATCH /api/chats/{chat_id}` - сменить профиль чата или глубину контекста.
- `DELETE /api/chats/{chat_id}` - удалить чат.
- `GET /api/models` - список установленных моделей Ollama для текущего пользователя.
- `POST /api/chat` - отправить сообщение в конкретный чат с глобальной активной моделью.
- `GET /api/memories` - список долговременных записей текущего пользователя.
- `POST /api/memories` - создать запись памяти.
- `PATCH /api/memories/{memory_id}` - изменить `content` и/или `is_active`.
- `DELETE /api/memories/{memory_id}` - удалить запись памяти.

Для `POST /api/chat` frontend передаёт только:

- `chat_id`
- `content`
- `mode`
- `context_message_limit` не нужен для отправки сообщения, он хранится в самом чате.

Модель и system prompt frontend не передаёт.

## Вход и выход

- Вход: `POST /api/auth/login` принимает `username` и `password`, возвращает пользователя и устанавливает HttpOnly cookie.
- Текущий пользователь: `GET /api/auth/me`.
- Выход: `POST /api/auth/logout` удаляет серверную сессию и очищает cookie.
- Без действующей сессии `GET /api/chats`, `GET /api/profiles` и `POST /api/chat` возвращают `401`.

## Ограничения этапа

- История сохраняется в SQLite между обновлениями страницы.
- Для каждого чата хранится собственная глубина контекста `context_message_limit`, но полная история сообщений остаётся в SQLite и на frontend.
- Память создаётся только вручную через API и подмешивается в system prompt как отдельный блок.
- Автоматическое извлечение фактов из чатов пока отсутствует.
- Память не поддерживает embeddings, RAG, поиск или версии.
- Нет памяти отдельных вкладок, суммаризации контекста, версий профилей и административной панели.
- Нет публичной регистрации.
- Нет следующих этапов roadmap.
- Глобальная активная модель Ollama остаётся общей для всего backend.
- Изменения `instructions` применяются к следующим ответам чатов, а не к уже сохранённой истории.

## Ollama

Запусти Ollama отдельно и при необходимости подтяни модель:

```powershell
ollama pull VladimirGav/gemma4-26b-16GB-VRAM:latest
```

Используется REST API Ollama:

- `GET /api/tags`
- `POST /api/chat`

Backend также отдаёт нормализованный список моделей через `GET /api/models`.

При сборке запроса backend сначала добавляет скрытый system prompt и инструкции профиля, а затем только последние `context_message_limit` сообщений текущего чата в хронологическом порядке. В `messages` система не пишет служебный prompt и не удаляет старую историю.

На этапе 0.8.1 в system prompt также добавляется отдельный блок долговременной памяти пользователя:

- используются только активные записи текущего пользователя;
- записи сортируются по `updated_at` от новых к старым;
- действует лимит `4000` символов на добавляемый блок;
- отдельная запись не обрезается посередине;
- если памяти нет, отдельный блок не добавляется;
- память другого пользователя не попадает в prompt.

Если Ollama недоступна, просмотр сохранённых чатов не ломается.

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

Если `frontend/dist` существует, FastAPI раздаёт собранный frontend с того же origin.

## Проверка

### Автоматизированные backend-тесты без Ollama

```powershell
cd backend
python -m unittest discover -s tests
python -m compileall app
```

### Проверка frontend

```powershell
cd frontend
npm run build
```

### Ручные проверки с Ollama

1. Запусти Ollama отдельно.
2. Запусти backend: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
3. Проверь создание и редактирование профилей через UI.
4. Убедись, что новый и существующий чат используют выбранный профиль.
5. Измени глубину контекста у текущего чата и проверь, что следующий ответ использует только последние сообщения.
6. Измени `instructions` профиля и проверь, что это влияет только на следующий ответ.

## UI

- На desktop список чатов виден рядом с текущим чатом.
- На mobile список чатов открывается как drawer поверх контента.
- Пользовательский интерфейс проекта должен оставаться на русском языке.
