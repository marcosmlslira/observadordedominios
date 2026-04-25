"use client"

import { useCallback, useEffect, useState } from "react"
import { ArrowLeft, RefreshCw } from "lucide-react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { CronConfigCard } from "./cron-config-card"
import { TldMetricsTable } from "./tld-metrics-table"
import { TldStatusTable } from "./tld-status-table"
import { OrderingModeSelector } from "./ordering-mode-selector"
import type { OrderingMode } from "./ordering-mode-selector"
import {
  getIngestionConfigs,
  getTldPolicies,
  updateIngestionCron,
  patchTldPolicy,
  patchIngestionConfig,
  bulkSetTldPolicies,
  triggerTldIngestion,
  ingestionApi,
} from "@/lib/api"
import type {
  IngestionSourceConfig,
  IngestionTldPolicy,
  OpenintelStatusResponse,
  TldMetricsRow,
  TldStatusResponse,
} from "@/lib/types"

const SOURCE_LABELS: Record<string, string> = {
  czds: "CZDS",
  openintel: "OpenINTEL",
}

// Sources where ordering_mode can be configured
const ORDERING_MODE_SOURCES = new Set(["czds"])

// Sources where individual TLD priority editing is supported
const PRIORITY_SOURCES = new Set(["czds", "openintel"])

interface SourceConfigPageProps {
  source: string
}

function formatUtcDateTime(iso: string | null): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return "—"
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: "UTC",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(d)
}

function overallBadgeLabel(status: OpenintelStatusResponse["overall_status"]): string {
  if (status === "healthy") return "Operando normalmente"
  if (status === "warning") return "Atenção"
  return "Falha"
}

function overallBadgeClass(status: OpenintelStatusResponse["overall_status"]): string {
  if (status === "healthy") return "border-emerald-200 bg-emerald-50 text-emerald-700"
  if (status === "warning") return "border-amber-200 bg-amber-50 text-amber-700"
  return "border-red-200 bg-red-50 text-red-700"
}

export function SourceConfigPage({ source }: SourceConfigPageProps) {
  const [config, setConfig] = useState<IngestionSourceConfig | null>(null)
  const [policies, setPolicies] = useState<IngestionTldPolicy[]>([])
  const [metricsRows, setMetricsRows] = useState<TldMetricsRow[]>([])
  const [openintelStatus, setOpenintelStatus] = useState<OpenintelStatusResponse | null>(null)
  const [tldStatus, setTldStatus] = useState<TldStatusResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const label = SOURCE_LABELS[source] ?? source.toUpperCase()
  const supportsOrderingMode = ORDERING_MODE_SOURCES.has(source)
  const supportsPriority = PRIORITY_SOURCES.has(source)

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [configs, tldPolicies, checkpoints, tldRunMetrics, openintelStatusResponse, tldStatusResponse] = await Promise.all([
        getIngestionConfigs(),
        getTldPolicies(source),
        ingestionApi.getCheckpoints(source),
        ingestionApi.getTldRunMetrics(source, 10),
        source === "openintel" ? ingestionApi.getOpenintelStatus() : Promise.resolve(null),
        ingestionApi.getTldStatus(source),
      ])

      const sourceConfig = configs.find((c) => c.source === source) ?? null
      setConfig(sourceConfig)
      setPolicies(tldPolicies)
      setOpenintelStatus(openintelStatusResponse)
      setTldStatus(tldStatusResponse)

      // Build lookup maps
      const checkpointMap = Object.fromEntries(
        checkpoints.map((c: { tld: string; last_successful_run_at: string | null }) => [
          c.tld,
          c.last_successful_run_at,
        ])
      )
      const metricsMap = Object.fromEntries(
        tldRunMetrics.map((m) => [m.tld, m.runs])
      )
      // Policy priority map (generic table covers both czds and openintel)
      const priorityMap = Object.fromEntries(
        tldPolicies.map((p) => [p.tld, p.priority])
      )
      const openintelMap = openintelStatusResponse
        ? Object.fromEntries(openintelStatusResponse.items.map((item) => [item.tld, item]))
        : {}

      const rows: TldMetricsRow[] = tldPolicies.map((p): TldMetricsRow => {
        const runs = metricsMap[p.tld] ?? []
        const lastRun = runs[0] ?? null
        const openintelItem = openintelMap[p.tld]
        const durationSeconds =
          lastRun?.finished_at && lastRun?.started_at
            ? (new Date(lastRun.finished_at).getTime() - new Date(lastRun.started_at).getTime()) / 1000
            : null

        return {
          tld: p.tld,
          is_enabled: p.is_enabled,
          priority: priorityMap[p.tld] ?? null,
          last_duration_seconds: durationSeconds,
          last_domains_inserted: lastRun?.domains_inserted ?? null,
          last_successful_run_at: checkpointMap[p.tld] ?? null,
          recent_runs: runs
            .slice()
            .reverse() // oldest first for sparkbar
            .map((r) => ({
              status: r.status as "success" | "failed" | "running",
              duration_seconds: r.finished_at
                ? (new Date(r.finished_at).getTime() - new Date(r.started_at).getTime()) / 1000
                : null,
              started_at: r.started_at,
            })),
          domains_inserted_total: p.domains_inserted ?? null,
          last_seen_at: p.last_seen_at ?? null,
          openintel_last_verification_at: openintelItem?.last_verification_at ?? null,
          openintel_last_available_snapshot_date: openintelItem?.last_available_snapshot_date ?? null,
          openintel_last_ingested_snapshot_date: openintelItem?.last_ingested_snapshot_date ?? null,
          openintel_status: openintelItem?.status ?? "no_data",
          openintel_status_reason: openintelItem?.status_reason ?? "Sem dados ainda",
          openintel_last_error_message: openintelItem?.last_error_message ?? null,
        }
      })
      // Default sort: server ordering (execution order = priority field)
      setMetricsRows(rows)
    } catch (e) {
      setError("Erro ao carregar dados. Tente novamente.")
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [source])

  useEffect(() => {
    loadData()
  }, [loadData])

  async function handleSaveCron(cron: string) {
    await updateIngestionCron(source, cron)
    setConfig((prev) => prev ? { ...prev, cron_expression: cron } : prev)
  }

  async function handleSaveOrderingMode(mode: OrderingMode) {
    await patchIngestionConfig(source, mode)
    setConfig((prev) => prev ? { ...prev, ordering_mode: mode } : prev)
  }

  async function handleToggleTld(tld: string, enabled: boolean) {
    await patchTldPolicy(source, tld, { is_enabled: enabled })
    setMetricsRows((prev) =>
      prev.map((r) => (r.tld === tld ? { ...r, is_enabled: enabled } : r))
    )
    setPolicies((prev) =>
      prev.map((p) => (p.tld === tld ? { ...p, is_enabled: enabled } : p))
    )
  }

  async function handlePatchPriority(tld: string, priority: number) {
    await patchTldPolicy(source, tld, { priority })
    setMetricsRows((prev) =>
      prev.map((r) => (r.tld === tld ? { ...r, priority } : r))
    )
    setPolicies((prev) =>
      prev.map((p) => (p.tld === tld ? { ...p, priority } : p))
    )
  }

  async function handleEnableAll() {
    const tlds = metricsRows.map((r) => ({ tld: r.tld, is_enabled: true }))
    await bulkSetTldPolicies(source, tlds)
    setMetricsRows((prev) => prev.map((r) => ({ ...r, is_enabled: true })))
  }

  async function handleDisableAll() {
    const tlds = metricsRows.map((r) => ({ tld: r.tld, is_enabled: false }))
    await bulkSetTldPolicies(source, tlds)
    setMetricsRows((prev) => prev.map((r) => ({ ...r, is_enabled: false })))
  }

  const canTrigger = source === "czds" || source === "openintel"

  async function handleTriggerTld(tld: string) {
    await triggerTldIngestion(source, tld)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href="/admin/ingestion">
            <Button variant="ghost" size="sm" className="gap-1">
              <ArrowLeft className="h-3 w-3" />
              Ingestions
            </Button>
          </Link>
          <h1 className="text-2xl font-semibold">{label}</h1>
        </div>
        <Button variant="outline" size="sm" onClick={loadData} disabled={loading}>
          <RefreshCw className={`h-3 w-3 mr-1 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {error && (
        <p className="text-sm text-destructive">{error}</p>
      )}

      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-20 rounded-xl" />
          <Skeleton className="h-64 rounded-xl" />
        </div>
      ) : (
        <>
          {config && (
            <>
              <CronConfigCard
                initialCron={config.cron_expression}
                onSave={handleSaveCron}
              />
              {supportsOrderingMode && (
                <div className="rounded-xl border p-4">
                  <OrderingModeSelector
                    value={(config.ordering_mode as OrderingMode) || "corpus_first"}
                    onSave={handleSaveOrderingMode}
                  />
                </div>
              )}
            </>
          )}

          {source === "openintel" && openintelStatus && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <span>Status de verificação OpenINTEL</span>
                  <Badge variant="outline" className={overallBadgeClass(openintelStatus.overall_status)}>
                    {overallBadgeLabel(openintelStatus.overall_status)}
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <p className="text-muted-foreground">
                  Última verificação: {formatUtcDateTime(openintelStatus.last_verification_at)} (UTC)
                </p>
                <p>{openintelStatus.overall_message}</p>
                <div className="flex flex-wrap gap-2 text-xs">
                  <Badge variant="outline" className="border-blue-200 bg-blue-50 text-blue-700">
                    Em dia: {openintelStatus.status_counts.up_to_date_no_new_snapshot}
                  </Badge>
                  <Badge variant="outline" className="border-emerald-200 bg-emerald-50 text-emerald-700">
                    Novo ingerido: {openintelStatus.status_counts.new_snapshot_ingested}
                  </Badge>
                  <Badge variant="outline" className="border-amber-200 bg-amber-50 text-amber-700">
                    Atrasado: {openintelStatus.status_counts.delayed}
                  </Badge>
                  <Badge variant="outline" className="border-red-200 bg-red-50 text-red-700">
                    Falha: {openintelStatus.status_counts.failed}
                  </Badge>
                </div>
              </CardContent>
            </Card>
          )}

          {tldStatus && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Status dos TLDs — hoje</CardTitle>
              </CardHeader>
              <CardContent>
                <TldStatusTable
                  items={tldStatus.items}
                  ok_count={tldStatus.ok_count}
                  failed_count={tldStatus.failed_count}
                  running_count={tldStatus.running_count}
                  never_run_count={tldStatus.never_run_count}
                />
              </CardContent>
            </Card>
          )}

          <TldMetricsTable
            rows={metricsRows}
            source={source}
            showPriority={supportsPriority}
            onToggle={handleToggleTld}
            onPatchPriority={supportsPriority ? handlePatchPriority : undefined}
            onTrigger={canTrigger ? handleTriggerTld : undefined}
            onEnableAll={handleEnableAll}
            onDisableAll={handleDisableAll}
          />
        </>
      )}
    </div>
  )
}
