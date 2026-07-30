<script>
  import { page } from '$app/stores';
  import { locale } from '$lib/locale.svelte.js';

  let { data } = $props();
  let account = $derived(data.account);

  const t = $derived({
    title: locale.current === 'ru' ? 'Ваш аккаунт' : 'Your Account',
    statusLabel: locale.current === 'ru' ? 'Статус' : 'Status',
    active: locale.current === 'ru' ? 'Активна' : 'Active',
    disabled: locale.current === 'ru' ? 'Отключена' : 'Disabled',
    daysLeft: locale.current === 'ru' ? 'Осталось' : 'Days left',
    days: (n) => {
      if (locale.current === 'ru') {
        const d = Math.abs(n) % 100;
        const dd = d % 10;
        if (d > 10 && d < 20) return 'дней';
        if (dd > 1 && dd < 5) return 'дня';
        if (dd === 1) return 'день';
        return 'дней';
      }
      return n === 1 ? 'day' : 'days';
    },
    subscriptionLink: locale.current === 'ru' ? 'Ссылка для подключения' : 'Subscription link',
    copyBtn: locale.current === 'ru' ? 'Скопировать ссылку' : 'Copy link',
    copied: locale.current === 'ru' ? 'Скопировано!' : 'Copied!',
    loading: locale.current === 'ru' ? 'Загрузка...' : 'Loading...',
    renew: locale.current === 'ru' ? 'Продлить' : 'Renew',
    expiredMsg: locale.current === 'ru' ? 'Срок действия подписки истёк.' : 'Your subscription has expired.'
  });

  // Текст статуса
  let statusText = $derived(
    account?.status === 'active' || account?.status === 'free_tariff'
      ? t.active
      : t.disabled
  );

  let copySuccess = $state(false);

  function copyLink() {
    if (account?.subscription_link) {
      navigator.clipboard.writeText(account.subscription_link);
      copySuccess = true;
      setTimeout(() => copySuccess = false, 2000);
    }
  }
</script>

<div class="max-w-xl mx-auto py-8">
  <h1 class="text-2xl font-bold text-white mb-6">{t.title}</h1>

  {#if account}
    <div class="bg-gray-900/50 border border-gray-800 rounded-xl p-6 space-y-4">
      <!-- Статус -->
      <div>
        <span class="text-gray-400">{t.statusLabel}:</span>
        <span class="ml-2 font-semibold" class:text-emerald-400={account.status === 'active'} class:text-yellow-400={account.status !== 'active'}>
          {statusText}
        </span>
      </div>

      <!-- Оставшиеся дни (из API) -->
      {#if account.days_left !== undefined && account.days_left !== null}
        <div>
          <span class="text-gray-400">{t.daysLeft}:</span>
          <span class="ml-2 text-white font-bold">
            {account.days_left} {t.days(account.days_left)}
          </span>
        </div>
      {/if}

      <!-- Ссылка для подключения (появится после доработки API) -->
      {#if account.subscription_link}
        <div>
          <div class="text-gray-400 mb-1">{t.subscriptionLink}:</div>
          <div class="flex items-center gap-3 flex-wrap">
            <code class="bg-gray-800 px-3 py-1.5 rounded text-sm text-gray-300 break-all">
              {account.subscription_link}
            </code>
            <button
              onclick={copyLink}
              class="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg transition font-semibold flex items-center gap-1"
            >
              {#if copySuccess}
                <span>✓</span> {t.copied}
              {:else}
                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
                {t.copyBtn}
              {/if}
            </button>
          </div>
        </div>
      {:else if account.status === 'active'}
        <p class="text-yellow-400 text-sm">
          {locale.current === 'ru'
            ? 'Ссылка для подключения временно недоступна.'
            : 'Subscription link is temporarily unavailable.'}
        </p>
      {/if}

      <!-- Действия для неактивных подписок -->
      {#if account.status !== 'active'}
        <div class="mt-4 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
          <p class="text-yellow-300 text-sm">
            {t.expiredMsg}
            <a href="/pricing" class="underline font-medium hover:text-yellow-200">{t.renew}</a>
          </p>
        </div>
      {/if}
    </div>
  {:else}
    <p class="text-gray-400 animate-pulse">{t.loading}</p>
  {/if}
</div>
