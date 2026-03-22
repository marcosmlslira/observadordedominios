// ── Auth ─────────────────────────────────────────────────

export interface LoginRequest {
  email: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

// ── Monitored Brands ────────────────────────────────────

export interface Brand {
  id: string
  organization_id: string
  brand_name: string
  brand_label: string
  keywords: string[]
  tld_scope: string[]
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface BrandListResponse {
  items: Brand[]
  total: number
}

export interface CreateBrandRequest {
  brand_name: string
  keywords: string[]
  tld_scope: string[]
}

export interface UpdateBrandRequest {
  brand_name?: string
  keywords?: string[]
  tld_scope?: string[]
  is_active?: boolean
}

// ── CZDS Ingestion ──────────────────────────────────────

export interface IngestionRun {
  run_id: string
  tld: string
  status: string
  started_at: string
  finished_at: string | null
  domains_seen: number
  domains_inserted: number
  domains_reactivated: number
  domains_deleted: number
  artifact_key: string | null
  error_message: string | null
}

export interface TriggerSyncRequest {
  tld: string
  force: boolean
}

export interface TriggerSyncResponse {
  run_id: string
  status: string
}

// ── Similarity Matches ──────────────────────────────────

export interface SimilarityMatch {
  id: string
  brand_id: string
  domain_name: string
  tld: string
  label: string
  score_final: number
  score_trigram: number | null
  score_levenshtein: number | null
  score_brand_hit: number | null
  score_keyword: number | null
  score_homograph: number | null
  reasons: string[]
  risk_level: string
  first_detected_at: string
  domain_first_seen: string
  status: string
  reviewed_by: string | null
  reviewed_at: string | null
  notes: string | null
}

export interface MatchListResponse {
  items: SimilarityMatch[]
  total: number
}

export interface UpdateMatchStatusRequest {
  status: string
  notes?: string
}

// ── Scan ────────────────────────────────────────────────

export interface ScanResultResponse {
  brand_id: string
  tld: string | null
  candidates: number
  matched: number
  removed: number
  status: string
}

export interface ScanSummaryResponse {
  results: ScanResultResponse[]
}
