"use client"

import type { SourceSummary } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { CheckCircle2, XCircle, Loader2, Activity } from "lucide-react"

const SOURCE_LABELS: Record<string, string> = {
  czds: "CZDS",
  certstream: "CertStream",
  crtsh: "crt.sh",
  openintel: "OpenINTEL",
  "crtsh-bulk": "crt.sh Bulk",
}

const SUMMARY_SOURCES = ["czds", "certstream", "crtsh", "openintel"] as const

function StatusIcon({ status }: { status: string | null }) {
  switch (status) {
    case "success":
      return <CheckCircle2 className="h-4 w-4 text-emerald-500" />
    case "running":
      return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />
    case "failed":
      return <XCircle className="h-4 w-4 text-red-500" />
    default:
      return <Activity className="h-4 w-4 text-muted-foreground" />
  }
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "never"
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function emptySummary(source: string): SourceSummary {
  return {
    source,
    total_runs: 0, successful_runs: 0, failed_runs: 0, running_now: 0,
    last_run_at: null, last_success_at: null, last_status: null,
    total_domains_seen: 0, total_domains_inserted: 0,
    mode: null, cron_expression: null, status_hint: null, next_expected_run_hint: null,
    bulk_job_status: null, bulk_chunks_total: 0, bulk_chunks_done: 0,
    bulk_chunks_error: 0, bulk_chunks_pending: 0,
  }
}

interface SourceHealthCardsProps {
  summaries: SourceSummary[]
  activeSource: string
  onSourceClick: (source: string) => void
}

export function SourceHealthCards({ summaries, activeSource, onSourceClick }: SourceHealthCardsProps) {
  const summaryMap = new Map(summaries.map((item) => [item.source, item]))

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
      {SUMMARY_SOURCES.map((source) => {
        const s = summaryMap.get(source) || emptySummary(source)
        return (
          <Card
            key={s.source}
            className={`cursor-pointer transition-colors ${
              activeSource === s.source ? "ring-2 ring-primary" : ""
            }`}
            onClick={() =>
              onSourceClick(activeSource === s.source ? "all" : s.source)
            }
          >
            <CardHeader className="flex flex-row items-center justify-between pb-1 pt-3 px-4">
              <CardTitle className="text-sm font-medium">
                {SOURCE_LABELS[s.source] || s.source}
              </CardTitle>
              <StatusIcon status={s.last_status} />
            </CardHeader>
            <CardContent className="px-4 pb-3">
              <div className="text-xl font-bold tabular-nums">
                {s.total_domains_inserted.toLocaleString()}
              </div>
              <p className="text-xs text-muted-foreground">domains inserted</p>
              {s.mode && (
                <p className="mt-1 text-xs text-muted-foreground">{s.mode}</p>
              )}
              <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
                <span>{s.successful_runs} ok</span>
                {s.failed_runs > 0 && (
                  <span className="text-red-500">{s.failed_runs} failed</span>
                )}
                {s.running_now > 0 && (
                  <span className="text-blue-500">{s.running_now} running</span>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Last: {timeAgo(s.last_run_at)}
              </p>
              {s.next_expected_run_hint && (
                <p className="mt-1 text-xs text-muted-foreground">
                  Next: {new Date(s.next_expected_run_hint).toLocaleString()}
                </p>
              )}
            </CardContent>
          </Card>
        )
      })}
      {summaries.length === 0 && (
        <p className="col-span-4 text-sm text-muted-foreground">
          No ingestion data yet
        </p>
      )}
    </div>
  )
}
