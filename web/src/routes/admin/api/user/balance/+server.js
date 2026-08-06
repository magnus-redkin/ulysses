// web/src/routes/admin/api/user/balance/+server.js

import { json } from '@sveltejs/kit';
import { isValidSession } from '$lib/server/auth';

const BACKEND_URL = process.env.BACKEND_API_URL || 'http://127.0.0.1:8000';

/** @type {import('./$types').RequestHandler} */
export async function GET({ cookies, url }) {
  const sessionToken = cookies.get('session');
  if (!isValidSession(sessionToken)) {
    return json({ error: 'Unauthorized' }, { status: 401 });
  }

  const tgUserId = url.searchParams.get('tg_user_id');
  const hiddifyUuid = url.searchParams.get('hiddify_uuid');

  if (!tgUserId && !hiddifyUuid) {
    return json(
      { error: 'Either tg_user_id or hiddify_uuid is required' },
      { status: 400 }
    );
  }

  const backendParams = new URLSearchParams();
  if (tgUserId) backendParams.set('tg_user_id', tgUserId);
  if (hiddifyUuid) backendParams.set('hiddify_uuid', hiddifyUuid);

  try {
    const resp = await fetch(`${BACKEND_URL}/api/user/balance?${backendParams}`);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      return json(
        { error: err.detail || 'Backend error' },
        { status: resp.status }
      );
    }
    const data = await resp.json();
    return json(data, { headers: { 'Cache-Control': 'no-store' } });
  } catch (err) {
    console.error('Error fetching user balance for admin:', err);
    return json({ error: 'Internal server error' }, { status: 500 });
  }
}
