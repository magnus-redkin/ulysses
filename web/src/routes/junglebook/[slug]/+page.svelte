<script>
  import { page } from '$app/state';

  // 1. Сканируем файлы через Vite glob
  const ruChapters = import.meta.glob('$lib/junglebook/ru/*.md', { eager: true });

  // Список глав для бокового меню
    const chapters = [
      { slug: 'index', title: 'Содержание Книги' },
      // Глава 1
      { slug: 'threats', title: '1: Эволюция хищников — классификация угроз и блокировок' },
      { slug: 'global-threats', title: '- глобальные угрозы' },
      { slug: 'local-threats', title: '- локальные угрозы' },
      { slug: 'dpi-intro', title: '- механизмы DPI' },
      { slug: 'sni-blocking', title: '- блокировки по SNI' },
      { slug: 'behavioral-analysis', title: '- поведенческий анализ' },
    // Глава 2
      { slug: 'threats', title: '2: Экосистема Hiddify - универсальный комбайн' },
      { slug: 'hiddify-philosophy', title: '- философия Hiddify' },
      { slug: 'cores-architecture', title: '- архитектура ядер' },
      { slug: 'panel-comparison', title: '- сравнение панелей' },
    // Глава 3
      { slug: 'threats', title: '3: Справочник протоколов' },
      { slug: 'vless-reality', title: '- маскировка VLESS+Reality' },
      { slug: 'quic-protocols', title: '- скорость через QUIC' },
      { slug: 'heavy-dpi-workarounds', title: '- тяжелая артиллерия' },
      { slug: 'legacy-protocols', title: '- триада старой школы' },
    // Глава 4
      { slug: 'threats', title: '4: Практика — протоколы в Hiddify-Manager' },
      { slug: 'regional-targeting', title: '- карта по регионам' },
      { slug: 'hf-reality-setup', title: '- настройка Reality' },
      { slug: 'cdn-transport-tuning', title: '- оптимизация транспортов' },
      { slug: 'doh-ech-tuning', title: '- тюнинг DoH и ECH' }
  ];

  // 2. Получаем текущий slug (Svelte 5 Runes)
  let currentSlug = $derived(page.params.slug || 'index');

  // 3. Динамически вычисляем компонент на основе slug
  let CurrentContent = $derived(() => {
    const path = `/src/lib/junglebook/ru/${currentSlug}.md`;
    return ruChapters[path]?.default || null;
  });
</script>

<div class="py-10 grid grid-cols-1 md:grid-cols-12 gap-8">
  <!-- Боковое меню (Оглавление) -->
  <aside class="md:col-span-4 border-r border-slate-800 pr-4">
    <h3 class="text-xs font-mono uppercase tracking-wider text-slate-500 mb-4">Jungle Book</h3>
    <nav class="flex flex-col gap-1">
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
  <main class="md:col-span-8 prose prose-invert max-w-none">
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
