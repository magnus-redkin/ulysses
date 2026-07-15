<script>
  import { page } from '$app/stores';
  import { locale } from '$lib/locale.svelte.js';

  // Лениво импортируем все файлы контента из папки lib/content
  const pages = import.meta.glob('$lib/content/**/*.md');

  // Получаем имя текущей страницы из URL (параметр [page])
  let pageName = $derived($page.params.page || 'service');

  // Формируем путь и динамически загружаем нужный компонент Svelte/Markdown
  let CurrentContent = $derived.by(() => {
    const path = `/src/lib/content/${locale.current}/${pageName}.md`;

    if (pages[path]) {
      // Инициализируем компонент через промис
      return svelteComponentFromPromise(pages[path]());
    }
    return null;
  });

  // Вспомогательная функция для разворачивания асинхронного импорта в компонент
  function svelteComponentFromPromise(promise) {
    let component = $state(null);
    promise.then((mod) => { component = mod.default; });
    return { get current() { return component; } };
  }

  let author = $derived(locale.current === 'ru' ? 'Мария' : 'Mary');
</script>

<main class="p-6 border rounded-xl shadow-sm mt-4_">
  <h2 class="text-xl font-medium text-gray-500 mb-4_">
    <!-- {locale.current === 'ru' ? 'Пользователь' : 'User'}: {author} -->
  </h2>

  <article class="prose max-w-none text-white">
    {#if CurrentContent && CurrentContent.current}
      {@const Content = CurrentContent.current}
      <Content />
    {:else}
      <p class="text-red-500 font-medium">404 - Page not found === </p>
    {/if}
  </article>
</main>
