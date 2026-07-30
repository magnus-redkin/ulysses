<script>
  import { page } from '$app/state';

  // 1. Сканируем файлы через Vite glob
  const ruChapters = import.meta.glob('$lib/junglebook/ru/*.md', { eager: true });

  // Список глав для бокового меню
  const chapters = [
    { slug: 'index', title: 'Содержание Книги' },
    { slug: 'protocols', title: 'Глава 1: Прокси-протоколы' }
  ];

  // 2. Получаем текущий slug (Svelte 5 Runes)
  let currentSlug = $derived(page.params.slug || 'index');

  // 3. Динамически вычисляем компонент на основе slug
  let CurrentContent = $derived(() => {
    const path = `/src/lib/junglebook/ru/${currentSlug}.md`;
    return ruChapters[path]?.default || null;
  });
</script>

<div class="py-10 grid grid-cols-1 md:grid-cols-4 gap-8">
  <!-- Боковое меню (Оглавление) -->
  <aside class="md:col-span-1 border-r border-slate-800 pr-4">
    <h3 class="text-xs font-mono uppercase tracking-wider text-slate-500 mb-4">Jungle Book</h3>
    <nav class="flex flex-col gap-2">
      {#each chapters as ch}
        <a
          href="/junglebook/{ch.slug}"
          class="text-sm font-medium transition-colors p-2 rounded-md {currentSlug === ch.slug ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30' : 'text-slate-400 hover:text-slate-200'}"
        >
          {ch.title}
        </a>
      {/each}
    </nav>
  </aside>

  <!-- Основной текст главы -->
  <main class="md:col-span-3 prose prose-invert max-w-none">
    {#if CurrentContent()}
      {@const ContentComponent = CurrentContent()}
      <ContentComponent />
    {:else}
      <div class="p-4 bg-rose-950/40 border border-rose-800 text-rose-300 font-mono rounded">
        <h2 class="text-rose-400 font-bold mb-2">Глава не найдена</h2>
        <p class="text-xs">В папке `$lib/junglebook/ru/` отсутствует файл <span class="text-white bg-slate-900 px-1 py-0.5 rounded">{currentSlug}.md</span></p>
      </div>
    {/if}
  </main>
</div>
