<script>
  import { locale } from '$lib/locale.svelte.js';

  // Получаем pageId из роутера
  let { data } = $props();

  // 1. Говорим Vite заранее просканировать папку content на наличие всех .md файлов.
  // Флаг { eager: true } заставит Vite сразу загрузить их компоненты в карту памяти.
  const modules = import.meta.glob('/src/lib/content/**/*.md', { eager: true });

  // 2. Пишем простую, чистую синхронную функцию для поиска нужного markdown-компонента.
  // Svelte 5 автоматически перезапустит эту функцию, если изменятся locale.current или data.pageId.
  function getMarkdownComponent(currentLocale, pageId) {
    // Формируем точный ключ, который Vite гарантированно найдет в своей карте модулей
    const targetPath = `/src/lib/content/${currentLocale}/${pageId}.md`;

    // Возвращаем дефолтный экспорт (.default), который и является готовым Svelte-компонентом из Markdown
    return modules[targetPath]?.default || null;
  }

  // 3. Создаем реактивную переменную для текущего компонента
  let ContentComponent = $derived(getMarkdownComponent(locale.current, data.pageId));
</script>

{#if ContentComponent}
  <article class="prose prose-invert max-w-none py-8">
    <!-- Рендерим динамический компонент стандартным для Svelte 5 способом -->
    <ContentComponent />
  </article>
{:else}
  <div class="text-slate-400 py-12 text-center bg-slate-800/30 border border-slate-800 rounded-lg">
    Документ [{data.pageId}] не найден для локали [{locale.current}].
    <br />
    <span class="text-xs text-slate-600 font-mono">Проверьте наличие файла: /src/lib/content/{locale.current}/{data.pageId}.md</span>
  </div>
{/if}
