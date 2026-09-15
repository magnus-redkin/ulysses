<svelte:head>
  <title>Оплата не прошла — Ulysses</title>
</svelte:head>

<div class="payment-result">
  <div class="icon">❌</div>
  <h1>Оплата не прошла</h1>
  <p>
    Платёж отменён или отклонён. Вернитесь в Telegram-бота и попробуйте снова —
    можно выбрать другой способ оплаты.
  </p>
  <a class="btn" href="https://t.me/ulysses_vpn_bot" target="_blank" rel="noopener">
    Вернуться в бота
  </a>
</div>

<style>
  .payment-result {
    max-width: 480px;
    margin: 10vh auto;
    padding: 32px 24px;
    text-align: center;
    font-family: system-ui, -apple-system, sans-serif;
    color: #e8eaf0;
    background: #1a1d24;
    border-radius: 16px;
  }
  .icon { font-size: 56px; margin-bottom: 8px; }
  h1 { margin: 0 0 12px; font-size: 24px; }
  p { color: #9aa3b2; line-height: 1.5; margin-bottom: 24px; }
  .btn {
    display: inline-block;
    padding: 12px 24px;
    background: #4f7cff;
    color: #fff;
    border-radius: 10px;
    text-decoration: none;
    font-weight: 600;
  }
  .btn:hover { background: #3d68e0; }
</style>
