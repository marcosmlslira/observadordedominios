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

export interface BrandSeedsByFamily {
  by_family: Record<string, BrandSeed[]>
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
  snapshot_date: string | null
  reason_code: string | null
  error_message: string | null
}

export interface SourceSummary {
  source: string
  total_runs: number
  successful_runs: number
  failed_runs: number
  running_now: number
  running_active_count?: number
  running_stale_count?: number
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

export interface ManualCycleTriggerResponse {
  status: "accepted" | "already_running"
  message: string
}

// ── Ingestion cycle audit (GET /v1/ingestion/cycles) ──────────────────────────

export interface IngestionCycleItem {
  cycle_id: string
  started_at: string
  finished_at: string | null
  status: string
  triggered_by: string
  tld_total: number | null
  tld_success: number
  tld_failed: number
  tld_skipped: number
  tld_load_only: number
  last_heartbeat_at: string | null
}

export interface IngestionCyclesResponse {
  items: IngestionCycleItem[]
  total: number
}

// ── TLD health (GET /v1/ingestion/tlds/health) ────────────────────────────────

export interface TldHealthItem {
  source: string
  tld: string
  last_status: string | null
  last_reason_code: string | null
  last_started_at: string | null
  last_finished_at: string | null
  domains_inserted: number | null
  domains_seen: number | null
  last_error_message: string | null
}

export interface TldHealthResponse {
  items: TldHealthItem[]
  total: number
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
  error_message: string | null
  started_at: string | null
  finished_at: string | null
}

export interface ScanJobResponse {
  job_id: string
  brand_id: string
  requested_tld: string | null
  status: string
  queued_at: string
  started_at: string | null
  finished_at: string | null
  force_full: boolean
  tlds_effective: string[]
  last_error: string | null
  results: ScanResultResponse[]
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
  ordering_mode: string
  updated_at: string
}

export interface IngestionTldPolicy {
  source: string
  tld: string
  is_enabled: boolean
  priority: number | null
  domains_inserted: number
  last_seen_at: string | null
  updated_at: string
}

export interface TldMetricsRow {
  tld: string
  is_enabled: boolean
  priority: number | null
  last_duration_seconds: number | null   // finished_at - started_at of last run
  last_domains_inserted: number | null
  last_successful_run_at: string | null
  recent_runs: Array<{                   // last 10 runs, oldest→newest
    status: "success" | "failed" | "running"
    duration_seconds: number | null
    started_at: string
  }>
  // CertStream-specific cumulative stats (null for run-based sources)
  domains_inserted_total: number | null
  last_seen_at: string | null
  // OpenINTEL verification fields
  openintel_last_verification_at?: string | null
  openintel_last_available_snapshot_date?: string | null
  openintel_last_ingested_snapshot_date?: string | null
  openintel_status?: OpenintelVisualStatus
  openintel_status_reason?: string | null
  openintel_last_error_message?: string | null
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

export type OpenintelVisualStatus =
  | "up_to_date_no_new_snapshot"
  | "new_snapshot_ingested"
  | "delayed"
  | "failed"
  | "no_data"

export interface OpenintelGlobalCounts {
  up_to_date_no_new_snapshot: number
  new_snapshot_ingested: number
  delayed: number
  failed: number
  no_data: number
}

export interface OpenintelTldStatusItem {
  tld: string
  is_enabled: boolean
  priority: number | null
  last_verification_at: string | null
  last_available_snapshot_date: string | null
  last_ingested_snapshot_date: string | null
  status: OpenintelVisualStatus
  status_reason: string
  last_error_message: string | null
}

export interface OpenintelStatusResponse {
  source: string
  last_verification_at: string | null
  overall_status: "healthy" | "warning" | "failed"
  overall_message: string
  status_counts: OpenintelGlobalCounts
  items: OpenintelTldStatusItem[]
}

// ── Unified TLD Status ────────────────────────────────

export type TldStatusCategory = "ok" | "partial" | "running" | "failed" | "never_run" | "never_attempted"

export interface TldStatusItem {
  tld: string
  source: string
  is_enabled: boolean
  priority: number | null
  status: TldStatusCategory
  execution_status_today: "never_attempted" | "no_run_today" | "running" | "success" | "failed" | "skipped"
  functional_status: "healthy" | "degraded" | "unknown" | "running"
  last_run_id: string | null
  last_run_at: string | null
  last_status: string | null
  last_success_at: string | null
  last_failure_at: string | null
  last_reason_code: string | null
  last_error_message: string | null
  domains_inserted_today: number
  domains_deleted_today: number
  error_message: string | null
}

export interface TldStatusResponse {
  source: string
  items: TldStatusItem[]
  total: number
  ok_count: number
  partial_count: number
  failed_count: number
  running_count: number
  never_run_count: number
}

export interface IngestionIncidentItem {
  timestamp: string
  source: string
  tld: string
  run_id: string
  status: string
  reason_code: string | null
  message: string | null
}

export interface IngestionIncidentsResponse {
  hours: number
  total: number
  items: IngestionIncidentItem[]
}

// ── Dual-phase heatmap types ─────────────────────────

export type PhaseStatus = "ok" | "pending" | "failed" | "running" | "no_snapshot"

export interface TldDailyStatus {
  date: string
  r2_status: PhaseStatus
  pg_status: PhaseStatus
  r2_reason: string | null
  pg_reason: string | null
  error: string | null
  duration_seconds: number | null
  domains_inserted: number
  domains_deleted: number
}

export interface HeatmapTldRow {
  tld: string
  source: string
  domain_count: number
  days: TldDailyStatus[]
}

export interface HeatmapResponse {
  source: string | null
  days: string[]
  rows: HeatmapTldRow[]
}

export interface DailySummaryItem {
  date: string
  source: string
  tld_total: number
  r2_ok: number
  r2_failed: number
  pg_ok: number
  pg_failed: number
  pg_pending: number
  no_snapshot: number
  duration_seconds: number | null
  domains_inserted: number
  pg_complete_pct: number
}

export interface DailySummaryResponse {
  items: DailySummaryItem[]
}

export interface TldReloadResponse {
  status: "accepted" | "already_running" | "not_configured"
  message: string
  run_id: string | null
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
  status: string | null
  self_owned: boolean | null
  ownership_classification: string | null
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

export interface LifecycleStatus {
  enrichment_phase: "pending" | "running" | "completed" | "failed" | "idle"
  enrichment_budget: number
  enrichment_total: number
  enrichment_started_at: string | null
  enrichment_finished_at: string | null
  assessment_eligible: number
  assessment_completed: number
}

export interface MatchSnapshotListResponse {
  items: MatchSnapshot[]
  total: number
  active_scan: ScanJobResponse | null
  last_scan: ScanJobResponse | null
  lifecycle: LifecycleStatus | null
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
