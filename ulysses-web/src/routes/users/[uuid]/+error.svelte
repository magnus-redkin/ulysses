<script>
    import { page } from '$app/stores';
    import { locale } from '$lib/locale.svelte.js';
</script>

<div class="min-h-screen bg-gray-950 flex items-center justify-center">
    <div class="text-center">
        <h1 class="text-4xl font-bold text-red-400 mb-4">
            {$page.status}
        </h1>
        <p class="text-gray-400 mb-8">
            {$page.error?.message || (locale.current === 'ru' ? 'Пользователь не найден' : 'User not found')}
        </p>
        <a href="/" class="text-emerald-400 hover:text-emerald-300 underline">
            {locale.current === 'ru' ? '← Вернуться на главную' : '← Back to home'}
        </a>
    </div>
</div>
