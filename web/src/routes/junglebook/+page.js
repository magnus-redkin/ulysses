//web/src/routes/junglebook/+page.js

import { redirect } from '@sveltejs/kit';

export function load() {
  throw redirect(307, '/junglebook/index');
}
