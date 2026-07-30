// src/hooks.server.js
export function handleError({ error }) {
  // Проверяем, является ли ошибка 404 (Not Found)
  if (error.message && error.message.includes('Not found')) {
    return {
      message: '' // Возвращаем пустую строку или кастомный текст, чтобы подавить лог
    };
  }

  // Для всех остальных ошибок используем стандартное поведение SvelteKit
  return {
    message: 'Internal Error'
  };
}
