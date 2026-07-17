<script>
  import { locale } from '$lib/locale.svelte.js';
  import { page } from '$app/stores';
  import SocialLinks from './SocialLinks.svelte';

</script>


<svelte:head>
  {#if locale.current === 'ru'}
    <title>Улисс VPN — Умный VPN с открытым исходным кодом</title>
    <meta name="description" content="Улисс VPN — бесплатный умный VPN с открытым исходным кодом на базе Hiddify. Надежная защита VLESS, REALITY, gRPC и xHTTP без слежки и CloudFlare." />
    <meta name="keywords" content="vpn с открытым исходным кодом, умный vpn, hiddify vpn, vless reality vpn, бесплатный впн, ulysses vpn" />

    <!-- Open Graph (Для красивого отображения ссылки в Telegram/VK) -->
    <meta property="og:title" content="Улисс VPN — Умный VPN с открытым исходным кодом" />
    <meta property="og:description" content="Бесплатный умный VPN на базе Hiddify с открытым исходным кодом. Защита VLESS + REALITY." />
  {:else}
    <title>Ulysses VPN — Smart Open-Source VPN</title>
    <meta name="description" content="Ulysses VPN is a smart, open-source VPN powered by Hiddify. Secure VLESS, REALITY, gRPC, and xHTTP protocols without corporate spying." />
    <meta name="keywords" content="open source vpn, smart vpn, hiddify vpn, vless reality, free vpn, ulysses vpn" />

    <!-- Open Graph for English -->
    <meta property="og:title" content="Ulysses VPN — Smart Open-Source VPN" />
    <meta property="og:description" content="Smart open-source VPN powered by Hiddify. VLESS + REALITY protection." />
  {/if}

  <meta property="og:type" content="website" />
  <meta name="robots" content="index, follow" />
</svelte:head>


<main class="p-6 border rounded-xl shadow-sm mt-4">
  <article class="prose max-w-none text-white">

    {#if locale.current === 'ru'}
      <h1>Улисс VPN</h1>
      <p>умный VPN с открытым исходным кодом на базе Hiddify (без CloudFlare)</p>
      <h1>готовится к запуску! Ждите!</h1>

      <SocialLinks />

      <p class="text-lg opacity-80 mt-4">
        VLESS + REALITY + gRPC + xHTTP
      </p>

      <ul class="list-disc list-inside space-y-1 mt-2 opacity-80">
        <li><b>VLESS</b> - упаковывает ваши данные в стандартные web-пакеты</li>
        <li><b>gRPC</b> - отправляет их в виде потока стандартных запросов HTTP/2</li>
        <li><b>xHTTP</b> - современная замена gRPC</li>
        <li><b>REALITY</b> - показывает системам блокировок сертификат любого известного сайта</li>
        <li><b>Ulysses</b> - служит щитом, мгновенно подменяя ip адрес в случае его блокировки. Как CloudFlare, но не шпионя за вами - мы используем только открытый код под свободной лицензией</li>
      </ul>

      <p class="my-6 font-bold">несколько минут, и вы в сети:</p>

    {:else}
      <h1>Ulysses VPN</h1>
    <p>smart open-source VPN powered by Hiddify (CloudFlare-free)</p>
      <h1>Getting ready to launch! Wait!</h1>

      <SocialLinks />

      <p class="text-lg opacity-80 mt-4">
        VLESS + REALITY + gRPC + xHTTP
      </p>

      <ul class="list-disc list-inside space-y-1 mt-2 opacity-80">
        <li><b>VLESS</b> - wraps your data into standard web packets</li>
        <li><b>gRPC</b> - sends data as a stream of standard HTTP/2 requests</li>
        <li><b>xHTTP</b> - a modern replacement for gRPC</li>
        <li><b>REALITY</b> - displays a certificate of any well-known website to censorship systems</li>
        <li><b>Ulysses</b> - acts as a shield, instantly rotating IP addresses in case of a block. Just like CloudFlare, but without spying on you — we use exclusively open-source code under free licenses</li>
        <li><b>support</b>: <a href="https://t.me/ulysses_vpn_bot">@Улисс</a></li>
      </ul>

      <p class="my-6 font-bold">A few minutes, and you are online:</p>
    {/if}

    <!-- Кнопки действий вынесены из условий, так как они одинаковы для обоих языков -->
    <div class="flex flex-col sm:flex-row justify-start items-center gap-4 my-6">
      <!-- Кнопка 1: Полный прайсинг -->
      <a
        href="/pricing"
        class="w-full sm:w-auto px-8 py-4 bg-slate-800 hover:bg-slate-700 text-white font-bold rounded-xl border border-slate-700 hover:border-slate-600 transition-all text-center shadow-lg hover:shadow-slate-900/50"
      >
        {locale.current === 'ru' ? 'Посмотреть тарифы' : 'View Pricing'}
      </a>

      <!-- Кнопка 2: Сразу выбрать Free-тариф -->
      <a
        href="/pricing?plan=free"
        class="w-full sm:w-auto px-8 py-4 bg-emerald-500 hover:bg-emerald-400 text-black font-extrabold rounded-xl transition-all text-center shadow-lg shadow-emerald-500/10 hover:shadow-emerald-500/20 ring-4 ring-emerald-500/10 hover:ring-emerald-500/20"
      >
        {locale.current === 'ru' ? 'Попробовать бесплатно' : 'Try for Free'}
      </a>
    </div>

    {#if locale.current === 'ru'}
      <p><b>поддержка</b> Телеграм: <a href="https://t.me/ulysses_vpn_bot">@Улисс</a></p>
    {:else}
      <p><b>support</b> Telegram: <a href="https://t.me/ulysses_vpn_bot">@Улисс</a></p>
    {/if}

  </article>

</main>
