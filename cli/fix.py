import os
import httpx
import click
from rich.console import Console

console = Console()
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000")
API_KEY = os.getenv("HOST_API_KEY", "")

@click.group()
def fix():
    """Инструменты автоматического исправления и синхронизации Ulysses VPN."""

@fix.command()
def cleanup_invoices():
    """Удалить все просроченные инвойсы (pending старше 24 часов)."""
    headers = {"X-API-Key": API_KEY}
    try:
        resp = httpx.post(
            f"{BACKEND_API_URL}/api/admin/fix/cleanup-invoices",
            headers=headers,
            timeout=15.0
        )
        if resp.status_code == 200:
            data = resp.json()
            console.print(f"[green]✅ Инвойсы очищены. Удалено: {data.get('deleted_count', 0)}[/green]")
        else:
            console.print(f"[red]❌ Ошибка API: {resp.status_code}[/red]")
            try:
                detail = resp.json().get("detail", "")
                if detail:
                    console.print(f"[dim]{detail}[/dim]")
            except Exception:
                pass
    except httpx.RequestError as e:
        console.print(f"[red]❌ Ошибка подключения к API: {e}[/red]")

@fix.command(name="process-pending")
@click.option("--limit", default=50, show_default=True, help="Максимальное число подписок для обработки")
def process_pending(limit):
    """Принудительно обработать зависшие подписки."""
    headers = {"X-API-Key": API_KEY}
    try:
        resp = httpx.post(
            f"{BACKEND_API_URL}/api/admin/fix/process-pending",
            headers=headers,
            params={"limit": limit},
            timeout=30.0
        )
        if resp.status_code == 200:
            data = resp.json()
            console.print(f"[green]✅ Обработано подписок: {data.get('processed_count', 0)}[/green]")
        else:
            console.print(f"[red]❌ Ошибка API: {resp.status_code}[/red]")
            if resp.status_code == 401:
                console.print("[dim]Проверьте HOST_API_KEY[/dim]")
    except httpx.RequestError as e:
        console.print(f"[red]❌ Ошибка подключения к API: {e}[/red]")
