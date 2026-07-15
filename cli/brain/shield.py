import click
from rich.console import Console
from rich.table import Table
from cli.brain.db import query, execute, close
from cli.brain.dns import get_cloudns_records, update_cloudns_record

console = Console()


@click.group()
def shield():
    """Управление щитами"""
    pass


@shield.command(name="status")
def shield_status():
    """Показать состояние всех щитов"""
    shields = query("""
        SELECT id, ip, country, datacenter, status,
               last_health_check, created_at
        FROM brain.shields
        ORDER BY id
    """)

    if not shields:
        console.print("[yellow]⚠[/] Щиты не найдены. Выполните 'uadmin brain seed'.")
        close()
        return

    table = Table(title="🛡️  Состояние щитов")
    table.add_column("ID", style="cyan", width=4)
    table.add_column("IP", style="white")
    table.add_column("Страна", style="green")
    table.add_column("DC", style="white")
    table.add_column("Статус", style="yellow")
    table.add_column("Последняя проверка", style="dim")

    status_styles = {
        "active": "[green]active[/green]",
        "blocked": "[red]blocked[/red]",
        "reserve": "[blue]reserve[/blue]",
        "offline": "[dim]offline[/dim]",
    }

    # Нормализуем ответ в итерируемый список
    shields_list = shields if isinstance(shields, list) else [shields] if isinstance(shields, dict) else []

    for s in shields_list:
        status_display = status_styles.get(s["status"], s["status"])
        last_check = s["last_health_check"].strftime("%H:%M:%S") if s["last_health_check"] else "—"
        table.add_row(
            str(s["id"]),
            s["ip"],
            s["country"],
            s["datacenter"] or "—",
            status_display,
            last_check
        )

    console.print(table)
    close()


@shield.command(name="block")
@click.argument('shield_id', type=int)
def shield_block(shield_id):
    """Пометить щит как заблокированный и автоматически переключить DNS на резерв"""
    s_res = query("SELECT id, ip, country, status FROM brain.shields WHERE id = %(sid)s", {"sid": shield_id})

    if not s_res:
        console.print(f"[red]❌ Щит с ID={shield_id} не найден.[/red]")
        close()
        return

    # Умная распаковка: list или dict
    s = s_res[0] if isinstance(s_res, list) and len(s_res) > 0 else s_res

    if s["status"] == "blocked":
        console.print(f"[yellow]⚠[/] Щит {shield_id} ({s['ip']}, {s['country']}) уже заблокирован.")
        close()
        return

    # 1. Блокируем текущий щит в БД
    execute("UPDATE brain.shields SET status = 'blocked' WHERE id = %(sid)s", {"sid": shield_id})
    execute(
        "INSERT INTO brain.incidents (shield_id, action_taken, notification_sent) VALUES (%(sid)s, 'manual_block', FALSE)",
        {"sid": shield_id}
    )
    console.print(f"[red]🔴[/] Щит {shield_id} ({s['ip']}) заблокирован. Инцидент записан.")

    # 2. Ищем свободный резервный щит
    reserve_shield = query(
        "SELECT id, ip, country FROM brain.shields WHERE status = 'reserve' ORDER BY id LIMIT 1"
    )

    if not reserve_shield:
        console.print("[bold red]🚨 КРИТИЧЕСКАЯ ОШИБКА: Нет доступных резервных щитов! Переключение невозможно.[/bold red]")
        close()
        return

    # Умная распаковка для резервного щита
    next_shield = reserve_shield[0] if isinstance(reserve_shield, list) and len(reserve_shield) > 0 else reserve_shield
    next_id = next_shield["id"]
    next_ip = next_shield["ip"]

    console.print(f"[yellow]🔄🔄 Поиск резерва:[/] Найдена замена: Щит {next_id} ({next_ip}, {next_shield['country']})")

    # 3. Активируем новый щит на уровне БД
    execute("UPDATE brain.shields SET status = 'active' WHERE id = %(sid)s", {"sid": next_id})

    # 4. Обновляем локальный DNS-кэш состояния
    execute("UPDATE brain.dns_state SET is_active = False WHERE domain = 'vpn.ulysses.best'")

    exists = query("SELECT id FROM brain.dns_state WHERE domain = 'vpn.ulysses.best' AND ip = %(ip)s", {"ip": next_ip})
    if exists:
        record_id_db = exists[0]["id"] if isinstance(exists, list) and len(exists) > 0 else exists["id"] if isinstance(exists, dict) else exists
        execute("UPDATE brain.dns_state SET is_active = True, updated_at = NOW() WHERE id = %(id)s", {"id": record_id_db})
    else:
        execute("INSERT INTO brain.dns_state (domain, ip, is_active, updated_at) VALUES ('vpn.ulysses.best', %(ip)s, True, NOW())", {"ip": next_ip})

    console.print(f"[bold green]🎯 СЕТЬ ПЕРЕНАПРАВЛЕНА:[/] DNS-запись vpn.ulysses.best переключена на резервный гейт {next_ip}!")

    # 5. Интеграция с живым ClouDNS API через импортированные методы
    console.print("[yellow]🌐[/] Отправка команды переключения IP в ClouDNS API...")

    records_list = get_cloudns_records("ulysses.best")

    if isinstance(records_list, dict) and "error" in records_list:
        console.print(f"[red]❌ Ошибка получения данных ClouDNS:[/] {records_list['error']}")
        close()
        return

    record_id = None
    for r_data in records_list:
        if isinstance(r_data, dict) and r_data.get("type") == "A":
            cloudns_host = str(r_data.get("host", "")).strip().lower()
            if cloudns_host in ("vpn", "vpn.ulysses.best"):
                record_id = r_data.get("id")
                break

    if record_id:
        result = update_cloudns_record(record_id, next_ip, "ulysses.best")
        if "success" in result:
            console.print(f"[bold green]🚀 ОБЛАКО ОБНОВЛЕНО:[/] В панели ClouDNS успешно прописан резервный IP {next_ip}")
        else:
            console.print(f"[red]❌ Ошибка изменения в ClouDNS:[/] {result['error']}")
    else:
        console.print("[red]❌ Ошибка:[/] Запись vpn.ulysses.best не найдена в панели ClouDNS.")

    close()


@shield.command(name="unblock")
@click.argument('shield_id', type=int)
def shield_unblock(shield_id):
    """Разблокировать щит (перевести в резерв)"""
    s_res = query("SELECT id, ip, country, status FROM brain.shields WHERE id = %(sid)s", {"sid": shield_id})

    if not s_res:
        console.print(f"[red]❌ Щит с ID={shield_id} не найден.[/red]")
        close()
        return

    s = s_res[0] if isinstance(s_res, list) and len(s_res) > 0 else s_res

    if s["status"] not in ("blocked",):
        console.print(f"[yellow]⚠[/] Щит {shield_id} ({s['ip']}, {s['country']}) не заблокирован (статус: {s['status']}).")
        close()
        return

    execute("UPDATE brain.shields SET status = 'reserve' WHERE id = %(sid)s", {"sid": shield_id})
    execute(
        "UPDATE brain.incidents SET resolved_at = NOW() WHERE shield_id = %(sid)s AND resolved_at IS NULL",
        {"sid": shield_id}
    )

    console.print(f"[green]🟢[/] Щит {shield_id} ({s['ip']}, {s['country']}) разблокирован и переведён в резерв.")
    close()
