# Ulysses Admin CLI — Справка и статус разработки

## Общие положения
- CLI работает через защищённый API бэкенда (ключ `HOST_API_KEY` в `.env`).
- Все данные поступают из бэкенда, прямого доступа к БД из CLI нет (кроме `db`).
- Полный список команд: `uadmin --help`.

## 1. Диагностика и статистика

### `uadmin stats`
Показать общую статистику (пользователи, подписки). При наличии зависших подписок выводит их список.
- Данные получает из API `/api/admin/stats`.

### `uadmin check [OPTIONS] [QUERY]`
Кросс-диагностика аномалий, расхождений с Hiddify.
- `uadmin check` – сводка (инвойсы, подписки, расхождения).
- `uadmin check -v` – детализация проблемных инвойсов/подписок.
- `uadmin check --sync` – полная сверка с панелью Hiddify (по UUID пользователей). Показывает:
  - `missing_in_hiddify` – профиля нет на ноде.
  - (в будущем) `should_be_enabled/disabled` – расхождения статусов.
- `uadmin check <ID>` – поиск по tg_id / email / uuid.

## 2. Исправление и обслуживание

### `uadmin fix cleanup-invoices`
Удалить все pending инвойсы старше 24 часов.
- Запрос к API `/api/admin/fix/cleanup-invoices`.

### `uadmin fix process-pending [--limit N]`
Принудительно обработать зависшие подписки (возвращает в `provisioning`).
- Запрос к API `/api/admin/fix/process-pending`.

### `uadmin db`
Управление резервным копированием и восстановлением БД (работает локально, без API).
- `uadmin db dump` – создать дамп с ротацией (backup_latest.sql / backup_previous.sql).
- `uadmin db restore <file>` – восстановить БД из файла.
- `uadmin db reset` – полный сброс и переинициализация БД (требует `init_db.sh`).
- `uadmin db query <SQL>` – выполнить произвольный SQL (SELECT/INSERT/UPDATE/DELETE).

## 3. Управление пользователями и подписками

### `uadmin user`
Управление пользователями биллинга.
- `uadmin user list` – список всех пользователей.
- `uadmin user create ...` – создать пользователя (с тест-драйвом).
- `uadmin user delete <ID>` – удалить пользователя (каскадно).
- `uadmin user json <ID>` – показать Sing‑Box конфиг подписки (генерируется сервисом).
- `uadmin user link <ID>` – ссылка подписки для импорта.
- `uadmin user sub <ID>` – история подписок пользователя.

## 4. Системная информация

### `uadmin system [all|bot|back|web|db|ram] [--logs]`
Системные метрики сервера и детальный анализ компонентов.
- `uadmin system all` – сводка (диск, RAM, PostgreSQL, бот, backend).
- `uadmin system bot --logs` – статус бота и последние логи.

### `uadmin monitor`
Демон мониторинга (работает в фоне через systemd).
- `uadmin monitor status` – текущее состояние из демона (HTTP localhost:9898).
- `uadmin monitor check` – однократный прогон всех проверок.

### `uadmin help`
Показать подробную справку по всем командам uadmin.

---

## TODO / Что осталось реализовать

### Срочно (MVP)
- [ ] **`uadmin fix repair-missing`** – автоматически пересоздавать в Hiddify профили, отмеченные как `missing_in_hiddify`, при наличии активной подписки. Для неактивных — либо не создавать, либо создавать и сразу отключать.
- [ ] Доработать сверку Hiddify: добавить `should_be_enabled` / `should_be_disabled` (сейчас сверка видит только отсутствие профиля). Для этого нужен метод `get_user_info` в `HiddifyProvisioner`, возвращающий `enabled` статус.
- [ ] Финальное тестирование всей цепочки: `stats` → `check --sync` → `fix repair-missing` → `check --sync` (аномалии должны исчезнуть).

### Улучшения
- [ ] Перенести всю оставшуюся бизнес-логику из CLI в сервисы (если ещё есть прямые SQL-запросы).
- [ ] Интеграция Hiddify-статуса в `uadmin system` (доступность API, версия панели).
- [ ] Ротация дампов при ежечасном бекапе (сейчас только два файла, при желании можно увеличить глубину).
- [ ] Добавить в мониторинг проверку свободного места перед дампом (warning если >90%).

### Shield (бывший Brain)
- [ ] Разработать модуль `Shield` для автоматической замены IP гейтов при блокировке.
- [ ] Обновление файла `config/gate_ips.json` через Shield.
- [ ] Интеграция с демоном мониторинга: при длительном офлайне гейта Shield получает команду на замену.

---

## Быстрый тест-план
1. `uadmin stats` – убедиться, что нет зависших подписок.
2. `uadmin check` – сводка (должны быть 0 аномалий после очистки).
3. `uadmin check -v` – детализация (пустые списки).
4. `uadmin check --sync` – сверка с Hiddify (если есть `missing_in_hiddify`, проверить статус подписки).
5. `uadmin fix cleanup-invoices` – чистим инвойсы (тест на пустой БД).
6. `uadmin fix process-pending` – обработка очереди (0 подписок).
7. `uadmin user link <ID>` – проверка генерации ссылки.
8. `uadmin user json <ID>` – проверка генерации конфига.
9. `uadmin db dump` – проверка создания дампа.
10. Проверка systemd-таймера: `systemctl status ulysses-maintenance.timer` (должен быть active/enabled).
