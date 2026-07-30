<script>
    import { onMount, onDestroy } from 'svelte';
    import { browser } from '$app/environment';

    let {
        show = $bindable(),
        title = 'Информация',
        onClose,
        children
    } = $props();

    // Обработчик клавиши Escape
    function handleEscape(event) {
        if (event.key === 'Escape' && show) {
            onClose?.();
        }
    }

    onMount(() => {
        if (browser) {
            document.addEventListener('keydown', handleEscape);
            // Блокируем скролл страницы
            document.body.style.overflow = 'hidden';
        }
    });

    onDestroy(() => {
        if (browser) {
            document.removeEventListener('keydown', handleEscape);
            // Восстанавливаем скролл
            document.body.style.overflow = '';
        }
    });
</script>

{#if show}
    <div
        class="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4"
        onclick={() => onClose?.()}
    >
        <div
            class="bg-slate-900 border border-slate-700 rounded-2xl p-6 max-w-2xl w-full max-h-[80vh] overflow-y-auto shadow-2xl"
            onclick={(e) => e.stopPropagation()}
        >
            <!-- Заголовок -->
            <div class="flex justify-between items-center mb-4">
                <h3 class="text-lg font-bold text-white">{title}</h3>
                <button
                    onclick={() => onClose?.()}
                    class="text-slate-400 hover:text-white text-2xl leading-none transition-colors"
                >
                    ×
                </button>
            </div>

            <!-- Содержимое -->
            <div class="text-sm text-slate-300">
                {@render children?.()}
            </div>
        </div>
    </div>
{/if}
