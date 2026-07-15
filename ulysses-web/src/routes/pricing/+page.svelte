<script>
  import { enhance } from '$app/forms';
  import { locale } from '$lib/locale.svelte.js';
  import { page } from '$app/stores';

  let { form } = $props();

  const t = $derived({
    title: locale.current === 'ru' ? 'Выберите тариф' : 'Choose your plan',
    emailLabel: locale.current === 'ru' ? 'Ваш Email' : 'Your Email',
    confirmEmailLabel: locale.current === 'ru' ? 'Подтвердите Email' : 'Confirm Email',
    submitBtn: locale.current === 'ru' ? 'Продолжить' : 'Continue',
    errorMatch: locale.current === 'ru' ? 'Email адреса не совпадают' : 'Emails do not match',
    errorInvalid: locale.current === 'ru' ? 'Некорректный формат Email' : 'Invalid email format',
    errorSelectPlan: locale.current === 'ru' ? 'Пожалуйста, выберите тариф' : 'Please select a plan',
    loading: locale.current === 'ru' ? 'Загрузка тарифов...' : 'Loading plans...',
    errorLoad: locale.current === 'ru' ? 'Не удалось загрузить тарифы' : 'Failed to load plans'
  });

  // Данные из load функции — через $page.data
  let plans = $derived($page.data?.plans ?? []);
  let loadError = $derived($page.data?.error ?? null);
  let isLoaded = $derived($page.data?.plans !== undefined);

  let selectedPlan = $state('');
  let email = $state('');
  let confirmEmail = $state('');
  let isSubmitting = $state(false);

  let isEmailValid = $derived(/^[\w-\.]+@([\w-]+\.)+[\w-]{2,4}$/.test(email));
  let doEmailsMatch = $derived(email === confirmEmail);
  let isFormValid = $derived(selectedPlan && isEmailValid && doEmailsMatch && !isSubmitting);

  function handleSubmit() {
    if (isFormValid) {
      isSubmitting = true;
    }
  }

  // Для отладки
  $effect(() => {
    console.log('plans:', plans);
    console.log('isLoaded:', isLoaded);
    console.log('loadError:', loadError);
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
            <h3 class="text-xl font-bold text-white mb-2">{plan.name}</h3>
            <p class="text-3xl font-extrabold text-emerald-400 mb-4">₽{plan.price}</p>
            {#if plan.desc}
              <p class="text-gray-400 text-sm">{plan.desc}</p>
            {/if}
          </button>
        {/each}
      </div>

      {#if !selectedPlan}
        <p class="text-amber-400 text-sm text-center font-medium">{t.errorSelectPlan}</p>
      {/if}

      <div class="space-y-4 max-w-md mx-auto pt-6 border-t border-gray-800">
        <div>
          <label for="email" class="block text-sm font-medium text-gray-400 mb-1">{t.emailLabel}</label>
          <input
            id="email"
            name="email"
            type="email"
            bind:value={email}
            required
            autocomplete="off"
            placeholder="your@email.com"
            class="w-full bg-gray-900 border border-gray-800 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-colors"
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

        <button
          type="submit"
          disabled={!isFormValid}
          class="w-full mt-4 bg-emerald-500 text-black font-bold py-3 px-6 rounded-lg transition-all
            hover:bg-emerald-400 disabled:bg-gray-800 disabled:text-gray-500 disabled:cursor-not-allowed
            {isSubmitting ? 'opacity-75' : ''}"
        >
          {isSubmitting ? '⏳ ' + (locale.current === 'ru' ? 'Отправка...' : 'Processing...') : t.submitBtn}
        </button>

        {#if form?.success}
          <div class="bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-4 text-center">
            <p class="text-emerald-400 font-medium">✓ {form.message}</p>
            {#if form.order_id}
              <p class="text-gray-400 text-sm mt-1">
                {locale.current === 'ru' ? 'Номер заказа' : 'Order ID'}: {form.order_id}
              </p>
            {/if}
            {#if form.amount}
              <p class="text-gray-400 text-sm">
                {locale.current === 'ru' ? 'Сумма' : 'Amount'}: ${form.amount}
              </p>
            {/if}
          </div>
        {/if}

        {#if form?.error}
          <div class="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-center">
            <p class="text-red-400 font-medium">✕ {form.error}</p>
          </div>
        {/if}
      </div>
    </form>
  {/if}
</div>
