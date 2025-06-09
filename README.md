# Telegram User Parser & Inviter Service

[English version below]

---

## Описание проекта

Многофункциональный сервис для парсинга пользователей из Telegram-каналов и чатов, фильтрации неадекватных и нецелевых контактов, и автоматической рассылки приглашений (инвайтов) или массового добавления пользователей в супергруппу.

**Ключевые возможности:**
- Парсинг открытых чатов, каналов, сообщений, реакций, комментаторов (deep crawling)
- Фильтрация админов, ботов, уже обработанных пользователей
- Поддержка постов (парсинг авторов реакций/комментариев к отдельным сообщениям)
- Гибкая работа с источниками (https://t.me/..., @username, ID, ссылки на сообщения)
- Рассылка инвайтов по шаблонам (Direct Message, поддержка HTML/emoji)
- Массовое приглашение в супергруппу с контролем лимитов Telegram и проверкой членства
- Журналы логов всех операций: приглашения, ошибки, история попыток, прогресс парсинга
- Поддержка режима продолжения или сброса прогресса (restart/continue)
- Простая конфигурация через .env

---

## Структура проекта

- parser/main.py # Парсер пользователей
- tg_inviter/message_sender.py # Рассылка инвайтов (личные сообщения)
- messages.py # Шаблоны сообщений
- super_group_inviter.py # Массовое добавление в группу/канал
- channels.txt # Источники (список чатов/каналов/постов)
- users.csv # Спарсенные пользователи
- invited_log.csv # Журнал рассылки/инвайтов
- parsed_sources.txt # Уже обработанные источники
- requirements.txt # Зависимости Python
- docker-compose.yml # Docker-оркестрация (если нужно)
- .env # Переменные окружения (API_ID, HASH и т.д.)


---

## Быстрый старт

1. **Установите зависимости:**
    ```bash
    pip install -r requirements.txt
    ```
2. **Настройте `.env`:**  
    Пример:
    ```
    API_ID=YOUR_API_ID
    API_HASH=YOUR_API_HASH
    SESSION_NAME=parser_session
    CHANNELS_FILE=channels.txt
    USERS_CSV=users.csv
    INVITED_LOG_CSV=invited_log.csv
    PARSED_SOURCES_FILE=parsed_sources.txt
    DATE_FORMAT=%Y-%m-%d %H:%M
    CHANNEL_URL=https://t.me/your_channel
    ```

3. **Заполните `channels.txt`**  
    Укажите чаты, каналы или посты для парсинга (по одному в строке).

4. **Соберите пользователей:**
    ```bash
    python parser/main.py
    ```

5. **Проверьте/добавьте шаблоны сообщений в `tg_inviter/messages.py`:**
    ```python
   messages = {
     1: "Привет! 👋 Приглашаю в наш уютный канал {anchor}...",
     2: "Загляни на {anchor} — там лучшие новости о Таиланде!"
    }
    ```

6. **Запустите рассылку личных инвайтов:**
    ```bash
    python tg_inviter/message_sender.py
    ```

7. **(Опционально) Массовое добавление в группу/канал:**
    ```bash
    python tg_inviter/super_group_inviter.py
    ```

---

## Особенности

- Соблюдаются лимиты Telegram (дневные/пакетные)
- Повторные приглашения не отправляются (в течение 30 дней или при отказе)
- Вся история попыток и ошибок фиксируется для контроля качества
- Гибко добавляются новые шаблоны сообщений и источники

---

## Docker (если нужен запуск в контейнере)

1. Настройте `.env` и зависимости.
2. Соберите и запустите контейнеры:
    ```bash
    docker-compose up --build
    ```

---

## Лицензия

Только для легального использования, не нарушающего правила Telegram!

---

# English

## Project description

A multi-purpose Telegram user parsing and inviting service:  
- Parse users from Telegram channels, groups, post reactions and comments.
- Filter out bots, admins, and duplicates.
- Flexible source formats: @username, ID, message/post links.
- Direct invitation messages by template (HTML, emoji supported).
- Bulk group/channel invites with membership check.
- Logging: all invites, attempts, errors, progress.
- Resume or reset modes.
- Simple .env config.

## Project structure

See above.

## Quickstart

1. **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
2. **Setup `.env`:**  
    Example:
    ```
    API_ID=YOUR_API_ID
    API_HASH=YOUR_API_HASH
    SESSION_NAME=parser_session
    CHANNELS_FILE=channels.txt
    USERS_CSV=users.csv
    INVITED_LOG_CSV=invited_log.csv
    PARSED_SOURCES_FILE=parsed_sources.txt
    DATE_FORMAT=%Y-%m-%d %H:%M
    CHANNEL_URL=https://t.me/your_channel
    ```
3. **Fill `channels.txt` with sources to parse.**

4. **Collect users:**
    ```bash
    python parser/main.py
    ```

5. **Edit templates in `tg_inviter/messages.py` as needed.**

6. **Run direct message inviter:**
    ```bash
    python tg_inviter/message_sender.py
    ```

7. **(Optional) Bulk invite to group/channel:**
    ```bash
    python tg_inviter/super_group_inviter.py
    ```

## Features

- Telegram limits respected (daily, batch)
- No repeated invites (30-day cooldown, auto-refusal)
- All actions, errors, attempts are logged
- Easy to add new templates and sources

## Docker

1. Setup `.env` and requirements.
2. Build and run containers:
    ```bash
    docker-compose up --build
    ```

---

## License

For legal use only, do not violate Telegram rules!

---
