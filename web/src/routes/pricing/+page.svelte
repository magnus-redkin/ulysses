<script>
  import { enhance } from '$app/forms';
  import { locale } from '$lib/locale.svelte.js';
  import { page } from '$app/stores';

  let { form } = $props();

  // Централизованный словарь переводов для интерфейса страницы
  const t = $derived({
    title: locale.current === 'ru' ? 'Выберите тариф' : 'Choose your plan',
    emailLabel: locale.current === 'ru' ? 'Ваш Email' : 'Your Email',
    confirmEmailLabel: locale.current === 'ru' ? 'Подтвердите Email' : 'Confirm Email',
    submitBtn: locale.current === 'ru' ? 'Продолжить' : 'Continue',
    errorMatch: locale.current === 'ru' ? 'Email адреса не совпадают' : 'Emails do not match',
    errorInvalid: locale.current === 'ru' ? 'Некорректный формат Email' : 'Invalid email format',
    errorSelectPlan: locale.current === 'ru' ? 'Пожалуйста, выберите тариф' : 'Please select a plan',
    loading: locale.current === 'ru' ? 'Загрузка тарифов...' : 'Loading plans...',
    errorLoad: locale.current === 'ru' ? 'Не удалось загрузить тарифы' : 'Failed to load plans',
    submitting: locale.current === 'ru' ? 'Отправка...' : 'Processing...',
    orderId: locale.current === 'ru' ? 'Номер заказа' : 'Order ID',
    amount: locale.current === 'ru' ? 'Сумма' : 'Amount'
  });

  // Справочник периодов и дней для локализации и математических расчетов стоимости дня
  const planMeta = {
    sub_free: {
      ru: { period: 'Попробовать 3 дня бесплатно' },
      en: { period: 'Try 3 days for free' },
      days: 3
    },
    sub_1m: {
      ru: { period: '1 месяц' },
      en: { period: '1 month' },
      days: 30
    },
    sub_3m: {
      ru: { period: '3 месяца' },
      en: { period: '3 months' },
      days: 90
    },
    sub_6m: {
      ru: { period: '6 месяцев' },
      en: { period: '6 months' },
      days: 180
    },
    sub_12m: {
      ru: { period: '1 год' },
      en: { period: '1 year' },
      days: 365
    },
    sub_24m: {
      ru: { period: '2 года' },
      en: { period: '2 years' },
      days: 730
    }
  };

  // Умная нормализация, расчет цены в день (в USDT для EN) и мультиязычный перевод
  let plans = $derived(($page.data?.plans ?? []).map(plan => {
    const meta = planMeta[plan.id];

    if (!meta) return plan;

    const isRu = locale.current === 'ru';
    const currencySign = isRu ? ' ₽' : ' $';
    const dayWord = isRu ? ' в день' : ' / day';

    // Расчет цены в зависимости от выбранной валюты (Рубли или USDT по курсу 80)
    const finalPrice = isRu ? plan.price : (plan.id === 'sub_free' ? 0 : (plan.price / 80).toFixed(2));
    const currencyWord = isRu ? ' рублей' : ' $';

    // Расчет цены за один день использования (в соответствующей валюте)
    const finalPriceNum = isRu ? plan.price : (plan.price / 80);
    const pricePerDay = meta.days > 0 ? (finalPriceNum / meta.days).toFixed(isRu ? 1 : 2) : '0';

    return {
      ...plan,
      isFree: plan.id === 'sub_free',
      displayTitle: meta[isRu ? 'ru' : 'en'].period + (plan.id === 'sub_free' ? '' : ': ' + finalPrice + currencyWord),
      displayPricePerDay: pricePerDay + currencySign + dayWord,
      desc: isRu ? plan.desc : (plan.desc ? 'High-speed secure VLESS connection' : '')
    };
  }));

  let loadError = $derived($page.data?.error ?? null);
  let isLoaded = $derived($page.data?.plans !== undefined);

  let selectedPlan = $state('');
  let email = $state('');
  let confirmEmail = $state('');
  let isSubmitting = $state(false);

  // Валидация
  let isEmailValid = $derived(/^[\w-\.]+@([\w-]+\.)+[\w-]{2,4}$/.test(email));
  let doEmailsMatch = $derived(email === confirmEmail);
  let isFormValid = $derived(selectedPlan && isEmailValid && doEmailsMatch && !isSubmitting);

  // Реактивная переменная: нужно ли подсвечивать поле Email прямо сейчас
  let shouldHighlightEmail = $derived(selectedPlan !== '' && email === '');

  function handleSubmit() {
    if (isFormValid) {
      isSubmitting = true;
    }
  }

  // Гарантированный автовыбор бесплатного тарифа при переходе по ссылке ?plan=free
  $effect(() => {
    const planParam = $page.url.searchParams.get('plan');

    if (planParam && plans.length > 0) {
      const targetPlan = plans.find(p => {
        const idStr = String(p.id).toLowerCase();
        const nameStr = String(p.name).toLowerCase();
        const paramStr = planParam.toLowerCase();

        return idStr === paramStr ||
               nameStr === paramStr ||
               nameStr.includes('free') ||
               nameStr.includes('бесплат');
      });

      if (targetPlan) {
        selectedPlan = targetPlan.id;
      }
    }
  });
</script>

<div class="max-w-3xl mx-auto py-8">
  <h1 class="text-3xl font-bold text-center pl-4 text-white mb-8">{t.title}</h1>

  {#if !isLoaded}
    <div class="text-center py-12">
      <p class="text-gray-400 animate-pulse">{t.loading}</p>
    </div>

  {:else if loadError}
    <div class="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-center">
      <p class="text-red-400 font-medium">{t.errorLoad}</p>
      <p class="text-gray-400 text-sm mt-1">{loadError}</p>
    </div>

  {:else}
    <form method="POST" use:enhance onsubmit={handleSubmit} class="space-y-8">
      <input type="hidden" name="plan" value={selectedPlan} />

      <!-- Сетка тарифных планов -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        {#each plans as plan}
          <button
            type="button"
            onclick={() => selectedPlan = plan.id}
            class="p-6 border rounded-xl text-left transition-all relative overflow-hidden
              {selectedPlan === plan.id
                ? 'bg-gray-800 border-emerald-500 ring-2 ring-emerald-500/20'
                : 'bg-gray-900/50 border-gray-800 hover:border-gray-700'}"
          >
            {#if selectedPlan === plan.id}
              <span class="absolute top-3 right-3 bg-emerald-500 text-black text-xs font-bold px-2 py-0.5 rounded-full">✓</span>
            {/if}

            {#if plan.isFree}
              <!-- ДЛЯ FREE: одна строка с названием/периодом -->
              <h3 class="text-xl font-bold text-white my-2">{plan.displayTitle}</h3>
              {#if plan.desc}
                <!-- <p class="text-gray-400 text-sm mt-2">{plan.desc}</p> -->
              {/if}
            {:else}
              <!-- ДЛЯ ПЛАТНЫХ: две строки (период + цена за день) -->
              <h3 class="text-xl font-bold text-white mb-1">{plan.displayTitle}</h3>
              <p class="text-2xl font-extrabold text-emerald-400 mb-4">{plan.displayPricePerDay}</p>
              {#if plan.desc}
                <!-- <p class="text-gray-400 text-sm">{plan.desc}</p> -->
              {/if}
            {/if}
          </button>
        {/each}
      </div>

      {#if !selectedPlan}
        <p class="text-amber-400 text-sm text-center font-medium">{t.errorSelectPlan}</p>
      {/if}

      <!-- Блок полей ввода Email -->
      <div class="space-y-4 max-w-md mx-auto pt-6 border-t border-gray-800">
        <div>
          <!-- Включение цвета при активации подсветки -->
          <label for="email" class="block text-sm font-medium mb-1 transition-colors {shouldHighlightEmail ? 'text-emerald-400 font-bold' : 'text-gray-400'}">
            {t.emailLabel}
          </label>
          <input
            id="email"
            name="email"
            type="email"
            bind:value={email}
            required
            autocomplete="off"
            placeholder="your@email.com"
            /* Подсветка поля: рамка, тень и мягкий бесконечный цикл пульсации */
            class="w-full bg-gray-900 border rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-all
              {shouldHighlightEmail
                ? 'border-emerald-500 ring-4 ring-emerald-500/20 shadow-[0_0_15px_rgba(16,185,129,0.1)] animate-[pulse_2s_infinite]'
                : 'border-gray-800'}"
          />
          {#if email && !isEmailValid}
            <p class="text-red-400 text-xs mt-1 font-medium">{t.errorInvalid}</p>
          {/if}
        </div>

        <div>
          <label for="confirmEmail" class="block text-sm font-medium text-gray-400 mb-1">{t.confirmEmailLabel}</label>
          <input
            id="confirmEmail"
            type="email"
            bind:value={confirmEmail}
            required
            disabled={!isEmailValid || isSubmitting}
            autocomplete="off"
            placeholder="your@email.com"
            class="w-full bg-gray-900 border border-gray-800 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          />
          {#if confirmEmail && !doEmailsMatch}
            <p class="text-red-400 text-xs mt-1 font-medium">{t.errorMatch}</p>
          {/if}
        </div>

        <!-- Кнопка отправки формы -->
        <button
          type="submit"
          disabled={!isFormValid}
          class="w-full mt-4 bg-emerald-500 text-black font-bold py-3 px-6 rounded-lg transition-all
            hover:bg-emerald-400 disabled:bg-gray-800 disabled:text-gray-500 disabled:cursor-not-allowed
            {isSubmitting ? 'opacity-75' : ''}"
        >
          {isSubmitting ? '⏳ ' + t.submitting : t.submitBtn}
        </button>

        <!-- Обработка успешного ответа сервера -->
        {#if form?.success}
          <div class="bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-4 text-center">
            <p class="text-emerald-400 font-medium">✓ {form.message}</p>
            {#if form.order_id}
              <p class="text-gray-400 text-sm mt-1">
                {t.orderId}: {form.order_id}
              </p>
            {/if}
            {#if form.amount}
              <p class="text-gray-400 text-sm">
                {t.amount}: ${form.amount}
              </p>
            {/if}
          </div>
        {/if}

        <!-- Обработка ошибок сервера -->
        {#if form?.error}
          <div class="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-center">
            <p class="text-red-400 font-medium">✕ {form.error}</p>
          </div>
        {/if}
      </div>
    </form>
  {/if}
</div>
