import { fail, redirect } from '@sveltejs/kit'; // Убедитесь, что импортирован redirect
import { authenticate, isValidSession } from '$lib/server/auth';
import PouchDB from 'pouchdb';

const BOT_TOKEN = process.env.BOT_TOKEN;

const db = new PouchDB('.db_tickets');
const BACKEND_API_URL = process.env.BACKEND_API_URL || 'http://127.0.0.1:8000';

export async function load({ cookies }) {
    const sessionToken = cookies.get('session');

    if (!sessionToken || !isValidSession(sessionToken)) {
        return { authenticated: false };
    }

    try {
        const result = await db.allDocs({ include_docs: true });
        const tickets = result.rows.map((row) => row.doc).filter(doc => doc.type === 'ticket');

      tickets.sort((a, b) => {
        // Сначала открытые
        if (a.status === 'open' && b.status !== 'open') return -1;
        if (a.status !== 'open' && b.status === 'open') return 1;
        // Потом по дате обновления (свежие сверху)
        return new Date(b.updated_at) - new Date(a.updated_at);
      });

        return {
            authenticated: true,
            tickets
        };
    } catch (err) {
        return { authenticated: true, tickets: [] };
    }
}

export const actions = {
    login: async ({ request, cookies }) => {
        const data = await request.formData();
        const password = data.get('password');

        const sessionToken = authenticate(password);

        if (!sessionToken) {
            return fail(400, { incorrect: true, message: 'Неверный пароль администратора' });
        }

        // Устанавливаем надежную куку на 30 дней
        cookies.set('session', sessionToken, {
            path: '/',
            httpOnly: true,
            sameSite: 'strict',
            secure: process.env.NODE_ENV === 'production',
            maxAge: 60 * 60 * 24 * 30
        });

        // МАКСИМАЛЬНО ЖЕСТКИЙ СЕРВЕРНЫЙ РЕДИРЕКТ НА СЕБЯ
        throw redirect(303, '/admin');
    },

    logout: ({ cookies }) => {
        cookies.delete('session', { path: '/' });
        throw redirect(303, '/admin');
    },

  executeCommand: async ({ request, fetch }) => {
      const data = await request.formData();
      const command = data.get('command'); // stats, check, fix, notify, system

      let endpoint = '/api/admin/stats';
      let method = 'GET';

      // Карта маршрутов к бэкенду FastAPI (порт 8000)
      if (command === 'check') endpoint = '/api/admin/check';
      if (command === 'fix') { endpoint = '/api/admin/fix/sync'; method = 'POST'; }
      if (command === 'system') endpoint = '/api/admin/system';

    try {
      const res = await fetch(`${BACKEND_API_URL}${endpoint}`, { method });
      if (!res.ok) return { modalData: { error: `HTTP ${res.status}` }, command };
      return { modalData: await res.json(), command };
    } catch (err) {
      return { modalData: { error: err.message }, command };
    }
  },


  sendMessage: async ({ request }) => {
    const data = await request.formData();
    const ticketId = data.get('ticketId');
    const text = data.get('text');

    if (!ticketId || !text) return fail(400, { missing: true });

    try {
        const ticket = await db.get(ticketId);
        const safeText = text.replace(/_/g, '\\_').replace(/\*/g, '\\*');
        ticket.messages.push({
            sender: 'agent',
            text: safeText,
            created_at: new Date().toISOString()
        });
        ticket.updated_at = new Date().toISOString();
        await db.put(ticket);

        // ============================================
        // ОТПРАВЛЯЕМ ПРЯМО В TELEGRAM BOT API
        // ============================================

        if (BOT_TOKEN) {
            try {
                const response = await fetch(
                    `https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`,
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            chat_id: ticket.tg_user_id,
                            text: `📩 *Ответ поддержки Ulysses Lab:*\n\n${safeText}`,
                            parse_mode: 'Markdown'
                        })
                    }
                );

                if (!response.ok) {
                    const error = await response.text();
                    console.error('❌ Ошибка отправки в Telegram:', error);
                } else {
                    console.log('✅ Сообщение отправлено в Telegram');
                }
            } catch (e) {
                console.error('❌ Не удалось отправить в Telegram:', e);
            }
        } else {
            console.error('❌ BOT_TOKEN не найден в .env');
        }

        return { success: true, updatedTicket: ticket };
    } catch (err) {
        return fail(500, { error: err.message });
    }
  },

  closeTicket: async ({ request }) => {
    const data = await request.formData();
    const ticketId = data.get('ticketId');

    if (!ticketId) return fail(400, { missing: true });

    try {
        const ticket = await db.get(ticketId);
        ticket.status = 'closed';
        ticket.updated_at = new Date().toISOString();

        // Добавляем системное сообщение о закрытии
        ticket.messages.push({
            sender: 'system',
            text: '✅ Тикет закрыт администратором',
            created_at: new Date().toISOString()
        });

        await db.put(ticket);

        // Отправляем уведомление пользователю в Telegram

        if (BOT_TOKEN) {
            try {
                await fetch(
                    `https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`,
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            chat_id: ticket.tg_user_id,
                            text: '✅ *Ваш тикет закрыт администратором Ulysses Lab.*\n\nЕсли у вас остались вопросы, вы можете открыть новый тикет, написав сообщение в этот чат.',
                            parse_mode: 'Markdown'
                        })
                    }
                );
            } catch (e) {
                console.error('Не удалось отправить уведомление о закрытии:', e);
            }
        }

        return { success: true, updatedTicket: ticket };
    } catch (err) {
        return fail(500, { error: err.message });
    }
  }


};
