"use client"

import { useCallback, useEffect, useState } from "react"
import { ArrowLeft, RefreshCw } from "lucide-react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { CronConfigCard } from "./cron-config-card"
import { TldMetricsTable } from "./tld-metrics-table"
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
  TldMetricsRow,
} from "@/lib/types"

const SOURCE_LABELS: Record<string, string> = {
  czds: "CZDS",
  certstream: "CertStream",
  openintel: "OpenINTEL",
}

// Sources where ordering_mode can be configured
const ORDERING_MODE_SOURCES = new Set(["czds"])

// Sources where individual TLD priority editing is supported
const PRIORITY_SOURCES = new Set(["czds", "openintel"])

interface SourceConfigPageProps {
  source: string
}

export function SourceConfigPage({ source }: SourceConfigPageProps) {
  const [config, setConfig] = useState<IngestionSourceConfig | null>(null)
  const [policies, setPolicies] = useState<IngestionTldPolicy[]>([])
  const [metricsRows, setMetricsRows] = useState<TldMetricsRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const label = SOURCE_LABELS[source] ?? source.toUpperCase()
  const isContinuousStream = source === "certstream"
  const supportsOrderingMode = ORDERING_MODE_SOURCES.has(source)
  const supportsPriority = PRIORITY_SOURCES.has(source)

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [configs, tldPolicies, checkpoints, tldRunMetrics] = await Promise.all([
        getIngestionConfigs(),
        getTldPolicies(source),
        ingestionApi.getCheckpoints(source),
        ingestionApi.getTldRunMetrics(source, 10),
      ])

      const sourceConfig = configs.find((c) => c.source === source) ?? null
      setConfig(sourceConfig)
      setPolicies(tldPolicies)

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

      const rows: TldMetricsRow[] = tldPolicies.map((p): TldMetricsRow => {
        const runs = metricsMap[p.tld] ?? []
        const lastRun = runs[0] ?? null
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
                source={source}
                initialCron={config.cron_expression}
                isContinuousStream={isContinuousStream}
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
