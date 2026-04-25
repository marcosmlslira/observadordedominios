"use client"

import type { IngestionRun } from "@/lib/types"

const SOURCES = [
  { key: "czds", label: "CZDS" },
  { key: "openintel", label: "OpenINTEL" },
] as const

const COLS = 30

function cellColor(status: string | undefined): string {
  switch (status) {
    case "success":
      return "bg-emerald-500"
    case "failed":
      return "bg-red-500"
    case "running":
    case "queued":
      return "bg-blue-500"
    default:
      return "bg-muted"
  }
}

function formatDuration(start: string, end: string | null): string {
  if (!end) return "ongoing"
  const ms = new Date(end).getTime() - new Date(start).getTime()
  const secs = Math.floor(ms / 1000)
  if (secs < 60) return `${secs}s`
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m ${secs % 60}s`
  return `${Math.floor(mins / 60)}h ${mins % 60}m`
}

interface Props {
  runs: IngestionRun[]
}

export function IngestionRunGrid({ runs }: Props) {
  const bySource = new Map<string, IngestionRun[]>()
  for (const source of SOURCES.map((s) => s.key)) {
    const sourceRuns = runs
      .filter((r) => r.source === source)
      .sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime())
      .slice(0, COLS)
    bySource.set(source, sourceRuns)
  }

  return (
    <div className="space-y-2">
      {SOURCES.map(({ key, label }) => {
        const sourceRuns = bySource.get(key) ?? []
        const slots = Array.from({ length: COLS }, (_, i) => sourceRuns[i])

        return (
          <div key={key} className="flex items-center gap-3">
            <span className="w-24 shrink-0 text-right text-xs text-muted-foreground font-mono">
              {label}
            </span>
            <div className="flex gap-0.5">
              {slots.map((run, i) => {
                if (!run) {
                  return (
                    <div
                      key={i}
                      className="h-5 w-3 rounded-sm bg-muted opacity-30"
                    />
                  )
                }
                const tooltip = [
                  `TLD: .${run.tld}`,
                  `Status: ${run.status}`,
                  `Duration: ${formatDuration(run.started_at, run.finished_at)}`,
                  `Inserted: ${run.domains_inserted.toLocaleString()}`,
                  run.error_message ? `Error: ${run.error_message}` : null,
                ]
                  .filter(Boolean)
                  .join("\n")

                return (
                  <div
                    key={run.run_id}
                    title={tooltip}
                    className={`h-5 w-3 rounded-sm cursor-default transition-opacity hover:opacity-70 ${cellColor(run.status)}`}
                  />
                )
              })}
            </div>
            <span className="text-xs text-muted-foreground tabular-nums">
              {sourceRuns.length > 0
                ? `${sourceRuns.filter((r) => r.status === "success").length}/${sourceRuns.length} ok`
                : "no runs"}
            </span>
          </div>
        )
      })}
      <div className="flex items-center gap-3 pt-1 pl-[108px]">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <div className="h-3 w-3 rounded-sm bg-emerald-500" /> success
        </div>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <div className="h-3 w-3 rounded-sm bg-red-500" /> failed
        </div>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <div className="h-3 w-3 rounded-sm bg-blue-500" /> running
        </div>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <div className="h-3 w-3 rounded-sm bg-muted opacity-30" /> no run
        </div>
      </div>
    </div>
  )
}
