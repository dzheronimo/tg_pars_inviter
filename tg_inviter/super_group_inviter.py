import asyncio
from telethon import TelegramClient
from telethon.tl.functions.channels import (
    GetParticipantsRequest,
    InviteToChannelRequest,
)
from telethon.tl.types import ChannelParticipantsSearch
import pandas as pd
import time
from datetime import datetime, timedelta
import os

API_ID = "26097139"
API_HASH = "08fb3f70f75dc2f320464c8e90ecce57"
SESSION_NAME = "parser_session"
GROUP_LINK_OR_ID = "thai4us"  # например, -1001234567890 или username группы
USERS_CSV = "users.csv"
INVITED_LOG_CSV = "invited_log.csv"
USERS_PER_BATCH = 10
BATCH_PAUSE_SEC = 120
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def load_log():
    if os.path.exists(INVITED_LOG_CSV):
        return pd.read_csv(INVITED_LOG_CSV, dtype=str)
    return pd.DataFrame(
        columns=[
            "user_id",
            "username",
            "invited",
            "invite_datetime",
            "is_member",
            "last_check_datetime",
            "tries",
            "error_message",
        ]
    )


def save_log(df):
    df.to_csv(INVITED_LOG_CSV, index=False, encoding="utf-8-sig")


def eligible_for_invite(row):
    if row.get("is_member", "0") == "1":
        return False
    if row.get("invited", "0") == "1" and row.get("invite_datetime"):
        last_sent = datetime.strptime(row["invite_datetime"], DATE_FORMAT)
        if (datetime.now() - last_sent).days < 30:
            return False
    return True


def get_last_try(row):
    try:
        return int(row.get("tries", 0))
    except Exception:
        return 0


async def is_member(client, group, user_id, username):
    try:
        search = str(username) if pd.notna(username) and username else str(user_id)
        result = await client(
            GetParticipantsRequest(
                channel=group,
                filter=ChannelParticipantsSearch(search),
                offset=0,
                limit=100,
                hash=0,
            )
        )
        for p in result.users:
            if (str(p.id) == str(user_id)) or (
                username and p.username and p.username.lower() == username.lower()
            ):
                return True
        return False
    except Exception as e:
        print(f"   [!] Ошибка при проверке членства {user_id}: {e}")
        return False


async def main():
    df_users = pd.read_csv(USERS_CSV, dtype=str)
    df_log = load_log()
    users_dict = {}  # user_id: row in log
    for _, row in df_log.iterrows():
        users_dict[str(row["user_id"])] = row

    to_check = []
    for _, row in df_users.iterrows():
        user_id = str(row["user_id"])
        username = str(row["username"]) if pd.notna(row["username"]) else ""
        record = users_dict.get(user_id)
        if record:
            if not eligible_for_invite(record):
                continue
        to_check.append({"user_id": user_id, "username": username})

    print(f"Пользователей для проверки/инвайта: {len(to_check)}")

    async with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
        group = await client.get_entity(GROUP_LINK_OR_ID)
        invite_candidates = []
        for i, user in enumerate(to_check):
            user_id, username = user["user_id"], user["username"]
            now_str = datetime.now().strftime(DATE_FORMAT)
            member = await is_member(client, group, user_id, username)
            tries = 0
            last_error = ""
            # Найти число попыток по user_id
            record = df_log[df_log["user_id"] == user_id]
            if not record.empty:
                tries = get_last_try(record.iloc[-1])
            log_row = {
                "user_id": user_id,
                "username": username,
                "invited": 0,
                "invite_datetime": "",
                "is_member": int(member),
                "last_check_datetime": now_str,
                "tries": tries,
                "error_message": last_error,
            }
            df_log = df_log.append(log_row, ignore_index=True)
            if not member:
                invite_candidates.append(
                    {"user_id": user_id, "username": username, "tries": tries}
                )
            if i % 10 == 0:
                save_log(df_log)
        save_log(df_log)

        print(f"Кандидатов к инвайту: {len(invite_candidates)}")
        # Отправка приглашений пачками
        for i in range(0, len(invite_candidates), USERS_PER_BATCH):
            batch = invite_candidates[i : i + USERS_PER_BATCH]
            try:
                users_tuples = [int(c["user_id"]) for c in batch]
                await client(InviteToChannelRequest(channel=group, users=users_tuples))
                print(
                    f"  ✓ Добавлено {len(users_tuples)} пользователей ({i+1}-{i+len(users_tuples)})"
                )
                invite_time = datetime.now().strftime(DATE_FORMAT)
                for user in batch:
                    df_log = df_log.append(
                        {
                            "user_id": user["user_id"],
                            "username": user["username"],
                            "invited": 1,
                            "invite_datetime": invite_time,
                            "is_member": 0,
                            "last_check_datetime": invite_time,
                            "tries": user["tries"] + 1,
                            "error_message": "",
                        },
                        ignore_index=True,
                    )
            except Exception as e:
                print(f"  [!] Ошибка при добавлении пачки: {e}")
                invite_time = datetime.now().strftime(DATE_FORMAT)
                for user in batch:
                    df_log = df_log.append(
                        {
                            "user_id": user["user_id"],
                            "username": user["username"],
                            "invited": 0,
                            "invite_datetime": invite_time,
                            "is_member": 0,
                            "last_check_datetime": invite_time,
                            "tries": user["tries"] + 1,
                            "error_message": str(e),
                        },
                        ignore_index=True,
                    )
            save_log(df_log)
            time.sleep(BATCH_PAUSE_SEC)
    print("\n== Всё! Добавление завершено ==\n")


if __name__ == "__main__":
    asyncio.run(main())
