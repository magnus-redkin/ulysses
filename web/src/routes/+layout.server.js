// src/routes/+layout.server.js
export function load({ url }) {
  return {
    isAdminRoute: url.pathname.startsWith('/admin')
  };
}
