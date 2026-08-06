import { redirect } from '@sveltejs/kit';
import { isValidSession } from '$lib/server/auth';

/** @type {import('@sveltejs/kit').Handle} */
export async function handle({ event, resolve }) {
  // Защита маршрутов админки
  if (event.url.pathname.startsWith('/admin')) {
    const token = event.cookies.get('session');
    const isAuthenticated = isValidSession(token);

    // Если не админ и путь не корень админки (чтобы дать странице логина загрузиться),
    // то редиректим на /admin для входа.
    // Исключаем сам /admin и /admin/ (страница логина)
    if (!isAuthenticated && event.url.pathname !== '/admin') {
      throw redirect(303, '/admin');
    }

    // Если запрос к /admin, просто отдаём страницу (она сама проверит сессию)
  }

  const response = await resolve(event);
  return response;
}
