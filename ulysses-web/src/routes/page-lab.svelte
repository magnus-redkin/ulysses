<script>
  import { locale } from '$lib/locale.svelte.js';
  import { page } from '$app/stores';
</script>

<main class="p-6 border rounded-xl shadow-sm mt-4">
  <article class="prose max-w-none text-white">

    {#if locale.current === 'ru'}
      <h1>Независимый аудит смарт-контрактов</h1>

      <p class="text-lg opacity-80 mt-4">
        Выявляем уязвимости, скрытые механизмы и признаки мошенничества в смарт-контрактах
        до их публичного запуска. Снижаем риски для инвесторов и сообществ.
      </p>

      <h2 class="mt-8">Что входит в аудит:</h2>
      <ul class="list-disc list-inside space-y-1 mt-2 opacity-80">
        <li>Статический и динамический анализ кода</li>
        <li>Поиск уязвимостей (reentrancy, access control, overflow и др.)</li>
        <li>Проверка токеномики и скрытых привилегий</li>
        <li>Fuzzing и симуляция атак</li>
        <li>Понятный отчёт с приоритетами исправлений</li>
      </ul>

      <h2 class="mt-8">Примеры отчётов</h2>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mt-4">
        <!-- TokenX -->
        <div class="border border-white/10 rounded-lg p-6 bg-white/5">
          <h3 class="text-xl font-semibold">TokenX — ERC-20</h3>
          <p class="mt-2 opacity-80">
            Аудит стандартного токена. Выявлен риск неограниченной эмиссии,
            исправлен до деплоя. Контракт признан безопасным.
          </p>
          <p>&nbsp;</p>
          <div class="flex flex-wrap gap-3 mt-4">
            <a href="/examples/TokenX_Public.pdf" target="_blank"
               class="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition-colors">
              📄 Публичный отчёт (PDF)
            </a>
            <a href="/examples/TokenX_Internal.pdf" target="_blank"
               class="inline-flex items-center gap-2 px-4 py-2 bg-gray-600 hover:bg-gray-700 rounded-lg text-sm font-medium transition-colors">
              🔒 Внутренний отчёт (PDF)
            </a>
          </div>
        </div>

        <!-- DeFi-Yield-Y -->
        <div class="border border-white/10 rounded-lg p-6 bg-white/5">
          <h3 class="text-xl font-semibold">DeFi-Yield-Y — Yield Farming / Staking</h3>
          <p class="mt-2 opacity-80">
            Комплексный аудит 4 контрактов. Обнаружены реентранси и манипуляция
            оракулом — исправлены. Централизованная функция принята с условием
            миграции на multisig.
          </p>
          <div class="flex flex-wrap gap-3 mt-4">
            <a href="/examples/DeFiYieldY_Public.pdf" target="_blank"
               class="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition-colors">
              📄 Публичный отчёт (PDF)
            </a>
            <a href="/examples/DeFiYieldY_Internal.pdf" target="_blank"
               class="inline-flex items-center gap-2 px-4 py-2 bg-gray-600 hover:bg-gray-700 rounded-lg text-sm font-medium transition-colors">
              🔒 Внутренний отчёт (PDF)
            </a>
          </div>
        </div>
      </div>

    {:else}
      <h1>Independent Smart Contract Audits</h1>

      <p class="text-lg opacity-80 mt-4">
        We identify vulnerabilities, hidden mechanisms, and scam patterns in smart contracts
        before public launch. We reduce risks for investors and communities.
      </p>

      <h2 class="mt-8">What the audit includes:</h2>
      <ul class="list-disc list-inside space-y-1 mt-2 opacity-80">
        <li>Static and dynamic code analysis</li>
        <li>Vulnerability detection (reentrancy, access control, overflow, etc.)</li>
        <li>Tokenomics and hidden privilege checks</li>
        <li>Fuzzing and attack simulation</li>
        <li>Clear report with fix priorities</li>
      </ul>

      <h2 class="mt-8">Report Examples</h2>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mt-4">
        <!-- TokenX -->
        <div class="border border-white/10 rounded-lg p-6 bg-white/5">
          <h3 class="text-xl font-semibold">TokenX — ERC-20</h3>
          <p class="mt-2 opacity-80">
            Standard token audit. Unlimited minting risk identified and fixed
            before deployment. Contract deemed safe for launch.
          </p>
          <div class="flex flex-wrap gap-3 mt-4">
            <a href="/examples/TokenX_Public.pdf" target="_blank"
               class="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition-colors">
              📄 Public Report (PDF)
            </a>
            <a href="/examples/TokenX_Internal.pdf" target="_blank"
               class="inline-flex items-center gap-2 px-4 py-2 bg-gray-600 hover:bg-gray-700 rounded-lg text-sm font-medium transition-colors">
              🔒 Internal Report (PDF)
            </a>
          </div>
        </div>

        <!-- DeFi-Yield-Y -->
        <div class="border border-white/10 rounded-lg p-6 bg-white/5">
          <h3 class="text-xl font-semibold">DeFi-Yield-Y — Yield Farming / Staking</h3>
          <p class="mt-2 opacity-80">
            Comprehensive audit of 4 contracts. Reentrancy and oracle manipulation
            found and fixed. Centralized function accepted with condition to
            migrate to multisig.
          </p>
          <div class="flex flex-wrap gap-3 mt-4">
            <a href="/examples/DeFiYieldY_Public.pdf" target="_blank"
               class="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition-colors">
              📄 Public Report (PDF)
            </a>
            <a href="/examples/DeFiYieldY_Internal.pdf" target="_blank"
               class="inline-flex items-center gap-2 px-4 py-2 bg-gray-600 hover:bg-gray-700 rounded-lg text-sm font-medium transition-colors">
              🔒 Internal Report (PDF)
            </a>
          </div>
        </div>
      </div>
    {/if}

  </article>
</main>
