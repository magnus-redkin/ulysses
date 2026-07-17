<script>
  import './layout.css';
  import favicon from '$lib/assets/favicon.ico';
  import { locale } from '$lib/locale.svelte.js';

  // Импортируем оба хедера для быстрой смены языка
  import HeaderRU from '$lib/content/ru/header.md';
  import HeaderEN from '$lib/content/en/header.md';


  import { getContext } from 'svelte';


  let { children, data } = $props();
  // Выбираем хедер в зависимости от локали
  let CurrentHeader = $derived(locale.current === 'ru' ? HeaderRU : HeaderEN);

  // Структура меню (ключ страницы для URL : названия на разных языках)
  const menuItems = [
    { id: 'service', ru: 'Услуги', en: 'Services' },
    { id: 'pricing', ru: 'Тарифы', en: 'Pricing' },
    { id: 'soft', ru: 'Софт', en: 'Software' },
  ];

  // НОВОЕ: Меню футера (нижнее)
  const footerItems = [
    { id: 'offer', ru: 'Публичная оферта', en: 'Terms of Service' },
    { id: 'privacy', ru: 'Политика конфиденциальности', en: 'Privacy Policy' },
    { id: 'contacts', ru: 'Контакты', en: 'Contacts' }
  ];


</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>


{#if data.isAdminRoute}
  {@render children()}
{:else}

<div class="relative min-h-screen bg-slate-900 text-slate-200 font-sans overflow-hidden">

  <!-- Декоративное пятно (переход из голубого в розовый) -->
  <!-- Изменено: Z-индекс (z-0) и повышенная непрозрачность (/40), чтобы точно было видно -->
  <!-- <div class="absolute top-0 left-0 -translate-x-1/4 -translate-y-1/4 w-1/2 h-1/2 bg-gradient-to-br from-cyan-500/40 to-fuchsia-500/40 blur-3xl pointer-events-none rounded-full z-0"></div> -->
  <!-- Огромное неоновое облако с экстремальным размытием и плавным трехцветным переходом -->
<!-- <div class="absolute top-0 left-0 -translate-x-1/3 -translate-y-1/3 w-3/4 h-3/4 bg-gradient-to-br from-cyan-500/30 via-indigo-500/25 to-fuchsia-500/30 blur-[500px] pointer-events-none rounded-full z-0"></div> -->


<!-- Контейнер на 1/8 экрана (ширина 40% и высота 25% от экрана создадут нужную площадь) -->
<!-- Идеальный угловой неон: линейный градиент с сильным размытием, скрывающим форму квадрата -->
<div class="absolute top-0 left-0 w-[45vw] h-[35vh] -translate-x-12 -translate-y-12 bg-gradient-to-br from-cyan-400/40 via-fuchsia-500/20 to-transparent blur-[100px] pointer-events-none z-0"></div>



  <!-- Внутренний контейнер -->
  <!-- Изменено: добавлен z-10, удалены min-h-screen и конфликтующий text-gray-900 -->
  <div class="relative z-10 max-w-5xl mx-auto p-6">

	<!-- Панель управления языком и верхний динамический Хедер -->
	<header class="p-6 border-b border-slate-800 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
		<!-- Добавлен prose-invert, чтобы текст внутри CurrentHeader стал светлым -->
		<div class="prose prose-sm prose-invert">
			<CurrentHeader />
		</div>

		<!-- Кнопки адаптированы под темную тему -->
		<div class="flex items-center gap-2 p-1 bg-slate-800/50 border border-slate-700 rounded-lg">
			<button
				onclick={() => locale.set('ru')}
				class="px-3 py-1.5 rounded-md text-xs font-bold transition-all {locale.current === 'ru' ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'}"
			>RU</button>
			<button
				onclick={() => locale.set('en')}
				class="px-3 py-1.5 rounded-md text-xs font-bold transition-all {locale.current === 'en' ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'}"
			>EN</button>
		</div>
	</header>

	<!-- Контент текущей страницы -->
	<div class="max-w-5xl mx-auto">
		{@render children()}
	</div>

	<!-- Футер адаптирован под темную тему -->
	<footer class="border-t border-slate-800 px-6 py-4 flex flex-col sm:flex-row justify-between items-center gap-4 mt-12">
		<nav class="flex flex-wrap gap-6">
			{#each footerItems as item}
				<a
					href="/{item.id}"
					class="text-sm font-medium text-slate-400 hover:text-blue-400 transition-colors"
				>
					{locale.current === 'ru' ? item.ru : item.en}
				</a>
			{/each}
		</nav>
		<div class="text-xs text-slate-500 font-mono">
			&copy; {new Date().getFullYear()} Ulysses Lab.
		</div>
	</footer>
  </div>

</div>

{/if}
