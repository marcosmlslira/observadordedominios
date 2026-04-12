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

export interface CycleSummary {
  cycle_date: string
  health_status: string
  scan_status: string
  enrichment_status: string
  new_matches_count: number
  threats_detected: number
  dismissed_count: number
}

export interface ThreatCounts {
  immediate_attention: number
  defensive_gap: number
  watchlist: number
}

export interface MonitoringSummary {
  latest_cycle: CycleSummary | null
  threat_counts: ThreatCounts
  overall_health: "healthy" | "warning" | "critical" | "unknown"
}

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
  monitoring_summary?: MonitoringSummary
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
  cron_expression: string | null
  status_hint: string | null
  next_expected_run_hint: string | null
  bulk_job_status: string | null
  bulk_chunks_total: number
  bulk_chunks_done: number
  bulk_chunks_error: number
  bulk_chunks_pending: number
}

export interface TldCoverage {
  tld: string
  effective_source: string
  czds_available: boolean
  ct_enabled: boolean
  bulk_status: string
  fallback_reason: string | null
  priority_group: string
  last_ct_stream_seen_at: string | null
  last_crtsh_success_at: string | null
}

export interface CtBulkJob {
  job_id: string
  status: string
  requested_tlds: string[]
  resolved_tlds: string[]
  priority_tlds: string[]
  dry_run: boolean
  initiated_by: string | null
  started_at: string | null
  finished_at: string | null
  last_error: string | null
  total_chunks: number
  pending_chunks: number
  running_chunks: number
  done_chunks: number
  error_chunks: number
  total_raw_domains: number
  total_inserted_domains: number
}

export interface CtBulkChunk {
  chunk_id: string
  job_id: string
  target_tld: string
  chunk_key: string
  query_pattern: string
  prefix: string
  depth: number
  status: string
  attempt_count: number
  last_error_type: string | null
  last_error_excerpt: string | null
  next_retry_at: string | null
  raw_domains: number
  inserted_domains: number
  started_at: string | null
  finished_at: string | null
}

export interface CtBulkJobCreateRequest {
  tlds: string[]
  dry_run: boolean
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
  failure_count: number
  last_error_code: number | null
  last_error_at: string | null
  suspended_until: string | null
  notes: string | null
}

export interface CzdsPolicyPatchRequest {
  is_enabled?: boolean
  priority?: number
  cooldown_hours?: number
}

export interface CycleStatus {
  is_active: boolean
  total_tlds: number
  completed_tlds: number
  failed_tlds: number
  skipped_tlds: number
  current_tld: string | null
  cycle_started_at: string | null
  estimated_completion_at: string | null
  avg_tld_duration_seconds: number | null
}

export interface ScheduleEntry {
  source: string
  cron_expression: string
  next_run_at: string | null
  mode: string
}

export interface HealthSummary {
  total_tlds_enabled: number
  tlds_ok: number
  tlds_suspended: number
  tlds_failing: number
}

export interface IngestionCycleStatus {
  czds_cycle: CycleStatus
  schedules: ScheduleEntry[]
  health: HealthSummary
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
  llm_assessment: {
    risco_score: number
    categoria: string
    parecer_resumido: string
    principais_motivos: string[]
    recomendacao_acao: string
    confianca: number
  } | null
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

// ── Similarity Metrics ──────────────────────────────────

export interface SimilarityMetricsTotals {
  total_matches: number
  immediate_attention: number
  defensive_gap: number
  watchlist: number
  status_new: number
  status_reviewing: number
  status_dismissed: number
  status_confirmed: number
  risk_critical: number
  risk_high: number
  new_last_24h: number
  new_last_7d: number
  latest_detection_at: string | null
}

export interface SimilarityMetricsByBrand {
  brand_name: string
  brand_label: string
  total: number
  immediate: number
  last_match_at: string | null
  top_score: number | null
}

export interface SimilarityMetrics {
  totals: SimilarityMetricsTotals
  by_brand: SimilarityMetricsByBrand[]
  last_scan_job: { status: string; created_at: string; finished_at: string | null } | null
}

export interface TldDomainCount {
  tld: string
  count: number
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

// ── Ingestion Run / Checkpoint responses ─────────────────

export interface CheckpointResponse {
  source: string
  tld: string
  last_successful_run_id: string
  last_successful_run_at: string
}

// ── Ingestion Config ──────────────────────────────────────

export interface IngestionSourceConfig {
  source: string
  cron_expression: string
  updated_at: string
}

export interface IngestionTldPolicy {
  source: string
  tld: string
  is_enabled: boolean
  updated_at: string
}

export interface TldMetricsRow {
  tld: string
  is_enabled: boolean
  last_duration_seconds: number | null   // finished_at - started_at of last run
  last_domains_inserted: number | null
  last_successful_run_at: string | null
  recent_runs: Array<{                   // last 10 runs, oldest→newest
    status: "success" | "failed" | "running"
    duration_seconds: number | null
    started_at: string
  }>
}

export interface TriggerTldResponse {
  run_id: string
  source: string
  tld: string
  status: string
}

export interface TldRunMetricItem {
  status: string
  started_at: string
  finished_at: string | null
  domains_inserted: number | null
}

export interface TldRunMetrics {
  tld: string
  runs: TldRunMetricItem[]
}

// ── Monitoring Pipeline ─────────────────────────────

export interface DomainCheckDetail {
  ok: boolean
  details?: Record<string, unknown>
}

export interface DomainHealthCheck {
  domain_id: string
  domain_name: string
  is_primary: boolean
  overall_status: string
  dns?: DomainCheckDetail
  ssl?: DomainCheckDetail
  email_security?: DomainCheckDetail
  headers?: DomainCheckDetail
  takeover?: DomainCheckDetail
  blacklist?: DomainCheckDetail
  safe_browsing?: DomainCheckDetail
  urlhaus?: DomainCheckDetail
  phishtank?: DomainCheckDetail
  suspicious_page?: DomainCheckDetail
  last_check_at: string | null
}

export interface BrandHealthResponse {
  domains: DomainHealthCheck[]
}

export interface MonitoringCycleResponse {
  id: string
  brand_id: string
  organization_id: string
  cycle_date: string
  cycle_type: string
  health_status: string
  health_started_at: string | null
  health_finished_at: string | null
  scan_status: string
  scan_started_at: string | null
  scan_finished_at: string | null
  scan_job_id: string | null
  enrichment_status: string
  enrichment_started_at: string | null
  enrichment_finished_at: string | null
  enrichment_budget: number
  enrichment_total: number
  new_matches_count: number
  escalated_count: number
  dismissed_count: number
  threats_detected: number
  created_at: string
  updated_at: string
}

export interface CycleListResponse {
  items: MonitoringCycleResponse[]
  total: number
}

export interface SignalSchema {
  code: string
  severity: string | null
  score_adjustment: number | null
  description: string | null
  source_tool: string | null
}

export interface MatchSnapshot {
  id: string
  brand_id: string
  domain_name: string
  tld: string
  label: string
  score_final: number
  attention_bucket: string | null
  matched_rule: string | null
  auto_disposition: string | null
  auto_disposition_reason: string | null
  first_detected_at: string
  domain_first_seen: string
  derived_score: number | null
  derived_bucket: string | null
  derived_risk: string | null
  derived_disposition: string | null
  active_signals: SignalSchema[]
  signal_codes: string[]
  llm_assessment: {
    risco_score: number
    categoria: string
    parecer_resumido: string
    principais_motivos: string[]
    recomendacao_acao: string
    confianca: number
  } | null
  state_fingerprint: string | null
  last_derived_at: string | null
}

export interface MatchSnapshotListResponse {
  items: MatchSnapshot[]
  total: number
}

export interface MonitoringEvent {
  id: string
  event_type: string
  event_source: string
  tool_name: string | null
  tool_version: string | null
  result_data: Record<string, unknown>
  signals: Record<string, unknown>[] | null
  score_snapshot: Record<string, unknown> | null
  cycle_id: string | null
  created_at: string
}

export interface EventListResponse {
  items: MonitoringEvent[]
  total: number
}
