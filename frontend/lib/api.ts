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
  run: (
    slug: string,
    payload: string | import("./types").ToolRequest,
    force = false,
  ) =>
    api.post<import("./types").ToolResponse>(
      `/v1/tools/${slug}?force=${force}`,
      typeof payload === "string" ? { target: payload } : payload,
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

export const ingestionApi = {
  getCycleStatus: () =>
    api.get<import("./types").IngestionCycleStatus>("/v1/ingestion/cycle-status"),

  patchPolicy: (tld: string, body: import("./types").CzdsPolicyPatchRequest) =>
    api.patch<import("./types").CzdsPolicyItem>(`/v1/czds/policy/${tld}`, body),

  reorderPolicy: (tlds: string[]) =>
    api.post<void>("/v1/czds/policy/reorder", { tlds }),

  getCoverage: () =>
    api.get<import("./types").TldCoverage[]>("/v1/ingestion/tld-coverage"),

  listBulkJobs: () =>
    api.get<import("./types").CtBulkJob[]>("/v1/ingestion/ct-bulk/jobs"),

  getBulkChunks: (jobId: string) =>
    api.get<import("./types").CtBulkChunk[]>(`/v1/ingestion/ct-bulk/jobs/${jobId}/chunks`),

  startBulkJob: (body: import("./types").CtBulkJobCreateRequest) =>
    api.post<import("./types").CtBulkJob>("/v1/ingestion/ct-bulk/jobs", body),

  resumeBulkJob: (jobId: string) =>
    api.post<import("./types").CtBulkJob>(`/v1/ingestion/ct-bulk/jobs/${jobId}/resume`),

  cancelBulkJob: (jobId: string) =>
    api.post<import("./types").CtBulkJob>(`/v1/ingestion/ct-bulk/jobs/${jobId}/cancel`),

  getCheckpoints: (source: string) =>
    api.get<import("./types").CheckpointResponse[]>(`/v1/ingestion/checkpoints?source=${source}`),

  getRuns: ({ source, tld, limit = 10 }: { source: string; tld?: string; limit?: number }) => {
    const params = new URLSearchParams({ limit: String(limit) })
    if (source) params.set("source", source)
    if (tld) params.set("tld", tld)
    return api.get<import("./types").IngestionRun[]>(`/v1/ingestion/runs?${params}`)
  },

  getTldRunMetrics: (source: string, runsPerTld = 10) =>
    api.get<import("./types").TldRunMetrics[]>(
      `/v1/ingestion/tld-run-metrics?source=${encodeURIComponent(source)}&runs_per_tld=${runsPerTld}`
    ),
}

// ── Ingestion Config API ──────────────────────────────────────

export function getIngestionConfigs() {
  return api.get<import("./types").IngestionSourceConfig[]>("/v1/ingestion/config")
}

export function updateIngestionCron(source: string, cron_expression: string) {
  return api.put<import("./types").IngestionSourceConfig>(
    `/v1/ingestion/config/${source}`,
    { cron_expression }
  )
}

export function getTldPolicies(source: string) {
  return api.get<import("./types").IngestionTldPolicy[]>(`/v1/ingestion/tld-policy/${source}`)
}

export function patchTldPolicy(source: string, tld: string, is_enabled: boolean) {
  return api.patch<import("./types").IngestionTldPolicy>(
    `/v1/ingestion/tld-policy/${source}/${tld}`,
    { is_enabled }
  )
}

export function bulkSetTldPolicies(
  source: string,
  tlds: Array<{ tld: string; is_enabled: boolean }>
) {
  return api.put<import("./types").IngestionTldPolicy[]>(
    `/v1/ingestion/tld-policy/${source}`,
    { tlds }
  )
}

export function triggerTldIngestion(source: string, tld: string, force = false) {
  return api.post<import("./types").TriggerTldResponse>(
    `/v1/ingestion/trigger/${source}/${tld}`,
    { force }
  )
}
