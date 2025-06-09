import asyncio
import os
from dotenv import load_dotenv

from telethon import TelegramClient
from telethon.errors.rpcerrorlist import ChannelPrivateError
from telethon.tl.types import ChannelParticipantsAdmins
import pandas as pd
import re

load_dotenv()


API_ID = os.getenv("API_ID", "")
API_HASH = os.getenv("API_HASH", "")
SESSION_NAME = os.getenv("SESSION_NAME", "")
CHANNELS_FILE = os.getenv("CHANNELS_FILE", "")
USERS_CSV = os.getenv("USERS_CSV", "")
PARSED_SOURCES_FILE = os.getenv("PARSED_SOURCES_FILE", "")

FIELDS = ["user_id", "access_hash", "username", "first_name", "last_name", "is_bot"]

print("=== PARSER APP STARTED ===", flush=True)


def parse_line(line):
    """Преобразует строку в username, id или (username, message_id) для поста"""
    line = line.strip()
    if not line:
        return None
    m = re.match(r"^https://t\.me/([a-zA-Z0-9_]+)/(\d+)$", line)
    if m:
        return (m.group(1), int(m.group(2)))
    m = re.match(r"^https://t\.me/([a-zA-Z0-9_]+)$", line)
    if m:
        return m.group(1)
    if re.match(r"^-?\d+$", line):
        return int(line)
    if line.startswith("@"):
        return line[1:]
    return line


def load_parsed_sources():
    if os.path.exists(PARSED_SOURCES_FILE):
        with open(PARSED_SOURCES_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def save_parsed_source(source):
    with open(PARSED_SOURCES_FILE, "a", encoding="utf-8") as f:
        f.write(f"{source}\n")


def load_users():
    if os.path.exists(USERS_CSV):
        df = pd.read_csv(USERS_CSV, dtype={"user_id": str, "access_hash": str})
        return {int(row["user_id"]): dict(row) for _, row in df.iterrows()}
    return {}


def save_users(users_dict):
    if users_dict:
        df = pd.DataFrame(list(users_dict.values()))
        df.to_csv(USERS_CSV, index=False, columns=FIELDS, encoding="utf-8-sig")


async def get_admins(client, entity):
    admins = set()
    try:
        async for user in client.iter_participants(
            entity, filter=ChannelParticipantsAdmins
        ):
            admins.add(user.id)
    except Exception:
        pass
    return admins


async def get_discussion_id(client, channel):
    """Пытаемся найти обсуждение/чат для комментариев (если привязан)"""
    try:
        entity = await client.get_entity(channel)
        if hasattr(entity, "linked_chat_id") and entity.linked_chat_id:
            return entity.linked_chat_id
    except Exception:
        pass
    return None


async def parse_chat(client, chat, users_dict):
    try:
        entity = await client.get_entity(chat)
    except ChannelPrivateError:
        print(
            f"[!] Нет доступа к {chat} (приватный канал/группа). Добавьте себя в чат!"
        )
        return
    except Exception as e:
        print(f"[!] Ошибка доступа к {chat}: {e}")
        return

    print(f"▶ Парсим: {getattr(entity, 'title', chat)}")

    admins = await get_admins(client, entity)
    # Получаем участников (где разрешено)
    try:
        async for user in client.iter_participants(entity):
            if user.bot or user.id in admins:
                continue
            if user.id not in users_dict:
                users_dict[user.id] = {
                    "user_id": user.id,
                    "access_hash": getattr(user, "access_hash", ""),
                    "username": getattr(user, "username", ""),
                    "first_name": getattr(user, "first_name", ""),
                    "last_name": getattr(user, "last_name", ""),
                    "is_bot": user.bot,
                }
    except Exception as e:
        print(f"    [!] Не удалось получить участников: {e}")

    # Авторов сообщений и реакций
    try:
        async for msg in client.iter_messages(entity, limit=1000):
            # Автор поста
            if (
                msg.sender_id
                and msg.sender_id not in users_dict
                and msg.sender_id not in admins
            ):
                try:
                    user = await client.get_entity(msg.sender_id)
                    if not user.bot:
                        users_dict[user.id] = {
                            "user_id": user.id,
                            "access_hash": getattr(user, "access_hash", ""),
                            "username": getattr(user, "username", ""),
                            "first_name": getattr(user, "first_name", ""),
                            "last_name": getattr(user, "last_name", ""),
                            "is_bot": user.bot,
                        }
                except Exception:
                    continue
            # Реакции (где доступны)
            if getattr(msg, "reactions", None):
                for reaction in msg.reactions.results:
                    for peer_id in getattr(reaction, "recent_reacters_ids", []):
                        if peer_id not in users_dict and peer_id not in admins:
                            try:
                                user = await client.get_entity(peer_id)
                                if not user.bot:
                                    users_dict[user.id] = {
                                        "user_id": user.id,
                                        "access_hash": getattr(user, "access_hash", ""),
                                        "username": getattr(user, "username", ""),
                                        "first_name": getattr(user, "first_name", ""),
                                        "last_name": getattr(user, "last_name", ""),
                                        "is_bot": user.bot,
                                    }
                            except Exception:
                                continue
    except Exception as e:
        print(f"    [!] Не удалось получить сообщения: {e}")

    # Поиск комментаторов (если включено обсуждение)
    discussion_id = await get_discussion_id(client, chat)
    if discussion_id:
        print("    └ Ищем комментаторов из обсуждений...")
        await parse_chat(client, discussion_id, users_dict)


async def parse_source(client, source, users_dict):
    if isinstance(source, tuple) and len(source) == 2:
        # Это ссылка на сообщение (канал, message_id)
        username, msg_id = source
        try:
            entity = await client.get_entity(username)
            msg = await client.get_messages(entity, ids=msg_id)
            # Автор сообщения
            if msg.sender_id:
                user = await client.get_entity(msg.sender_id)
                if not user.bot and user.id not in users_dict:
                    users_dict[user.id] = {
                        "user_id": user.id,
                        "access_hash": getattr(user, "access_hash", ""),
                        "username": getattr(user, "username", ""),
                        "first_name": getattr(user, "first_name", ""),
                        "last_name": getattr(user, "last_name", ""),
                        "is_bot": user.bot,
                    }
            # Реакции
            if getattr(msg, "reactions", None):
                for reaction in msg.reactions.results:
                    for peer_id in getattr(reaction, "recent_reacters_ids", []):
                        if peer_id not in users_dict:
                            try:
                                user = await client.get_entity(peer_id)
                                if not user.bot:
                                    users_dict[user.id] = {
                                        "user_id": user.id,
                                        "access_hash": getattr(user, "access_hash", ""),
                                        "username": getattr(user, "username", ""),
                                        "first_name": getattr(user, "first_name", ""),
                                        "last_name": getattr(user, "last_name", ""),
                                        "is_bot": user.bot,
                                    }
                            except Exception:
                                continue
        except Exception as e:
            print(f"[!] Ошибка при парсинге сообщения {source}: {e}")
    else:
        await parse_chat(client, source, users_dict)


async def main():
    if not os.path.exists(CHANNELS_FILE):
        print(f"[!] Не найден файл источников каналов: {CHANNELS_FILE}")
        return
    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        sources = [line.strip() for line in f if line.strip()]
    all_sources_set = set(sources)

    if os.path.exists(PARSED_SOURCES_FILE) or os.path.exists(USERS_CSV):
        print("\nОбнаружены предыдущие результаты.")
        MODE = os.getenv("PARSER_MODE", "continue")

        if MODE == "reset":
            print("Очистка прогресса по переменной окружения...")
            if os.path.exists(PARSED_SOURCES_FILE):
                os.remove(PARSED_SOURCES_FILE)
            if os.path.exists(USERS_CSV):
                os.remove(USERS_CSV)
            parsed_sources = set()
            users_dict = {}
        else:
            print("Продолжаем с места остановки (PARSER_MODE=continue)")
            parsed_sources = load_parsed_sources()
            users_dict = load_users()
            print(
                f"Продолжаем. Уже обработано {len(parsed_sources)} из {len(all_sources_set)} источников."
            )
    else:
        parsed_sources = set()
        users_dict = {}

    async with TelegramClient(SESSION_NAME, int(API_ID), API_HASH) as client:
        for idx, raw_source in enumerate(sources):
            if raw_source in parsed_sources:
                print(
                    f"[{idx+1}/{len(sources)}] Пропускаем уже обработанный источник: {raw_source}"
                )
                continue
            print(f"[{idx+1}/{len(sources)}] Парсим: {raw_source}")
            parsed_source = parse_line(raw_source)
            try:
                await parse_source(client, parsed_source, users_dict)
            except Exception as e:
                print(f"[!] Ошибка при обработке источника {raw_source}: {e}")
            save_parsed_source(raw_source)
            save_users(users_dict)
    print(f"\n✓ Завершено. Собрано уникальных пользователей: {len(users_dict)}")
    print(f"✓ Итоги сохранены в {USERS_CSV}")


if __name__ == "__main__":
    asyncio.run(main())
