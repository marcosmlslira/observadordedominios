"use client"

import { useIngestionData } from "@/hooks/use-ingestion-data"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { CheckCircle2, XCircle, Loader2, Activity, Clock, RefreshCw } from "lucide-react"
import Link from "next/link"

import { RunsTable } from "@/components/ingestion/runs-table"
import { TldCoverageTable } from "@/components/ingestion/tld-coverage-table"
import { BulkCrtshPanel } from "@/components/ingestion/bulk-crtsh-panel"

const SOURCE_CONFIG = [
  { key: "czds",       label: "CZDS",       href: "/admin/ingestion/czds" },
  { key: "certstream", label: "CertStream",  href: "/admin/ingestion/certstream" },
  { key: "openintel",  label: "OpenINTEL",   href: "/admin/ingestion/openintel" },
  { key: "crtsh",      label: "crt.sh",      href: null },
]

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "nunca"
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return "agora"
  if (mins < 60) return `${mins}min atrás`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h atrás`
  return `${Math.floor(hours / 24)}d atrás`
}

function timeUntil(dateStr: string | null): string {
  if (!dateStr) return "—"
  const diff = new Date(dateStr).getTime() - Date.now()
  if (diff <= 0) return "agora"
  const mins = Math.floor(diff / 60_000)
  if (mins < 60) return `em ${mins}min`
  const hours = Math.floor(mins / 60)
  const rem = mins % 60
  return `em ${hours}h${rem > 0 ? ` ${rem}min` : ""}`
}

function formatDuration(startedAt: string, finishedAt: string | null): string {
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now()
  const secs = Math.floor((end - new Date(startedAt).getTime()) / 1000)
  if (secs < 60) return `${secs}s`
  return `${Math.floor(secs / 60)}m ${secs % 60}s`
}

function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return n.toLocaleString()
}

export default function IngestionPage() {
  const data = useIngestionData()

  if (data.loading) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold">Ingestion Monitoring</h1>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-36 rounded-xl" />)}
        </div>
        <Skeleton className="h-48 rounded-xl" />
      </div>
    )
  }

  const activeRuns = data.runs.filter((r) => r.status === "running")

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Ingestion Monitoring</h1>
        <Button variant="outline" size="sm" onClick={data.fetchData}>
          <RefreshCw className="h-3 w-3 mr-1" />
          Refresh
        </Button>
      </div>

      {/* Source status cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {SOURCE_CONFIG.map(({ key, label, href }) => {
          const s = data.summaries.find((x) => x.source === key)
          const isRunning = (s?.running_now ?? 0) > 0
          const status = isRunning ? "running" : (s?.last_status ?? null)

          return (
            <div key={key} className="rounded-lg border bg-card p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-sm">{label}</span>
                <span className={`text-xs flex items-center gap-1 ${
                  isRunning            ? "text-blue-400"
                  : status === "success" ? "text-emerald-500"
                  : status === "failed"  ? "text-red-500"
                  : "text-muted-foreground"
                }`}>
                  {isRunning            ? <Loader2 className="h-3 w-3 animate-spin" />
                  : status === "success" ? <CheckCircle2 className="h-3 w-3" />
                  : status === "failed"  ? <XCircle className="h-3 w-3" />
                  : <Activity className="h-3 w-3" />}
                  {isRunning ? "Rodando" : status === "success" ? "OK" : status ?? "Idle"}
                </span>
              </div>

              {s ? (
                <div className="text-xs text-muted-foreground space-y-1">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span>{s.mode ?? "—"}</span>
                    {s.cron_expression && (
                      <code className="text-[10px] bg-muted px-1 py-0.5 rounded font-mono">
                        {s.cron_expression}
                      </code>
                    )}
                  </div>
                  {s.next_expected_run_hint && !isRunning && (
                    <div className="flex items-center gap-1">
                      <Clock className="h-3 w-3 shrink-0" />
                      <span>Próximo {timeUntil(s.next_expected_run_hint)}</span>
                    </div>
                  )}
                  <div>Último: {timeAgo(s.last_run_at)}</div>
                  <div className="text-foreground font-medium">
                    {formatCount(s.total_domains_inserted)} inseridos
                  </div>
                </div>
              ) : (
                <div className="text-xs text-muted-foreground">Sem dados</div>
              )}

              {href && (
                <Link href={href} className="text-xs text-blue-400 hover:underline block">
                  Configurar →
                </Link>
              )}
            </div>
          )
        })}
      </div>

      {/* Active runs */}
      {activeRuns.length > 0 && (
        <div className="rounded-lg border bg-card overflow-hidden">
          <div className="px-4 py-3 border-b flex items-center gap-2">
            <Loader2 className="h-3.5 w-3.5 text-blue-500 animate-spin" />
            <h2 className="text-sm font-medium">
              Execuções Ativas ({activeRuns.length})
            </h2>
          </div>
          <div className="divide-y">
            {activeRuns.map((r) => (
              <div key={r.run_id} className="px-4 py-2.5 flex items-center gap-4 text-sm">
                <span className="font-medium w-24 shrink-0">{r.source}</span>
                <span className="font-mono text-xs text-muted-foreground w-20 shrink-0">
                  .{r.tld}
                </span>
                <span className="text-xs text-muted-foreground flex-1">
                  iniciado {timeAgo(r.started_at)} · {formatDuration(r.started_at, null)} em andamento
                </span>
                {r.domains_seen > 0 && (
                  <span className="text-xs text-muted-foreground">
                    {formatCount(r.domains_seen)} vistos
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tabs */}
      <Tabs defaultValue="runs">
        <TabsList>
          <TabsTrigger value="runs">Execuções</TabsTrigger>
          <TabsTrigger value="coverage">Cobertura por TLD</TabsTrigger>
          <TabsTrigger value="bulk">Bulk crt.sh</TabsTrigger>
        </TabsList>

        <TabsContent value="runs" className="mt-4">
          <RunsTable
            runs={data.runs}
            activeSource={data.activeSource}
            onSourceChange={data.setActiveSource}
          />
        </TabsContent>

        <TabsContent value="coverage" className="mt-4">
          <TldCoverageTable
            coverage={data.coverage}
            domainCounts={data.domainCounts}
          />
        </TabsContent>

        <TabsContent value="bulk" className="mt-4">
          <BulkCrtshPanel
            bulkJobs={data.bulkJobs}
            bulkChunks={data.bulkChunks}
            selectedBulkJobId={data.selectedBulkJobId}
            onSelectJob={data.setSelectedBulkJobId}
            onStartJob={data.startBulkJob}
            onResumeJob={data.resumeBulkJob}
            onCancelJob={data.cancelBulkJob}
            busy={data.bulkBusy}
            error={data.bulkError}
          />
        </TabsContent>
      </Tabs>
    </div>
  )
}
