import { json } from '@sveltejs/kit';
import PouchDB from 'pouchdb';

const db = new PouchDB('.db_tickets');

async function getTicketNumber(tg_user_id) {
  try {
    const result = await db.allDocs({ include_docs: true });
    const userTickets = result.rows
          .map(row => row.doc)
          .filter(doc => doc.type === 'ticket' && doc.tg_user_id === tg_user_id);
    return userTickets.length + 1;
  } catch (err) {
    return 1;
  }
}

// ============================================================
// 1. ПОЛУЧЕНИЕ ВСЕХ ТИКЕТОВ ДЛЯ АВТООБНОВЛЕНИЯ АДМИНКИ (GET)
// ============================================================
export async function GET({ cookies }) {
    // Защита: проверяем сессию админа перед отдачей данных
    const auth = cookies.get('session');
    if (!auth) {
        return json({ error: 'Unauthorized' }, { status: 401 });
    }

    try {
        const result = await db.allDocs({ include_docs: true });
        const tickets = result.rows
            .map((row) => row.doc)
            .filter(doc => doc && doc.type === 'ticket');

        // Сортируем: сначала открытые (open)
        tickets.sort((a, b) => (a.status === 'open' ? -1 : 1));

        return json({ tickets });
    } catch (err) {
        console.error("🚨 Ошибка при получении тикетов для админки:", err);
        return json({ error: err.message }, { status: 500 });
    }
}

// ============================================================
// 2. ПРИЕМ НОВЫХ СООБЩЕНИЙ ОТ TELEGRAM-БОТА (POST)
// ============================================================
export async function POST({ request }) {
    try {
        const data = await request.json();
        const { tg_user_id, username, text } = data;

        if (!tg_user_id || !text) {
            return new Response(JSON.stringify({ error: 'Missing fields' }), {
                status: 400,
                headers: { 'Content-Type': 'application/json' }
            });
        }

        // Проверяем, есть ли открытый тикет у этого пользователя
        const allDocs = await db.allDocs({ include_docs: true });
        const existingTickets = allDocs.rows
            .map(row => row.doc)
            .filter(doc =>
                doc.type === 'ticket' &&
                doc.tg_user_id === tg_user_id &&
                doc.status === 'open'
            );

        let ticket;
        let isNew = false;

        if (existingTickets.length > 0) {
            // Есть открытый тикет - добавляем сообщение
            ticket = existingTickets[0];
            ticket.messages.push({
                sender: 'user',
                text: text,
                created_at: new Date().toISOString()
            });
            ticket.updated_at = new Date().toISOString();
            await db.put(ticket);
        } else {
            // Создаем новый тикет
            const ticketNumber = await getTicketNumber(tg_user_id);
            ticket = {
                _id: `ticket_${tg_user_id}_${Date.now()}`,
                type: 'ticket',
                tg_user_id: tg_user_id,
                username: username || 'unknown',
                ticket_number: ticketNumber, // Добавляем номер
                status: 'open',
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
                messages: [{
                    sender: 'user',
                    text: text,
                    created_at: new Date().toISOString()
                }]
            };
            await db.put(ticket);
            isNew = true;
        }

        return new Response(JSON.stringify({
            success: true,
            ticket: ticket,
            ticket_number: ticket.ticket_number || 1,
            is_new: isNew
        }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' }
        });

    } catch (err) {
        console.error('Error creating ticket:', err);
        return new Response(JSON.stringify({ error: err.message }), {
            status: 500,
            headers: { 'Content-Type': 'application/json' }
        });
    }
}
