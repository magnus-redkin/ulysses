<script>
  // web/src/routes/junglebook/\[slug\]/+page.svelte

  import { page } from '$app/state';

  // 1. Сканируем файлы через Vite glob
  // const ruChapters = import.meta.glob('$lib/junglebook/ru/*.md', { eager: true });
  const ruChapters = import.meta.glob('/src/lib/junglebook/ru/*.md', { eager: true });

  // Список глав для бокового меню
    const chapters = [
      { slug: 'index', title: 'Содержание Книги' },
      // Глава 1
      { title: 'Эволюция хищников', chapter: true },
      { slug: 'threats', title: 'Классификация Угроз' },
      { slug: 'local-threats', title: 'локальные угрозы' },
      { slug: 'global-threats', title: 'глобальные угрозы' },
      { slug: 'future-threats', title: 'угрозы будущего' },

      // Глава 2
      { title: 'Как выбрать VPN?', chapter: true },
      { slug: 'how-to-choose-vpn', title: 'Критерии устойчивости в эпоху жесткой цензуры' },

      // Глава 3
      { title: 'Клиенты', chapter: true },
      { slug: 'client', title: 'Настройки клиента Hiddify' },
      { slug: 'v2rayN-Hiddify', title: 'v2rayN vs. Hiddify-Client vs. Happ' },

      // Глава 4
      { title: 'Справка по Протоколам и Транспортам', chapter: true },
      { slug: 'classic-protocols', title: 'Прокси-Протоколы: VLESS, VMess, Trojan, Shadowsocks (версии AEAD и 2022), Mieru' },
      { slug: 'udp-protocols', title: 'Udp-Ориентированные Высокоскоростные Протоколы: Hysteria2, TUIC, WireGuard' },
      { slug: 'mask', title: 'Технологии Маскировки и Защиты Трафика: Reality, ShadowTLS' },
      { slug: 'transports', title: 'Сетевые Транспорты и Обертки: TCP, WebSockets, gRPC, HTTPUpgrade, xHTTP' },
      { slug: 'additional-services', title: 'Вспомогательные и Встроенные Сервисы: SSH Proxy, MTProto, DNS over HTTPS' },

      // Глава 5
      { title: 'Архитектура Hiddify', chapter: true },
      { slug: 'xray-singbox', title: 'Xray vs. Singbox' },

      { title: '', chapter: true },
      { slug: 'links', title: 'полезные ссылки' },

  ];

  // 2. Получаем текущий slug (Svelte 5 Runes)
  let currentSlug = $derived(page.params.slug || 'index');

  // 3. Динамически вычисляем компонент на основе slug
  // let CurrentContent = $derived(() => {
  //   const path = `/src/lib/junglebook/ru/${currentSlug}.md`;
  //   return ruChapters[path]?.default || null;
  // });
  let CurrentContent = $derived(ruChapters[`/src/lib/junglebook/ru/${currentSlug}.md`]?.default || null);

</script>

<div class="py-10 grid grid-cols-1 md:grid-cols-12 gap-8">
  <!-- Боковое меню (Оглавление) -->
  <aside class="md:col-span-4 border-r border-slate-800 pr-4">
    <h3 class="text-xs font-mono uppercase tracking-wider text-slate-500 mb-4"><a href="/junglebook/">Jungle Book</a></h3>
    <nav class="flex flex-col gap-1_">
      {#each chapters as ch}
        {#if ch.chapter}
          <!-- Заголовок главы: отбит сверху (mt-5), уменьшен, выделен цветом -->
          <div class="text-base font-bold uppercase_ tracking-wider text-slate-200 mt-5 mb-1 px-2">
            <!-- <a href="/junglebook/{ch.slug}">{ch.title}</a> -->
            {ch.title}
          </div>

        {:else}
          <!-- Обычная ссылка: сжата по вертикали (py-1 вместо p-2) -->
          <div class="text-sm font-medium transition-colors px-2 py-1 pl-4 rounded-md {currentSlug === ch.slug ? 'bg-blue-400/20 text-blue-400 border border-blue-500/30' : 'text-slate-400 hover:text-slate-200'}">
            <a href="/junglebook/{ch.slug}">{ch.title}</a>
          </div>

        {/if}
      {/each}
    </nav>
  </aside>

  <!-- Основной текст главы -->
  <main class="md:col-span-8 prose prose-invert max-w-none">
    {#if CurrentContent}
      <!-- <ContentComponent /> -->
      <CurrentContent />
    {:else}
      <div class="p-4 bg-rose-950/40 border border-rose-800 text-rose-300 font-mono rounded">
        <h2 class="text-rose-400 font-bold mb-2">Глава не найдена</h2>
        <p class="text-xs">В папке `$lib/junglebook/ru/` отсутствует файл <span class="text-white bg-slate-900 px-1 py-0.5 rounded">{currentSlug}.md</span></p>
      </div>
    {/if}
  </main>
</div>
