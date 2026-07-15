<script>
    import { enhance } from '$app/forms';

    // Считываем статус системы ('ok' или 'error') из главного файла-оркестратора
    let { systemStatus = 'ok' } = $props();
</script>

<header class="bg-slate-900 border-b border-slate-800 p-4 flex justify-between items-center shrink-0">
    <h1 class="text-xl font-bold text-white m-0">🛡️ Ulysses Lab </h1>
    <div class="flex gap-2 items-center">

        <!-- КНОПКА-ИНДИКАТОР МОНИТОРИНГА СЕРВЕРА -->
        <form method="POST" action="?/executeCommand" use:enhance class="m-0">
            <input type="hidden" name="command" value="system" />
            <button
                type="submit"
                class="px-4 py-2 rounded-xl text-sm font-bold transition-all border shadow-sm cursor-pointer
                {systemStatus === 'ok'
                    ? 'bg-emerald-950/60 hover:bg-emerald-900/80 text-emerald-400 border-emerald-800/50'
                    : 'bg-red-950/80 hover:bg-red-900 text-red-400 border-red-800/60 animate-pulse'}"
            >
                {systemStatus === 'ok' ? ' 🟢 Система в норме' : '🚨 Требуется внимание!'}
            </button>
        </form>

        <form method="POST" action="?/executeCommand" use:enhance class="m-0">
            <input type="hidden" name="command" value="stats" />
            <button type="submit" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-xl text-sm transition-colors cursor-pointer">
                📊 Статистика
            </button>
        </form>

        <form method="POST" action="?/executeCommand" use:enhance class="m-0">
            <input type="hidden" name="command" value="check" />
            <button type="submit" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-xl text-sm transition-colors cursor-pointer">
                🔍 Чек проблем
            </button>
        </form>

        <form method="POST" action="?/executeCommand" use:enhance class="m-0">
            <input type="hidden" name="command" value="fix" />
            <button type="submit" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-xl text-sm transition-colors cursor-pointer">
                🔧 Исправить
            </button>
        </form>

        <form method="POST" action="?/executeCommand" use:enhance class="m-0">
            <input type="hidden" name="command" value="notify" />
            <button type="submit" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-xl text-sm transition-colors cursor-pointer">
                📨 Уведомить
            </button>
        </form>

        <form method="POST" action="?/logout" class="m-0">
            <button type="submit" class="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-xl text-sm transition-colors cursor-pointer font-medium">
                🚪 Выйти
            </button>
        </form>
    </div>
</header>
