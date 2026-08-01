# cli/db_utils.py
from sqlalchemy import text
import uuid

async def find_user_by_identifier(session, identifier: str):
    """
    Поиск пользователя по любому идентификатору.
    Возвращает кортеж (tg_username, tg_user_id, hiddify_uuid, db_id) или None.
    """
    row = None
    # print(f"DEBUG find_user_by_identifier: identifier={repr(identifier)}")
    # 1. По email (содержит @)
    if "@" in identifier:
        res = await session.execute(
            text("SELECT tg_username, tg_user_id, hiddify_uuid, id FROM users WHERE email = :email"),
            {"email": identifier}
        )
        row = res.fetchone()

    # 2. По UUID
    if not row:
        try:
            uuid.UUID(identifier)
            res = await session.execute(
                text("SELECT tg_username, tg_user_id, hiddify_uuid, id FROM users WHERE CAST(hiddify_uuid AS TEXT) = :uuid"),
                {"uuid": identifier}
            )
            row = res.fetchone()
        except ValueError:
            pass

    # 3. Число (TG ID или DB ID)
    if not row and identifier.isdigit():
        num = int(identifier)
        try:
            res = await session.execute(
                text("SELECT tg_username, tg_user_id, hiddify_uuid, id FROM users WHERE tg_user_id = :tg_id"),
                {"tg_id": num}
            )
            row = res.fetchone()
            # print(f"DEBUG tg_user_id search: num={num}, row={row}")
        except Exception as e:
            print(f"DEBUG tg_user_id search ERROR: {e}")

    return row
