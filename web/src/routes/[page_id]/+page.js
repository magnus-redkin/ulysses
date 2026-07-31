import { error } from '@sveltejs/kit';

export function load({ params }) {
  // Список разрешенных страниц, которые лежат в $lib/content/
  const allowedPages = ['offer', 'privacy', 'contacts'];

  if (!allowedPages.includes(params.page_id)) {
    // Если id страницы нет в списке, отдаем честный 404
    error(404, 'Not Found');
  }

  return {
    pageId: params.page_id
  };
}
