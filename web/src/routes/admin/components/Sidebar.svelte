<script>
    import { browser } from '$app/environment';
    import Modal from './Modal.svelte';

    let { tickets = [], selectedTicket, onSelect } = $props();

    // Состояния для внутренних модалок истории и информации
    let showHistory = $state(false);
    let historyTickets = $state([]);
    let selectedUser = $state(null);

    let showUserInfo = $state(false);
    let userInfo = $state(null);
    let isLoadingUserInfo = $state(false);
    let userInfoTarget = $state(null);

    // Вычисляемые (реактивные) списки Svelte 5
    let openTickets = $derived(tickets.filter(t => t.status === 'open'));
    let closedTickets = $derived(tickets.filter(t => t.status === 'closed'));

    // Функция открытия истории тикетов пользователя
    function openHistory(tg_user_id, event) {
        event.stopPropagation();
        selectedUser = tg_user_id;
        historyTickets = tickets
            .filter(t => t.tg_user_id === tg_user_id && t.status === 'closed')
            .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        showHistory = true;
    }

    // Функция быстрого просмотра биллинга по клику на ID
    async function fetchUserInfo(tg_user_id, event) {
        event.stopPropagation();
        userInfoTarget = tg_user_id;
        isLoadingUserInfo = true;
        showUserInfo = true;
        userInfo = null;

        try {
            const res = await fetch(`/api/user/balance?tg_user_id=${tg_user_id}`);
            if (res.ok) {
                userInfo = await res.json();
            } else if (res.status === 404) {
                userInfo = { error: "Пользователь не привязан к биллингу" };
            } else {
                const errorData = await res.json().catch(() => ({}));
                userInfo = { error: errorData.error || `Ошибка: ${res.status}` };
            }
        } catch (e) {
            userInfo = { error: "Нет связи с бэкендом VPN" };
        } finally {
            isLoadingUserInfo = false;
        }
    }
</script>

<section class="w-80 bg-slate-900 border-r border-slate-800 flex flex-col p-4 shrink-0 overflow-hidden">

    <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400 mb-4">
        📥 Активные обращения ({openTickets.length})
    </h3>

    <div class="flex-1 overflow-y-auto space-y-2 pr-1">
        {#each openTickets as ticket}
            <button
                class="w-full text-left bg-slate-950 border p-4 rounded-xl text-white transition-all cursor-pointer block m-0
                    {selectedTicket?._id === ticket._id ? 'border-blue-500 bg-slate-900 shadow-lg shadow-blue-500/5' :
                    'border-slate-800 hover:border-slate-700'}"
                onclick={() => onSelect(ticket)}
            >
                <div class="flex justify-between items-center mb-2 text-xs">
                    <!-- Кликабельный ID -->
                    <span
                        class="font-mono text-blue-400 hover:text-blue-300 cursor-pointer transition-colors font-bold"
                        onclick={(e) => fetchUserInfo(ticket.tg_user_id, e)}
                        role="presentation"
                    >
                        ID: {ticket.tg_user_id}
                        {#if ticket.ticket_number}
                            <span class="text-slate-500 ml-1">№{ticket.ticket_number}</span>
                        {/if}
                    </span>

                    <!-- Кнопка вызова истории -->
                    <span
                        onclick={(e) => openHistory(ticket.tg_user_id, e)}
                        class="text-[10px] text-blue-400 hover:text-blue-300 transition-colors font-bold uppercase tracking-wide cursor-pointer"
                        role="presentation"
                    >
                        📜 История ({closedTickets.filter(t => t.tg_user_id === ticket.tg_user_id).length})
                    </span>
                </div>
                <p class="text-sm text-slate-400 truncate m-0 font-normal">
                    {ticket.messages && ticket.messages.length > 0 ?
                        ticket.messages[ticket.messages.length - 1].text : 'Без текста'}
                </p>
                <div class="text-[10px] text-slate-500 mt-2 font-mono">
                    {new Date(ticket.updated_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                </div>
            </button>
        {/each}

        {#if openTickets.length === 0}
            <div class="text-sm text-slate-500 text-center mt-8">
                <p class="m-0">🎉 Все тикеты закрыты!</p>
            </div>
        {/if}
    </div>
</section>

<!-- МОДАЛКА ИСТОРИИ ТИКЕТОВ ПОЛЬЗОВАТЕЛЯ -->
<Modal
    bind:show={showHistory}
    title="📜 История тикетов пользователя {selectedUser}"
    onClose={() => {
        showHistory = false;
        historyTickets = [];
        selectedUser = null;
    }}
>
    {#snippet children()}
        <div class="space-y-2 max-h-[60vh] overflow-y-auto pr-1">
            {#each historyTickets as ticket}
                <div
                    class="bg-slate-950 border border-slate-800 rounded-xl p-4 hover:border-slate-700 transition-colors cursor-pointer"
                    onclick={() => {
                        onSelect(ticket);
                        showHistory = false;
                        historyTickets = [];
                        selectedUser = null;
                    }}
                    role="presentation"
                >
                    <div class="flex justify-between items-center mb-2">
                        <span class="text-xs text-slate-400 font-mono">
                            №{ticket.ticket_number || '?'} •
                            {new Date(ticket.created_at).toLocaleDateString()}
                            {new Date(ticket.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                        </span>
                        <span class="text-[10px] text-emerald-400 font-bold uppercase tracking-wide">
                            ✅ Закрыт
                        </span>
                    </div>
                    <p class="text-sm text-slate-300 truncate m-0 font-normal">
                        {ticket.messages && ticket.messages.length > 0 ?
                            ticket.messages[0].text : 'Без текста'}
                    </p>
                    <div class="text-[10px] text-slate-500 mt-1 font-mono">
                        Сообщений в архиве: {ticket.messages?.length || 0}
                    </div>
                </div>
            {/each}

            {#if historyTickets.length === 0}
                <div class="text-center text-slate-500 py-8 text-sm">
                    Нет закрытых тикетов в архиве
                </div>
            {/if}
        </div>
    {/snippet}
</Modal>

<!-- МОДАЛКА БЫСТРОЙ ИНФОРМАЦИИ О КЛИЕНТЕ ИЗ FastAPI БЕКЕНДА -->
<Modal
    bind:show={showUserInfo}
    title="👤 Информация о пользователе"
    onClose={() => {
        showUserInfo = false;
        userInfo = null;
        userInfoTarget = null;
    }}
>
    {#snippet children()}
        {#if isLoadingUserInfo}
            <div class="text-center py-8 text-slate-500 text-sm animate-pulse">
                ⏳ Загрузка данных биллинга...
            </div>
        {:else if userInfo}
            {#if userInfo.error}
                <div class="text-center py-4 text-amber-400 bg-amber-500/5 border border-amber-500/10 rounded-xl p-4 text-sm font-medium">
                    ⚠️ {userInfo.error}
                </div>
            {:else}
                <div class="space-y-3 bg-slate-950 border border-slate-800 rounded-xl p-5 text-sm">
                    <div class="flex justify-between items-center">
                        <span class="text-slate-400">Статус подписки:</span>
                        <span class="text-xs font-bold px-2 py-0.5 rounded {userInfo.is_active ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}">
                            {userInfo.is_active ? '🟢 Активен' : '🔴 Приостановлен'}
                        </span>
                    </div>
                    <div class="flex justify-between items-center border-t border-slate-900 pt-2">
                        <span class="text-slate-400">Email профиля:</span>
                        <code class="text-blue-400 bg-slate-900 px-2 py-0.5 rounded font-mono text-xs select-all truncate max-w-[200px]">{userInfo.email || '—'}</code>
                    </div>
                    <div class="flex justify-between items-center border-t border-slate-900 pt-2">
                        <span class="text-slate-400">Дней осталось:</span>
                        <span class="text-slate-200 font-bold font-mono">{userInfo.days_left || 0} дн.</span>
                    </div>
                    <div class="flex justify-between items-center border-t border-slate-900 pt-2 pb-1">
                        <span class="text-slate-400">Потребление трафика:</span>
                        <span class="text-slate-200 font-medium">
                            {userInfo.traffic?.used_gb?.toFixed(2) || 0} ГБ /
                            {userInfo.traffic?.total_gb?.toFixed(1) || 0} ГБ
                        </span>
                    </div>
                    <div class="mt-2 pt-1">
                        <div class="w-full bg-slate-900 rounded-full h-2 overflow-hidden border border-slate-800/40">
                            <div
                                class="h-full rounded-full transition-all
                                    {userInfo.traffic?.percent < 70 ? 'bg-emerald-500' :
                                     userInfo.traffic?.percent >= 70 && userInfo.traffic?.percent < 90 ? 'bg-amber-500' : 'bg-red-500'}"
                                style="width: {Math.min(userInfo.traffic?.percent || 0, 100)}%"
                            ></div>
                        </div>

                    <!-- </div> -->
                        <div class="text-[10px] text-slate-500 mt-1.5 text-right font-mono font-bold">
                            использовано: {userInfo.traffic?.percent?.toFixed(1) || 0}%
                        </div>
                    </div>
                </div>
            {/if}
        {/if}
    {/snippet}
</Modal>
