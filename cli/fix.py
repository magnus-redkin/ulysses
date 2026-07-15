import asyncio
import httpx
import click
from rich.console import Console

console = Console()
BACKEND_API_URL = "http://127.0.0.1:8000"

@click.group()
def fix():
    """Инструменты автоматического исправления и синхронизации Ulysses VPN"""
    pass


@fix.command(name="sync")
def fix_sync():
    """Запустить принудительную синхронизацию состояния БД и нод VPN"""
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
@click.option("--force", is_flag=True, help="Принудительно обнулить счетчики попыток перед запуском")
def fix_pending(force):
    """Принудительно перезапустить обработку всех зависших подписок"""

    async def _pending():
        # Если передан флаг --force, сначала сбрасываем ошибки напрямую в БД
        if force:
            console.print("[yellow]🔄 Флаг --force активирован. Сброс счетчиков попыток в БД...[/yellow]")
            from app.database import AsyncSessionLocal
            from sqlalchemy import text

            try:
                async with AsyncSessionLocal() as session:
                    # Обнуляем попытки и стираем текст ошибки для всех provisioning подписок
                    sql = """
                        UPDATE subscriptions
                        SET provisioning_attempts = 0, provisioning_error = NULL, updated_at = NOW()
                        WHERE status = 'provisioning'
                    """
                    result = await session.execute(text(sql))
                    await session.commit()
                    console.print(f"[green]✅ Сброшено записей в карантине: {result.rowcount}[/green]")
            except Exception as db_err:
                console.print(f"[red]❌ Ошибка при сбросе счетчиков в БД: {db_err}[/red]")
                return

        console.print("[yellow]⏳ Попытка повторной активации зависших подписок через API...[/yellow]")
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
    """Очистить зависшие, просроченные или неоплаченные инвойсы"""
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
