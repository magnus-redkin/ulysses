import { fail, redirect, isRedirect } from '@sveltejs/kit';

const BACKEND_URL = 'http://localhost:8000';

/** @type {import('./$types').PageServerLoad} */
export const load = async ({ fetch }) => {
  try {
    const response = await fetch(`${BACKEND_URL}/api/billing/tariffs`);

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      return { plans: [], error: err.detail || `HTTP ${response.status}` };
    }

    const tariffsObj = await response.json();

    // Преобразуем объект в массив с нужными полями
    const plans = Object.entries(tariffsObj).map(([slug, tariff]) => ({
      id: slug,
      name: tariff.name_ru || tariff.name_en || slug,
      price: tariff.price,
      desc: tariff.description_ru || tariff.description_en || '',
      days: tariff.days,
      traffic_gb: tariff.traffic_gb
    }));

    return { plans };
  } catch (e) {
    console.error('Failed to load tariffs:', e);
    return { plans: [], error: e.message };
  }
};

/** @type {import('./$types').Actions} */
export const actions = {
  default: async ({ request }) => {
    const data = await request.formData();
    const email = data.get('email');
    const plan = data.get('plan');

    if (!email || !plan) {
      return fail(400, { error: 'Missing required fields' });
    }

    try {
      const response = await fetch(`${BACKEND_URL}/api/billing/create-invoice`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: String(email), tariff_slug: String(plan) })
      });

      if (!response.ok) {
        const errorData = await response.json();
        return fail(response.status, { error: errorData.detail || 'Backend error' });
      }

        const result = await response.json();
        console.log('CREATE INVOICE RESPONSE:', JSON.stringify(result, null, 2));

      // Если статус подразумевает успешное создание подписки
      if (result.status === 'free_tariff' || result.status === 'success') {
        // Бесплатный тариф – не редиректим, показываем сообщение о письме
        return {
          success: true,
          message: 'Check your email for the subscription link' // или локализованная строка
        };

        // Перенаправляем на персональную страницу
        // let uuid = result.hiddify_uuid;
        // if (!uuid) {
        //   return fail(500, { error: 'No account identifier returned from backend' });
        // }
        // throw redirect(302, `/account/${uuid}`);
      }

      // Если ошибка – возвращаем форму с ошибкой
      return fail(500, { error: result.detail || 'Subscription creation failed' });

    } catch (err) {
      if (isRedirect(err)) throw err; // ← заменили instanceof на isRedirect
      console.error('Backend connection error:', err);
      return fail(500, { error: 'Internal server error: backend is unreachable' });
    }
  }
};
