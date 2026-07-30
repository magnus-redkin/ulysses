import { json } from '@sveltejs/kit';

/** @type {import('./$types').RequestHandler} */
export async function GET({ url }) {
    const hiddifyUuid = url.searchParams.get('hiddify_uuid');

    if (!hiddifyUuid) {
        return json({ error: 'hiddify_uuid parameter is required' }, { status: 400 });
    }

    // Валидация UUID
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(hiddifyUuid)) {
        return json({ error: 'Invalid UUID format' }, { status: 400 });
    }

    try {
        // Здесь должен быть запрос к вашему бэкенду
        const backendUrl = `http://localhost:8000/api/user/balance?hiddify_uuid=${hiddifyUuid}`;

        console.log(`Fetching user balance for UUID: ${hiddifyUuid}`);

        const response = await fetch(backendUrl);

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            return json(
                { error: errorData.detail || 'Failed to fetch user data' },
                { status: response.status }
            );
        }

        const userData = await response.json();

        // Добавляем кеширование на 30 секунд
        return json(userData, {
            headers: {
                'Cache-Control': 'public, max-age=30'
            }
        });

    } catch (err) {
        console.error('Error fetching user balance:', err);
        return json(
            { error: 'Internal server error' },
            { status: 500 }
        );
    }
}
