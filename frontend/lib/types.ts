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
  primary_brand_name: string
  brand_label: string
  keywords: string[]
  tld_scope: string[]
  noise_mode: string
  notes: string | null
  official_domains: BrandDomain[]
  aliases: BrandAlias[]
  seeds: BrandSeed[]
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface BrandDomain {
  id: string
  domain_name: string
  registrable_domain: string
  registrable_label: string
  public_suffix: string
  hostname_stem: string | null
  is_primary: boolean
  is_active: boolean
}

export interface BrandAlias {
  id: string
  alias_value: string
  alias_normalized: string
  alias_type: string
  weight_override: number | null
  is_active: boolean
}

export interface BrandSeed {
  id: string
  source_ref_type: string
  source_ref_id: string | null
  seed_value: string
  seed_type: string
  channel_scope: string
  base_weight: number
  is_manual: boolean
  is_active: boolean
}

export interface BrandListResponse {
  items: Brand[]
  total: number
}

export interface CreateBrandRequest {
  brand_name: string
  primary_brand_name?: string
  official_domains: string[]
  aliases: BrandAliasRequest[]
  keywords: string[]
  tld_scope: string[]
  noise_mode?: string
  notes?: string
}

export interface UpdateBrandRequest {
  brand_name?: string
  primary_brand_name?: string
  official_domains?: string[]
  aliases?: BrandAliasRequest[]
  keywords?: string[]
  tld_scope?: string[]
  noise_mode?: string
  notes?: string
  is_active?: boolean
}

export interface BrandAliasRequest {
  value: string
  type: "brand_alias" | "brand_phrase" | "support_keyword"
}

export interface BrandSeedListResponse {
  items: BrandSeed[]
  total: number
}

// ── CZDS Ingestion ──────────────────────────────────────

export interface IngestionRun {
  run_id: string
  source: string
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

export interface SourceSummary {
  source: string
  total_runs: number
  successful_runs: number
  failed_runs: number
  running_now: number
  last_run_at: string | null
  last_success_at: string | null
  last_status: string | null
  total_domains_seen: number
  total_domains_inserted: number
  mode: string | null
  status_hint: string | null
  next_expected_run_hint: string | null
}

export interface TriggerSyncRequest {
  tld: string
  force: boolean
}

export interface TriggerSyncResponse {
  run_id: string
  status: string
}

export interface CzdsPolicyItem {
  tld: string
  is_enabled: boolean
  priority: number
  cooldown_hours: number
  notes: string | null
}

export interface CzdsPolicyResponse {
  source: "database" | "env"
  tlds: string[]
  items: CzdsPolicyItem[]
}

export interface CzdsPolicyUpdateRequest {
  tlds: string[]
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
  actionability_score: number | null
  attention_bucket: string | null
  attention_reasons: string[] | null
  recommended_action: string | null
  enrichment_status: string | null
  enrichment_summary: {
    signals?: { code: string; severity: string; description: string }[]
    tools?: Record<string, { status?: string; error?: string | null; summary?: Record<string, unknown> }>
    target?: string
    error?: string
  } | null
  last_enriched_at: string | null
  first_detected_at: string
  domain_first_seen: string
  status: string
  reviewed_by: string | null
  reviewed_at: string | null
  notes: string | null
  matched_channel: string | null
  matched_seed_id: string | null
  matched_seed_value: string | null
  matched_seed_type: string | null
  matched_rule: string | null
  source_stream: string | null
}

export interface MatchListResponse {
  items: SimilarityMatch[]
  total: number
}

export interface UpdateMatchStatusRequest {
  status: string
  notes?: string
}

// ── Free Tools ─────────────────────────────────────────

export type ToolType =
  | "dns_lookup"
  | "whois"
  | "ssl_check"
  | "screenshot"
  | "suspicious_page"
  | "http_headers"
  | "blacklist_check"
  | "email_security"
  | "reverse_ip"
  | "ip_geolocation"
  | "domain_similarity"
  | "website_clone"

export type ToolStatus = "running" | "completed" | "failed" | "timeout"

export interface ToolResponse {
  execution_id: string
  tool_type: ToolType
  target: string
  status: ToolStatus
  duration_ms: number | null
  cached: boolean
  result: Record<string, unknown> | null
  error: string | null
  executed_at: string
}

export interface ToolRequest {
  target: string
  reference_target?: string
}

export interface QuickAnalysisRequest {
  target: string
  tools?: ToolType[]
}

export interface QuickAnalysisToolResult {
  status: ToolStatus
  result: Record<string, unknown> | null
  error: string | null
  duration_ms: number | null
}

export interface QuickAnalysisResponse {
  quick_analysis_id: string
  target: string
  status: "completed" | "partial"
  total_duration_ms: number
  results: Record<string, QuickAnalysisToolResult>
}

export interface HistoryItem {
  execution_id: string
  tool_type: ToolType
  target: string
  status: ToolStatus
  duration_ms: number | null
  triggered_by: string
  created_at: string
}

export interface HistoryListResponse {
  items: HistoryItem[]
  total: number
}

export interface ToolDefinition {
  type: ToolType
  name: string
  description: string
  slug: string
  icon: string
  category: "essential" | "enrichment"
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
