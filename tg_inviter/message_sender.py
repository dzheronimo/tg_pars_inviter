import asyncio
from telethon import TelegramClient
from telethon.tl.custom import Dialog
from telethon.tl.patched import Message
from telethon.tl.types import Channel, User
import pandas as pd
import time
from datetime import datetime
import os
import random
import re
from typing import Any, Dict, Tuple, List, Optional

from telethon.errors import FloodWaitError

from tg_inviter.messages import messages  # словарь сообщений в формате {int: str}

API_ID: str = os.getenv("API_ID", "")
API_HASH: str = os.getenv("API_HASH", "")
SESSION_NAME: str = os.getenv("SESSION_NAME", "")
CHANNEL_URL: str = os.getenv("CHANNEL_URL", "")
USERS_CSV: str = os.getenv("USERS_CSV", "")
INVITED_LOG_CSV: str = os.getenv("INVITED_LOG_CSV", "")
DATE_FORMAT: str = os.getenv("DATE_FORMAT", "")

CHANNEL_TO_CHECK: str = os.getenv("CHANNEL_TO_CHECK", "")  # например, @your_channel

ANCHOR: str = f'<a href="{CHANNEL_URL}">Тай для своих</a>'

# Настройки для пауз
MIN_PAUSE_SEC: int = 4
MAX_PAUSE_SEC: int = 10
BATCH_SIZE: int = 20
MIN_BATCH_PAUSE_SEC: int = 180
MAX_BATCH_PAUSE_SEC: int = 480
DAILY_LIMIT: int = 20  # SAFETY: максимум инвайтов за запуск

DO_NOT_REPEAT_ERRORS: List[str] = [
    "privacy", "not a mutual contact", "can't write to this user", "blocked", "USER_IS_BLOCKED"
]


def load_log() -> pd.DataFrame:
    """
    Загружает лог инвайтов из файла INVITED_LOG_CSV или создает пустой DataFrame.

    Returns:
        pd.DataFrame: Лог инвайтов с колонками (user_id, username, invited, invite_datetime, tries, error_message).
    """
    if os.path.exists(INVITED_LOG_CSV):
        return pd.read_csv(INVITED_LOG_CSV, dtype=str)
    return pd.DataFrame(columns=[
        'user_id', 'username', 'invited', 'invite_datetime', 'tries', 'error_message'
    ])


def save_log(df: pd.DataFrame) -> None:
    """
    Сохраняет DataFrame логов инвайтов в файл INVITED_LOG_CSV.

    Args:
        df (pd.DataFrame): Лог рассылки для сохранения.
    """
    df.to_csv(INVITED_LOG_CSV, index=False, encoding='utf-8-sig')


def eligible_for_invite(row: Dict[str, Any]) -> bool:
    """
    Проверяет, может ли пользователь получить инвайт (не получал за последние 30 дней и нет фатальной ошибки).

    Args:
        row (Dict[str, Any]): Строка лога пользователя.

    Returns:
        bool: True, если можно инвайтить, иначе False.
    """
    if row.get('invited', '0') == '1' and row.get('invite_datetime'):
        last_sent = datetime.strptime(row['invite_datetime'], DATE_FORMAT)
        if (datetime.now() - last_sent).days < 30:
            return False
    if row.get('invited', '0') == '0' and row.get('error_message'):
        em = row['error_message'].lower()
        if any(err in em for err in DO_NOT_REPEAT_ERRORS):
            return False
    return True


def was_success(row: Dict[str, Any]) -> bool:
    """
    Проверяет, был ли успешный инвайт пользователю.

    Args:
        row (Dict[str, Any]): Строка лога пользователя.

    Returns:
        bool: True, если был успешный инвайт.
    """
    return row.get('invited', '0') == '1'


def get_last_try(row: Dict[str, Any]) -> int:
    """
    Возвращает число прошлых попыток инвайта.

    Args:
        row (Dict[str, Any]): Строка лога пользователя.

    Returns:
        int: Количество попыток.
    """
    try:
        return int(row.get('tries', 0))
    except Exception:
        return 0


def prepare_message(message_text: str) -> str:
    """
    Подменяет 'Тай для своих' на HTML-анкор в тексте сообщения.

    Args:
        message_text (str): Шаблон сообщения.

    Returns:
        str: Текст с заменой якоря.
    """
    return re.sub(r'Тай для своих', ANCHOR, message_text, flags=re.IGNORECASE)


async def try_send_message(
    client: TelegramClient,
    username: str,
    msg: str,
    idx: int,
    total: int
) -> Tuple[int, str]:
    """
    Отправляет сообщение пользователю с обработкой FloodWait, ошибок и повторными попытками.

    Args:
        client (TelegramClient): Активный клиент Telethon.
        username (str): Username пользователя (str).
        msg (str): Текст сообщения.
        idx (int): Индекс пользователя.
        total (int): Общее число сообщений.

    Returns:
        Tuple[int, str]: (1, '') если успех, (0, error_message) если неудача.
    """
    max_retries = 3
    n_retry = 0
    while n_retry < max_retries:
        try:
            await client.send_message(
                entity=username,
                message=msg,
                parse_mode='html'
            )
            print(f"[{idx+1}/{total}] OK: {username}")
            return 1, ''
        except FloodWaitError as e:
            wait = e.seconds + random.randint(5, 25)
            print(f"[{idx+1}/{total}] FloodWait: спим {wait} сек")
            time.sleep(wait)
            n_retry += 1
        except Exception as e:
            err_msg = str(e)
            print(f"[{idx+1}/{total}] Ошибка: {username}: {err_msg}")
            if any(err in err_msg.lower() for err in DO_NOT_REPEAT_ERRORS):
                return 0, err_msg
            if "disconnected" in err_msg.lower():
                print(f"Попытка повторить отправку для {username} (отключено от сети)...")
                time.sleep(random.randint(10, 25))
                n_retry += 1
                continue
            return 0, err_msg
    return 0, "Max retries exceeded"


async def is_member(
    client: TelegramClient,
    channel_entity: Any,
    user_id: str,
    username: str
) -> bool:
    """
    Проверяет, состоит ли user_id или username в участниках канала.

    Args:
        client (TelegramClient): Активный клиент Telethon.
        channel_entity (Any): Сущность канала/чата.
        user_id (str): Telegram user_id.
        username (str): Username пользователя.

    Returns:
        bool: True если подписан, иначе False.
    """
    from telethon.tl.types import ChannelParticipantsSearch
    try:
        search = username if username else str(user_id)
        async for user in client.iter_participants(channel_entity, search=search):
            if user.id == int(user_id):
                return True
        return False
    except Exception as e:
        print(f"[!] Ошибка при проверке подписки для {user_id} ({username}): {e}")
        return False


async def main() -> None:
    """
    Основная функция: формирует список пользователей для рассылки, фильтрует по подписке,
    рассылает сообщения с учетом лимитов и ведет лог.
    """
    df_users = pd.read_csv(USERS_CSV, dtype=str)
    df_log = load_log()
    invite_candidates: List[Dict[str, str]] = []
    already_invited: set = set()
    for _, row in df_log.iterrows():
        if was_success(row):
            already_invited.add(row['username'])

    # Считаем, сколько инвайтов уже было сегодня
    today = datetime.now().date()
    sent_today = 0
    for _, row in df_log.iterrows():
        if row.get('invite_datetime'):
            try:
                dt = datetime.strptime(row['invite_datetime'], DATE_FORMAT)
                if dt.date() == today and row.get('invited') == '1':
                    sent_today += 1
            except Exception:
                continue

    # Собираем кандидатов
    for _, row in df_users.iterrows():
        user_id = str(row['user_id'])
        username = str(row['username']) if pd.notna(row['username']) else ''
        if not username or username.strip() == '' or username.lower() == 'nan':
            continue
        if username in already_invited:
            continue
        log_rows = df_log[df_log['username'] == username]
        if not log_rows.empty:
            last_row = log_rows.iloc[-1]
            if not eligible_for_invite(last_row):
                continue
            if last_row.get('invite_datetime'):
                last_dt = datetime.strptime(last_row['invite_datetime'], DATE_FORMAT)
                if (datetime.now() - last_dt).total_seconds() < 24*3600 and last_row['invited'] == '0':
                    continue
        invite_candidates.append({'user_id': user_id, 'username': username})

    print(f'Пользователей для рассылки приглашения: {len(invite_candidates)}')
    print(f'Инвайтов уже отправлено сегодня: {sent_today}')
    remain_today: int = max(0, DAILY_LIMIT - sent_today)
    if remain_today <= 0:
        print('== Лимит сообщений на сегодня исчерпан ==')
        return

    count_sent: int = 0
    async with TelegramClient(SESSION_NAME, int(API_ID), API_HASH) as client:
        filtered_candidates: List[Dict[str, str]] = []
        channel_entity: Optional[Any] = None
        if CHANNEL_TO_CHECK:
            try:
                channel_entity = await client.get_entity(CHANNEL_TO_CHECK)
                print(f'Проверка подписки на канал {CHANNEL_TO_CHECK} включена')
            except Exception as e:
                print(f'[!] Ошибка получения канала для проверки подписки: {e}')
        if channel_entity:
            for user in invite_candidates:
                is_sub = await is_member(client, channel_entity, user['user_id'], user['username'])
                if not is_sub:
                    filtered_candidates.append(user)
                else:
                    print(f"    Пропускаем (уже подписан): @{user['username'] or user['user_id']}")
        else:
            filtered_candidates = invite_candidates

        print(f'Кандидатов для рассылки после проверки подписки: {len(filtered_candidates)}')

        for idx, user in enumerate(filtered_candidates):
            if count_sent >= remain_today:
                print('== Достигнут лимит рассылки на сегодня, стоп ==')
                break
            user_id, username = user['user_id'], user['username']
            msg_key = random.choice(list(messages.keys()))
            template = messages[msg_key]
            msg = prepare_message(template)
            now_str = datetime.now().strftime(DATE_FORMAT)
            tries = 1
            log_rows = df_log[df_log['username'] == username]
            if not log_rows.empty:
                tries = get_last_try(log_rows.iloc[-1]) + 1

            invited, error_message = await try_send_message(
                client, username, msg, idx, len(filtered_candidates)
            )

            if invited == 1:
                count_sent += 1

            log_row = {
                'user_id': user_id,
                'username': username,
                'invited': invited,
                'invite_datetime': now_str,
                'tries': tries,
                'error_message': error_message
            }
            df_log = pd.concat([df_log, pd.DataFrame([log_row])], ignore_index=True)
            save_log(df_log)

            # Пауза между сообщениями (рандом)
            if (idx + 1) % BATCH_SIZE != 0:
                pause = random.uniform(MIN_PAUSE_SEC, MAX_PAUSE_SEC)
                time.sleep(pause)
            else:
                batch_pause = random.uniform(MIN_BATCH_PAUSE_SEC, MAX_BATCH_PAUSE_SEC)
                print(f"Пауза после {BATCH_SIZE} сообщений: {int(batch_pause//60)} мин {int(batch_pause%60)} сек")
                time.sleep(batch_pause)
    print('\n== Всё! Рассылка завершена ==\n')


if __name__ == '__main__':
    asyncio.run(main())
