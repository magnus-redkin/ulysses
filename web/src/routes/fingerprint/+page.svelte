<script>
  import Bowser from 'bowser';

  // ============================================================
  // Вердикты
  // ============================================================
  async function browserPrivacyVerdict(browserName) {
    const name = (browserName || '').toLowerCase();
    const ua = navigator.userAgent.toLowerCase();

    if (ua.includes('torbrowser') || ua.includes('tor browser')) {
      return { level: 'green', reason: 'Tor Browser' };
    }
    if (ua.includes('mullvad')) {
      return { level: 'green', reason: 'Mullvad Browser' };
    }
    if (navigator.brave) {
      try {
        const isBrave = await navigator.brave.isBrave?.();
        if (isBrave) return { level: 'yellow', reason: 'Brave' };
      } catch {}
    }

    if (name.includes('firefox')) {
      // Признаки активной защиты (FPP/RFP)
      const isSquare =
        window.screen.width % 200 === 0 && window.screen.height % 100 === 0;
      const tz = (Intl.DateTimeFormat().resolvedOptions().timeZone || '').toLowerCase();
      const isUTC = tz === 'utc' || tz === 'etc/utc';
      const isHW2 = navigator.hardwareConcurrency === 2;
      const isWin32OnLinux =
        navigator.platform === 'Win32' && ua.includes('linux');

      const signals = [isSquare, isUTC, isHW2, isWin32OnLinux].filter(Boolean).length;

      if (signals >= 2) {
        return { level: 'green', reason: 'Firefox с защитой отпечатка' };
      }
      if (signals === 1) {
        return { level: 'yellow', reason: 'Firefox с частичной защитой' };
      }
      return { level: 'red', reason: 'Firefox без активной защиты' };
    }

    if (
      name.includes('chrome') || name.includes('edge') ||
      name.includes('safari') || name.includes('opera') || name.includes('yandex')
    ) {
      return { level: 'red', reason: 'Стандартный браузер без защиты' };
    }
    return { level: 'yellow', reason: 'Неизвестный браузер' };
  }

  function dnsVerdict(resolverIp) {
    if (!resolverIp) return { level: 'green', reason: 'DNS защищён (DoH)' };

    const trusted = [/^9\.9\.9\./, /^149\.112\.112\./, /^94\.140\.1[45]\./, /^194\.242\.0\./, /^194\.242\.1\./];
    const publicLogs = [/^1\.1\.1\./, /^1\.0\.0\./, /^8\.8\.8\./, /^8\.8\.4\./, /^208\.67\.22[02]\./, /^77\.88\.8\./];
    const cloudflareRanges = [/^172\.6[4-9]\./, /^172\.7[0-1]\./, /^104\.1[6-9]\./, /^104\.2[0-7]\./, /^162\.15[89]\./, /^162\.16[0-1]\./];

    const match = (arr) => arr.some((re) => re.test(resolverIp));
    if (match(trusted)) return { level: 'green', reason: 'Trusted no-log resolver' };
    if (match(publicLogs) || match(cloudflareRanges)) return { level: 'yellow', reason: 'Публичный DNS (логирует запросы)' };
    return { level: 'red', reason: 'DNS не защищён — вероятно провайдер' };
  }

  // ============================================================
  // РАЗДЕЛ 1: Браузер
  // ============================================================
  let browser = $state(null);
  let browserDetails = $state([]);
  let browserVerdict = $state(null);
  let browserLoading = $state(false);
  let browserError = $state(null);

  async function checkBrowser() {
    browserLoading = true;
    browserError = null;
    browser = null;
    browserDetails = [];
    browserVerdict = null;
    try {
      const b = Bowser.getParser(window.navigator.userAgent);
      const name = b.getBrowserName();
      browser = {
        name,
        version: b.getBrowserVersion(),
        os: b.getOSName(),
        engine: b.getEngineName(),
        platform: b.getPlatformType(),
      };
      browserVerdict = await browserPrivacyVerdict(name);

      const FingerprintJS = (await import('@fingerprintjs/fingerprintjs')).default;
      const fp = await FingerprintJS.load();
      const result = await fp.get();
      const c = result.components;
      const d = [];
      if (c.platform?.value) d.push(`ОС: ${c.platform.value}`);
      if (c.screenResolution?.value) {
        const r = c.screenResolution.value;
        d.push(`Экран: ${r[0]}×${r[1]}`);
      }
      if (c.timezone?.value) d.push(`Часовой пояс: ${c.timezone.value}`);
      if (c.languages?.value) {
        const l = Array.isArray(c.languages.value) ? c.languages.value.slice(0, 3).join(', ') : c.languages.value;
        d.push(`Языки: ${l}`);
      }
      if (c.hardwareConcurrency?.value) d.push(`Ядер CPU: ${c.hardwareConcurrency.value}`);
      if (c.colorDepth?.value) d.push(`Глубина цвета: ${c.colorDepth.value}-bit`);
      if (c.deviceMemory?.value) d.push(`Память устройства: ${c.deviceMemory.value} GB`);
      if (c.touchSupport?.value) d.push(`Тачскрин: ${c.touchSupport.value.maxTouchPoints > 0 ? 'да' : 'нет'}`);
      browserDetails = d;
    } catch (e) {
      browserError = e.message || 'Не удалось получить отпечаток';
    } finally {
      browserLoading = false;
    }
  }

  // ============================================================
  // РАЗДЕЛ 2: Утечки
  // ============================================================
  let leakResult = $state(null);
  let leakVerdict = $state(null);
  let leakLoading = $state(false);
  let leakError = $state(null);

  async function checkWebRTC() {
    return new Promise((resolve) => {
      const ips = new Set();
      let resolved = false;
      let pc;
      try {
        pc = new RTCPeerConnection({ iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] });
      } catch (e) {
        resolve({ error: e.message, ips: [] });
        return;
      }
      pc.createDataChannel('');
      pc.onicecandidate = (e) => {
        if (!e.candidate) {
          if (!resolved) {
            resolved = true;
            try { pc.close(); } catch {}
            resolve({ ips: [...ips] });
          }
          return;
        }
        const m = e.candidate.candidate.match(/(\d+\.\d+\.\d+\.\d+)/);
        if (m) {
          const ip = m[1];
          const isPrivate =
            ip.startsWith('192.168.') ||
            ip.startsWith('10.') ||
            /^172\.(1[6-9]|2[0-9]|3[01])\./.test(ip) ||
            ip.startsWith('127.');
          if (!isPrivate) ips.add(ip);
        }
      };
      pc.createOffer().then((o) => pc.setLocalDescription(o)).catch((e) => {
        if (!resolved) { resolved = true; resolve({ error: e.message, ips: [] }); }
      });
      setTimeout(() => {
        if (!resolved) {
          resolved = true;
          try { pc.close(); } catch {}
          resolve({ ips: [...ips], timeout: true });
        }
      }, 5000);
    });
  }

  async function checkDNS() {
    try {
      const r = await fetch('https://edns.ip-api.com/json', { cache: 'no-store' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      return { resolverIp: j.dns?.ip || null, resolverGeo: j.dns?.geo || null };
    } catch (e) {
      return { error: e.message };
    }
  }

  async function checkLeaks() {
    leakLoading = true;
    leakError = null;
    leakResult = null;
    leakVerdict = null;
    try {
      const [webrtc, dns] = await Promise.all([checkWebRTC(), checkDNS()]);
      leakResult = { webrtc, dns };

      const webrtcLeaks = webrtc.ips && webrtc.ips.length > 0;
      const dnsV = dnsVerdict(dns.resolverIp);

      if (webrtcLeaks || dnsV.level === 'red') {
        leakVerdict = {
          level: 'red',
          reason: webrtcLeaks ? 'WebRTC выдаёт ваш реальный IP' : 'DNS идёт мимо VPN',
        };
      } else if (dnsV.level === 'yellow') {
        leakVerdict = { level: 'yellow', reason: 'DNS идёт через публичный сервис' };
      } else {
        leakVerdict = { level: 'green', reason: 'Утечек не обнаружено' };
      }
    } catch (e) {
      leakError = e.message || 'Ошибка проверки';
    } finally {
      leakLoading = false;
    }
  }

  // ============================================================
  // РАЗДЕЛ 3: MITM
  // ============================================================
  const TLS_API = 'https://ulysses.best:9443/api/fingerprint';
  const LS_BASELINE = 'ulysses_tls_baseline';
  const LS_CURRENT = 'ulysses_tls_current';

  // Загрузка из localStorage при старте
  function loadTlsState() {
    try {
      const b = localStorage.getItem(LS_BASELINE);
      if (b) tlsBaseline = JSON.parse(b);
      const c = localStorage.getItem(LS_CURRENT);
      if (c) tlsCurrent = JSON.parse(c);
      recomputeVerdict();
    } catch {}
  }

  function saveBaseline(snap) {
    tlsBaseline = snap;
    try { localStorage.setItem(LS_BASELINE, JSON.stringify(snap)); } catch {}
  }
  function saveCurrent(snap) {
    tlsCurrent = snap;
    try { localStorage.setItem(LS_CURRENT, JSON.stringify(snap)); } catch {}
  }

  let tlsBaseline = $state(null);
  let tlsCurrent = $state(null);
  let tlsVerdict = $state(null);
  let tlsLoading = $state(false);
  let tlsError = $state(null);


  function recomputeVerdict() {
    if (!tlsBaseline || !tlsCurrent) {
      tlsVerdict = null;
      return;
    }

    const ipChanged = tlsBaseline.ip !== tlsCurrent.ip;
    const ja3Changed = tlsBaseline.ja3_hash !== tlsCurrent.ja3_hash;
    const ja4Changed = tlsBaseline.ja4 !== tlsCurrent.ja4;

    // Сначала проверяем IP. Если он не изменился — значит VPN не работает,
    // и сравнение JA3/JA4 бессмысленно (шум от session resumption).
    if (!ipChanged) {
      tlsVerdict = {
        level: 'yellow',
        reason: 'Проверка недействительна — IP не изменился',
      };
      return;
    }

    // IP изменился, VPN работает. Теперь смотрим на TLS.
    if (ja3Changed || ja4Changed) {
      tlsVerdict = {
        level: 'red',
        reason: 'VPN расшифровывает трафик (MITM)',
      };
    } else {
      tlsVerdict = {
        level: 'green',
        reason: 'VPN безопасен — TLS не меняется',
      };
    }
  }


  async function fetchTlsSnapshot() {
    const res = await fetch(TLS_API, { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return {
      ip: data.ip || '—',
      ja3_hash: data.ja3_hash || '—',
      ja4: data.ja4 || '—',
      timestamp: Date.now(),
    };
  }

  async function checkNoVpn() {
    tlsLoading = true;
    tlsError = null;
    try {
      const snap = await fetchTlsSnapshot();
      saveBaseline(snap);
      // При новой baseline сбрасываем current, чтобы не было путаницы
      try { localStorage.removeItem(LS_CURRENT); } catch {}
      tlsCurrent = null;
      recomputeVerdict();
    } catch (e) {
      tlsError = e.message || 'Не удалось получить данные';
    } finally {
      tlsLoading = false;
    }
  }

  async function checkWithVpn() {
    tlsLoading = true;
    tlsError = null;
    try {
      const snap = await fetchTlsSnapshot();
      saveCurrent(snap);
      recomputeVerdict();
    } catch (e) {
      tlsError = e.message || 'Не удалось получить данные';
    } finally {
      tlsLoading = false;
    }
  }

  function resetTls() {
    tlsBaseline = null;
    tlsCurrent = null;
    tlsVerdict = null;
    tlsError = null;
    try {
      localStorage.removeItem(LS_BASELINE);
      localStorage.removeItem(LS_CURRENT);
    } catch {}
  }

  // Загружаем состояние при монтировании
  import { onMount } from 'svelte';
  onMount(() => {
    loadTlsState();
  });

  // ============================================================
  // UI-хелперы
  // ============================================================
  function levelDot(level) {
    if (level === 'green') return 'bg-green-500 shadow-[0_0_12px_rgba(34,197,94,0.8)]';
    if (level === 'yellow') return 'bg-yellow-500 shadow-[0_0_12px_rgba(234,179,8,0.8)]';
    return 'bg-red-500 shadow-[0_0_12px_rgba(239,68,68,0.8)]';
  }
  function levelText(level) {
    if (level === 'green') return 'text-green-400';
    if (level === 'yellow') return 'text-yellow-300';
    return 'text-red-400';
  }
  function levelBg(level) {
    if (level === 'green') return 'bg-green-500/10 border-green-500/30';
    if (level === 'yellow') return 'bg-yellow-500/10 border-yellow-500/30';
    return 'bg-red-500/10 border-red-500/30';
  }
</script>

<svelte:head>
  <title>Проверка приватности — Ulysses</title>
</svelte:head>

<div class="min-h-screen bg-slate-950 text-slate-200 py-12 px-4">
  <div class="max-w-3xl mx-auto">

    <div class="mb-12">
      <h1 class="text-4xl font-bold text-white mb-3">Проверка приватности</h1>
      <p class="text-slate-400 text-lg">Что о вас знают сайты и ваш VPN</p>
    </div>

    <!-- ============================================ -->
    <!-- РАЗДЕЛ 1: Браузер                            -->
    <!-- ============================================ -->
    <section class="bg-slate-900 rounded-2xl p-8 mb-8 border border-slate-800">
      <h2 class="text-2xl font-semibold text-white mb-2">1. Что сайты знают о вашем браузере</h2>
      <p class="text-slate-400 mb-6 text-sm">
        Каждый раз, когда вы заходите на сайт, браузер передаёт десятки параметров.
        Их комбинация уникальна — как отпечаток пальца.
      </p>

      <button onclick={checkBrowser} disabled={browserLoading}
        class="bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:cursor-not-allowed text-white font-medium px-6 py-3 rounded-xl transition">
        {browserLoading ? 'Проверяю...' : 'Проверить браузер'}
      </button>

      {#if browserError}
        <div class="mt-6 bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400 text-sm">⚠️ {browserError}</div>
      {/if}

      {#if browser}
        <div class="mt-6 bg-slate-800 rounded-xl p-5">
          <div class="text-xs text-slate-500 uppercase tracking-wide mb-2">Ваш браузер</div>
          <div class="text-2xl font-semibold text-white">{browser.name} {browser.version}</div>
          <div class="text-sm text-slate-400 mt-1">{browser.os} · движок {browser.engine} · {browser.platform}</div>
        </div>

        {#if browserDetails.length}
          <div class="mt-4 bg-slate-800 rounded-xl p-5">
            <div class="text-xs text-slate-500 uppercase tracking-wide mb-3">Что вас выдаёт</div>
            <ul class="space-y-1.5 text-sm">
              {#each browserDetails as d}<li class="text-slate-300">• {d}</li>{/each}
            </ul>
          </div>
        {/if}
      {/if}

      {#if browserVerdict}
        <!-- ВЕРДИКТ: одна строка -->
        <div class="mt-6 flex items-center gap-3">
          <div class="w-5 h-5 rounded-full {levelDot(browserVerdict.level)} flex-shrink-0"></div>
          <div class="text-lg font-semibold {levelText(browserVerdict.level)}">
            {browserVerdict.reason}
          </div>
        </div>

        <!-- ЛЕГЕНДА: в рамке, мелким шрифтом -->
        <div class="mt-3 p-4 rounded-xl border border-slate-800 bg-slate-950/60 text-[11px] leading-relaxed text-slate-500 space-y-1">
          <div><span class="text-green-500">🟢</span> Tor, Mullvad, Firefox с FPP — защита от отпечатка</div>
          <div><span class="text-yellow-500">🟡</span> Brave, Firefox с частичной защитой — частичная защита</div>
          <div><span class="text-red-500">🔴</span> Chrome, Firefox без защиты — полный отпечаток</div>
        </div>
      {/if}



      <div class="mt-6 pt-6 border-t border-slate-800">
        <a href="/junglebook/fingerprint" class="text-blue-400 hover:text-blue-300 text-sm">📖 Что это значит и как это исправить →</a>
      </div>
    </section>

    <!-- ============================================ -->
    <!-- РАЗДЕЛ 2: Утечки                              -->
    <!-- ============================================ -->
    <section class="bg-slate-900 rounded-2xl p-8 mb-8 border border-slate-800">
      <h2 class="text-2xl font-semibold text-white mb-2">2. Утечки вашего реального IP</h2>
      <p class="text-slate-400 mb-6 text-sm">
        Даже при включённом VPN ваш реальный IP может утечь через WebRTC или DNS.
      </p>

      <button onclick={checkLeaks} disabled={leakLoading}
        class="bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:cursor-not-allowed text-white font-medium px-6 py-3 rounded-xl transition">
        {leakLoading ? 'Проверяю...' : 'Проверить утечки'}
      </button>

      {#if leakError}
        <div class="mt-6 bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400 text-sm">⚠️ {leakError}</div>
      {/if}

      {#if leakResult}
        <div class="mt-6 space-y-3">
          <div class="bg-slate-800 rounded-xl p-5">
            <div class="text-xs text-slate-500 uppercase tracking-wide mb-2">WebRTC</div>
            {#if leakResult.webrtc.error}
              <div class="text-sm text-yellow-400">⚠️ {leakResult.webrtc.error}</div>
            {:else if leakResult.webrtc.ips.length > 0}
              <div class="text-red-400 text-sm font-medium mb-2">🔴 Публичный IP: {leakResult.webrtc.ips.join(', ')}</div>
            {:else}
              <div class="text-green-400 text-sm">✅ Публичный IP не утекает</div>
            {/if}
          </div>

          <div class="bg-slate-800 rounded-xl p-5">
            <div class="text-xs text-slate-500 uppercase tracking-wide mb-2">DNS-резолвер</div>
            {#if leakResult.dns.error}
              <div class="text-sm text-yellow-400">⚠️ {leakResult.dns.error}</div>
            {:else}
              <div class="text-sm font-mono text-slate-300">{leakResult.dns.resolverIp || '—'}</div>
              {#if leakResult.dns.resolverGeo}
                <div class="text-xs text-slate-400 mt-1">{leakResult.dns.resolverGeo}</div>
              {/if}
            {/if}
          </div>
        </div>
      {/if}

      {#if leakVerdict}
        <!-- ВЕРДИКТ: одна строка -->
        <div class="mt-6 flex items-center gap-3">
          <div class="w-5 h-5 rounded-full {levelDot(leakVerdict.level)} flex-shrink-0"></div>
          <div class="text-lg font-semibold {levelText(leakVerdict.level)}">
            {leakVerdict.reason}
          </div>
        </div>

        <!-- ЛЕГЕНДА: в рамке -->
        <div class="mt-3 p-4 rounded-xl border border-slate-800 bg-slate-950/60 text-[11px] leading-relaxed text-slate-500 space-y-1">
          <div><span class="text-green-500">🟢</span> Утечек нет — DNS через VPN или no-log resolver</div>
          <div><span class="text-yellow-500">🟡</span> DNS через публичный сервис (Cloudflare, Google)</div>
          <div><span class="text-red-500">🔴</span> WebRTC выдаёт IP или DNS через провайдера</div>
        </div>
      {/if}


      <div class="mt-6 pt-6 border-t border-slate-800">
        <a href="/junglebook/leaks" class="text-blue-400 hover:text-blue-300 text-sm">📖 Что такое утечки IP и DNS →</a>
      </div>
    </section>

    <!-- ============================================ -->
    <!-- РАЗДЕЛ 3: MITM                               -->
    <!-- ============================================ -->
    <section class="bg-slate-900 rounded-2xl p-8 mb-8 border border-slate-800">
      <h2 class="text-2xl font-semibold text-white mb-2">3. Проверка VPN на подмену TLS</h2>
      <p class="text-slate-400 mb-6 text-sm">
        Некоторые VPN расшифровывают ваш трафик — это MITM (Man in The Middle). Такой VPN видит все ваши пароли и данные.
      </p>

<div class="bg-slate-800/50 rounded-xl p-5 mb-6 text-sm">
  <div class="text-slate-400 mb-3 font-medium">Порядок действий:</div>
  <ol class="space-y-2 text-slate-300">
    <li class="flex gap-2"><span class="text-blue-400">1.</span> Выключите VPN</li>
    <li class="flex gap-2"><span class="text-blue-400">2.</span> Нажмите «① Проверить БЕЗ VPN»</li>
    <li class="flex gap-2"><span class="text-blue-400">3.</span> Включите VPN</li>
    <li class="flex gap-2"><span class="text-blue-400">4.</span> Нажмите «② Проверить С VPN»</li>
  </ol>

  <details class="mt-4 text-xs text-slate-500">
    <summary class="cursor-pointer text-slate-400 hover:text-slate-300">
      ⚙️ Если VPN работает в режиме прокси (не TUN)
    </summary>
    <div class="mt-3 space-y-2 leading-relaxed pl-1">
      <p>В режиме прокси браузер сам направляет трафик через VPN. Для проверки:</p>
      <ol class="ml-4 space-y-1 list-decimal">
        <li>Отключите прокси в настройках браузера</li>
        <li>Нажмите «① Проверить БЕЗ VPN»</li>
        <li>Включите прокси обратно</li>
        <li>Нажмите «② Проверить С VPN»</li>
      </ol>
      <p class="text-slate-600 mt-2">
        💡 В режиме TUN (Hiddify App, sing-box, Clash) проверка работает
        автоматически — просто включайте и выключайте VPN.
      </p>
    </div>
  </details>
</div>


      <div class="flex flex-wrap gap-3">
        <button onclick={checkNoVpn} disabled={tlsLoading}
          class="bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:cursor-not-allowed text-white font-medium px-6 py-3 rounded-xl transition">
          {tlsLoading ? 'Проверяю...' : '① Проверить БЕЗ VPN'}
        </button>
        <button onclick={checkWithVpn} disabled={tlsLoading}
          class="bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:cursor-not-allowed text-white font-medium px-6 py-3 rounded-xl transition">
          {tlsLoading ? '...' : '② Проверить С VPN'}
        </button>
        <button onclick={resetTls} disabled={tlsLoading || (!tlsBaseline && !tlsCurrent)}
          class="bg-slate-800 hover:bg-slate-700 disabled:bg-slate-900 disabled:text-slate-600 disabled:cursor-not-allowed text-slate-400 hover:text-slate-200 font-medium px-6 py-3 rounded-xl transition">
          ✕ Очистить
        </button>
      </div>


      {#if tlsBaseline && tlsCurrent && tlsBaseline.ip === tlsCurrent.ip}
        <div class="mt-4 p-4 rounded-xl bg-yellow-500/10 border border-yellow-500/30 text-yellow-200 text-sm">
          ⚠️ <strong>IP не изменился.</strong> Похоже, между двумя проверками VPN не был включён.
          Нажмите «✕ Очистить» и пройдите проверку заново:
          <div class="mt-2 text-xs opacity-90">
            ① выключите VPN → нажмите «Проверить БЕЗ VPN» → ② включите VPN → нажмите «Проверить С VPN»
          </div>
        </div>
      {/if}


      {#if tlsError}
        <div class="mt-6 bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400 text-sm">⚠️ {tlsError}</div>
      {/if}

      {#if tlsBaseline}
        <div class="mt-6 bg-slate-800 rounded-xl p-5">
          <div class="text-xs text-slate-500 uppercase tracking-wide mb-3">
            ① Без VPN {#if tlsCurrent}<span class="text-slate-600">— сохранено</span>{/if}
          </div>
          <div class="grid grid-cols-[80px_1fr] gap-y-2 text-sm font-mono">
            <div class="text-slate-500">IP:</div><div class="text-slate-300">{tlsBaseline.ip}</div>
            <div class="text-slate-500">JA3:</div><div class="text-slate-300 truncate">{tlsBaseline.ja3_hash}</div>
            <div class="text-slate-500">JA4:</div><div class="text-slate-300 truncate">{tlsBaseline.ja4}</div>
          </div>
        </div>
      {/if}

      {#if tlsCurrent}
        <div class="mt-4 bg-slate-800 rounded-xl p-5">
          <div class="text-xs text-slate-500 uppercase tracking-wide mb-3">② С VPN</div>
          <div class="grid grid-cols-[80px_1fr] gap-y-2 text-sm font-mono">
            <div class="text-slate-500">IP:</div>
            <div class={tlsBaseline.ip !== tlsCurrent.ip ? 'text-green-400' : 'text-slate-300'}>{tlsCurrent.ip}</div>
            <div class="text-slate-500">JA3:</div>
            <div class={tlsBaseline.ja3_hash !== tlsCurrent.ja3_hash ? 'text-red-400' : 'text-green-400'}>{tlsCurrent.ja3_hash}</div>
            <div class="text-slate-500">JA4:</div>
            <div class={tlsBaseline.ja4 !== tlsCurrent.ja4 ? 'text-red-400' : 'text-green-400'}>{tlsCurrent.ja4}</div>
          </div>
        </div>

        <button onclick={resetTls} class="mt-6 text-slate-500 hover:text-slate-300 text-sm">
          ↻ Сбросить и проверить заново
        </button>
      {/if}


      {#if tlsVerdict}
        <!-- ВЕРДИКТ: одна строка -->
        <div class="mt-6 flex items-center gap-3">
          <div class="w-5 h-5 rounded-full {levelDot(tlsVerdict.level)} flex-shrink-0"></div>
          <div class="text-lg font-semibold {levelText(tlsVerdict.level)}">
            {tlsVerdict.reason}
          </div>
        </div>

        <!-- ЛЕГЕНДА: в рамке -->
        <div class="mt-3 p-4 rounded-xl border border-slate-800 bg-slate-950/60 text-[11px] leading-relaxed text-slate-500 space-y-1">
          <div><span class="text-green-500">🟢</span> IP изменился, JA3 не меняется — VPN безопасен</div>
          <div><span class="text-yellow-500">🟡</span> IP не изменился — VPN не работает или не был включён между проверками</div>
          <div><span class="text-red-500">🔴</span> IP изменился, но JA3 тоже изменился — VPN расшифровывает трафик</div>
        </div>
      {/if}

      <div class="mt-6 pt-6 border-t border-slate-800">
        <a href="/junglebook/mitm-risks" class="text-blue-400 hover:text-blue-300 text-sm">📖 Как читать результат и почему это важно →</a>
      </div>
    </section>

    <div class="text-center pt-4">
      <a href="https://t.me/ulysses_vpn_bot" target="_blank" rel="noopener"
         class="inline-block bg-blue-600 hover:bg-blue-500 text-white font-medium px-8 py-4 rounded-xl transition">
        Подключиться к Ulysses
      </a>
    </div>

  </div>
</div>
