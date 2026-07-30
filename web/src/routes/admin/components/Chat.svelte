<script>
    import { enhance } from '$app/forms';
    import { onMount } from 'svelte';

    let { selectedTicket = $bindable() } = $props();
    let replyText = $state('');
    let messagesContainer = $state(null);

    // Функция скролла вниз
    function scrollToBottom() {
        if (messagesContainer) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }

    // Скроллим при загрузке и при обновлении сообщений
    $effect(() => {
        if (selectedTicket?.messages) {
            setTimeout(scrollToBottom, 50);
        }
    });

    onMount(() => {
        setTimeout(scrollToBottom, 100);
    });

    // Функция закрытия тикета
    async function closeTicket() {
        if (!confirm('Закрыть этот тикет?')) return;

        try {
            const response = await fetch('/admin/api/tickets', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ticketId: selectedTicket._id })
            });

            if (response.ok) {
                const result = await response.json();
                if (result.success) {
                    // ОЧИЩАЕМ ЧАТ - устанавливаем selectedTicket в null
                    selectedTicket = null;

                    // Обновляем список тикетов
                    const ticketsResponse = await fetch('/admin/api/tickets');
                    if (ticketsResponse.ok) {
                        const ticketsData = await ticketsResponse.json();
                        window.dispatchEvent(new CustomEvent('tickets-updated', {
                            detail: ticketsData.tickets
                        }));
                    }
                }
            }
        } catch (error) {
            console.error('Ошибка закрытия тикета:', error);
        }
    }
</script>

<!-- Остальной код чата -->
{#if selectedTicket}
    <div class="flex-1 flex flex-col h-full border-r border-slate-800 overflow-hidden">
        <!-- Заголовок -->
        <div class="px-6 py-4 bg-slate-900 border-b border-slate-800 shrink-0 flex justify-between items-center">
            <h4 class="m-0 font-semibold text-slate-200 text-sm">
                💬 История сообщений пользователя
                <code class="bg-slate-950 px-2 py-0.5 rounded text-blue-400 font-mono text-xs">
                    {selectedTicket.tg_user_id}
                    {#if selectedTicket.ticket_number}
                        <span class="text-slate-400 ml-1">№{selectedTicket.ticket_number}</span>
                    {/if}
                </code>
            </h4>
            <span class="text-xs px-2 py-1 rounded-full {selectedTicket.status === 'open' ? 'bg-amber-500/20 text-amber-400' : 'bg-green-500/20 text-green-400'}">
                {selectedTicket.status === 'open' ? '🟡 Открыт' : '✅ Закрыт'}
            </span>
        </div>

        <!-- Сообщения -->
        <div
            bind:this={messagesContainer}
            class="flex-1 p-6 overflow-y-auto space-y-3 flex flex-col"
            style="max-height: calc(100vh - 300px); min-height: 300px;"
        >
            {#each selectedTicket.messages || [] as msg}
                <div class="flex w-full {msg.sender === 'agent' ? 'justify-end' : msg.sender === 'system' ? 'justify-center' : 'justify-start'}">
                    {#if msg.sender === 'system'}
                        <div class="text-xs text-slate-500 bg-slate-800/50 px-4 py-2 rounded-full">
                            {msg.text}
                        </div>
                    {:else}
                        <div class="max-w-[65%] p-3 px-4 rounded-2xl text-sm relative
                            {msg.sender === 'agent' ? 'bg-blue-600 text-white rounded-tr-sm shadow-md' :
                            'bg-slate-800 text-slate-100 rounded-tl-sm border border-slate-700'}">
                            <p class="m-0 leading-relaxed break-words">{msg.text}</p>
                            <span class="block text-right text-[10px] opacity-70 mt-1">
                                {msg.created_at ? new Date(msg.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '—'}
                            </span>
                        </div>
                    {/if}
                </div>
            {/each}
            <div id="chat-bottom"></div>
        </div>

        <!-- Форма -->
        <div class="p-4 bg-slate-900 border-t border-slate-800 shrink-0">
            <form
                method="POST"
                action="?/sendMessage"
                use:enhance={() => {
                    return ({ result }) => {
                        if (result.type === 'success') {
                            selectedTicket.messages = result.data.updatedTicket.messages;
                            replyText = '';
                            setTimeout(scrollToBottom, 50);
                        }
                    };
                }}
                class="flex gap-3 items-center w-full m-0"
            >
                <input type="hidden" name="ticketId" value={selectedTicket._id} />
                <input
                    type="text"
                    name="text"
                    placeholder={selectedTicket.status === 'closed' ? 'Тикет закрыт' : 'Напишите ответ пользователю в Telegram...'}
                    bind:value={replyText}
                    required
                    disabled={selectedTicket.status === 'closed'}
                    class="flex-1 p-3 bg-slate-950 border border-slate-800 text-white rounded-xl focus:outline-none focus:border-blue-500 text-sm
                        {selectedTicket.status === 'closed' ? 'opacity-50 cursor-not-allowed' : ''}"
                />
                <button
                    type="submit"
                    disabled={selectedTicket.status === 'closed'}
                    class="px-5 py-3 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-xl text-sm transition-colors shrink-0 cursor-pointer
                        {selectedTicket.status === 'closed' ? 'opacity-50 cursor-not-allowed' : ''}"
                >
                    Отправить 🚀
                </button>

                <button
                    type="button"
                    onclick={closeTicket}
                    class="px-5 py-3 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-xl text-sm transition-colors shrink-0 cursor-pointer
                        {selectedTicket.status === 'closed' ? 'opacity-50 cursor-not-allowed' : ''}"
                    disabled={selectedTicket.status === 'closed'}
                >
                    ✅ Закрыть
                </button>
            </form>
        </div>
    </div>
{:else}
    <div class="flex-1 flex justify-center items-center text-slate-500 text-sm text-center p-8">
        <p>👈 Выберите открытый тикет слева для просмотра диалога и статуса VPN-подписки</p>
    </div>
{/if}
