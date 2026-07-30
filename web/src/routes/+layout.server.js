// src/routes/+layout.js (без .server)
export function load({ url }) {
  return {
    isAdminRoute: url.pathname.startsWith('/admin')
  };
}
