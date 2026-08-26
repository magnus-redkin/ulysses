<script>
    let { show = false, onClose } = $props();
    let target = $state('all');
    let message = $state('');
    let tg_user_id = $state('');
</script>

{#if show}
<div class="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
    <div class="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-lg p-6 space-y-4">
        <h2 class="text-lg font-bold text-white">📨 Уведомления</h2>

        <!-- Выбор типа получателей -->
        <div class="flex gap-2">
            <button type="button" onclick={() => target = 'all'}
                class:bg-emerald-600={target === 'all'}
                class:bg-slate-800={target !== 'all'}
                class="px-4 py-2 rounded-lg text-sm font-medium text-white transition">
                Все пользователи
            </button>
            <button type="button" onclick={() => target = 'user'}
                class:bg-emerald-600={target === 'user'}
                class:bg-slate-800={target !== 'user'}
                class="px-4 py-2 rounded-lg text-sm font-medium text-white transition">
                Конкретный ID
            </button>
            <button type="button" onclick={() => target = 'admin'}
                class:bg-emerald-600={target === 'admin'}
                class:bg-slate-800={target !== 'admin'}
                class="px-4 py-2 rounded-lg text-sm font-medium text-white transition">
                Админам
            </button>
        </div>

        {#if target === 'user'}
            <input
                type="text"
                placeholder="Telegram ID"
                bind:value={tg_user_id}
                class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white placeholder-slate-500"
            />
        {/if}

        <textarea
            bind:value={message}
            rows="5"
            placeholder="Текст сообщения"
            class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white placeholder-slate-500"
        ></textarea>

        <form method="POST" action="?/notifyUsers">
            <input type="hidden" name="target" value={target} />
            <input type="hidden" name="message" value={message} />
            {#if target === 'user'}
                <input type="hidden" name="tg_user_id" value={tg_user_id} />
            {/if}

            <div class="flex justify-end gap-2">
                <button type="button" onclick={onClose} class="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-sm font-medium">
                    Отмена
                </button>
                <button type="submit" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-bold">
                    Отправить
                </button>
            </div>
        </form>
    </div>
</div>
{/if}
