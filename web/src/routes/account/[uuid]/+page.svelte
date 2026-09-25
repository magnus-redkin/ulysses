<script>
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

    globalLabel: locale.current === 'ru'
      ? '🌍 Global — для пользователей в РФ: обход блокировок'
      : '🌍 Global — for users in Russia: bypass blocks',
    ruLabel: locale.current === 'ru'
      ? '🇷🇺 Russia — для тех, кто за рубежом: Госуслуги, Сбер, Twigle'
      : '🇷🇺 Russia — for those abroad: Gosuslugi, Sber, Twigle',
    compatLabel: locale.current === 'ru'
      ? '🛠 Compat — для устаревших клиентов и Happ на iOS'
      : '🛠 Compat — for outdated clients and Happ on iOS',
    compatHint: locale.current === 'ru'
      ? 'Используйте, только если Global не работает.'
      : 'Use only if Global doesn\'t work.',
    junglebookHint: locale.current === 'ru'
      ? 'Почему две ссылки? Читайте в Книге Джунглей.'
      : 'Why two links? Read the Jungle Book.',
    copyGlobal: locale.current === 'ru' ? 'Скопировать Global' : 'Copy Global',
    copyRu: locale.current === 'ru' ? 'Скопировать Russia' : 'Copy Russia',
    copyCompat: locale.current === 'ru' ? 'Скопировать Compat' : 'Copy Compat',


    copied: locale.current === 'ru' ? 'Скопировано!' : 'Copied!',
    loading: locale.current === 'ru' ? 'Загрузка...' : 'Loading...',
    renew: locale.current === 'ru' ? 'Продлить' : 'Renew',
    expiredMsg: locale.current === 'ru'
      ? 'Срок действия подписки истёк.'
      : 'Your subscription has expired.'
  });

  let statusText = $derived(
    account?.status === 'active' || account?.status === 'free_tariff'
      ? t.active
      : t.disabled
  );

  let copiedLink = $state(null);

  function copyLink(link) {
    if (!link) return;
    navigator.clipboard.writeText(link);
    copiedLink = link;
    setTimeout(() => (copiedLink = null), 2000);
  }
</script>

<div class="max-w-xl mx-auto py-8">
  <h1 class="text-2xl font-bold text-white mb-6">{t.title}</h1>

  {#if account}
    <div class="bg-gray-900/50 border border-gray-800 rounded-xl p-6 space-y-4">
      <!-- Статус -->
      <div>
        <span class="text-gray-400">{t.statusLabel}:</span>
        <span class="ml-2 font-semibold"
              class:text-emerald-400={account.status === 'active'}
              class:text-yellow-400={account.status !== 'active'}>
          {statusText}
        </span>
      </div>

      <!-- Осталось дней -->
      {#if account.days_left !== undefined && account.days_left !== null}
        <div>
          <span class="text-gray-400">{t.daysLeft}:</span>
          <span class="ml-2 text-white font-bold">
            {account.days_left} {t.days(account.days_left)}
          </span>
        </div>
      {/if}


      <!-- Ссылки: Global + Russia сверху, Compat снизу -->
      {#if account.global_link || account.ru_link}
        <div class="space-y-3">
          <!-- Global -->
          {#if account.global_link}
            <div>
              <div class="text-gray-400 mb-1">{t.globalLabel}:</div>
              <div class="flex items-center gap-3 flex-wrap">
                <code class="bg-gray-800 px-3 py-1.5 rounded text-sm text-gray-300 break-all">
                  {account.global_link}
                </code>
                <button
                  onclick={() => copyLink(account.global_link)}
                  class="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg transition font-semibold flex items-center gap-1"
                >
                  {#if copiedLink === account.global_link}
                    <span>✓</span> {t.copied}
                  {:else}
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                    {t.copyGlobal}
                  {/if}
                </button>
              </div>
            </div>
          {/if}

          <!-- Russia -->
          {#if account.ru_link}
            <div>
              <div class="text-gray-400 mb-1">{t.ruLabel}:</div>
              <div class="flex items-center gap-3 flex-wrap">
                <code class="bg-gray-800 px-3 py-1.5 rounded text-sm text-gray-300 break-all">
                  {account.ru_link}
                </code>
                <button
                  onclick={() => copyLink(account.ru_link)}
                  class="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg transition font-semibold flex items-center gap-1"
                >
                  {#if copiedLink === account.ru_link}
                    <span>✓</span> {t.copied}
                  {:else}
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                    {t.copyRu}
                  {/if}
                </button>
              </div>
            </div>
          {/if}

          <!-- Разъяснение -->
          <p class="text-sm text-gray-500 pt-2">
            <a href="/junglebook/two_links" class="underline hover:text-gray-300 transition">
              {t.junglebookHint}
            </a>
          </p>

          <!-- Compat (снизу, компактно) -->
          {#if account.compat_link}
            <div class="pt-4 mt-2 border-t border-gray-800">
              <div class="text-gray-500 mb-1 text-sm">{t.compatLabel}:</div>
              <div class="text-xs text-gray-600 mb-2">{t.compatHint}</div>
              <div class="flex items-center gap-3 flex-wrap">
                <code class="bg-gray-800/60 px-3 py-1.5 rounded text-xs text-gray-400 break-all">
                  {account.compat_link}
                </code>
                <button
                  onclick={() => copyLink(account.compat_link)}
                  class="bg-gray-700 hover:bg-gray-600 text-gray-200 px-3 py-1.5 rounded-lg transition text-sm font-medium flex items-center gap-1"
                >
                  {#if copiedLink === account.compat_link}
                    <span>✓</span> {t.copied}
                  {:else}
                    {t.copyCompat}
                  {/if}
                </button>
              </div>
            </div>
          {/if}
        </div>
      {:else if account.status === 'active'}
        <p class="text-yellow-400 text-sm">
          {locale.current === 'ru'
            ? 'Ссылки для подключения временно недоступны.'
            : 'Subscription links are temporarily unavailable.'}
        </p>
      {/if}


      <!-- Действия -->
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
