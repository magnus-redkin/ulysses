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

<div class="min-h-screen text-gray-900 font-sans max-w-5xl mx-auto p-6">
	<!-- Панель управления языком и верхний динамический Хедер -->
	<header class="p-6 border-b_ flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
		<div class="prose prose-sm">
			<CurrentHeader />
		</div>

		<div class="flex items-center gap-2 p-1 rounded-lg">
			<button
				onclick={() => locale.set('ru')}
				class="px-3 py-1.5 rounded-md text-xs font-bold transition-all {locale.current === 'ru' ? 'text-blue-600 shadow-sm' : 'text-gray-500 hover:text-gray-900'}"
			>RU</button>
			<button
				onclick={() => locale.set('en')}
				class="px-3 py-1.5 rounded-md text-xs font-bold transition-all {locale.current === 'en' ? 'text-blue-600 shadow-sm' : 'text-gray-500 hover:text-gray-900'}"
			>EN</button>
		</div>
	</header>

	<!-- Главное меню разделов сайта -->
	<nav class="border_ px-6 py-3_ flex gap-6">
		{#each menuItems as item}
			<a
				href="/{item.id}"
				class="text-sm_ font-medium text-gray-600 hover:text-blue-600 transition-colors"
			>
				{locale.current === 'ru' ? item.ru : item.en}
			</a>
		{/each}
	</nav>

	<!-- Контент текущей страницы -->
	<div class="max-w-5xl mx-auto px-6_">
		{@render children()}
	</div>

	<footer class="border-t border-gray-800 px-6 py-4 flex flex-col sm:flex-row justify-between items-center gap-4 mt-12">
		<nav class="flex flex-wrap gap-6">
			{#each footerItems as item}
				<a
					href="/{item.id}"
					class="text-sm font-medium text-gray-600 hover:text-blue-600 transition-colors"
				>
					{locale.current === 'ru' ? item.ru : item.en}
				</a>
			{/each}
		</nav>
		<div class="text-xs text-gray-500 font-mono">
			&copy; {new Date().getFullYear()} Ulysses Lab.
		</div>
	</footer>
</div>
{/if}
