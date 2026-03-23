const PRODUCTION_API_URL = "https://api.observadordedominios.com.br"
const DEVELOPMENT_API_URL = "http://localhost:8005"

function normalizeUrl(url: string) {
  return url.replace(/\/+$/, "")
}

export const API_BASE_URL = normalizeUrl(
  process.env.NEXT_PUBLIC_API_URL ||
    (process.env.NODE_ENV === "development"
      ? DEVELOPMENT_API_URL
      : PRODUCTION_API_URL),
)
