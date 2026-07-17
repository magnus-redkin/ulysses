# cli/check.py

# АНАЛИЗ АНОМАЛИЙ И КРОСС-ДИАГНОСТИКА СИСТЕМЫ CLI CHECK
# Данный модуль выполняет глубокое перекрестное сканирование локальной базы данных PostgreSQL
# и удаленных нод VPN через API бэкенда. Выявляет критические аномалии профилей, расхождения
# тумблеров активности аккаунтов, зависшие подписки и просроченные инвойсы.

import asyncio
import httpx
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()
BACKEND_API_URL = "http://127.0.0.1:8000"

CONTEXT_SETTINGS = dict(
    help_option_names=['-h', '--help'],
    max_content_width=120
)

@click.command(context_settings=CONTEXT_SETTINGS)
@click.argument('query', required=False)
@click.option('--verbose', '-v', is_flag=True, help="Показать детальный список проблемных сущностей")
def check(query, verbose):
    """Проверить систему на аномалии и рассинхронизацию с нодами VPN.

    Без аргументов — полная сводка по всем аномалиям системы.\n
    С аргументом — детализация по конкретному UUID, email, tg_id или username.\n
    С флагом -v — разворачивает списки проблемных ID прямо в сводке.\n
    Пример: uadmin check -v
    """
    async def _run():
        if query:
            await _check_entity(query)
        else:
            await _check_summary(verbose)

    asyncio.run(_run())

check.get_usage = lambda ctx: "uadmin check [ОПЦИИ] [QUERY]"


async def _check_summary(verbose: bool):
    """Полная сводка аномалий"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(f"{BACKEND_API_URL}/api/admin/check")
            if response.status_code != 200:
                console.print(f"[red]❌ Ошибка API: {response.status_code}[/red]")
                return

            data = response.json()
            summary = data.get("summary", {})

            console.print(Panel.fit(
                "[bold red]🔍 ПРОВЕРКА СИСТЕМЫ[/bold red]",
                border_style="red"
            ))

            sum_table = Table(title="Сводный отчёт")
            sum_table.add_column("Категория", style="cyan")
            sum_table.add_column("Аномалии", style="yellow")

            dirty_invoices = summary.get("dirty_invoices_count", 0)
            failed_provisioning = summary.get("failed_provisioning_count", 0)

            sum_table.add_row("🗑️ Устаревшие инвойсы", str(dirty_invoices))
            sum_table.add_row("🚨 Зависшие активации", str(failed_provisioning))
            sum_table.add_row("🔄 Расхождения статусов с Hiddify", str(summary.get("status_mismatches_count", 0)))
            sum_table.add_row("🌍 Критические аномалии профилей", str(summary.get("hiddify_anomalies_count", 0)))
            console.print(sum_table)

            # 🌟 ДЕТАЛИЗАЦИЯ ПО ФЛАГУ --VERBOSE НАПРЯМУЮ ИЗ БД
                        # 🌟 ДЕТАЛИЗАЦИЯ ПО ФЛАГУ --VERBOSE НАПРЯМУЮ ИЗ БД И API
            if verbose:
                from app.database import AsyncSessionLocal
                from sqlalchemy import text

                async with AsyncSessionLocal() as session:
                    # 1. КАТЕГОРИЯ: УСТАРЕВШИЕ ИНВОЙСЫ
                    if dirty_invoices > 0:
                        console.print("\n[bold red]📋 Детализация устаревших инвойсов (старше 48ч):[/bold red]")
                        inv_sql = """
                            SELECT id, email, tariff_slug, amount, created_at
                            FROM payment_attempts
                            WHERE status = 'pending' AND created_at < NOW() - INTERVAL '2 days'
                            ORDER BY created_at DESC
                        """
                        inv_res = await session.execute(text(inv_sql))
                        inv_rows = inv_res.fetchall()

                        inv_table = Table(border_style="red")
                        inv_table.add_column("Invoice ID (UUID)", style="dim")
                        inv_table.add_column("Контакты / Алиас", style="cyan")
                        inv_table.add_column("Тариф", style="blue")
                        inv_table.add_column("Сумма", style="green")
                        inv_table.add_column("Создан", style="white")

                        for r in inv_rows:
                            i_id, email, tariff, amount, created_at = r
                            inv_table.add_row(
                                str(i_id), email, tariff, f"{amount} RUB",
                                created_at.strftime("%Y-%m-%d %H:%M") if created_at else "-"
                            )
                        console.print(inv_table)

                    # 2. КАТЕГОРИЯ: ЗАВИСШИЕ АКТИВАЦИИ (STATUS = PROVISIONING)
                    if failed_provisioning > 0:
                        console.print("\n[bold yellow]📋 Детализация подписок, зависших в очереди выдачи нод:[/bold yellow]")
                        sub_sql = """
                            SELECT s.id, u.tg_user_id, u.email, s.tariff_slug, s.provisioning_attempts, s.provisioning_error
                            FROM subscriptions s
                            JOIN users u ON s.user_id = u.id
                            WHERE s.status = 'provisioning_failed' OR s.status = 'provisioning'
                            ORDER BY s.id DESC
                        """
                        sub_res = await session.execute(text(sub_sql))
                        sub_rows = sub_res.fetchall()

                        sub_table = Table(border_style="yellow")
                        sub_table.add_column("Sub ID", style="dim", justify="center")
                        sub_table.add_column("Пользователь (Контакты)", style="cyan")
                        sub_table.add_column("Тариф", style="blue")
                        sub_table.add_column("Попыток", style="magenta", justify="center")
                        sub_table.add_column("Последний Traceback / Текст ошибки ноды", style="red")

                        for r in sub_rows:
                            s_id, tg_id, email, tariff_slug, atts, err = r
                            contact = f"TG: {tg_id}" if tg_id else email
                            sub_table.add_row(str(s_id), contact, tariff_slug, str(atts or 0), str(err or "Ожидает повтора"))
                        console.print(sub_table)

            # 3. КАТЕГОРИИ ИЗ API: РАСХОЖДЕНИЯ С HIDDIFY И СТРУКТУРНЫЕ АНОМАЛИИ
            # (Эти блоки уже написаны у вас ниже на основе массивов `data.get("status_mismatches")`
            # и `data.get("anomalies")`. Они сработают автоматически при наличии данных в JSON ответе бэкенда!)


            mismatches = data.get("status_mismatches", [])
            if mismatches:
                console.print("\n[bold yellow]🔄 Расхождения активности с Hiddify:[/bold yellow]")
                mis_table = Table()
                mis_table.add_column("Аккаунт", style="green")
                mis_table.add_column("UUID", style="yellow")
                mis_table.add_column("Проблема", style="red")
                mis_table.add_column("План", style="cyan")
                for m in mismatches:
                    action_text = "Включить" if m["action"] == "enable" else "Отключить"
                    mis_table.add_row(m.get("email", "—"), m["uuid"], m["issue"], action_text)
                console.print(mis_table)

            anomalies = data.get("anomalies", [])
            if anomalies:
                console.print("\n[bold orange3]⚠️ Критические структурные аномалии:[/bold orange3]")
                an_table = Table()
                an_table.add_column("Тип", style="cyan")
                an_table.add_column("Сущность", style="green")
                an_table.add_column("UUID", style="yellow")
                an_table.add_column("Описание", style="red")
                for a in anomalies:
                    an_table.add_row(a.get("type", "—"), a.get("email", "—"), a["uuid"], a.get("details", "—"))
                console.print(an_table)

            total = (dirty_invoices + failed_provisioning +
                     summary.get("status_mismatches_count", 0) + summary.get("hiddify_anomalies_count", 0))

            if total == 0:
                console.print("\n[green]✅ Система в порядке. Аномалий не обнаружено.[/green]")
            else:
                console.print(f"\n[yellow]⚠️ Всего аномалий: {total}[/yellow]")
                console.print("[dim]uadmin check <uuid|email|tg> — детализация по конкретной сущности[/dim]")
                console.print("[dim]uadmin check -v            — развернуть все списки аномалий сразу[/dim]")

    except Exception as e:
        console.print(f"[red]❌ Ошибка: {e}[/red]")

async def _check_entity(query: str):
    """Детализация по конкретной сущности"""
    console.print(f"[yellow]🔍 Поиск: {query}...[/yellow]")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{BACKEND_API_URL}/api/admin/check",
                params={"query": query}
            )

            if response.status_code == 404:
                console.print("[red]❌ Не найдено ни в биллинге, ни в Hiddify[/red]")
                return

            if response.status_code != 200:
                console.print(f"[red]❌ Ошибка API: {response.status_code}[/red]")
                return

            data = response.json()
            anomaly = data.get("anomaly")

            entity_type = "Аккаунт" if data.get("found_in_db") else "Профиль Hiddify"
            console.print(Panel.fit(f"[bold blue]🔎 {entity_type}: {query}[/bold blue]", border_style="blue"))

            account = data.get("account")
            if account:
                acc_table = Table(title="📋 Биллинг (Аккаунт)")
                acc_table.add_column("Поле", style="cyan")
                acc_table.add_column("Значение", style="green")
                acc_table.add_row("ID", str(account.get("id") or "—"))
                acc_table.add_row("Email", account.get("email") or "—")
                acc_table.add_row("TG ID", str(account.get("tg_user_id") or "—"))
                acc_table.add_row("TG Username", f"@{account.get('tg_username')}" if account.get("tg_username") else "—")
                acc_table.add_row("UUID", account.get("hiddify_uuid") or "—")
                console.print(acc_table)

            subscription = data.get("subscription")
            if subscription:
                sub_table = Table(title="📅 Подписка")
                sub_table.add_column("Поле", style="cyan")
                sub_table.add_column("Значение", style="green")
                sub_table.add_row("ID", str(subscription.get("id") or "—"))
                sub_table.add_row("Статус", subscription.get("status") or "—")
                sub_table.add_row("Тариф", subscription.get("tariff_slug") or "—")
                sub_table.add_row("Истекает", subscription.get("expires_at") or "—")
                console.print(sub_table)

            hiddify = data.get("hiddify_profile")
            if hiddify:
                hf_table = Table(title="🔑 Hiddify (Профиль)")
                hf_table.add_column("Поле", style="cyan")
                hf_table.add_column("Значение", style="yellow")
                hf_table.add_row("Имя", hiddify.get("name", "—"))
                hf_table.add_row("UUID", hiddify.get("uuid", "—"))
                hf_table.add_row("Статус", "🟢 Включен" if hiddify.get("enabled") else "🔴 Выключен")
                hf_table.add_row("Трафик", f"{hiddify.get('usage_gb', 0)} / {hiddify.get('limit_gb', 0)} GB")
                hf_table.add_row("Дней осталось", str(hiddify.get("days_left", "—")))
                console.print(hf_table)

            if anomaly:
                anomaly_map = {
                    "missing_in_hiddify": "🔴 Аккаунт в биллинге, но профиль отсутствует в Hiddify",
                    "unknown_in_db": "🟡 Профиль в Hiddify, но отсутствует в биллинге",
                    "should_be_enabled": "🟡 Должен быть включен, но выключен в Hiddify",
                    "should_be_disabled": "🟡 Должен быть выключен, но включен в Hiddify"
                }
                console.print(f"\n[bold red]⚠️ Аномалия:[/bold red] {anomaly_map.get(anomaly, anomaly)}")

                if anomaly == "missing_in_hiddify":
                    console.print("\n[dim]Исправление (ручное):[/dim]")
                    console.print("[dim]  → Пересоздать профиль в админке Hiddify[/dim]")
                    if account and account.get("hiddify_uuid"):
                        console.print(f"[dim]  → Аккаунт: uadmin user list --query {account['hiddify_uuid']}[/dim]")
                elif anomaly == "unknown_in_db":
                    console.print("\n[dim]Исправление (ручное):[/dim]")
                    console.print("[dim]  → Удалить профиль в админке Hiddify[/dim]")
                    console.print("[dim]  → Или создать аккаунт в биллинге с этим UUID[/dim]")
                elif anomaly in ("should_be_enabled", "should_be_disabled"):
                    console.print("\n[dim]Исправление (автоматическое):[/dim]")
                    console.print("[dim]  → uadmin fix sync[/dim]")
            else:
                console.print("\n[green]✅ Аномалий нет. Всё синхронизировано.[/green]")

    except Exception as e:
        console.print(f"[red]❌ Ошибка: {e}[/red]")


if __name__ == "__main__":
    check(prog_name="uadmin check")
