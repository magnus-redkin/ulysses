# =====================================================================
# 🧠 АРХИТЕКТУРА И ЛОГИКА ВЗАИМОДЕЙСТВИЯ МОДУЛЕЙ DNS & SHIELD
# =====================================================================
# Настоящий модуль управляет состоянием распределенной сети гейтов (щитов)
# и обеспечивает отказоустойчивость (Failover) поддомена vpn.ulysses.best.
#
# 1. СИНХРОНИЗАЦИЯ (uadmin brain dns sync):
#    - Мозг (сервер Admin) отправляет авторизованный POST-запрос
#      на официальный API-эндпоинт: https://cloudns.net.
#    - Авторизация выполняется через главный ("auth-id", а не sub-auth-id)
#      ключ 63795. В панели ClouDNS жестко настроен белый список IP (Allowed IPs),
#      разрешающий запросы исключительно с IP-адреса Мозга.
#    - API ClouDNS возвращает записи в виде словаря словарей (id: данные).
#      Скрипт нормализует этот ответ в плоский список и ищет А-запись,
#      где поле "host" равно "vpn" или "vpn.ulysses.best".
#    - Найденный актуальный IP (например, 83.147.216.201 от Aeza) заносится
#      в локальную базу Postgres (brain.dns_state) со статусом is_active = True.
#
# 2. АВТОМАТИЧЕСКИЙ ПЕРЕКЛЮЧАТЕЛЬ И БЛОКИРОВКА (uadmin brain shield block <id>):
#    - При вызове команды блокировки (или при срабатывании healthcheck-триггера):
#      а) Текущий активный щит помечается в БД (brain.shields) как "blocked".
#      б) Скрипт ищет в БД первый доступный сервер со статусом "reserve"
#         (например, резервный IP 62.60.249.53) и переводит его в статус "active".
#      в) Локальный кэш brain.dns_state полностью сбрасывает старую активность
#         и активирует запись под новый резервный IP.
#
# 3. ЖИВАЯ МОДИФИКАЦИЯ ОБЛАКА (Интеграция uadmin в ClouDNS):
#    - Сразу после изменения локального кэша, модуль shield вызывает функцию
#      get_cloudns_records() для динамического поиска внутреннего системного ID
#      целевой А-записи "vpn" непосредственно на серверах ClouDNS.
#    - Получив этот ID, скрипт формирует финальный POST-запрос на эндпоинт:
#      https://cloudns.net, передавая "record-id"
#      и новый целевой IP резервного гейта.
#    - Так как для домена ulysses.best выставлен минимальный TTL (1 минута),
#      все VPN-клиенты переключаются на новый выживший шлюз без участия админа.
# =====================================================================

import click
import os
from datetime import datetime
import httpx
from rich.console import Console
from rich.table import Table
from cli.brain.db import query, execute, close

console = Console()

# =====================================================================
# ⚙️ НАСТРОЙКА ДЛЯ ПЕРЕЕЗДА (ПЕРЕКЛЮЧАТЕЛЬ РЕЖИМА)
# =====================================================================
USE_MOCK_DNS = False
# =====================================================================

def get_cloudns_records(domain_name="ulysses.best"):
    """Запрашивает список всех записей домена из ClouDNS API"""
    api_key = os.getenv("CLOUDNS_API_KEY")
    api_secret = os.getenv("CLOUDNS_API_SECRET")

    if not api_key or not api_secret:
        return {"error": "Не настроены CLOUDNS_API_KEY и CLOUDNS_API_SECRET в .env"}

    # Строго официальный API-домен с указанием json формата
    url = "https://api.cloudns.net/dns/records.json"
    data_payload = {
        "auth-id": api_key,
        "auth-password": api_secret,
        "domain-name": domain_name
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    try:
        with httpx.Client(timeout=15.0, follow_redirects=True, headers=headers) as client:
            response = client.post(url, data=data_payload)

        if response.status_code != 200:
            return {"error": f"Ошибка сервера API. Код: {response.status_code}"}

        try:
            records = response.json()
        except Exception:
            return {"error": f"Ответ ClouDNS API не является JSON: '{response.text[:200]}'"}

        # Если API вернул ошибку в структуре статуса
        if isinstance(records, dict):
            if records.get("status") == "Failed" or "error" in records:
                error_msg = records.get("statusDescription", records.get("error", "Неизвестная ошибка"))
                return {"error": f"ClouDNS API отказал: {error_msg}"}
            return list(records.values())
        elif isinstance(records, list):
            return records
        return []
    except Exception as e:
        return {"error": f"Сетевое исключение: {str(e)}"}


def update_cloudns_record(record_id, next_ip, domain_name="ulysses.best"):
    """Изменяет целевой IP-адрес для конкретной записи через ClouDNS API"""
    api_key = os.getenv("CLOUDNS_API_KEY")
    api_secret = os.getenv("CLOUDNS_API_SECRET")

    if not api_key or not api_secret:
        return {"error": "Не настроены API ключи в .env"}

    # Боевой эндпоинт модификации записей
    url = "https://api.cloudns.net/dns/mod-record.json"
    data_payload = {
        "auth-id": api_key,
        "auth-password": api_secret,
        "domain-name": domain_name,
        "record-id": record_id,
        "record": next_ip
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    try:
        with httpx.Client(timeout=15.0, follow_redirects=True, headers=headers) as client:
            res = client.post(url, data=data_payload)

        if res.status_code != 200:
            return {"error": f"Код ответа API: {res.status_code}"}

        try:
            mod_json = res.json()
            if mod_json.get("status") == "Success" or mod_json.get("status") is True:
                return {"success": True}
            return {"error": mod_json.get("statusDescription", res.text)}
        except Exception:
            if "status" in res.text:
                return {"success": True}
            return {"error": res.text[:200]}
    except Exception as e:
        return {"error": str(e)}


@click.group()
def dns():
    """Управление DNS-записями (Cloudns API)"""
    pass

@dns.command(name="show")
def dns_show():
    """Показать текущее состояние DNS-кэша (brain.dns_state)"""
    records = query("""
        SELECT id, domain, ip, is_active, updated_at
        FROM brain.dns_state
        ORDER BY domain, ip
    """)

    if not records:
        console.print("[yellow]⚠[/] DNS-кэш пуст. Выполните синхронизацию: uadmin brain dns sync")
        close()
        return

    table = Table(title="🌐 DNS-кэш (brain.dns_state)")
    table.add_column("ID", style="cyan", width=4)
    table.add_column("Домен", style="green")
    table.add_column("IP", style="white")
    table.add_column("Активен", style="yellow")
    table.add_column("Обновлён", style="dim")

    for r in records:
        active = "[green]✓[/]" if r["is_active"] else "[dim]—[/]"
        updated = r["updated_at"].strftime("%Y-%m-%d %H:%M") if r["updated_at"] else "—"
        table.add_row(str(r["id"]), r["domain"], r["ip"], active, updated)

    console.print(table)
    close()

@dns.command(name="sync")
def dns_sync():
    """Синхронизировать DNS-кэш с Cloudns API"""
    domain_name = "ulysses.best"
    subdomain = "vpn"
    full_domain = f"{subdomain}.{domain_name}"

    console.print(f"[yellow]🔄[/] Запрос данных ClouDNS для {full_domain}...")

    if USE_MOCK_DNS:
        console.print("[bold cyan]🤖 [MOCK-РЕЖИМ]: Включена локальная заглушка DNS.[/]")
        mock_dns_ip = "83.147.216.201"
        console.print(f"[green]✓[/] [MOCK]: Данные получены. Текущий IP в DNS: [white]{mock_dns_ip}[/]")

        execute("UPDATE brain.dns_state SET is_active = False WHERE domain = %(domain)s", {"domain": full_domain})
        exists = query("SELECT id FROM brain.dns_state WHERE domain = %(domain)s AND ip = %(ip)s",
                       {"domain": full_domain, "ip": mock_dns_ip})

        if exists:
            execute("UPDATE brain.dns_state SET is_active = True, updated_at = NOW() WHERE id = %(id)s", {"id": exists["id"]})
        else:
            execute("INSERT INTO brain.dns_state (domain, ip, is_active, updated_at) VALUES (%(domain)s, %(ip)s, True, NOW())",
                    {"domain": full_domain, "ip": mock_dns_ip})

        console.print("[green]✓[/] Локальный DNS-кэш успешно обновлен данными заглушки.")
        close()
        return

    records_list = get_cloudns_records(domain_name)
    console.print(f"[yellow]⚙️ [DEBUG] Первая запись из API:[/] {records_list[0] if isinstance(records_list, list) and records_list else records_list}")

    if isinstance(records_list, dict) and "error" in records_list:
        console.print(f"[red]❌ Ошибка:[/] {records_list['error']}")
        close()
        return

    target_records = []
    for r_data in records_list:
        if isinstance(r_data, dict) and r_data.get("type") == "A":
            cloudns_host = str(r_data.get("host", "")).strip().lower()
            if cloudns_host in (subdomain.lower(), full_domain.lower()):
                target_records.append(r_data)

    if not target_records:
        console.print(f"[red]❌[/] Запись {full_domain} не найдена в ClouDNS панели.")
        close()
        return

    execute("UPDATE brain.dns_state SET is_active = False WHERE domain = %(domain)s", {"domain": full_domain})

    for target_record in target_records:
        current_dns_ip = target_record.get("record")
        if not current_dns_ip:
            continue

        console.print(f"  • Обнаружен active IP в DNS: [white]{current_dns_ip}[/]")
        exists = query("SELECT id FROM brain.dns_state WHERE domain = %(domain)s AND ip = %(ip)s",
                       {"domain": full_domain, "ip": current_dns_ip})

        if exists:
            # Извлекаем ID из первой строки полученного списка результатов
            record_id_db = exists[0]["id"] if isinstance(exists[0], dict) else exists[0][0]
            execute("UPDATE brain.dns_state SET is_active = True, updated_at = NOW() WHERE id = %(id)s", {"id": record_id_db})
        else:
            execute("INSERT INTO brain.dns_state (domain, ip, is_active, updated_at) VALUES (%(domain)s, %(ip)s, True, NOW())",
                    {"domain": full_domain, "ip": current_dns_ip})

    console.print("[green]✓[/] Локальный DNS-кэш успешно обновлен.")
    close()
