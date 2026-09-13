<script>
  import { locale } from '$lib/locale.svelte.js';
  import SocialLinks from './SocialLinks.svelte';
</script>

<svelte:head>
  {#if locale.current === 'ru'}
    <title>Улисс VPN — Умный VPN с открытым исходным кодом</title>
    <meta name="description" content="Улисс — умный VPN с открытым исходным кодом на базе Hiddify. Надежная защита VLESS, REALITY, и xHTTP без слежки и CloudFlare." />
    <meta name="keywords" content="vpn с открытым исходным кодом, умный vpn, hiddify vpn, vless reality vpn, бесплатный впн, ulysses vpn" />
    <meta property="og:title" content="Улисс — умный VPN с открытым исходным кодом" />
    <meta property="og:description" content="умный VPN на базе Hiddify с открытым исходным кодом. Защита VLESS + REALITY." />
  {:else}
    <title>Ulysses VPN — Smart Open-Source VPN</title>
    <meta name="description" content="Ulysses VPN is a smart, open-source VPN powered by Hiddify. Secure VLESS, REALITY, and xHTTP protocols without corporate spying." />
    <meta name="keywords" content="open source vpn, smart vpn, hiddify vpn, vless reality, free vpn, ulysses vpn" />
    <meta property="og:title" content="Ulysses VPN — Smart Open-Source VPN" />
    <meta property="og:description" content="Smart open-source VPN powered by Hiddify. VLESS + REALITY protection." />
  {/if}
  <meta property="og:type" content="website" />
  <meta name="robots" content="index, follow" />
</svelte:head>

<main class="p-6 border rounded-xl shadow-sm mt-4">
  <article class="prose max-w-none text-white">

    <h1>{locale.current === 'ru' ? 'Улисс VPN' : 'Ulysses VPN'}</h1>

    <p>
      {locale.current === 'ru'
        ? 'умный VPN с открытым исходным кодом на базе Hiddify'
        : 'smart open-source VPN powered by Hiddify '}
    </p>

    <SocialLinks />

    <p class="text-lg opacity-80 mt-4">
      VLESS + Reality + xHTTP + gRPC + ...
    </p>

    <div class="mt-6 space-y-3 text-sm text-gray-400">
      <p class="pb-4">
        {@html locale.current === 'ru'
          ? '• Улисс <b>не использует Cloudflare</b> и <b>не поддерживает обход белых списков</b> — эти технологии так или иначе связаны с регуляторными организациями и раскрытием данных третьим сторонам. Мы работаем только на собственной инфраструктуре, а трафик идёт напрямую к нашим серверам.'
          : '• Ulysses <b>does not use Cloudflare</b> and <b>does not provide white-list bypass</b> — these technologies are tied to regulatory organizations and third-party data disclosure. We operate solely on our own infrastructure, and traffic goes directly to our servers.'}
      </p>
      <p class="pb-4">
        {@html locale.current === 'ru'
          ? '• Каждому пользователю выдаются две ссылки: 🟢 Simple — для повседневного использования (Telegram, YouTube, браузер), 🔴 Advanced — расширенный набор протоколов: если Simple не работает или нужен минимальный пинг для игр.'
          : '• Every user gets two links: 🟢 Simple — for everyday use (Telegram, YouTube, browser), 🔴 Advanced — an extended protocol set: use it if Simple doesn\'t work or if you need low ping for gaming.'}
      </p>
      <p class="pb-4">
        {locale.current === 'ru'
          ? '• Путеводитель по выживанию и обходу блокировок: '
          : '• A guide to survival and bypassing censorship: '}
        <a href="/junglebook/" class="underline hover:text-white transition">
          <b>{locale.current === 'ru' ? 'Книга Джунглей' : 'Jungle Book'}</b>
        </a>
      </p>

      <p class="pb-4">
        {locale.current === 'ru'
          ? '• Выбрать клиент: откройте сайт, тап на Download и выберите вашу платформу:'
          : '• Choose a client: open the site, tap Download, and pick your platform:'}
      </p>

      <ul class="list-none space-y-2 pl-4 pb-4">
        <li>
          ✅ <b>Hiddify</b> —
          <a href="https://hiddify.com/" target="_blank" rel="noopener" class="underline hover:text-white transition">hiddify.com</a>
          <span class="text-emerald-400">
            {locale.current === 'ru' ? '(рекомендуется)' : '(recommended)'}
          </span>
        </li>
        <li>
          <b>v2rayTun</b> —
          <a href="https://v2raytun.com/" target="_blank" rel="noopener" class="underline hover:text-white transition">v2raytun.com</a>
        </li>
        <li>
          <b>Happ</b> —
          <a href="https://happ.info/" target="_blank" rel="noopener" class="underline hover:text-white transition">happ.info</a>
        </li>
      </ul>


            <p class="pb-4">
        📖 {locale.current === 'ru'
          ? 'Подробнее о выборе клиента и протоколов — в '
          : 'More about choosing a client and protocols — in the '}
        <a href="/junglebook/" class="underline hover:text-white transition">
          {locale.current === 'ru' ? 'Книге Джунглей' : 'Jungle Book'}
        </a>
      </p>

    </div>

    <p class="my-6 font-bold">
      {locale.current === 'ru' ? 'несколько минут, и вы в сети:' : 'A few minutes, and you are online:'}
    </p>

    <div class="flex flex-col sm:flex-row justify-start items-center gap-4 my-6">
      <a
        href="/pricing"
        class="w-full sm:w-auto px-8 py-4 bg-slate-800 hover:bg-slate-700 text-white font-bold rounded-xl border border-slate-700 hover:border-slate-600 transition-all text-center shadow-lg hover:shadow-slate-900/50"
      >
        {locale.current === 'ru' ? 'Посмотреть тарифы' : 'View Pricing'}
      </a>

      <a
        href="/pricing?plan=free"
        class="w-full sm:w-auto px-8 py-4 bg-emerald-500 hover:bg-emerald-400 text-black font-extrabold rounded-xl transition-all text-center shadow-lg shadow-emerald-500/10 hover:shadow-emerald-500/20 ring-4 ring-emerald-500/10 hover:ring-emerald-500/20"
      >
        {locale.current === 'ru' ? 'Попробовать бесплатно' : 'Try for Free'}
      </a>
    </div>

    <p>
      <b>{locale.current === 'ru' ? 'Телеграм' : 'Telegram'}</b>:
      <a href="https://t.me/ulysses_vpn_bot">@ulysses_vpn_bot</a>
    </p>

  </article>
</main>
