"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Database,
  Loader2,
  RefreshCw,
  RotateCcw,
  Search,
  XCircle,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { api, ingestionApi } from "@/lib/api"
import type {
  DailySummaryItem,
  HeatmapResponse,
  HeatmapTldRow,
  IngestionCycleItem,
  IngestionCycleStatus,
  IngestionIncidentItem,
  PhaseStatus,
  SourceSummary,
  TldDailyStatus,
} from "@/lib/types"

// ── Types ──────────────────────────────────────────────────────────────────────

type SourceFilter = "all" | "czds" | "openintel"
type StatusFilter = "all" | "attention" | "pg_ok" | "pg_failed" | "pg_pending" | "running" | "no_data"
type SortMode = "domains" | "attention" | "tld"

const SOURCES: Array<{ value: SourceFilter; label: string }> = [
  { value: "all", label: "Todas as fontes" },
  { value: "czds", label: "CZDS" },
  { value: "openintel", label: "OpenINTEL / R2" },
]

const PERIODS = [7, 14, 30, 60, 90]

// ── Phase status visuals ────────────────────────────────────────────────────

const R2_DOT: Record<PhaseStatus, string> = {
  ok:          "bg-emerald-400",
  pending:     "bg-zinc-300 dark:bg-zinc-600",
  failed:      "bg-red-500",
  running:     "bg-blue-400 animate-pulse",
  no_snapshot: "bg-zinc-200 dark:bg-zinc-700",
}

const PG_DOT: Record<PhaseStatus, string> = {
  ok:          "bg-emerald-600",
  pending:     "bg-amber-400",
  failed:      "bg-red-700",
  running:     "bg-blue-600 animate-pulse",
  no_snapshot: "bg-zinc-200 dark:bg-zinc-700",
}

const PG_CELL_BG: Record<PhaseStatus, string> = {
  ok:          "border-emerald-200 bg-emerald-50 dark:border-emerald-900/60 dark:bg-emerald-950/35",
  pending:     "border-amber-200 bg-amber-50 dark:border-amber-900/60 dark:bg-amber-950/35",
  failed:      "border-red-200 bg-red-50 dark:border-red-900/60 dark:bg-red-950/35",
  running:     "border-blue-200 bg-blue-50 dark:border-blue-900/60 dark:bg-blue-950/35",
  no_snapshot: "border-border-subtle bg-card",
}

const PHASE_LABEL: Record<PhaseStatus, string> = {
  ok:          "OK",
  pending:     "Pendente",
  failed:      "Falha",
  running:     "Executando",
  no_snapshot: "Sem snapshot",
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function localDateKey(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, "0")
  const d = String(date.getDate()).padStart(2, "0")
  return `${y}-${m}-${d}`
}

function addLocalDays(date: Date, days: number): Date {
  const next = new Date(date)
  next.setDate(next.getDate() + days)
  return next
}

function startOfLocalDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}

function buildDateKeys(periodDays: number): string[] {
  const today = startOfLocalDay(new Date())
  const start = addLocalDays(today, -(periodDays - 1))
  return Array.from({ length: periodDays }, (_, i) => localDateKey(addLocalDays(start, i)))
}

function formatDateLabel(key: string): string {
  const [year, month, day] = key.split("-").map(Number)
  return new Date(year, month - 1, day).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })
}

function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return "-"
  return new Date(value).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })
}

function formatCount(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)}K`
  return value.toLocaleString("pt-BR")
}

function formatDuration(seconds: number | null | undefined): string | null {
  if (!seconds || seconds < 0) return null
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ${m % 60}m`
  return `${Math.floor(h / 24)}d ${h % 24}h`
}

function normalizeTld(v: string): string {
  return v.trim().toLowerCase().replace(/^\./, "")
}

// ── Cell tooltip builder ────────────────────────────────────────────────────

function buildCellTitle(tld: string, cell: TldDailyStatus): string {
  return [
    `.${tld} — ${cell.date}`,
    `R2: ${PHASE_LABEL[cell.r2_status]}${cell.r2_reason ? ` (${cell.r2_reason})` : ""}`,
    `PG: ${PHASE_LABEL[cell.pg_status]}${cell.pg_reason ? ` (${cell.pg_reason})` : ""}`,
    cell.domains_inserted ? `${formatCount(cell.domains_inserted)} novos` : null,
    cell.duration_seconds ? `Duração: ${formatDuration(cell.duration_seconds)}` : null,
    cell.error ? `Erro: ${cell.error}` : null,
  ].filter(Boolean).join(" | ")
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function IngestionPage() {
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all")
  const [periodDays, setPeriodDays] = useState(14)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all")
  const [sortMode, setSortMode] = useState<SortMode>("domains")
  const [tldQuery, setTldQuery] = useState("")

  const [heatmap, setHeatmap] = useState<HeatmapResponse | null>(null)
  const [dailySummary, setDailySummary] = useState<DailySummaryItem[]>([])
  const [summaries, setSummaries] = useState<SourceSummary[]>([])
  const [cycleStatus, setCycleStatus] = useState<IngestionCycleStatus | null>(null)
  const [incidents, setIncidents] = useState<IngestionIncidentItem[]>([])
  const [recentCycles, setRecentCycles] = useState<IngestionCycleItem[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [manualTriggering, setManualTriggering] = useState(false)
  const [manualMessage, setManualMessage] = useState("")
  const [error, setError] = useState("")
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null)

  // cell action state
  const [actionTld, setActionTld] = useState<{ source: string; tld: string; date: string; cell: TldDailyStatus } | null>(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [actionMsg, setActionMsg] = useState("")

  const dateKeys = useMemo(() => buildDateKeys(periodDays), [periodDays])
  const todayKey = dateKeys[dateKeys.length - 1]
  const fromDate = dateKeys[0]

  const fetchData = useCallback(async (initial = false) => {
    if (initial) setLoading(true)
    setRefreshing(true)
    setError("")

    const heatmapSource = sourceFilter !== "all" ? sourceFilter : undefined

    try {
      const [heatmapData, summaryData, cycleData, incidentsData, cyclesData, dailyData] =
        await Promise.all([
          ingestionApi.getHeatmap({ source: heatmapSource, days: periodDays }),
          api.get<SourceSummary[]>("/v1/ingestion/summary"),
          ingestionApi.getCycleStatus().catch(() => null),
          ingestionApi.getIncidents({ hours: 24, limit: 80 }).catch(() => ({
            hours: 24, total: 0, items: [] as IngestionIncidentItem[],
          })),
          ingestionApi.getCycles(10).catch(() => ({ items: [] as IngestionCycleItem[], total: 0 })),
          ingestionApi.getDailySummary({
            source: heatmapSource,
            from_date: fromDate,
            to_date: todayKey,
          }).catch(() => ({ items: [] as DailySummaryItem[] })),
        ])

      setHeatmap(heatmapData)
      setSummaries(summaryData)
      setCycleStatus(cycleData)
      setIncidents(incidentsData.items ?? [])
      setRecentCycles(cyclesData.items ?? [])
      setDailySummary(dailyData.items ?? [])
      setLastFetchedAt(new Date())
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao carregar dados de ingestão")
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [periodDays, sourceFilter, fromDate, todayKey])

  useEffect(() => {
    void fetchData(true)
    const interval = window.setInterval(() => void fetchData(false), 60_000)
    return () => window.clearInterval(interval)
  }, [fetchData])

  const triggerDailyCycle = useCallback(async () => {
    setManualTriggering(true)
    setError("")
    setManualMessage("")
    try {
      const response = await ingestionApi.triggerDailyCycle()
      setManualMessage(response.message)
      await fetchData(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao disparar ciclo manual")
    } finally {
      setManualTriggering(false)
    }
  }, [fetchData])

  // ── Summary by date ───────────────────────────────────────────────────────

  const summaryByDate = useMemo(() => {
    const map = new Map<string, DailySummaryItem[]>()
    for (const item of dailySummary) {
      const list = map.get(item.date) ?? []
      list.push(item)
      map.set(item.date, list)
    }
    return map
  }, [dailySummary])

  // ── Filtered/sorted rows ───────────────────────────────────────────────────

  const matrixRows = useMemo(() => {
    const rows = heatmap?.rows ?? []
    const query = normalizeTld(tldQuery)

    return rows
      .filter((row) => !query || row.tld.includes(query))
      .filter((row) => {
        if (statusFilter === "all") return true
        const today = row.days.find((d) => d.date === todayKey)
        if (!today) return statusFilter === "no_data"
        if (statusFilter === "pg_ok") return today.pg_status === "ok"
        if (statusFilter === "pg_failed") return today.pg_status === "failed"
        if (statusFilter === "pg_pending") return today.pg_status === "pending" && today.r2_status === "ok"
        if (statusFilter === "running") return today.pg_status === "running" || today.r2_status === "running"
        if (statusFilter === "attention") return today.pg_status === "failed" || today.r2_status === "failed" || today.pg_status === "pending"
        return true
      })
      .filter((row) => sourceFilter === "all" || row.source === sourceFilter)
      .sort((a, b) => {
        if (sortMode === "tld") return a.tld.localeCompare(b.tld)
        const aFails = a.days.filter((d) => d.pg_status === "failed" || d.r2_status === "failed").length
        const bFails = b.days.filter((d) => d.pg_status === "failed" || d.r2_status === "failed").length
        if (sortMode === "attention") return bFails - aFails || b.domain_count - a.domain_count
        return b.domain_count - a.domain_count || a.tld.localeCompare(b.tld)
      })
  }, [heatmap, tldQuery, statusFilter, sourceFilter, sortMode, todayKey])

  const visibleRows = tldQuery.trim() ? matrixRows : matrixRows.slice(0, 200)

  // ── Counter cards ─────────────────────────────────────────────────────────

  const counters = useMemo(() => {
    const todayRows = (heatmap?.rows ?? []).map((r) => r.days.find((d) => d.date === todayKey))
    const pgOk = todayRows.filter((d) => d?.pg_status === "ok").length
    const pgFailed = todayRows.filter((d) => d?.pg_status === "failed").length
    const pgPending = todayRows.filter((d) => d?.pg_status === "pending" && d?.r2_status === "ok").length
    const r2Failed = todayRows.filter((d) => d?.r2_status === "failed").length
    const running = todayRows.filter((d) => d?.r2_status === "running" || d?.pg_status === "running").length
    const inserted = dailySummary
      .filter((d) => d.date === todayKey)
      .reduce((acc, d) => acc + d.domains_inserted, 0)
    return { pgOk, pgFailed, pgPending, r2Failed, running, inserted }
  }, [heatmap, dailySummary, todayKey])

  // ── Cell actions ──────────────────────────────────────────────────────────

  const handleCellClick = (row: HeatmapTldRow, cell: TldDailyStatus) => {
    if (cell.pg_status === "pending" && cell.r2_status === "pending" && !cell.error) return
    setActionTld({ source: row.source, tld: row.tld, date: cell.date, cell })
    setActionMsg("")
  }

  const handleCellAction = async (action: "reload" | "run" | "dismiss") => {
    if (!actionTld) return
    setActionLoading(true)
    setActionMsg("")
    try {
      const { source, tld, date } = actionTld
      let result
      if (action === "reload") result = await ingestionApi.reloadTld(source, tld, date)
      else if (action === "run") result = await ingestionApi.runTld(source, tld, date)
      else result = await ingestionApi.dismissTld(source, tld, date)
      setActionMsg(result.message)
      setTimeout(() => void fetchData(false), 3000)
    } catch (err) {
      setActionMsg(err instanceof Error ? err.message : "Erro ao executar ação")
    } finally {
      setActionLoading(false)
    }
  }

  const nextSchedules = useMemo(() => {
    return (cycleStatus?.schedules ?? [])
      .filter((s) => s.mode === "cron" && s.next_run_at)
      .sort((a, b) => new Date(a.next_run_at ?? 0).getTime() - new Date(b.next_run_at ?? 0).getTime())
  }, [cycleStatus])

  if (loading) {
    return (
      <div className="space-y-5">
        <div className="space-y-2">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-4 w-96 max-w-full" />
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-6">
          {[1, 2, 3, 4, 5, 6].map((i) => <Skeleton key={i} className="h-28 rounded-lg" />)}
        </div>
        <Skeleton className="h-[520px] rounded-lg" />
      </div>
    )
  }

  return (
    <div className="space-y-5">
      {/* ── Header ── */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-normal">Status de ingestão</h1>
            {refreshing && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
          </div>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Heatmap dual-fase (R2 · PG) por TLD e data. Clique em uma célula para reprocessar.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span>Última leitura: {formatDateTime(lastFetchedAt)}</span>
          <Button onClick={() => void triggerDailyCycle()} disabled={manualTriggering || refreshing}>
            {manualTriggering ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="mr-2 h-3.5 w-3.5" />}
            Executar ciclo agora
          </Button>
          <Button variant="outline" size="sm" onClick={() => void fetchData(false)} disabled={refreshing}>
            <RefreshCw className={`mr-2 h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} />
            Atualizar
          </Button>
        </div>
      </div>

      {nextSchedules.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
          <span className="mr-1 text-xs">Próximas:</span>
          {nextSchedules.map((s) => (
            <span key={s.source} className="inline-flex items-center gap-1 rounded-full border border-border-subtle bg-muted/35 px-2 py-0.5">
              <span className="font-medium">{s.source.toUpperCase()}</span>
              <span>{formatDateTime(s.next_run_at)}</span>
            </span>
          ))}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-900/60 dark:bg-red-950/35 dark:text-red-200">
          {error}
        </div>
      )}
      {manualMessage && !error && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900 dark:border-emerald-900/60 dark:bg-emerald-950/35 dark:text-emerald-200">
          {manualMessage}
        </div>
      )}

      {/* ── Counter cards ── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-6">
        <MetricCard icon={CheckCircle2} label="PG ok hoje" value={formatCount(counters.pgOk)} tone="success" />
        <MetricCard icon={XCircle} label="PG falhou hoje" value={formatCount(counters.pgFailed)} tone="danger" />
        <MetricCard icon={Database} label="R2 falhou hoje" value={formatCount(counters.r2Failed)} tone="danger" />
        <MetricCard icon={Clock3} label="PG pendente" value={formatCount(counters.pgPending)} tone="warning" />
        <MetricCard icon={Loader2} label="Executando" value={formatCount(counters.running)} tone="info" spin={counters.running > 0} />
        <MetricCard icon={CheckCircle2} label="Domínios inseridos" value={formatCount(counters.inserted)} tone="success" />
      </div>

      {/* ── Filters ── */}
      <div className="rounded-lg border border-border-subtle bg-card p-3">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
          <FilterField label="Período">
            <Select value={String(periodDays)} onValueChange={(v) => setPeriodDays(Number(v))}>
              <SelectTrigger className="h-10"><SelectValue /></SelectTrigger>
              <SelectContent>
                {PERIODS.map((p) => <SelectItem key={p} value={String(p)}>Últimos {p} dias</SelectItem>)}
              </SelectContent>
            </Select>
          </FilterField>

          <FilterField label="Fonte">
            <Select value={sourceFilter} onValueChange={(v) => setSourceFilter(v as SourceFilter)}>
              <SelectTrigger className="h-10"><SelectValue /></SelectTrigger>
              <SelectContent>
                {SOURCES.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </FilterField>

          <FilterField label="Status (PG hoje)">
            <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as StatusFilter)}>
              <SelectTrigger className="h-10"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                <SelectItem value="attention">Precisa atenção</SelectItem>
                <SelectItem value="pg_ok">PG ok</SelectItem>
                <SelectItem value="pg_failed">PG falhou</SelectItem>
                <SelectItem value="pg_pending">R2 ok, PG pendente</SelectItem>
                <SelectItem value="running">Executando</SelectItem>
                <SelectItem value="no_data">Sem execução</SelectItem>
              </SelectContent>
            </Select>
          </FilterField>

          <FilterField label="Ordenação">
            <Select value={sortMode} onValueChange={(v) => setSortMode(v as SortMode)}>
              <SelectTrigger className="h-10"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="domains">Qtd. de domínios</SelectItem>
                <SelectItem value="attention">Atenção primeiro</SelectItem>
                <SelectItem value="tld">TLD A-Z</SelectItem>
              </SelectContent>
            </Select>
          </FilterField>

          <FilterField label="TLD">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={tldQuery}
                onChange={(e) => setTldQuery(e.target.value)}
                placeholder="Buscar por com, br, app…"
                className="h-10 pl-9"
              />
            </div>
          </FilterField>
        </div>
      </div>

      {/* ── Heatmap ── */}
      <section className="w-full min-w-0 rounded-lg border border-border-subtle bg-card">
        <div className="flex flex-col gap-2 border-b border-border-subtle px-4 py-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-sm font-medium">Heatmap de ingestão — dual-fase</h2>
            <p className="text-xs text-muted-foreground">
              {visibleRows.length} de {matrixRows.length} TLDs · ●R2 ●PG · clique na célula para reprocessar
            </p>
          </div>
          <PhaseLegend />
        </div>

        <div className="max-h-[74vh] overflow-auto">
          <div
            className="grid min-w-max"
            style={{ gridTemplateColumns: `160px repeat(${dateKeys.length}, minmax(68px, 1fr))` }}
          >
            {/* Header row — TLD label */}
            <div className="sticky left-0 top-0 z-20 border-b border-r border-border-subtle bg-card px-3 py-2 text-xs font-medium text-muted-foreground">
              TLD
            </div>

            {/* Header row — date columns with daily aggregate */}
            {dateKeys.map((key) => {
              const items = summaryByDate.get(key) ?? []
              const tldTotal = items.reduce((acc, d) => acc + d.tld_total, 0)
              const pgOk = items.reduce((acc, d) => acc + d.pg_ok, 0)
              const pgFail = items.reduce((acc, d) => acc + d.pg_failed, 0)
              const inserted = items.reduce((acc, d) => acc + d.domains_inserted, 0)
              const maxDur = items.reduce((max, d) => Math.max(max, d.duration_seconds ?? 0), 0)
              const pct = tldTotal > 0 ? Math.round((pgOk / tldTotal) * 100) : null

              return (
                <div key={key} className="sticky top-0 z-10 border-b border-border-subtle bg-card px-1 py-1 text-center">
                  <div className="text-xs font-medium text-muted-foreground">{formatDateLabel(key)}</div>
                  {pct !== null && (
                    <div className={`text-[10px] font-semibold leading-tight ${pct >= 90 ? "text-emerald-600 dark:text-emerald-400" : pct >= 70 ? "text-amber-600 dark:text-amber-400" : "text-red-600 dark:text-red-400"}`}>
                      {pct}%
                    </div>
                  )}
                  {maxDur > 0 && (
                    <div className="text-[9px] text-muted-foreground">{formatDuration(maxDur)}</div>
                  )}
                  {inserted > 0 && (
                    <div className="text-[9px] text-emerald-600 dark:text-emerald-400">{formatCount(inserted)}</div>
                  )}
                  {pgFail > 0 && (
                    <div className="text-[9px] font-medium text-red-600 dark:text-red-400">{pgFail}✗</div>
                  )}
                </div>
              )
            })}

            {/* Data rows */}
            {visibleRows.map((row) => (
              <HeatmapRow
                key={`${row.source}-${row.tld}`}
                row={row}
                dateKeys={dateKeys}
                onCellClick={(cell) => handleCellClick(row, cell)}
              />
            ))}
          </div>

          {visibleRows.length === 0 && (
            <div className="px-4 py-12 text-center text-sm text-muted-foreground">
              Nenhum TLD encontrado para os filtros atuais.
            </div>
          )}
        </div>
      </section>

      {/* ── Cell action panel ── */}
      {actionTld && (
        <section className="rounded-lg border border-border-subtle bg-card">
          <div className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
            <div>
              <h2 className="text-sm font-medium">
                Ações — <span className="font-mono">.{actionTld.tld}</span> · {actionTld.date}
              </h2>
              <p className="text-xs text-muted-foreground">
                R2: <span className="font-medium">{PHASE_LABEL[actionTld.cell.r2_status]}</span>
                {" · "}
                PG: <span className="font-medium">{PHASE_LABEL[actionTld.cell.pg_status]}</span>
              </p>
            </div>
            <Button variant="ghost" size="sm" onClick={() => setActionTld(null)}>✕</Button>
          </div>
          <div className="p-4 space-y-3">
            {actionTld.cell.error && (
              <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800 dark:border-red-900/60 dark:bg-red-950/35 dark:text-red-200">
                {actionTld.cell.error}
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              {actionTld.cell.r2_status === "ok" && (
                <Button
                  size="sm"
                  onClick={() => void handleCellAction("reload")}
                  disabled={actionLoading}
                >
                  {actionLoading ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="mr-2 h-3.5 w-3.5" />}
                  Reload PG (sem Databricks)
                </Button>
              )}
              <Button
                size="sm"
                variant="outline"
                onClick={() => void handleCellAction("run")}
                disabled={actionLoading}
              >
                Rerun completo (R2 + PG)
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => void handleCellAction("dismiss")}
                disabled={actionLoading}
                className="text-muted-foreground"
              >
                Marcar como sem snapshot
              </Button>
            </div>
            {actionMsg && (
              <p className="text-xs text-muted-foreground">{actionMsg}</p>
            )}
          </div>
        </section>
      )}

      {/* ── Cycles + Incidents ── */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <section className="rounded-lg border border-border-subtle bg-card">
          <div className="border-b border-border-subtle px-4 py-3">
            <h2 className="text-sm font-medium">Ciclos recentes</h2>
            <p className="text-xs text-muted-foreground">Últimos 10 ciclos diários.</p>
          </div>
          {recentCycles.length === 0 ? (
            <div className="px-4 py-4 text-sm text-muted-foreground">Sem ciclos registrados ainda.</div>
          ) : (
            <div className="divide-y divide-border-subtle">
              {recentCycles.map((cycle) => <CycleRow key={cycle.cycle_id} cycle={cycle} />)}
            </div>
          )}
        </section>

        <section className="rounded-lg border border-border-subtle bg-card">
          <div className="border-b border-border-subtle px-4 py-3">
            <h2 className="text-sm font-medium">Incidentes (24h)</h2>
            <p className="text-xs text-muted-foreground">Falhas com reason code e run_id.</p>
          </div>
          {incidents.length === 0 ? (
            <div className="px-4 py-4 text-sm text-muted-foreground">Sem incidentes registrados.</div>
          ) : (
            <div className="divide-y divide-border-subtle">
              {incidents.slice(0, 20).map((incident) => (
                <div key={incident.run_id} className="px-4 py-3 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-mono font-medium">{incident.source}.{incident.tld}</span>
                    <span className="rounded-full border border-border-subtle bg-muted/30 px-2 py-0.5 text-[11px]">
                      {incident.reason_code ?? "-"}
                    </span>
                    <span className="text-xs text-muted-foreground">{formatDateTime(incident.timestamp)}</span>
                  </div>
                  {incident.message && (
                    <div className="mt-1 line-clamp-2 text-xs text-red-600 dark:text-red-300">{incident.message}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      {/* ── Source summaries ── */}
      <section className="rounded-lg border border-border-subtle bg-card">
        <div className="border-b border-border-subtle px-4 py-3">
          <h2 className="text-sm font-medium">Fontes</h2>
        </div>
        <div className="divide-y divide-border-subtle">
          {summaries.map((summary) => (
            <div key={summary.source} className="px-4 py-3 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">{summary.source}</span>
                <span className="text-xs text-muted-foreground">{summary.mode ?? "-"}</span>
              </div>
              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                <span>{formatCount(summary.running_now)} rodando</span>
                <span>{formatCount(summary.failed_runs)} falhas</span>
                <span>último: {formatDateTime(summary.last_run_at)}</span>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function FilterField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="min-w-0 space-y-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  )
}

function MetricCard({
  icon: Icon,
  label,
  value,
  tone,
  spin = false,
}: {
  icon: typeof AlertTriangle
  label: string
  value: string
  tone: "danger" | "info" | "success" | "neutral" | "warning"
  spin?: boolean
}) {
  const toneClass = {
    danger:  "text-red-600 bg-red-50 dark:text-red-300 dark:bg-red-950/35",
    info:    "text-blue-600 bg-blue-50 dark:text-blue-300 dark:bg-blue-950/35",
    success: "text-emerald-600 bg-emerald-50 dark:text-emerald-300 dark:bg-emerald-950/35",
    neutral: "text-muted-foreground bg-muted",
    warning: "text-amber-600 bg-amber-50 dark:text-amber-300 dark:bg-amber-950/35",
  }[tone]

  return (
    <div className="rounded-lg border border-border-subtle bg-card p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          <p className="mt-2 font-mono text-xl font-semibold tabular-nums">{value}</p>
        </div>
        <div className={`rounded-md p-2 ${toneClass}`}>
          <Icon className={`h-4 w-4 ${spin ? "animate-spin" : ""}`} />
        </div>
      </div>
    </div>
  )
}

function PhaseLegend() {
  return (
    <div className="flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
      <span className="flex items-center gap-1">
        <span className="inline-flex gap-0.5">
          <span className="h-2 w-2 rounded-full bg-emerald-400" />
          <span className="h-2 w-2 rounded-full bg-emerald-600" />
        </span>
        Ok (R2·PG)
      </span>
      <span className="flex items-center gap-1">
        <span className="inline-flex gap-0.5">
          <span className="h-2 w-2 rounded-full bg-emerald-400" />
          <span className="h-2 w-2 rounded-full bg-amber-400" />
        </span>
        R2 ok, PG pendente
      </span>
      <span className="flex items-center gap-1">
        <span className="inline-flex gap-0.5">
          <span className="h-2 w-2 rounded-full bg-emerald-400" />
          <span className="h-2 w-2 rounded-full bg-red-700" />
        </span>
        R2 ok, PG falhou
      </span>
      <span className="flex items-center gap-1">
        <span className="inline-flex gap-0.5">
          <span className="h-2 w-2 rounded-full bg-red-500" />
          <span className="h-2 w-2 rounded-full bg-zinc-300 dark:bg-zinc-600" />
        </span>
        R2 falhou
      </span>
    </div>
  )
}

function HeatmapRow({
  row,
  dateKeys,
  onCellClick,
}: {
  row: HeatmapTldRow
  dateKeys: string[]
  onCellClick: (cell: TldDailyStatus) => void
}) {
  const cellByDate = useMemo(() => {
    const map = new Map<string, TldDailyStatus>()
    for (const d of row.days) map.set(d.date, d)
    return map
  }, [row.days])

  return (
    <>
      <div className="sticky left-0 z-10 min-w-0 border-r border-border-subtle bg-card px-2 py-0.5">
        <div className="flex items-center gap-1 whitespace-nowrap text-[9px] leading-none">
          <span className="truncate font-mono text-xs font-medium">.{row.tld}</span>
          <span className="shrink-0 rounded-full border border-border-subtle bg-muted/30 px-1 py-0.5 text-[8px] font-medium leading-none text-muted-foreground">
            {row.source === "czds" ? "CZDS" : "OI"}
          </span>
          {row.domain_count > 0 && (
            <span className="shrink-0 text-muted-foreground">{formatCount(row.domain_count)}d</span>
          )}
        </div>
      </div>

      {dateKeys.map((key) => {
        const cell = cellByDate.get(key) ?? {
          date: key, r2_status: "pending" as PhaseStatus, pg_status: "pending" as PhaseStatus,
          r2_reason: null, pg_reason: null, error: null, duration_seconds: null,
          domains_inserted: 0, domains_deleted: 0,
        }
        return (
          <DualPhaseCell
            key={`${row.tld}-${key}`}
            tld={row.tld}
            cell={cell}
            onClick={() => onCellClick(cell)}
          />
        )
      })}
    </>
  )
}

function DualPhaseCell({
  tld,
  cell,
  onClick,
}: {
  tld: string
  cell: TldDailyStatus
  onClick: () => void
}) {
  const isActive = cell.pg_status !== "pending" || cell.r2_status !== "pending" || !!cell.error
  const bgClass = PG_CELL_BG[cell.pg_status]
  const title = buildCellTitle(tld, cell)

  return (
    <div className="border-b border-border-subtle p-px">
      <button
        type="button"
        title={title}
        onClick={isActive ? onClick : undefined}
        className={`flex h-8 w-full min-w-0 flex-col items-center justify-center rounded-md border px-1 transition-colors ${bgClass} ${isActive ? "cursor-pointer hover:brightness-95" : "cursor-default"}`}
      >
        {/* Phase dots: R2 (top) · PG (bottom) */}
        <div className="flex items-center gap-0.5">
          <span className={`h-1.5 w-1.5 rounded-full ${R2_DOT[cell.r2_status]}`} />
          <span className={`h-1.5 w-1.5 rounded-full ${PG_DOT[cell.pg_status]}`} />
        </div>

        {/* Content label */}
        {cell.pg_status === "ok" && cell.domains_inserted > 0 ? (
          <span className="mt-0.5 font-mono text-[8px] tabular-nums text-emerald-800 dark:text-emerald-300">
            {formatCount(cell.domains_inserted)}
          </span>
        ) : cell.pg_status === "running" || cell.r2_status === "running" ? (
          <Loader2 className="mt-0.5 h-2.5 w-2.5 animate-spin text-blue-600" />
        ) : cell.pg_status === "failed" ? (
          <XCircle className="mt-0.5 h-2.5 w-2.5 text-red-700" />
        ) : cell.pg_status === "pending" && cell.r2_status === "ok" ? (
          <Clock3 className="mt-0.5 h-2.5 w-2.5 text-amber-600" />
        ) : null}
      </button>
    </div>
  )
}

const CYCLE_STATUS_META: Record<string, { label: string; className: string }> = {
  running:     { label: "Executando",  className: "bg-blue-50 text-blue-700 dark:bg-blue-950/35 dark:text-blue-200" },
  succeeded:   { label: "Sucesso",     className: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/35 dark:text-emerald-200" },
  failed:      { label: "Falha",       className: "bg-red-50 text-red-700 dark:bg-red-950/35 dark:text-red-200" },
  interrupted: { label: "Interrompido",className: "bg-amber-50 text-amber-700 dark:bg-amber-950/35 dark:text-amber-200" },
}

function CycleRow({ cycle }: { cycle: IngestionCycleItem }) {
  const meta = CYCLE_STATUS_META[cycle.status] ?? { label: cycle.status, className: "bg-muted text-muted-foreground" }
  const dur = cycle.started_at && cycle.finished_at
    ? formatDuration(Math.floor((new Date(cycle.finished_at).getTime() - new Date(cycle.started_at).getTime()) / 1000))
    : null
  const total = cycle.tld_success + cycle.tld_failed + cycle.tld_skipped + cycle.tld_load_only

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-sm">
      <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${meta.className}`}>
        {meta.label}
      </span>
      <span className="text-muted-foreground">{formatDateTime(cycle.started_at)}</span>
      {dur && <span className="font-mono text-xs text-muted-foreground">{dur}</span>}
      <span className="text-xs text-muted-foreground">
        gatilho: <span className="font-medium text-foreground">{cycle.triggered_by}</span>
      </span>
      <span className="ml-auto flex shrink-0 flex-wrap gap-x-3 text-xs text-muted-foreground">
        <span className="text-emerald-700 dark:text-emerald-300">{cycle.tld_success} ok</span>
        {cycle.tld_load_only > 0 && <span className="text-blue-700 dark:text-blue-300">{cycle.tld_load_only} load-only</span>}
        {cycle.tld_skipped > 0 && <span>{cycle.tld_skipped} skip</span>}
        {cycle.tld_failed > 0 && <span className="text-red-700 dark:text-red-300">{cycle.tld_failed} falha</span>}
        <span className="text-muted-foreground">/ {cycle.tld_total ?? total} TLDs</span>
      </span>
    </div>
  )
}
