import { env } from '$env/dynamic/private';

// Простая проверка пароля и создание токена
export function authenticate(password) {
  // Читаем пароль динамически из системного окружения
  const securePassword = env.ADMIN_PASSWORD;

  if (password === securePassword) {
    return 'authenticated_session_active';
  }
  return null;
}

// Проверка валидности сессии
export function isValidSession(token) {
  return token === 'authenticated_session_active';
}
