import type { NextConfig } from 'next';

/**
 * In production a reverse proxy (deploy/Caddyfile) sends /api/* straight to the API, so the API sees
 * the candidate's address for its rate limits. In development the same paths are rewritten here.
 */
const devApi = process.env.NODE_ENV === 'development' ? (process.env.CLEARHIRE_API_URL ?? 'http://127.0.0.1:8077') : null;

const config: NextConfig = {
  output: 'standalone',
  poweredByHeader: false,
  reactStrictMode: true,
  async rewrites() {
    return devApi ? [{ source: '/api/public/:path*', destination: `${devApi}/api/public/:path*` }] : [];
  },
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
        ],
      },
      {
        // the status link is the candidate's only key: never leak it in a Referer header or a search index
        source: '/status/:token',
        headers: [
          { key: 'Referrer-Policy', value: 'no-referrer' },
          { key: 'X-Robots-Tag', value: 'noindex, nofollow' },
          { key: 'Cache-Control', value: 'private, no-store' },
        ],
      },
    ];
  },
};

export default config;
