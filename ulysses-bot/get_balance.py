async def get_balance(tg_id: int) -> str:
    """Получение баланса пользователя"""
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(text("""
                SELECT s.hiddify_uuid, u.email, s.status
                FROM subscriptions s
                JOIN users u ON s.user_id = u.id
                WHERE u.tg_user_id = :tg_id
                ORDER BY s.created_at DESC
                LIMIT 1
            """), {"tg_id": tg_id})
            row = result.fetchone()

            if not row:
                return "⚠️ *Аккаунт не привязан*\n\nИспользуйте ссылку из письма для привязки."

            uuid, email, status = str(row[0]), row[1], row[2]

            logger.info(f"🔍 Поиск баланса: tg={tg_id}, uuid={uuid[:8]}..., status={status}")

            # Если статус provisioning - сообщаем что активируется
            if status == 'provisioning':
                return (
                    "🔄 *Подписка активируется*\n\n"
                    f"📧 `{email}`\n\n"
                    "Ваша подписка оплачена и скоро будет активирована.\n"
                    "Обычно это занимает до 1 минуты.\n\n"
                    "Попробуйте проверить позже."
                )

            # Запрос к Hiddify API
            headers = {"Hiddify-API-Key": HIDDIFY_API_KEY}
            response = await http_client.get(HIDDIFY_BASE_URL, headers=headers)

            if response.status_code != 200:
                return "⚠️ Сервер временно недоступен"

            users = response.json()
            target = None

            for u in users:
                if str(u.get("uuid", "")).lower() == uuid.lower():
                    target = u
                    break

            if not target:
                # Проверяем еще раз - может UUID в другом регистре
                logger.warning(f"UUID {uuid} не найден в API. Всего пользователей: {len(users)}")
                return (
                    "⚠️ *Подписка синхронизируется*\n\n"
                    "Подписка найдена в биллинге, но еще не появилась на VPN-сервере.\n"
                    "Обычно это занимает до 1 минуты.\n\n"
                    "Попробуйте позже или нажмите /start для обновления."
                )

            usage = float(target.get("current_usage_GB", 0))
            total = float(target.get("usage_limit_GB", 0))
            days = int(target.get("package_days", 0))
            active = bool(target.get("enable", True))
            remaining = max(0, total - usage)
            pct = (usage / total * 100) if total > 0 else 0

            status_text = "🟢 Активна" if active else "🔴 Приостановлена"
            bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))

            msg = (
                f"📊 *Статус подписки*\n\n"
                f"{status_text}\n"
                f"📧 `{email}`\n\n"
                f"📈 Трафик:\n"
                f"`{bar}` {pct:.1f}%\n"
                f"• Использовано: *{usage:.2f} ГБ*\n"
                f"• Осталось: *{remaining:.2f} ГБ*\n"
                f"• Всего: *{total:.0f} ГБ*\n\n"
                f"⏳ Дней: *{days}*"
            )

            return msg

        except Exception as e:
            logger.error(f"Ошибка баланса: {e}")
            return "⚠️ Не удалось загрузить данные"
