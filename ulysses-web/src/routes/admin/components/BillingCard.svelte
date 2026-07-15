<script>
    let { info, loading } = $props();
</script>

<div class="w-64 bg-slate-900 p-5 overflow-y-auto shrink-0 space-y-4">
    <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400 border-b border-slate-800 pb-2 m-0">📊 Статус VPN ядра</h3>
    {#if loading}
        <p class="text-sm text-slate-500 animate-pulse m-0">⏳ Запрос к балансу FastAPI...</p>
    {:else if info}
        {#if info.error}
            <p class="text-sm text-red-400 bg-red-500/5 p-3 rounded-lg border border-red-500/10 m-0">{info.error}</p>
        {:else}
            <div class="space-y-4 text-sm">
                <div>
                    <span class="text-xs text-slate-500 block mb-1">Почта аккаунта</span>
                    <code class="bg-slate-950 text-blue-400 px-2 py-1 rounded block text-xs truncate select-all">{info.email}</code>
                </div>
                <div class="flex justify-between items-center">
                    <span class="text-slate-400 text-xs">Состояние</span>
                    <span class="text-xs font-bold px-2 py-0.5 rounded {info.is_active ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}">
                        {info.is_active ? '🟢 Активен' : '🔴 Отключен'}
                    </span>
                </div>
                <div class="flex justify-between items-center">
                    <span class="text-slate-400 text-xs">Дней подписки</span>
                    <span class="font-semibold text-slate-200">{info.days_left} дн.</span>
                </div>
                <div>
                    <div class="flex justify-between text-xs text-slate-400 mb-1">
                        <span>Трафик</span>
                        <span>{info.traffic?.used_gb || 0} / {info.traffic?.total_gb || 0} ГБ</span>
                    </div>
                    <div class="w-full bg-slate-950 h-1.5 rounded-full overflow-hidden">
                        <div class="bg-emerald-500 h-full transition-all" style="width: {info.traffic?.percent || 0}%"></div>
                    </div>
                </div>
                <div class="pt-2 border-t border-slate-800">
                    <span class="text-xs text-slate-500 block mb-1">Hiddify UUID</span>
                    <code class="bg-slate-950 text-slate-400 p-2 rounded block text-[10px] break-all select-all font-mono leading-normal">{info.uuid}</code>
                </div>
            </div>
        {/if}
    {/if}
</div>
