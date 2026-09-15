<script>
    import Login from './components/Login.svelte';
    import Header from './components/Header.svelte';
    import Sidebar from './components/Sidebar.svelte';
    import Chat from './components/Chat.svelte';
    import BillingCard from './components/BillingCard.svelte';
  import Modal from './components/Modal.svelte';
  import NotifyModal from './components/NotifyModal.svelte';

    let { data, form } = $props();

    // Реактивные состояния
    let selectedTicket = $state(null);
    let activeModal = $state(false);
    let currentUserInfo = $state(null);
  let isLoadingUserInfo = $state(false);
  let showNotifyModal = $state(false);

  let previousTicketIds = $state(new Set());
  let audioCtx = null;

    // Логика открытия модалки при получении ответа от сервера
    $effect(() => {
        if (form?.modalData) activeModal = true;
    });

  function playNotificationSound() {
    try {
      if (!audioCtx) audioCtx = new AudioContext();
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = 'sine';
      osc.frequency.value = 880;
      gain.gain.value = 0.3;
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start();
      setTimeout(() => osc.stop(), 200);
    } catch (e) {
      console.warn('Не удалось воспроизвести звук:', e);
    }
  }
  // or:
  // const audio = new Audio('/sounds/notification.mp3');
  // audio.play().catch(e => console.warn(e));


    // Обработчик клика по тикету (загрузка баланса)
    async function handleSelectTicket(ticket) {
        selectedTicket = ticket;
        currentUserInfo = null;
        isLoadingUserInfo = true;
        try {
          const res = await fetch(`/admin/api/user/balance?tg_user_id=${ticket.tg_user_id}`);
            if (res.ok) {
                currentUserInfo = await res.json();
            } else if (res.status === 404) {
                currentUserInfo = { error: "Пользователь не привязан к биллингу" };
            } else {
                const errorData = await res.json().catch(() => ({}));
                currentUserInfo = { error: errorData.error || `Ошибка HTTP ${res.status}` };
            }
        } catch (e) {
            currentUserInfo = { error: "Нет связи с бэкендом VPN" };
        } finally {
            isLoadingUserInfo = false;
        }
    }

    // Живая реактивная переменная для списка тикетов
  // let liveTickets = $state(data.tickets || []);
  let liveTickets = $state([]);

    $effect(() => {
        if (data.tickets) {
            liveTickets = data.tickets;
        }
    });

  // Функция фонового опроса API

  async function refreshTicketsSilently() {
    try {
      const res = await fetch('/admin/api/tickets');
      if (res.ok) {
        const body = await res.json();
        liveTickets = [...body.tickets];

        // Проверяем новые открытые тикеты
        const currentOpenIds = new Set(liveTickets.filter(t => t.status === 'open').map(t => t._id));
        const hasNew = [...currentOpenIds].some(id => !previousTicketIds.has(id));
        if (hasNew && previousTicketIds.size > 0) {
          playNotificationSound();
        }
        previousTicketIds = currentOpenIds;

        if (selectedTicket) {
          const updated = liveTickets.find(t => t._id === selectedTicket._id);
          if (updated) {
            selectedTicket = { ...updated };
          }
        }
      }
    } catch (e) {
      console.error("Ошибка фонового обновления тикетов:", e);
    }
  }


    // Запускаем таймер опроса
    $effect(() => {
        const interval = setInterval(refreshTicketsSilently, 4000);
        return () => clearInterval(interval);
    });

    // Функция закрытия модалки
    function closeModal() {
        activeModal = false;
        // Не удаляем form, чтобы не потерять данные
    }

    // Определяем заголовок для модалки
    function getModalTitle() {
        if (!form?.command) return '📋 Информация';
        const titles = {
            'stats': '📊 Статистика',
            'check': '🔍 Проверка проблем',
            'fix': '🔧 Исправление проблем',
            'notify': '📨 Уведомления'
        };
        return titles[form.command] || '📋 Информация';
    }
</script>

{#if !data.authenticated}
    <Login {form} />
{:else}
    <div class="flex flex-col flex-1 bg-slate-950 text-slate-200 overflow-hidden w-full">
      <Header onNotifyClick={() => showNotifyModal = true} />

        <main class="flex flex-1 overflow-hidden w-full">
            <Sidebar
                tickets={liveTickets}
                {selectedTicket}
                onSelect={handleSelectTicket}
            />

            <section class="flex-1 flex bg-slate-950 overflow-hidden">
                {#if selectedTicket}
                    <div class="flex flex-1 overflow-hidden w-full h-full">
                        <Chat bind:selectedTicket />
                        <BillingCard info={currentUserInfo} loading={isLoadingUserInfo} />
                    </div>
                {:else}
                    <div class="flex flex-1 justify-center items-center text-slate-500 text-sm text-center p-8">
                        <p>👈 Выберите открытый тикет слева для просмотра диалога и статуса VPN-подписки</p>
                    </div>
                {/if}
            </section>
        </main>
    </div>
{/if}

<!-- Модалка для верхних кнопок (Статистика, Чек проблем и т.д.) -->
<Modal
    bind:show={activeModal}
    title={getModalTitle()}
    onClose={closeModal}
>
    {#snippet children()}
        {#if form?.modalData?.error}
            <div class="text-red-400 bg-red-500/10 rounded-xl p-4">
                ⚠️ {form.modalData.error}
            </div>
        {:else}
            <pre class="bg-slate-800 rounded-xl p-4 overflow-x-auto text-xs text-slate-300 whitespace-pre-wrap font-mono max-h-[50vh]">
                {JSON.stringify(form?.modalData, null, 2)}
            </pre>
        {/if}
    {/snippet}
</Modal>

<NotifyModal
    show={showNotifyModal}
    onClose={() => showNotifyModal = false}
/>
