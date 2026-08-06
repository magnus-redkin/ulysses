import crypto from 'crypto';

// In-memory хранилище сессий: ключ — токен, значение — { createdAt: Date }
const sessions = new Map();

// Время жизни сессии (24 часа)
const SESSION_TTL_MS = 24 * 60 * 60 * 1000;

/**
 * Проверяет пароль и создаёт сессию.
 * @param {string} password - введённый пароль
 * @returns {string|null} токен сессии или null при неверном пароле
 */
export function authenticate(password) {
  const securePassword = process.env.ADMIN_PASSWORD;
  if (!securePassword) {
    console.error('ADMIN_PASSWORD is not set in environment');
    return null;
  }

  if (password === securePassword) {
    const token = crypto.randomUUID();
    sessions.set(token, { createdAt: Date.now() });
    return token;
  }
  return null;
}

/**
 * Проверяет, действителен ли токен сессии.
 * @param {string} token
 * @returns {boolean}
 */
export function isValidSession(token) {
  if (!token) return false;
  const session = sessions.get(token);
  if (!session) return false;

  const age = Date.now() - session.createdAt;
  if (age > SESSION_TTL_MS) {
    // Токен истёк — удаляем
    sessions.delete(token);
    return false;
  }
  return true;
}

/**
 * Удаляет сессию (logout).
 * @param {string} token
 */
export function destroySession(token) {
  if (token) {
    sessions.delete(token);
  }
}

/**
 * Проверяет API-ключ для межсервисных запросов (бот -> веб).
 * @param {Request} request - объект запроса SvelteKit
 * @returns {boolean}
 */
export function verifyApiKey(request) {
  const apiKey = request.headers.get('X-API-Key');
  const expectedKey = process.env.HOST_API_KEY;
  if (!expectedKey) {
    console.error('HOST_API_KEY is not set in environment');
    return false;
  }
  return apiKey === expectedKey;
}
