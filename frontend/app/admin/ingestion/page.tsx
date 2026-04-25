"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Database,
  Loader2,
  RefreshCw,
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
  IngestionCycleStatus,
  IngestionRun,
  OpenintelStatusResponse,
  OpenintelTldStatusItem,
  SourceSummary,
  TldDomainCount,
  TldStatusResponse,
} from "@/lib/types"

type SourceFilter = "all" | "czds" | "openintel"
type StatusFilter = "all" | "attention" | "success" | "failed" | "running" | "queued" | "no_data"
type SortMode = "domains" | "attention" | "tld"
type CellStatus = "success" | "failed" | "running" | "queued" | "delayed" | "no_data"

const SOURCES: Array<{ value: SourceFilter; label: string }> = [
  { value: "all", label: "Todas as fontes" },
  { value: "czds", label: "CZDS" },
  { value: "openintel", label: "OpenINTEL / R2" },
]

const PERIODS = [7, 14, 30, 60, 90]
const SOURCE_PRIORITY: SourceFilter[] = ["czds", "openintel"]
const SOURCE_PILL_LABEL: Record<string, string> = {
  czds: "CZDS",
  openintel: "OI",
}

const STATUS_META: Record<CellStatus, { label: string; className: string; dot: string }> = {
  success: {
    label: "Sucesso",
    className: "border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900/60 dark:bg-emerald-950/35 dark:text-emerald-200",
    dot: "bg-emerald-500",
  },
  failed: {
    label: "Falha",
    className: "border-red-200 bg-red-50 text-red-900 dark:border-red-900/60 dark:bg-red-950/35 dark:text-red-200",
    dot: "bg-red-500",
  },
  running: {
    label: "Executando",
    className: "border-blue-200 bg-blue-50 text-blue-900 dark:border-blue-900/60 dark:bg-blue-950/35 dark:text-blue-200",
    dot: "bg-blue-500",
  },
  queued: {
    label: "Na fila",
    className: "border-zinc-200 bg-zinc-50 text-zinc-800 dark:border-zinc-800 dark:bg-zinc-900/55 dark:text-zinc-200",
    dot: "bg-zinc-400",
  },
  delayed: {
    label: "R2 pendente",
    className: "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/35 dark:text-amber-200",
    dot: "bg-amber-500",
  },
  no_data: {
    label: "Sem execução",
    className: "border-border-subtle bg-card text-muted-foreground",
    dot: "bg-zinc-300 dark:bg-zinc-700",
  },
}

function localDateKey(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

function runDateKey(value: string): string {
  return localDateKey(new Date(value))
}

function addLocalDays(date: Date, days: number): Date {
  const next = new Date(date)
  next.setDate(next.getDate() + days)
  return next
}

function startOfLocalDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}

function formatDateLabel(key: string): string {
  const [year, month, day] = key.split("-").map(Number)
  return new Date(year, month - 1, day).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
  })
}

function formatDateTime(value: string | Date | null): string {
  if (!value) return "-"
  return new Date(value).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function formatCount(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)}K`
  return value.toLocaleString("pt-BR")
}

function formatRunDuration(startedAt: string | null, finishedAt: string | null): string | null {
  if (!startedAt) return null
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now()
  const seconds = Math.max(0, Math.floor((end - new Date(startedAt).getTime()) / 1000))
  if (seconds < 60) return `${seconds}s`

  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`

  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ${minutes % 60}m`

  return `${Math.floor(hours / 24)}d ${hours % 24}h`
}

function sourceLabel(source: string): string {
  return SOURCES.find((item) => item.value === source)?.label ?? source
}

function sourcePillLabel(source: string): string {
  return SOURCE_PILL_LABEL[source] ?? source.toUpperCase()
}

function normalizeTld(value: string): string {
  return value.trim().toLowerCase().replace(/^\./, "")
}

function buildPeriod(periodDays: number) {
  const today = startOfLocalDay(new Date())
  const start = addLocalDays(today, -(periodDays - 1))
  const end = addLocalDays(today, 1)
  return { start, end }
}

function buildDateKeys(periodDays: number): string[] {
  const { start } = buildPeriod(periodDays)
  return Array.from({ length: periodDays }, (_, index) => localDateKey(addLocalDays(start, index)))
}

function isR2Pending(item: OpenintelTldStatusItem | undefined): boolean {
  return item?.status === "delayed"
}

export default function IngestionPage() {
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all")
  const [periodDays, setPeriodDays] = useState(7)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all")
  const [sortMode, setSortMode] = useState<SortMode>("domains")
  const [tldQuery, setTldQuery] = useState("")

  const [runs, setRuns] = useState<IngestionRun[]>([])
  const [summaries, setSummaries] = useState<SourceSummary[]>([])
  const [domainCounts, setDomainCounts] = useState<TldDomainCount[]>([])
  const [cycleStatus, setCycleStatus] = useState<IngestionCycleStatus | null>(null)
  const [openintelStatus, setOpenintelStatus] = useState<OpenintelStatusResponse | null>(null)
  const [tldStatuses, setTldStatuses] = useState<Record<string, TldStatusResponse | null>>({})
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [manualTriggering, setManualTriggering] = useState(false)
  const [manualMessage, setManualMessage] = useState("")
  const [error, setError] = useState("")
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null)

  const fetchData = useCallback(async (initial = false) => {
    const { start, end } = buildPeriod(periodDays)
    const params = new URLSearchParams({
      limit: "2000",
      started_from: start.toISOString(),
      started_to: end.toISOString(),
    })
    if (sourceFilter !== "all") params.set("source", sourceFilter)

    if (initial) setLoading(true)
    setRefreshing(true)
    setError("")

    try {
      const [runsData, summaryData, countsData, cycleData, openintelData, czdsStatus, openintelTldStatus] =
        await Promise.all([
          api.get<IngestionRun[]>(`/v1/ingestion/runs?${params}`),
          api.get<SourceSummary[]>("/v1/ingestion/summary"),
          api.get<TldDomainCount[]>("/v1/ingestion/domain-counts").catch(() => []),
          ingestionApi.getCycleStatus().catch(() => null),
          ingestionApi.getOpenintelStatus().catch(() => null),
          ingestionApi.getTldStatus("czds").catch(() => null),
          ingestionApi.getTldStatus("openintel").catch(() => null),
        ])

      setRuns(runsData.filter((run) => run.source === "czds" || run.source === "openintel"))
      setSummaries(summaryData)
      setDomainCounts(countsData)
      setCycleStatus(cycleData)
      setOpenintelStatus(openintelData)
      setTldStatuses({
        czds: czdsStatus,
        openintel: openintelTldStatus,
      })
      setLastFetchedAt(new Date())
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao carregar dados de ingestão")
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [periodDays, sourceFilter])

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

  const dateKeys = useMemo(() => buildDateKeys(periodDays), [periodDays])
  const todayKey = dateKeys[dateKeys.length - 1]

  const domainCountByTld = useMemo(() => {
    return new Map(domainCounts.map((item) => [item.tld, item.count]))
  }, [domainCounts])

  const openintelByTld = useMemo(() => {
    return new Map((openintelStatus?.items ?? []).map((item) => [item.tld, item]))
  }, [openintelStatus])

  const queuedTlds = useMemo(() => {
    if (!cycleStatus?.czds_cycle.is_active) return new Set<string>()
    if (sourceFilter !== "all" && sourceFilter !== "czds") return new Set<string>()

    const items = tldStatuses.czds?.items ?? []
    const current = items.find((item) => item.tld === cycleStatus.czds_cycle.current_tld)
    const currentPriority = current?.priority ?? 0

    return new Set(
      items
        .filter((item) => (
          item.is_enabled &&
          item.status === "never_run" &&
          item.tld !== cycleStatus.czds_cycle.current_tld &&
          (item.priority ?? 0) > currentPriority
        ))
        .map((item) => item.tld),
    )
  }, [cycleStatus, sourceFilter, tldStatuses])

  const matrixRows = useMemo(() => {
    const tlds = new Set<string>()
    domainCounts.forEach((item) => tlds.add(item.tld))
    runs.forEach((run) => tlds.add(run.tld))
    openintelStatus?.items.forEach((item) => tlds.add(item.tld))
    Object.values(tldStatuses).forEach((response) => response?.items.forEach((item) => tlds.add(item.tld)))

    const query = normalizeTld(tldQuery)
    const statusesBySource = {
      czds: new Set((tldStatuses.czds?.items ?? []).map((item) => item.tld)),
      openintel: new Set((tldStatuses.openintel?.items ?? []).map((item) => item.tld)),
    }
    const rows = Array.from(tlds).map((tld) => {
      const tldRuns = runs.filter((run) => run.tld === tld)
      const latestRun = tldRuns[0]
      const r2 = openintelByTld.get(tld)
      const isQueued = queuedTlds.has(tld)
      const presentSources = new Set<string>(tldRuns.map((run) => run.source))
      if (statusesBySource.czds.has(tld)) presentSources.add("czds")
      if (statusesBySource.openintel.has(tld) || r2) presentSources.add("openintel")
      const primarySource = (
        sourceFilter !== "all"
          ? sourceFilter
          : SOURCE_PRIORITY.find((source) => presentSources.has(source))
      ) ?? latestRun?.source ?? "czds"
      const cells = dateKeys.map((key) => {
        const dayRuns = tldRuns.filter((run) => runDateKey(run.started_at) === key)
        const latestDayRun = dayRuns[0]
        const inserted = dayRuns.reduce((total, run) => total + (run.domains_inserted || 0), 0)
        const hasRunning = dayRuns.some((run) => run.status === "running")
        const hasFailed = dayRuns.some((run) => run.status === "failed")
        const hasSuccess = dayRuns.some((run) => run.status === "success" || run.status === "ok")
        const availableOnThisDay = r2?.last_available_snapshot_date === key
        const pendingR2OnThisDay = (sourceFilter === "all" || sourceFilter === "openintel") && availableOnThisDay && isR2Pending(r2)

        let status: CellStatus = "no_data"
        if (hasRunning) status = "running"
        else if (hasFailed) status = "failed"
        else if (pendingR2OnThisDay) status = "delayed"
        else if (hasSuccess) status = "success"
        else if (key === todayKey && isQueued) status = "queued"

        return {
          key,
          status,
          inserted,
          runs: dayRuns.length,
          duration: latestDayRun ? formatRunDuration(latestDayRun.started_at, latestDayRun.finished_at) : null,
          latestStartedAt: latestDayRun?.started_at ?? null,
          latestFinishedAt: latestDayRun?.finished_at ?? null,
          sources: Array.from(new Set(dayRuns.map((run) => run.source))),
          error: dayRuns.find((run) => run.status === "failed")?.error_message ?? null,
          r2,
        }
      })

      const failedDays = cells.filter((cell) => cell.status === "failed").length
      const attentionScore = failedDays + (isR2Pending(r2) ? 2 : 0) + (latestRun?.status === "running" ? 1 : 0)
      const currentStatus: StatusFilter =
        latestRun?.status === "running" ? "running" :
        latestRun?.status === "failed" || r2?.status === "failed" ? "failed" :
        isR2Pending(r2) ? "attention" :
        isQueued ? "queued" :
        latestRun?.status === "success" || latestRun?.status === "ok" ? "success" :
        "no_data"

      return {
        tld,
        cells,
        primarySource,
        currentStatus,
        latestRun,
        r2,
        domainCount: domainCountByTld.get(tld) ?? 0,
        inserted: tldRuns.reduce((total, run) => total + (run.domains_inserted || 0), 0),
        failedDays,
        attentionScore,
      }
    })

    return rows
      .filter((row) => !query || row.tld.includes(query))
      .filter((row) => {
        if (statusFilter === "all") return true
        if (statusFilter === "attention") {
          return row.currentStatus === "failed" || row.currentStatus === "attention" || row.failedDays > 0
        }
        return row.currentStatus === statusFilter
      })
      .sort((a, b) => {
        if (sortMode === "tld") return a.tld.localeCompare(b.tld)
        if (sortMode === "attention") return b.attentionScore - a.attentionScore || b.domainCount - a.domainCount
        return b.domainCount - a.domainCount || a.tld.localeCompare(b.tld)
      })
  }, [
    dateKeys,
    domainCountByTld,
    domainCounts,
    openintelByTld,
    openintelStatus,
    queuedTlds,
    runs,
    sortMode,
    sourceFilter,
    statusFilter,
    tldQuery,
    tldStatuses,
    todayKey,
  ])

  const visibleRows = tldQuery.trim() ? matrixRows : matrixRows.slice(0, 180)
  const nextSchedules = useMemo(() => {
    return (cycleStatus?.schedules ?? [])
      .filter((schedule) => schedule.mode === "cron" && schedule.next_run_at)
      .sort((a, b) => new Date(a.next_run_at ?? 0).getTime() - new Date(b.next_run_at ?? 0).getTime())
  }, [cycleStatus])

  const counters = useMemo(() => {
    const failedTlds = new Set<string>()
    const runningTlds = new Set<string>()
    let inserted = 0

    runs.forEach((run) => {
      inserted += run.domains_inserted || 0
      if (run.status === "failed") failedTlds.add(run.tld)
      if (run.status === "running") runningTlds.add(run.tld)
    })

    const delayedR2 = (openintelStatus?.items ?? []).filter((item) => item.is_enabled && item.status === "delayed")
    const failedR2 = (openintelStatus?.items ?? []).filter((item) => item.is_enabled && item.status === "failed")

    return {
      failedTlds: failedTlds.size + failedR2.length,
      runningTlds: runningTlds.size,
      queuedTlds: queuedTlds.size,
      r2Pending: delayedR2.length,
      inserted,
    }
  }, [openintelStatus, queuedTlds, runs])

  const r2AttentionItems = useMemo(() => {
    return (openintelStatus?.items ?? [])
      .filter((item) => item.is_enabled && ["delayed", "failed", "no_data"].includes(item.status))
      .sort((a, b) => {
        const priority = { failed: 0, delayed: 1, no_data: 2 }
        return (priority[a.status as keyof typeof priority] ?? 3) - (priority[b.status as keyof typeof priority] ?? 3)
      })
      .slice(0, 10)
  }, [openintelStatus])

  if (loading) {
    return (
      <div className="space-y-5">
        <div className="space-y-2">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-4 w-96 max-w-full" />
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
          {[1, 2, 3, 4, 5].map((item) => <Skeleton key={item} className="h-28 rounded-lg" />)}
        </div>
        <Skeleton className="h-[520px] rounded-lg" />
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-normal">Status de ingestão</h1>
            {refreshing && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
          </div>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Matriz por data e TLD com execuções recentes, fila CZDS e disponibilidade OpenINTEL/R2.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span>Atualiza a cada 1 minuto</span>
          <span className="hidden h-1 w-1 rounded-full bg-border-strong sm:block" />
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
          {nextSchedules.map((schedule) => (
            <span key={schedule.source} className="inline-flex items-center gap-1 rounded-full border border-border-subtle bg-muted/35 px-2 py-0.5">
              <span className="font-medium">{sourcePillLabel(schedule.source)}</span>
              <span>{formatDateTime(schedule.next_run_at)}</span>
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

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-5">
        <MetricCard icon={AlertTriangle} label="TLDs com atenção" value={formatCount(counters.failedTlds + counters.r2Pending)} tone="danger" />
        <MetricCard icon={XCircle} label="Falhas recentes" value={formatCount(counters.failedTlds)} tone="danger" />
        <MetricCard icon={Loader2} label="Executando agora" value={formatCount(counters.runningTlds)} tone="info" spin={counters.runningTlds > 0} />
        <MetricCard icon={Clock3} label="Na fila CZDS" value={formatCount(counters.queuedTlds)} tone="neutral" />
        <MetricCard icon={Database} label="Domínios adicionados" value={formatCount(counters.inserted)} tone="success" />
      </div>

      <div className="rounded-lg border border-border-subtle bg-card p-3">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
          <FilterField label="Período">
            <Select value={String(periodDays)} onValueChange={(value) => setPeriodDays(Number(value))}>
              <SelectTrigger className="h-10">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PERIODS.map((period) => (
                  <SelectItem key={period} value={String(period)}>
                    Últimos {period} dias
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FilterField>

          <FilterField label="Fonte">
            <Select value={sourceFilter} onValueChange={(value) => setSourceFilter(value as SourceFilter)}>
              <SelectTrigger className="h-10">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SOURCES.map((source) => (
                  <SelectItem key={source.value} value={source.value}>{source.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FilterField>

          <FilterField label="Status atual">
            <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as StatusFilter)}>
              <SelectTrigger className="h-10">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                <SelectItem value="attention">Precisa atenção</SelectItem>
                <SelectItem value="failed">Falha</SelectItem>
                <SelectItem value="success">Sucesso</SelectItem>
                <SelectItem value="running">Executando</SelectItem>
                <SelectItem value="queued">Na fila</SelectItem>
                <SelectItem value="no_data">Sem execução</SelectItem>
              </SelectContent>
            </Select>
          </FilterField>

          <FilterField label="Ordenação">
            <Select value={sortMode} onValueChange={(value) => setSortMode(value as SortMode)}>
              <SelectTrigger className="h-10">
                <SelectValue />
              </SelectTrigger>
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
                onChange={(event) => setTldQuery(event.target.value)}
                placeholder="Buscar por com, br, app..."
                className="h-10 pl-9"
              />
            </div>
          </FilterField>
        </div>
      </div>

      <div className="space-y-4">
        <section className="w-full min-w-0 rounded-lg border border-border-subtle bg-card">
          <div className="flex flex-col gap-2 border-b border-border-subtle px-4 py-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-sm font-medium">Heatmap de ingestão</h2>
              <p className="text-xs text-muted-foreground">
                {visibleRows.length} de {matrixRows.length} TLDs visíveis · eixo X por data, eixo Y por TLD
              </p>
            </div>
            <Legend />
          </div>

          <div className="max-h-[74vh] overflow-auto">
            <div
              className="grid min-w-max"
              style={{ gridTemplateColumns: `150px repeat(${dateKeys.length}, minmax(62px, 1fr))` }}
            >
              <div className="sticky left-0 top-0 z-20 border-b border-r border-border-subtle bg-card px-3 py-2 text-xs font-medium text-muted-foreground">
                TLD
              </div>
              {dateKeys.map((key) => (
                <div key={key} className="sticky top-0 z-10 border-b border-border-subtle bg-card px-2 py-2 text-center text-xs font-medium text-muted-foreground">
                  {formatDateLabel(key)}
                </div>
              ))}

              {visibleRows.map((row) => (
                <RowCells key={row.tld} row={row} dateKeys={dateKeys} />
              ))}
            </div>

            {visibleRows.length === 0 && (
              <div className="px-4 py-12 text-center text-sm text-muted-foreground">
                Nenhum TLD encontrado para os filtros atuais.
              </div>
            )}
          </div>
        </section>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <section className="rounded-lg border border-border-subtle bg-card">
            <div className="border-b border-border-subtle px-4 py-3">
              <h2 className="text-sm font-medium">R2 / OpenINTEL</h2>
              <p className="text-xs text-muted-foreground">{openintelStatus?.overall_message ?? "Sem leitura do status OpenINTEL."}</p>
            </div>
            <div className="grid grid-cols-2 gap-2 p-3 text-sm">
              <R2Count label="Pendente" value={openintelStatus?.status_counts.delayed ?? 0} tone="warning" />
              <R2Count label="Falha" value={openintelStatus?.status_counts.failed ?? 0} tone="danger" />
              <R2Count label="Importado novo" value={openintelStatus?.status_counts.new_snapshot_ingested ?? 0} tone="success" />
              <R2Count label="Em dia" value={openintelStatus?.status_counts.up_to_date_no_new_snapshot ?? 0} tone="neutral" />
            </div>
            <div className="border-t border-border-subtle">
              {r2AttentionItems.length === 0 ? (
                <div className="px-4 py-4 text-sm text-muted-foreground">Nenhum snapshot pendente ou falha no R2.</div>
              ) : (
                <div className="divide-y divide-border-subtle">
                  {r2AttentionItems.map((item) => (
                    <div key={item.tld} className="px-4 py-3 text-sm">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono font-medium">.{item.tld}</span>
                        <span className={`rounded-full px-2 py-0.5 text-[11px] ${item.status === "failed" ? "bg-red-50 text-red-700 dark:bg-red-950/35 dark:text-red-200" : item.status === "delayed" ? "bg-amber-50 text-amber-700 dark:bg-amber-950/35 dark:text-amber-200" : "bg-muted text-muted-foreground"}`}>
                          {item.status_reason}
                        </span>
                      </div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        Disponível: {item.last_available_snapshot_date ?? "-"} · Importado: {item.last_ingested_snapshot_date ?? "-"}
                      </div>
                      {item.last_error_message && (
                        <div className="mt-1 line-clamp-2 text-xs text-red-600 dark:text-red-300">{item.last_error_message}</div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>

          <section className="rounded-lg border border-border-subtle bg-card">
            <div className="border-b border-border-subtle px-4 py-3">
              <h2 className="text-sm font-medium">Fontes</h2>
              <p className="text-xs text-muted-foreground">Resumo do contrato `/v1/ingestion/summary`.</p>
            </div>
            <div className="divide-y divide-border-subtle">
              {summaries.map((summary) => (
                <div key={summary.source} className="px-4 py-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">{sourceLabel(summary.source)}</span>
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
      </div>
    </div>
  )
}

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
  tone: "danger" | "info" | "success" | "neutral"
  spin?: boolean
}) {
  const toneClass = {
    danger: "text-red-600 bg-red-50 dark:text-red-300 dark:bg-red-950/35",
    info: "text-blue-600 bg-blue-50 dark:text-blue-300 dark:bg-blue-950/35",
    success: "text-emerald-600 bg-emerald-50 dark:text-emerald-300 dark:bg-emerald-950/35",
    neutral: "text-muted-foreground bg-muted",
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

function Legend() {
  const items: CellStatus[] = ["success", "failed", "running", "queued", "delayed", "no_data"]
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item) => (
        <span key={item} className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className={`h-2 w-2 rounded-full ${STATUS_META[item].dot}`} />
          {STATUS_META[item].label}
        </span>
      ))}
    </div>
  )
}

function RowCells({
  row,
}: {
  row: {
    tld: string
    primarySource: string
    domainCount: number
    inserted: number
    attentionScore: number
    cells: Array<{
      key: string
      status: CellStatus
      inserted: number
      runs: number
      duration: string | null
      latestStartedAt: string | null
      latestFinishedAt: string | null
      sources: string[]
      error: string | null
      r2?: OpenintelTldStatusItem
    }>
  }
  dateKeys: string[]
}) {
  return (
    <>
      <div
        className="sticky left-0 z-10 min-w-0 border-r border-border-subtle bg-card px-2 py-0.5"
        title={`.${row.tld} • ${formatCount(row.domainCount)} domínios • ${formatCount(row.inserted)} novos`}
      >
        <div className="flex items-center gap-1 whitespace-nowrap text-[9px] leading-none">
          <span className="truncate font-mono text-xs font-medium">.{row.tld}</span>
          <span className="shrink-0 rounded-full border border-border-subtle bg-muted/30 px-1 py-0.5 text-[8px] font-medium leading-none text-muted-foreground">
            {sourcePillLabel(row.primarySource)}
          </span>
          <span className="shrink-0 text-muted-foreground">{formatCount(row.domainCount)}d • {formatCount(row.inserted)}n</span>
          {row.attentionScore > 0 && <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-500" />}
        </div>
      </div>
      {row.cells.map((cell) => (
        <HeatmapCell key={`${row.tld}-${cell.key}`} cell={cell} />
      ))}
    </>
  )
}

function HeatmapCell({
  cell,
}: {
  cell: {
    key: string
    status: CellStatus
    inserted: number
    runs: number
    duration: string | null
    latestStartedAt: string | null
    latestFinishedAt: string | null
    sources: string[]
    error: string | null
    r2?: OpenintelTldStatusItem
  }
}) {
  const meta = STATUS_META[cell.status]
  const title = [
    meta.label,
    cell.runs ? `Execuções no dia: ${cell.runs}` : null,
    cell.sources.length ? `Fontes: ${cell.sources.join(", ")}` : null,
    cell.inserted ? `${cell.inserted.toLocaleString("pt-BR")} domínios adicionados` : null,
    cell.duration ? `Duração: ${cell.duration}` : null,
    cell.latestStartedAt ? `Início: ${formatDateTime(cell.latestStartedAt)}` : null,
    cell.latestFinishedAt ? `Fim: ${formatDateTime(cell.latestFinishedAt)}` : null,
    cell.r2 && cell.status === "delayed"
      ? `R2 disponível ${cell.r2.last_available_snapshot_date}, importado ${cell.r2.last_ingested_snapshot_date ?? "-"}`
      : null,
    cell.error,
  ].filter(Boolean).join(" | ")

  return (
    <div className="border-b border-border-subtle p-px">
      <div
        title={title}
        className={`flex h-7 min-w-0 items-center justify-center rounded-md border px-1 text-center text-[9px] leading-none transition-colors ${meta.className}`}
      >
        {cell.status === "running" ? (
          <div className="inline-flex min-w-0 items-center gap-1 whitespace-nowrap">
            <Loader2 className="h-3 w-3 animate-spin" />
            {cell.duration && <span className="font-mono tabular-nums">{cell.duration}</span>}
          </div>
        ) : cell.status === "failed" ? (
          <div className="inline-flex min-w-0 items-center gap-1 whitespace-nowrap">
            <XCircle className="h-3 w-3" />
            <span className="truncate">falha</span>
            {cell.duration && <span className="font-mono tabular-nums">{cell.duration}</span>}
          </div>
        ) : cell.status === "queued" ? (
          <div className="inline-flex min-w-0 items-center gap-1 whitespace-nowrap">
            <Clock3 className="h-3 w-3" />
            <span className="truncate">fila</span>
          </div>
        ) : cell.status === "delayed" ? (
          <div className="inline-flex min-w-0 items-center gap-1 whitespace-nowrap">
            <Database className="h-3 w-3" />
            <span className="truncate">R2</span>
          </div>
        ) : cell.status === "success" ? (
          <div className="inline-flex min-w-0 items-center gap-1 whitespace-nowrap">
            <CheckCircle2 className="h-3 w-3" />
            <span className="font-mono tabular-nums">{cell.inserted ? formatCount(cell.inserted) : "0"}</span>
            {cell.duration && <span className="font-mono tabular-nums">{cell.duration}</span>}
          </div>
        ) : (
          <span className="h-1.5 w-1.5 rounded-full bg-zinc-300 dark:bg-zinc-700" />
        )}
      </div>
    </div>
  )
}

function R2Count({ label, value, tone }: { label: string; value: number; tone: "warning" | "danger" | "success" | "neutral" }) {
  const toneClass = {
    warning: "text-amber-700 dark:text-amber-300",
    danger: "text-red-700 dark:text-red-300",
    success: "text-emerald-700 dark:text-emerald-300",
    neutral: "text-muted-foreground",
  }[tone]

  return (
    <div className="rounded-md border border-border-subtle p-3">
      <div className={`font-mono text-xl font-semibold tabular-nums ${toneClass}`}>{formatCount(value)}</div>
      <div className="mt-1 text-xs text-muted-foreground">{label}</div>
    </div>
  )
}
