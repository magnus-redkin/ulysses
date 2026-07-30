<script>
    import { locale } from '$lib/locale.svelte.js';

    /** @type {import('./$types').PageData} */
    let { data } = $props();

    const t = $derived({
        title: locale.current === 'ru' ? 'Информация о подписке' : 'Subscription Info',
        email: locale.current === 'ru' ? 'Email' : 'Email',
        uuid: locale.current === 'ru' ? 'UUID' : 'UUID',
        status: locale.current === 'ru' ? 'Статус' : 'Status',
        active: locale.current === 'ru' ? 'Активна' : 'Active',
        disabled: locale.current === 'ru' ? 'Отключена' : 'Disabled',
        traffic: locale.current === 'ru' ? 'Трафик' : 'Traffic',
        used: locale.current === 'ru' ? 'Использовано' : 'Used',
        total: locale.current === 'ru' ? 'Всего' : 'Total',
        remaining: locale.current === 'ru' ? 'Осталось' : 'Remaining',
        daysLeft: locale.current === 'ru' ? 'Осталось дней' : 'Days left',
        days: locale.current === 'ru' ? 'дней' : 'days',
        gb: locale.current === 'ru' ? 'ГБ' : 'GB',
        progress: locale.current === 'ru' ? 'Прогресс' : 'Progress',
        backToHome: locale.current === 'ru' ? 'На главную' : 'Back to home'
    });

    // Форматирование чисел
    const formatNumber = (num) => {
        return typeof num === 'number' ? num.toLocaleString() : '0';
    };

    const formatGB = (gb) => {
        if (typeof gb !== 'number') return '0 GB';
        if (gb >= 1000) {
            return `${(gb / 1000).toFixed(2)} TB`;
        }
        return `${gb.toFixed(2)} GB`;
    };

    // Определение цвета для прогресс-бара
    const getProgressColor = (percent) => {
        if (percent >= 90) return 'bg-red-500';
        if (percent >= 75) return 'bg-amber-500';
        if (percent >= 50) return 'bg-yellow-500';
        return 'bg-emerald-500';
    };

    // Копирование UUID в буфер обмена
    const copyToClipboard = async (text) => {
        try {
            await navigator.clipboard.writeText(text);
            // Можно добавить уведомление
        } catch (err) {
            console.error('Failed to copy:', err);
        }
    };
</script>

<div class="min-h-screen bg-gray-950 text-white">
    <div class="max-w-2xl mx-auto px-4 py-8">

        <!-- Навигация -->
        <a href="/" class="inline-flex items-center text-gray-400 hover:text-white transition-colors mb-8">
            <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"/>
            </svg>
            {t.backToHome}
        </a>

        <h1 class="text-3xl font-bold text-center mb-8">{t.title}</h1>

        {#if data?.user}
            <div class="space-y-6">

                <!-- Статус подписки -->
                <div class="bg-gray-900 rounded-xl border border-gray-800 p-6">
                    <div class="flex items-center justify-between mb-4">
                        <h2 class="text-lg font-semibold text-gray-300">{t.status}</h2>
                        <span class="px-3 py-1 rounded-full text-sm font-medium
                            {data.user.status === 'active'
                                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                                : 'bg-red-500/20 text-red-400 border border-red-500/30'}">
                            {data.user.status === 'active' ? t.active : t.disabled}
                        </span>
                    </div>

                    <!-- Email -->
                    <div class="flex items-center justify-between py-3 border-t border-gray-800">
                        <span class="text-gray-400">{t.email}</span>
                        <span class="font-medium">{data.user.email || '—'}</span>
                    </div>

                    <!-- UUID с копированием -->
                    <div class="flex items-center justify-between py-3 border-t border-gray-800">
                        <span class="text-gray-400">{t.uuid}</span>
                        <div class="flex items-center gap-2">
                            <code class="text-sm bg-gray-800 px-2 py-1 rounded">{data.uuid}</code>
                            <button
                                onclick={() => copyToClipboard(data.uuid)}
                                class="text-gray-500 hover:text-gray-300 transition-colors"
                                title="Copy UUID"
                            >
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                        d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/>
                                </svg>
                            </button>
                        </div>
                    </div>

                    <!-- Дни -->
                    {#if data.user.days_left !== undefined}
                        <div class="flex items-center justify-between py-3 border-t border-gray-800">
                            <span class="text-gray-400">{t.daysLeft}</span>
                            <span class="font-medium text-lg
                                {data.user.days_left <= 7 ? 'text-red-400' : 'text-emerald-400'}">
                                {data.user.days_left} {t.days}
                            </span>
                        </div>
                    {/if}
                </div>

                <!-- Трафик -->
                {#if data.user.traffic}
                    <div class="bg-gray-900 rounded-xl border border-gray-800 p-6">
                        <h2 class="text-lg font-semibold text-gray-300 mb-4">{t.traffic}</h2>

                        <!-- Прогресс-бар -->
                        <div class="mb-6">
                            <div class="flex justify-between text-sm mb-2">
                                <span class="text-gray-400">{t.progress}</span>
                                <span class="font-medium">{data.user.traffic.percent}%</span>
                            </div>
                            <div class="w-full bg-gray-800 rounded-full h-3 overflow-hidden">
                                <div
                                    class="h-full rounded-full transition-all duration-500 {getProgressColor(data.user.traffic.percent)}"
                                    style="width: {Math.min(data.user.traffic.percent, 100)}%"
                                ></div>
                            </div>
                        </div>

                        <!-- Детали трафика -->
                        <div class="grid grid-cols-3 gap-4">
                            <div class="text-center p-3 bg-gray-800 rounded-lg">
                                <p class="text-xs text-gray-400 mb-1">{t.used}</p>
                                <p class="text-lg font-bold text-amber-400">
                                    {formatGB(data.user.traffic.used_gb)}
                                </p>
                            </div>
                            <div class="text-center p-3 bg-gray-800 rounded-lg">
                                <p class="text-xs text-gray-400 mb-1">{t.remaining}</p>
                                <p class="text-lg font-bold text-emerald-400">
                                    {formatGB(data.user.traffic.remaining_gb)}
                                </p>
                            </div>
                            <div class="text-center p-3 bg-gray-800 rounded-lg">
                                <p class="text-xs text-gray-400 mb-1">{t.total}</p>
                                <p class="text-lg font-bold text-blue-400">
                                    {formatGB(data.user.traffic.total_gb)}
                                </p>
                            </div>
                        </div>
                    </div>
                {/if}
            </div>
        {:else}
            <!-- Loading state -->
            <div class="text-center py-12">
                <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-500 mx-auto"></div>
                <p class="mt-4 text-gray-400">
                    {locale.current === 'ru' ? 'Загрузка...' : 'Loading...'}
                </p>
            </div>
        {/if}

        <!-- Ошибка -->
        {#if data?.error}
            <div class="bg-red-500/10 border border-red-500/30 rounded-xl p-6 text-center">
                <p class="text-red-400 text-lg">❌ {data.error}</p>
            </div>
        {/if}
    </div>
</div>
