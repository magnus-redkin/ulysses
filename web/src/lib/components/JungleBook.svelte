<script>
  import { afterNavigate } from '$app/navigation';
  import { locale } from '$lib/locale.svelte.js';

  let { slug = 'index' } = $props();

  let currentLang = $derived(locale.current);

  const allChapters = import.meta.glob('/src/lib/junglebook/*/*.md');

  let contentPromise = $derived.by(() => {
    const path = `/src/lib/junglebook/${currentLang}/${slug}.md`;
    const loader = allChapters[path];
    return loader ? loader() : Promise.resolve(null);
  });

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

      { title: 'Температура по больнице', chapter: true },
      { slug: 'golden-shield', title: 'Золотой щит' },
      { slug: 'india-intranet', title: 'Индия' },
      { slug: 'europe', title: 'Европа' },
      { slug: 'usa-censorship', title: 'США' },
      { slug: 'israel-censorship', title: 'Израиль' },
      { slug: 'russia-censorship', title: 'Россия' },
      { slug: 'other-censorship', title: '...и нигде не лучше' },

      { title: 'Цифровая гигиена', chapter: true },
      { slug: 'fingerprint', title: 'Браузерный отпечаток' },
      { slug: 'leaks', title: 'Проверка утечек' },
      { slug: 'mitm-risks', title: 'Почему VPN не изменяет TLS-отпечаток' },
      { slug: 'tls-cloudflare', title: 'Cloudflare и парадокс доверия' },

      { title: 'Клиенты', chapter: true },
      { slug: 'download-client', title: 'Выбор клиента для прокси и VPN' },
      { slug: 'two_links', title: 'Почему две ссылки, Global и Russia?' },
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
      { slug: 'two_links', title: 'Why two links, Global и Russia?' },
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

  const t = $derived(currentLang === 'en'
    ? { notFound: 'Chapter not found', missingIn: 'Missing file', missingFolder: 'in folder', copy: 'Copy link' }
    : { notFound: 'Глава не найдена', missingIn: 'отсутствует файл', missingFolder: 'В папке', copy: 'Скопировать ссылку' }
  );

  let pageTitle = $derived.by(() => {
    const found = currentChapters.find(c => c.slug === slug);
    return found ? `${found.title} — Jungle Book` : 'Jungle Book';
  });

  // ---- АНКОРЫ ----

  function slugify(text) {
    return text
      .toString()
      .normalize('NFKD')
      .toLowerCase()
      .trim()
      .replace(/[^\w\s\u0400-\u04FF-]/g, '')
      .replace(/\s+/g, '-')
      .replace(/-+/g, '-');
  }

  function scrollToHash(hash) {
    if (!hash) return;
    const id = decodeURIComponent(hash.replace(/^#/, ''));
    if (!id) return;
    requestAnimationFrame(() => {
      const el = document.getElementById(id);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  /**
   * Экшен: расставляет id + кликабельные # у заголовков внутри контейнера.
   * @param {HTMLElement} node
   */
  function anchorHeadings(node) {
    const headings = node.querySelectorAll('h1, h2, h3, h4, h5, h6');
    const used = new Set();

    for (const h of headings) {
      if (h.dataset.anchored === 'true') continue;

      // текст без уже вставленного якоря
      const raw = (h.textContent || '').replace(/#$/, '').trim();
      if (!raw) continue;

      let id = slugify(raw);
      if (!id) continue;

      // уникальность
      if (used.has(id)) {
        let n = 2;
        const base = id;
        while (used.has(`${base}-${n}`)) n++;
        id = `${base}-${n}`;
      }
      used.add(id);

      h.id = id;
      h.dataset.anchored = 'true';

      const a = document.createElement('a');
      a.href = `#${id}`;
      a.className = 'heading-anchor';
      a.textContent = '#';
      a.title = t.copy;
      a.setAttribute('aria-label', t.copy);

      a.addEventListener('click', (e) => {
        e.preventDefault();
        const url = new URL(window.location.href);
        url.hash = id;
        history.replaceState(null, '', `#${id}`);
        navigator.clipboard?.writeText(url.toString()).catch(() => {});
        document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });

      h.appendChild(a);
    }

    // начальный скролл при монтировании
    scrollToHash(window.location.hash);

    return {
      destroy() {}
    };
  }

  // SvelteKit при клиентской навигации сам хэш не скроллит
  afterNavigate(({ to }) => {
    if (to?.hash) scrollToHash(to.hash);
  });
</script>

<svelte:head>
  <title>{pageTitle}</title>
</svelte:head>

<div class="py-10 grid grid-cols-1 md:grid-cols-12 gap-8">
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

  <main class="md:col-span-8 prose prose-invert max-w-none">
    {#await contentPromise}
      <p class="text-slate-500 font-mono text-sm">Loading…</p>
    {:then module}
      {#if module?.default}
        {@const Content = module.default}
        <div use:anchorHeadings>
          <Content />
        </div>
      {:else}
        <div class="p-4 bg-rose-950/40 border border-rose-800 text-rose-300 font-mono rounded">
          <h2 class="text-rose-400 font-bold mb-2">{t.notFound}</h2>
          <p class="text-xs">
            {t.missingFolder} <span class="text-white bg-slate-900 px-1 py-0.5 rounded">/src/lib/junglebook/{currentLang}/</span>
            {t.missingIn} <span class="text-white bg-slate-900 px-1 py-0.5 rounded">{slug}.md</span>
          </p>
        </div>
      {/if}
    {:catch err}
      <div class="p-4 bg-rose-950/40 border border-rose-800 text-rose-300 font-mono rounded">
        <h2 class="text-rose-400 font-bold mb-2">Error</h2>
        <pre class="text-xs whitespace-pre-wrap">{err?.message}</pre>
      </div>
    {/await}
  </main>
</div>

<style>
  /* `#` рядом с заголовком — видна при наведении */
  :global(.heading-anchor) {
    margin-left: 0.5rem;
    font-size: 0.75em;
    font-weight: 400;
    color: rgb(96 165 250); /* blue-400 */
    text-decoration: none;
    opacity: 0;
    transition: opacity 0.15s ease;
    user-select: none;
  }
  :global(:is(h1, h2, h3, h4, h5, h6):hover .heading-anchor),
  :global(.heading-anchor:focus-visible) {
    opacity: 1;
  }
  /* подсветка цели при переходе по якорю */
  :global(:is(h1, h2, h3, h4, h5, h6):target) {
    scroll-margin-top: 5rem;
    background: linear-gradient(90deg, rgb(59 130 246 / 0.15), transparent 60%);
    border-radius: 0.25rem;
  }
</style>
