import { error } from '@sveltejs/kit';

const BACKEND_URL = 'http://localhost:8000';

export async function load({ params, fetch }) {
  const uuid = params.uuid;
  const response = await fetch(`${BACKEND_URL}/api/user/balance?hiddify_uuid=${uuid}`);

  if (!response.ok) {
    if (response.status === 404) throw error(404, `Account not found: ${uuid}`);
    const errData = await response.json().catch(() => ({}));
    throw error(response.status, errData.detail || 'Failed to fetch account data');
  }

  const data = await response.json();

  return {
    account: {
      // Поля из текущего ответа API
      status: data.status,
      email: data.email,
      hiddify_uuid: data.hiddify_uuid,
      traffic: data.traffic,
      days_left: data.days_left,        // оставшиеся дни (int)
      is_active: data.is_active,
      tg_user_id: data.tg_user_id,
      tg_username: data.tg_username,
      db_id: data.db_id,
      // Новые поля (пока могут быть null)
      subscription_link: data.subscription_link,
      expires_at: data.expires_at,
      tariff_name: data.tariff_name
    }
  };
}
