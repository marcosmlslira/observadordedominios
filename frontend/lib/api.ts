import { API_BASE_URL } from "./config"

function getToken(): string | null {
  if (typeof window === "undefined") return null
  return localStorage.getItem("admin_token")
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) || {}),
  }
  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }

  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  })

  if (res.status === 401) {
    if (typeof window !== "undefined") {
      localStorage.removeItem("admin_token")
      window.location.href = "/login"
    }
    throw new Error("Unauthorized")
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(body.detail || `Request failed: ${res.status}`)
  }

  if (res.status === 204) return undefined as T

  return res.json()
}

export const api = {
  get: <T>(path: string) => request<T>(path),

  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    }),

  put: <T>(path: string, body: unknown) =>
    request<T>(path, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  patch: <T>(path: string, body: unknown) =>
    request<T>(path, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  delete: (path: string) =>
    request<void>(path, { method: "DELETE" }),
}

// ── Free Tools API ──────────────────────────────────────

export const toolsApi = {
  run: (slug: string, target: string, force = false) =>
    api.post<import("./types").ToolResponse>(
      `/v1/tools/${slug}?force=${force}`,
      { target },
    ),

  quickAnalysis: (target: string, tools?: string[]) =>
    api.post<import("./types").QuickAnalysisResponse>(
      "/v1/tools/quick-analysis",
      { target, ...(tools ? { tools } : {}) },
    ),

  history: (params?: { target?: string; tool_type?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams()
    if (params?.target) qs.set("target", params.target)
    if (params?.tool_type) qs.set("tool_type", params.tool_type)
    if (params?.limit) qs.set("limit", String(params.limit))
    if (params?.offset) qs.set("offset", String(params.offset))
    return api.get<import("./types").HistoryListResponse>(
      `/v1/tools/history?${qs}`,
    )
  },

  getExecution: (id: string) =>
    api.get<import("./types").ToolResponse>(`/v1/tools/history/${id}`),
}
