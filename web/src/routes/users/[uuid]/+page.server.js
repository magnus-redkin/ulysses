import { error } from '@sveltejs/kit';

/** @type {import('./$types').PageServerLoad} */
export async function load({ params, fetch }) {
    const { uuid } = params;

    // Валидация UUID
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(uuid)) {
        throw error(400, 'Invalid UUID format');
    }

    try {
        // Используем fetch от SvelteKit для запроса к нашему API
        const response = await fetch(`/api/user/balance?hiddify_uuid=${uuid}`);

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw error(response.status, errorData.error || 'User not found');
        }

        const userData = await response.json();

        return {
            user: userData,
            uuid
        };

    } catch (err) {
        if (err.status && err.body) {
            throw err;
        }
        console.error('Error loading user page:', err);
        throw error(500, 'Internal server error');
    }
}
