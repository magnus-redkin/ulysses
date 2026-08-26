<script>
  import { page } from '$app/state';
  import { locale } from '$lib/locale.svelte.js';

  // 1. Пропс: slug текущей страницы (исправлено для Svelte 5)
  let { slug = 'index' } = $props();

  // 2. Получаем текущий язык
  let currentLang = $derived(locale.current);

  // 3. Импортируем все .md файлы
  const allChapters = import.meta.glob('/src/lib/junglebook/*/*.md', { eager: true });

  // 4. Вычисляем содержимое
  let CurrentContent = $derived.by(() => {
    const path = `/src/lib/junglebook/${currentLang}/${slug}.md`;
    return allChapters[path]?.default || null;
  });

  // 5. Список глав с переводами (оставлен как у вас, добавлен whitelists)
  const chaptersData = {
    ru: [
      { slug: 'index', title: 'Содержание Книги' },
      { slug: 'aknowledgements', title: 'Благодарности' },
      { title: 'Эволюция хищников', chapter: true },
      { slug: 'threats', title: 'Классификация Угроз' },
      { slug: 'local-threats', title: 'локальные угрозы' },
      { slug: 'global-threats', title: 'глобальные угрозы' },
      { slug: 'future-threats', title: 'угрозы будущего' },
      { title: 'Как выбрать VPN?', chapter: true },
      { slug: 'how-to-choose-vpn', title: 'Критерии устойчивости в эпоху жесткой цензуры' },
      { slug: 'whitelists', title: 'Белые списки' },
      { title: 'Клиенты', chapter: true },
      { slug: 'client', title: 'Настройки клиента Hiddify' },
      { slug: 'v2rayN-Hiddify', title: 'v2rayN vs. Hiddify-Client vs. Happ' },
      { title: 'Справка по Протоколам и Транспортам', chapter: true },
      { slug: 'classic-protocols', title: 'Прокси-Протоколы: VLESS, VMess, Trojan, Shadowsocks (версии AEAD и 2022), Mieru' },
      { slug: 'udp-protocols', title: 'Udp-Ориентированные Высокоскоростные Протоколы: Hysteria2, TUIC, WireGuard' },
      { slug: 'mask', title: 'Технологии Маскировки и Защиты Трафика: Reality, ShadowTLS' },
      { slug: 'transports', title: 'Сетевые Транспорты и Обертки: TCP, WebSockets, gRPC, HTTPUpgrade, xHTTP' },
      { slug: 'additional-services', title: 'Вспомогательные и Встроенные Сервисы: SSH Proxy, MTProto, DNS over HTTPS' },
      { title: 'Архитектура Hiddify', chapter: true },
      { slug: 'xray-singbox', title: 'Xray vs. Singbox' },
      { slug: 'links', title: 'полезные ссылки' },
    ],
    en: [
      { slug: 'index', title: 'Table of Contents' },
      { slug: 'aknowledgements', title: 'Acknowledgments' },
      { title: 'Evolution of Predators', chapter: true },
      { slug: 'threats', title: 'Threat Classification' },
      { slug: 'local-threats', title: 'Local Threats' },
      { slug: 'global-threats', title: 'Global Threats' },
      { slug: 'future-threats', title: 'Future Threats' },
      { title: 'How to Choose a VPN?', chapter: true },
      { slug: 'how-to-choose-vpn', title: 'Resilience Criteria in the Age of Heavy Censorship' },
      { slug: 'whitelists', title: 'Whitelists' },
      { title: 'Clients', chapter: true },
      { slug: 'client', title: 'Hiddify Client Settings' },
      { slug: 'v2rayN-Hiddify', title: 'v2rayN vs. Hiddify-Client vs. Happ' },
      { title: 'Protocol & Transport Reference', chapter: true },
      { slug: 'classic-protocols', title: 'Proxy Protocols: VLESS, VMess, Trojan, Shadowsocks (AEAD & 2022), Mieru' },
      { slug: 'udp-protocols', title: 'UDP-Oriented High-Speed Protocols: Hysteria2, TUIC, WireGuard' },
      { slug: 'mask', title: 'Traffic Masking & Protection: Reality, ShadowTLS' },
      { slug: 'transports', title: 'Network Transports & Wrappers: TCP, WebSockets, gRPC, HTTPUpgrade, xHTTP' },
      { slug: 'additional-services', title: 'Auxiliary & Built-in Services: SSH Proxy, MTProto, DNS over HTTPS' },
      { title: 'Hiddify Architecture', chapter: true },
      { slug: 'xray-singbox', title: 'Xray vs. Singbox' },
      { slug: 'links', title: 'Useful Links' },
    ]
  };

  let currentChapters = $derived(chaptersData[currentLang] || chaptersData.ru);
</script>

<div class="py-10 grid grid-cols-1 md:grid-cols-12 gap-8">
  <!-- Боковое меню -->
  <aside class="md:col-span-4 border-r border-slate-800 pr-4">
    <h3 class="text-xs font-mono uppercase tracking-wider text-slate-500 mb-4">
      <a href="/junglebook/">Jungle Book</a>
    </h3>
    <nav class="flex flex-col gap-1_">
      {#each currentChapters as ch}
        {#if ch.chapter}
          <div class="text-base font-bold uppercase_ tracking-wider text-slate-200 mt-5 mb-1 px-2">
            {ch.title}
          </div>
        {:else}
          <div class="text-sm font-medium transition-colors px-2 py-1 pl-4 rounded-md {slug === ch.slug ? 'bg-blue-400/20 text-blue-400 border border-blue-500/30' : 'text-slate-400 hover:text-slate-200'}">
            <a href="/junglebook/{ch.slug}">{ch.title}</a>
          </div>
        {/if}
      {/each}
    </nav>
  </aside>

  <!-- Основной текст -->
  <main class="md:col-span-8 prose prose-invert max-w-none">
    {#if CurrentContent}
      <CurrentContent />
    {:else}
      <div class="p-4 bg-rose-950/40 border border-rose-800 text-rose-300 font-mono rounded">
        <h2 class="text-rose-400 font-bold mb-2">Глава не найдена</h2>
        <p class="text-xs">
          В папке <span class="text-white bg-slate-900 px-1 py-0.5 rounded">/src/lib/junglebook/{currentLang}/</span>
          отсутствует файл <span class="text-white bg-slate-900 px-1 py-0.5 rounded">{slug}.md</span>
        </p>
      </div>
    {/if}
  </main>
</div>
