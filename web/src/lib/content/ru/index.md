---
title: "index"
---

# Независимый аудит смарт-контрактов

Выявляем уязвимости, скрытые механизмы и признаки мошенничества в смарт-контрактах до их публичного запуска. Снижаем риски для инвесторов и сообществ.

**Что входит в аудит:**
- Статический и динамический анализ кода
- Поиск уязвимостей (reentrancy, access control, overflow и др.)
- Проверка токеномики и скрытых привилегий
- Fuzzing и симуляция атак
- Понятный отчёт с приоритетами исправлений

## Примеры отчётов

<div class="examples-grid">

<div class="example-card">
<h3>TokenX — ERC-20</h3>
<p>Аудит стандартного токена. Выявлен риск неограниченной эмиссии, исправлен до деплоя. Контракт признан безопасным.</p>
<div class="example-links">
<a href="/examples/TokenX_Public.pdf" class="btn btn-primary" target="_blank">📄 Публичный отчёт (PDF)</a>
<a href="/examples/TokenX_Internal.pdf" class="btn btn-secondary" target="_blank">🔒 Внутренний отчёт (PDF)</a>
</div>
</div>

<div class="example-card">
<h3>DeFi-Yield-Y — Yield Farming / Staking</h3>
<p>Комплексный аудит 4 контрактов. Обнаружены реентранси и манипуляция оракулом — исправлены. Централизованная функция принята с условием миграции на multisig.</p>
<div class="example-links">
<a href="/examples/DeFiYieldY_Public.pdf" class="btn btn-primary" target="_blank">📄 Публичный отчёт (PDF)</a>
<a href="/examples/DeFiYieldY_Internal.pdf" class="btn btn-secondary" target="_blank">🔒 Внутренний отчёт (PDF)</a>
</div>
</div>

</div>

<style>
.examples-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1.5rem;
  margin-top: 2rem;
}
.example-card {
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  padding: 1.5rem;
  background: rgba(255, 255, 255, 0.05);
}
.example-card h3 {
  margin-top: 0;
  margin-bottom: 0.5rem;
}
.example-card p {
  margin-bottom: 1rem;
  opacity: 0.8;
}
.example-links {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}
</style>
