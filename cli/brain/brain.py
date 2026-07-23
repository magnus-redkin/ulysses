# ulysses-backend/cli/brain.py

import asyncio
import click
from rich.console import Console
from rich.table import Table
from sqlalchemy import text
from app.database import AsyncSessionLocal

console = Console()

CONTEXT_SETTINGS = dict(
    help_option_names=['-h', '--help'],
    max_content_width=120
)

@click.group(context_settings=CONTEXT_SETTINGS)
def brain():
    """Управление сетевым ядром, щитами и телеметрией Ulysses VPN."""
    pass

brain.get_usage = lambda ctx: "uadmin brain [ОПЦИИ] КОМАНДА [ARGS]..."


@brain.command(name="status")
def brain_status():
    """Вывести текущий статус всех защитных щитов и DNS-маршрутизации."""
    async def _status():
        async with AsyncSessionLocal() as session:
            # 1. Таблица щитов
            res = await session.execute(text("SELECT id, ip, country, datacenter, status, last_health_check FROM brain.shields ORDER BY id ASC"))
            shields = res.fetchall()

            if not shields:
                console.print("[yellow]⚠️ В схеме brain.shields нет зарегистрированных нод.[/yellow]")
                return

            table = Table(title="🛡️ Защитные щиты (Сетевой контур)")
            table.add_column("ID", justify="center", style="dim")
            table.add_column("IP Адрес", style="cyan")
            table.add_column("Локация", style="green", justify="center")
            table.add_column("Датацентр", style="blue")
            table.add_column("Статус", style="bold")
            table.add_column("Последний чек", style="magenta")

            for r in shields:
                s_id, ip, country, dc, status, last_check = r
                status_str = f"[green]{status}[/green]" if status == "active" else f"[red]{status}[/red]"
                check_str = last_check.strftime("%Y-%m-%d %H:%M") if last_check else "-"

                table.add_row(str(s_id), ip, country, dc, status_str, check_str)

            console.print(table)

            # 2. Текущее состояние DNS
            res_dns = await session.execute(text("SELECT domain, ip, is_active FROM brain.dns_state"))
            dns_rows = res_dns.fetchall()

            if dns_rows:
                table_dns = Table(title="\n🌐 Текущее распределение DNS (Кэш ядра)")
                table_dns.add_column("Домен", style="white")
                table_dns.add_column("Целевой IP шлюза", style="cyan")
                table_dns.add_column("Маршрут активен", justify="center")

                for d in dns_rows:
                    domain, ip_dns, is_act = d
                    act_str = "[green]YES[/green]" if is_act else "[num dim]NO[/num dim]"
                    table_dns.add_row(domain, ip_dns, act_str)
                console.print(table_dns)

    asyncio.run(_status())


@brain.command(name="incidents")
@click.option("--limit", type=int, default=5, help="Количество выводимых строк истории")
def brain_incidents(limit):
    """Показать лог последних зафиксированных аварий и инцидентов."""
    async def _incidents():
        async with AsyncSessionLocal() as session:
            sql = """
                SELECT i.id, s.ip, s.datacenter, i.detected_at, i.resolved_at, i.action_taken
                FROM brain.incidents i
                JOIN brain.shields s ON i.shield_id = s.id
                ORDER BY i.detected_at DESC LIMIT :limit
            """
            res = await session.execute(text(sql), {"limit": limit})
            rows = res.fetchall()

            if not rows:
                console.print("[green]✨ Журнал инцидентов пуст. Аварий не зафиксировано.[/green]")
                return

            table = Table(title=f"🚨 Лог последних {limit} инцидентов инфраструктуры")
            table.add_column("ID", justify="center")
            table.add_column("Проблемный IP", style="cyan")
            table.add_column("Датацентр", style="blue")
            table.add_column("Время аварии", style="red")
            table.add_column("Статус фикса", style="green")
            table.add_column("Принятые меры", style="yellow")

            for r in rows:
                i_id, ip, dc, detected, resolved, action = r
                resolved_str = f"[green]Решён ({resolved.strftime('%M:%S')})[/green]" if resolved else "[red]АКТИВЕН (FAILOVER)[/red]"
                det_str = detected.strftime("%Y-%m-%d %H:%M:%S") if detected else "-"

                table.add_row(str(i_id), ip, dc, det_str, resolved_str, str(action))
            console.print(table)

    asyncio.run(_incidents())


if __name__ == "__main__":
    brain(prog_name="uadmin brain")
