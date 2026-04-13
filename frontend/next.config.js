/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',

  // Dev proxy: requests to /v1/* are forwarded to the production API server-side,
  // bypassing CORS restrictions that would block browser-originated cross-origin calls.
  async rewrites() {
    if (process.env.NODE_ENV !== 'development') return []
    const apiBase = process.env.NEXT_PUBLIC_API_URL_PROXY || 'https://api.observadordedominios.com.br'
    return [
      {
        source: '/v1/:path*',
        destination: `${apiBase}/v1/:path*`,
      },
    ]
  },
}

module.exports = nextConfig
