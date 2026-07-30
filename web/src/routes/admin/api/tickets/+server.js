import { isValidSession } from '$lib/server/auth';
import PouchDB from 'pouchdb';

const db = new PouchDB('.db_tickets');
const BOT_TOKEN = process.env.BOT_TOKEN;

// Существующий GET
export async function GET({ cookies }) {
    const sessionToken = cookies.get('session');

    if (!sessionToken || !isValidSession(sessionToken)) {
        return new Response(JSON.stringify({ error: 'Unauthorized' }), {
            status: 401,
            headers: { 'Content-Type': 'application/json' }
        });
    }

    try {
        const result = await db.allDocs({ include_docs: true });
        const tickets = result.rows.map((row) => row.doc).filter(doc => doc.type === 'ticket');
        tickets.sort((a, b) => {
            if (a.status === 'open' && b.status !== 'open') return -1;
            if (a.status !== 'open' && b.status === 'open') return 1;
            return new Date(b.updated_at) - new Date(a.updated_at);
        });

        return new Response(JSON.stringify({ tickets }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' }
        });
    } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), {
            status: 500,
            headers: { 'Content-Type': 'application/json' }
        });
    }
}

// ДОБАВЛЯЕМ POST для закрытия тикета
export async function POST({ request, cookies }) {
    const sessionToken = cookies.get('session');

    if (!sessionToken || !isValidSession(sessionToken)) {
        return new Response(JSON.stringify({ error: 'Unauthorized' }), {
            status: 401,
            headers: { 'Content-Type': 'application/json' }
        });
    }

    try {
        const data = await request.json();
        const { ticketId } = data;

        if (!ticketId) {
            return new Response(JSON.stringify({ error: 'Missing ticketId' }), {
                status: 400,
                headers: { 'Content-Type': 'application/json' }
            });
        }

        // Получаем тикет
        const ticket = await db.get(ticketId);

        // Проверяем, что тикет открыт
        if (ticket.status === 'closed') {
            return new Response(JSON.stringify({ error: 'Ticket already closed' }), {
                status: 400,
                headers: { 'Content-Type': 'application/json' }
            });
        }

        // Закрываем тикет
        ticket.status = 'closed';
        ticket.updated_at = new Date().toISOString();

        // Добавляем системное сообщение о закрытии
        if (!ticket.messages) ticket.messages = [];
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

        return new Response(JSON.stringify({
            success: true,
            ticket: ticket
        }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' }
        });

    } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), {
            status: 500,
            headers: { 'Content-Type': 'application/json' }
        });
    }
}
