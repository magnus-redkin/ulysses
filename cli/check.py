# cli/check.py
"""
Проверка аномалий системы: расхождения с Hiddify, зависшие подписки, мусор.
"""
import asyncio
import httpx
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()
BACKEND_API_URL = "http://127.0.0.1:8000"


@click.command()
@click.argument('query', required=False)
def check(query):
    """
    Проверить систему на аномалии.

    Без аргументов — полная сводка по всем аномалиям.
    С аргументом — детализация по UUID, email, tg_id или username.
    """

    async def _run():
        if query:
            await _check_entity(query)
        else:
            await _check_summary()

    asyncio.run(_run())


async def _check_summary():
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

            sum_table.add_row("🗑️ Устаревшие инвойсы", str(summary.get("dirty_invoices_count", 0)))
            sum_table.add_row("🚨 Зависшие активации", str(summary.get("failed_provisioning_count", 0)))
            sum_table.add_row("🔄 Расхождения статусов с Hiddify", str(summary.get("status_mismatches_count", 0)))
            sum_table.add_row("🌍 Критические аномалии профилей", str(summary.get("hiddify_anomalies_count", 0)))
            console.print(sum_table)

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

            total = (summary.get("dirty_invoices_count", 0) + summary.get("failed_provisioning_count", 0) +
                     summary.get("status_mismatches_count", 0) + summary.get("hiddify_anomalies_count", 0))

            if total == 0:
                console.print("\n[green]✅ Система в порядке. Аномалий не обнаружено.[/green]")
            else:
                console.print(f"\n[yellow]⚠️ Всего аномалий: {total}[/yellow]")
                console.print("[dim]uv run cli.py check <uuid|email|tg> — детализация по сущности[/dim]")
                console.print("[dim]uv run cli.py fix sync — исправление расхождений статусов[/dim]")

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
                        console.print(f"[dim]  → Аккаунт: uv run cli.py user info --uuid {account['hiddify_uuid']}[/dim]")
                elif anomaly == "unknown_in_db":
                    console.print("\n[dim]Исправление (ручное):[/dim]")
                    console.print("[dim]  → Удалить профиль в админке Hiddify[/dim]")
                    console.print("[dim]  → Или создать аккаунт в биллинге с этим UUID[/dim]")
                elif anomaly in ("should_be_enabled", "should_be_disabled"):
                    console.print("\n[dim]Исправление (автоматическое):[/dim]")
                    console.print("[dim]  → uv run cli.py fix sync[/dim]")
            else:
                console.print("\n[green]✅ Аномалий нет. Всё синхронизировано.[/green]")

    except Exception as e:
        console.print(f"[red]❌ Ошибка: {e}[/red]")
