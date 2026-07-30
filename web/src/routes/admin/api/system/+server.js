// src/routes/admin/api/system/+server.js

const BACKEND_API_URL = process.env.BACKEND_API_URL || 'http://127.0.0.1:8000';

// Только для отображения в сайдбаре (последнее сообщение от бота)
let lastBotMessage = {
    status: 'unknown',
    message: 'Нет данных',
    updated_at: new Date().toISOString()
};

export async function POST({ request }) {
    try {
        const payload = await request.json();

        lastBotMessage = {
            status: payload.is_healthy ? 'healthy' : 'degraded',
            message: payload.report_text || payload.message || '',
            updated_at: new Date().toISOString()
        };

        console.log('✅ Бот:', lastBotMessage.status, '-', lastBotMessage.message.substring(0, 50));

        return new Response(JSON.stringify({ success: true }), {
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

export async function GET({ cookies }) {
    try {
      const res = await fetch(`${BACKEND_API_URL}/admin/api/system`);
        if (res.ok) {
            const liveData = await res.json();
            return new Response(JSON.stringify(liveData), {
                status: 200,
                headers: { 'Content-Type': 'application/json' }
            });
        }
        throw new Error(`Backend HTTP ${res.status}`);
    } catch (e) {
        console.error('❌ Backend недоступен:', e.message);
        return new Response(JSON.stringify({
            error: true,
            status: 'down',
            message: 'Backend недоступен!',
            detail: e.message
        }), {
            status: 200,  // 200 чтобы фронтенд мог обработать
            headers: { 'Content-Type': 'application/json' }
        });
    }
}
