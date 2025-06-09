import asyncio
from dotenv import load_dotenv
from telethon import TelegramClient
import pandas as pd
import time
from datetime import datetime
import os
import random
import re

from telethon.errors import FloodWaitError

from tg_inviter.messages import messages  # словарь сообщений в формате {int: str}

load_dotenv()


API_ID = os.getenv("API_ID", "")
API_HASH = os.getenv("API_HASH", "")
SESSION_NAME = os.getenv("SESSION_NAME", "")
CHANNEL_URL = os.getenv("CHANNEL_URL", "")
USERS_CSV = os.getenv("USERS_CSV", "")
INVITED_LOG_CSV = os.getenv("INVITED_LOG_CSV", "")
DATE_FORMAT = os.getenv("DATE_FORMAT", "")

ANCHOR = f'<a href="{CHANNEL_URL}">Тай для своих</a>'

# Настройки для пауз
MIN_PAUSE_SEC = 4
MAX_PAUSE_SEC = 10
BATCH_SIZE = 20
MIN_BATCH_PAUSE_SEC = 180
MAX_BATCH_PAUSE_SEC = 480
DAILY_LIMIT = 20  # SAFETY: максимум инвайтов за запуск

# Ошибки, после которых повторять не стоит (privacy/block/нет взаимности)
DO_NOT_REPEAT_ERRORS = [
    "privacy",
    "not a mutual contact",
    "can't write to this user",
    "blocked",
    "USER_IS_BLOCKED",
]


def load_log():
    if os.path.exists(INVITED_LOG_CSV):
        return pd.read_csv(INVITED_LOG_CSV, dtype=str)
    return pd.DataFrame(
        columns=[
            "user_id",
            "username",
            "invited",
            "invite_datetime",
            "tries",
            "error_message",
        ]
    )


def save_log(df):
    df.to_csv(INVITED_LOG_CSV, index=False, encoding="utf-8-sig")


def eligible_for_invite(row):
    """Пользователь не получал успешного инвайта или последняя попытка была более 30 дней назад."""
    if row.get("invited", "0") == "1" and row.get("invite_datetime"):
        last_sent = datetime.strptime(row["invite_datetime"], DATE_FORMAT)
        if (datetime.now() - last_sent).days < 30:
            return False
    # SAFETY: не повторяем если был явный отказ
    if row.get("invited", "0") == "0" and row.get("error_message"):
        em = row["error_message"].lower()
        if any(err in em for err in DO_NOT_REPEAT_ERRORS):
            return False
    return True


def was_success(row):
    return row.get("invited", "0") == "1"


def get_last_try(row):
    try:
        return int(row.get("tries", 0))
    except Exception:
        return 0


def prepare_message(message_text):
    return re.sub(r"Тай для своих", ANCHOR, message_text, flags=re.IGNORECASE)


async def try_send_message(client, username, msg, idx, total):
    """Функция для отправки, с обработкой FloodWait и reconnection."""
    max_retries = 3
    n_retry = 0
    while n_retry < max_retries:
        try:
            await client.send_message(entity=username, message=msg, parse_mode="html")
            print(f"[{idx+1}/{total}] OK: {username}")
            return 1, ""
        except FloodWaitError as e:
            wait = e.seconds + random.randint(5, 25)
            print(f"[{idx+1}/{total}] FloodWait: спим {wait} сек")
            time.sleep(wait)
            n_retry += 1
        except Exception as e:
            err_msg = str(e)
            print(f"[{idx+1}/{total}] Ошибка: {username}: {err_msg}")
            # SAFETY: Не повторяем если приватность/блок/невзаимный контакт
            if any(err in err_msg.lower() for err in DO_NOT_REPEAT_ERRORS):
                return 0, err_msg
            # Повторяем если "Cannot send requests while disconnected"
            if "disconnected" in err_msg.lower():
                print(
                    f"Попытка повторить отправку для {username} (отключено от сети)..."
                )
                time.sleep(random.randint(10, 25))
                n_retry += 1
                continue
            return 0, err_msg
    return 0, "Max retries exceeded"


async def main():
    df_users = pd.read_csv(USERS_CSV, dtype=str)
    df_log = load_log()
    invite_candidates = []
    already_invited = set()
    for _, row in df_log.iterrows():
        if was_success(row):
            already_invited.add(row["username"])

    # SAFETY: считаем, сколько инвайтов уже было сегодня
    today = datetime.now().date()
    sent_today = 0
    for _, row in df_log.iterrows():
        if row.get("invite_datetime"):
            try:
                dt = datetime.strptime(row["invite_datetime"], DATE_FORMAT)
                if dt.date() == today and row.get("invited") == "1":
                    sent_today += 1
            except Exception:
                continue

    # Собираем кандидатов
    for _, row in df_users.iterrows():
        user_id = str(row["user_id"])
        username = str(row["username"]) if pd.notna(row["username"]) else ""
        if not username or username.strip() == "" or username.lower() == "nan":
            continue
        if username in already_invited:
            continue
        log_rows = df_log[df_log["username"] == username]
        if not log_rows.empty:
            last_row = log_rows.iloc[-1]
            if not eligible_for_invite(last_row):
                continue
            if last_row.get("invite_datetime"):
                last_dt = datetime.strptime(last_row["invite_datetime"], DATE_FORMAT)
                if (datetime.now() - last_dt).total_seconds() < 24 * 3600 and last_row[
                    "invited"
                ] == "0":
                    continue
        invite_candidates.append({"user_id": user_id, "username": username})

    print(f"Пользователей для рассылки приглашения: {len(invite_candidates)}")
    print(f"Инвайтов уже отправлено сегодня: {sent_today}")
    remain_today = max(0, DAILY_LIMIT - sent_today)
    if remain_today <= 0:
        print("== Лимит сообщений на сегодня исчерпан ==")
        return

    count_sent = 0
    async with TelegramClient(SESSION_NAME, int(API_ID), API_HASH) as client:
        for idx, user in enumerate(invite_candidates):
            if count_sent >= remain_today:
                print("== Достигнут лимит рассылки на сегодня, стоп ==")
                break
            user_id, username = user["user_id"], user["username"]
            msg_key = random.choice(list(messages.keys()))
            template = messages[msg_key]
            msg = prepare_message(template)
            now_str = datetime.now().strftime(DATE_FORMAT)
            tries = 1
            log_rows = df_log[df_log["username"] == username]
            if not log_rows.empty:
                tries = get_last_try(log_rows.iloc[-1]) + 1

            invited, error_message = await try_send_message(
                client, username, msg, idx, len(invite_candidates)
            )

            if invited == 1:
                count_sent += 1

            log_row = {
                "user_id": user_id,
                "username": username,
                "invited": invited,
                "invite_datetime": now_str,
                "tries": tries,
                "error_message": error_message,
            }
            df_log = pd.concat([df_log, pd.DataFrame([log_row])], ignore_index=True)
            save_log(df_log)

            # Пауза между сообщениями (рандом)
            if (idx + 1) % BATCH_SIZE != 0:
                pause = random.uniform(MIN_PAUSE_SEC, MAX_PAUSE_SEC)
                time.sleep(pause)
            else:
                batch_pause = random.uniform(MIN_BATCH_PAUSE_SEC, MAX_BATCH_PAUSE_SEC)
                print(
                    f"Пауза после {BATCH_SIZE} сообщений: {int(batch_pause//60)} мин {int(batch_pause%60)} сек"
                )
                time.sleep(batch_pause)
    print("\n== Всё! Рассылка завершена ==\n")


if __name__ == "__main__":
    asyncio.run(main())
