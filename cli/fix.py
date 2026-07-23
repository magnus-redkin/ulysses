# cli/fix.py

# АВТОМАТИЧЕСКОЕ ИСПРАВЛЕНИЕ И СИНХРОНИЗАЦИЯ СОСТОЯНИЯ КОНТУРА CLI FIX
# Модуль инкапсулирует административные команды для оперативного устранения аномалий.
# Обеспечивает ручную синхронизацию активности нод, сброс аварийных счетчиков очередей
# напрямую в СУБД и повторный точечный перезапуск выдачи услуг по идентификатору подписки.

import asyncio
import httpx
import click
from rich.console import Console

console = Console()
BACKEND_API_URL = "http://127.0.0.1:8000"

CONTEXT_SETTINGS = dict(
    help_option_names=['-h', '--help'],
    max_content_width=120
)

@click.group(context_settings=CONTEXT_SETTINGS)
def fix():
    """Инструменты автоматического исправления и синхронизации Ulysses VPN.

    Использование: uadmin fix КОМАНДА [АРГУМЕНТЫ]...
    """
    pass

fix.get_usage = lambda ctx: "uadmin fix [ОПЦИИ] КОМАНДА [ARGS]..."


@fix.command(name="sync")
def fix_sync():
    """Запустить принудительную синхронизацию состояния БД и нод VPN.

    Пример: uadmin fix sync
    """
    console.print("[yellow]⏳ Отправка запроса на синхронизацию нод...[/yellow]")
    async def _sync():
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(f"{BACKEND_API_URL}/api/admin/fix/sync")
                if response.status_code == 200:
                    console.print(f"[green]✅ Синхронизация успешно выполнена: {response.json()}[/green]")
                else:
                    console.print(f"[red]❌ Ошибка выполнения: HTTP {response.status_code} - {response.text}[/red]")
        except Exception as e:
            console.print(f"[red]❌ Ошибка подключения к бэкенду: {e}[/red]")

    asyncio.run(_sync())


@fix.command(name="pending")
@click.option("--force", is_flag=True, help="Принудительно обнулить счетчики попыток в СУБД перед запуском")
def fix_pending(force):
    """Принудительно перезапустить обработку всех зависших подписок.

    Пример: uadmin fix pending --force
    """
    async def _pending():
        if force:
            console.print("[yellow]🔄 Флаг --force активирован. Сброс счетчиков попыток в БД...[/yellow]")
            from app.database import AsyncSessionLocal
            from sqlalchemy import text

            try:
                async with AsyncSessionLocal() as session:
                    # 🟢 ИСПРАВЛЕНО: Заменен NOW() на CURRENT_TIMESTAMP для строгого соответствия TZ схемы
                    sql = """
                        UPDATE subscriptions
                        SET provisioning_attempts = 0, provisioning_error = NULL, updated_at = CURRENT_TIMESTAMP
                        WHERE status = 'provisioning'
                    """
                    result = await session.execute(text(sql))
                    await session.commit()
                    console.print(f"[green]✅ Сброшено записей в карантине: {result.rowcount}[/green]")
            except Exception as db_err:
                console.print(f"[red]❌ Ошибка при сбросе счетчиков в БД: {db_err}[/red]")
                return

        console.print("[yellow]⏳ Попытка повторной активации зависших подписок через API бэкенда...[/yellow]")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(f"{BACKEND_API_URL}/api/admin/fix/process-pending")
                if response.status_code == 200:
                    console.print(f"[green]✅ Обработка завершена: {response.json()}[/green]")
                else:
                    console.print(f"[red]❌ Ошибка выполнения: HTTP {response.status_code} - {response.text}[/red]")
        except Exception as e:
            console.print(f"[red]❌ Ошибка подключения к бэкенду: {e}[/red]")

    asyncio.run(_pending())


@fix.command(name="invoices")
def fix_invoices():
    """Очистить зависшие, просроченные или неоплаченные инвойсы.

    Пример: uadmin fix invoices
    """
    console.print("[yellow]⏳ Запуск процедуры очистки зависших счетов...[/yellow]")
    async def _cleanup():
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(f"{BACKEND_API_URL}/api/admin/fix/cleanup-invoices")
                if response.status_code == 200:
                    console.print(f"[green]✅ Очистка завершена: {response.json()}[/green]")
                else:
                    console.print(f"[red]❌ Ошибка выполнения: HTTP {response.status_code} - {response.text}[/red]")
        except Exception as e:
            console.print(f"[red]❌ Ошибка подключения к бэкенду: {e}[/red]")

    asyncio.run(_cleanup())


@fix.command(name="retry")
@click.argument("subscription_id", type=int)
def fix_retry(subscription_id: int):
    """Принудительно перезапустить выдачу для конкретной подписки по её ID.

    Пример: uadmin fix retry 63
    """
    console.print(f"[yellow]⏳ Отправка запроса на повтор активации подписки #[bold]{subscription_id}[/bold]...[/yellow]")

    async def _retry():
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(f"{BACKEND_API_URL}/api/billing/retry-provisioning/{subscription_id}")

                if response.status_code == 200:
                    data = response.json()
                    # 🟢 ИСПРАВЛЕНО: Безопасное приведение к строке при проверке статуса бэкенда
                    status_val = str(data.get("status", "")).lower()
                    if status_val in ("activated", "success", "active"):
                        console.print(f"[green]✅ Успешно: Подписка #[bold]{subscription_id}[/bold] активирована в Hiddify![/green]")
                    else:
                        console.print(f"[yellow]⚠️ Бэкенд вернул статус: {data}[/yellow]")
                else:
                    console.print(f"[red]❌ Ошибка бэкенда: HTTP {response.status_code} - {response.text}[/red]")
        except Exception as e:
            console.print(f"[red]❌ Ошибка подключения к бэкенду: {e}[/red]")

    asyncio.run(_retry())


if __name__ == "__main__":
    fix(prog_name="uadmin fix")
