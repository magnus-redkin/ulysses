# cli/db_utils.py

from sqlalchemy import text
import uuid


# Плейсхолдеры, которые нельзя использовать как username
_USERNAME_BLOCKLIST = {"unknown", "-", ""}


async def find_user_by_identifier(session, identifier: str):
    """
    Поиск пользователя по любому идентификатору:
      1. @username  (только если начинается с @)
      2. email      (если содержит @, но не в начале)
      3. UUID
      4. TG ID      (только цифры)
      5. DB ID      (только цифры, если TG ID не нашёлся)
      6. username   (без @ — на случай, если передали просто строку)

    Возвращает кортеж (tg_username, tg_user_id, hiddify_uuid, db_id) или None.
    """
    if not identifier:
        return None

    raw = str(identifier).strip()
    row = None

    # --- 1. @username ---
    if raw.startswith("@"):
        candidate = raw[1:].strip().lower()
        if candidate in _USERNAME_BLOCKLIST:
            return None
        res = await session.execute(
            text("""
                SELECT tg_username, tg_user_id, hiddify_uuid, id
                FROM users
                WHERE LOWER(tg_username) = :username
                  AND tg_username IS NOT NULL
                  AND LOWER(tg_username) NOT IN ('unknown', '-', '')
                LIMIT 1
            """),
            {"username": candidate}
        )
        return res.fetchone()

    # --- 2. email (содержит @, но не в начале) ---
    if "@" in raw:
        res = await session.execute(
            text("SELECT tg_username, tg_user_id, hiddify_uuid, id FROM users WHERE LOWER(email) = LOWER(:email)"),
            {"email": raw}
        )
        row = res.fetchone()
        if row:
            return row

    # --- 3. UUID ---
    try:
        uuid.UUID(raw)
        res = await session.execute(
            text("SELECT tg_username, tg_user_id, hiddify_uuid, id FROM users WHERE CAST(hiddify_uuid AS TEXT) = :uuid"),
            {"uuid": raw}
        )
        row = res.fetchone()
        if row:
            return row
    except ValueError:
        pass

    # --- 4./5. Число: TG ID, потом DB ID ---
    if raw.isdigit():
        num = int(raw)
        res = await session.execute(
            text("SELECT tg_username, tg_user_id, hiddify_uuid, id FROM users WHERE tg_user_id = :tg_id"),
            {"tg_id": num}
        )
        row = res.fetchone()
        if row:
            return row

        res = await session.execute(
            text("SELECT tg_username, tg_user_id, hiddify_uuid, id FROM users WHERE id = :db_id"),
            {"db_id": num}
        )
        row = res.fetchone()
        if row:
            return row

    # --- 6. username без @ ---
    candidate = raw.lower()
    if candidate not in _USERNAME_BLOCKLIST:
        res = await session.execute(
            text("""
                SELECT tg_username, tg_user_id, hiddify_uuid, id
                FROM users
                WHERE LOWER(tg_username) = :username
                  AND tg_username IS NOT NULL
                  AND LOWER(tg_username) NOT IN ('unknown', '-', '')
                LIMIT 1
            """),
            {"username": candidate}
        )
        row = res.fetchone()
        if row:
            return row

    return None
