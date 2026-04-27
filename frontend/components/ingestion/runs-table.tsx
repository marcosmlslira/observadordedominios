"use client"

import { useState } from "react"
import type { IngestionRun } from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

const SOURCE_LABELS: Record<string, string> = {
  czds: "CZDS",
  openintel: "OpenINTEL",
}

const ALL_SOURCES = ["all", "czds", "openintel"] as const

function statusVariant(status: string) {
  switch (status) {
    case "success": return "default" as const
    case "running":
    case "queued": return "secondary" as const
    case "failed": return "destructive" as const
    default: return "outline" as const
  }
}

interface RunsTableProps {
  runs: IngestionRun[]
  activeSource: string
  onSourceChange: (source: string) => void
}

export function RunsTable({ runs, activeSource, onSourceChange }: RunsTableProps) {
  const [statusFilter, setStatusFilter] = useState<string | null>(null)

  // Summary counts
  const successCount = runs.filter((r) => r.status === "success").length
  const failedCount = runs.filter((r) => r.status === "failed").length
  const runningCount = runs.filter((r) => r.status === "running" || r.status === "queued").length

  const filtered = statusFilter
    ? runs.filter((r) => r.status === statusFilter || (statusFilter === "running" && r.status === "queued"))
    : runs

  return (
    <div className="space-y-4">
      {/* Source filter */}
      <div className="flex gap-1 border-b border-border-subtle">
        {ALL_SOURCES.map((src) => (
          <button
            key={src}
            onClick={() => onSourceChange(src)}
            className={`px-3 py-1.5 text-sm transition-colors border-b-2 ${
              activeSource === src
                ? "border-primary text-foreground font-medium"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {src === "all" ? "All Sources" : (SOURCE_LABELS[src] || src)}
          </button>
        ))}
      </div>

      {/* Status summary bar */}
      <div className="flex items-center gap-2 text-sm">
        <span className="text-muted-foreground">{runs.length} runs:</span>
        <button
          onClick={() => setStatusFilter(statusFilter === "success" ? null : "success")}
          className={`transition-opacity ${statusFilter && statusFilter !== "success" ? "opacity-40" : ""}`}
        >
          <Badge variant="default" className="cursor-pointer">{successCount} success</Badge>
        </button>
        <button
          onClick={() => setStatusFilter(statusFilter === "failed" ? null : "failed")}
          className={`transition-opacity ${statusFilter && statusFilter !== "failed" ? "opacity-40" : ""}`}
        >
          <Badge variant="destructive" className="cursor-pointer">{failedCount} failed</Badge>
        </button>
        <button
          onClick={() => setStatusFilter(statusFilter === "running" ? null : "running")}
          className={`transition-opacity ${statusFilter && statusFilter !== "running" ? "opacity-40" : ""}`}
        >
          <Badge variant="secondary" className="cursor-pointer">{runningCount} running</Badge>
        </button>
        {statusFilter && (
          <button onClick={() => setStatusFilter(null)} className="text-xs text-muted-foreground underline ml-1">
            clear
          </button>
        )}
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Source</TableHead>
                <TableHead>TLD</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Started</TableHead>
                <TableHead>Finished</TableHead>
                <TableHead className="text-right">Seen</TableHead>
                <TableHead className="text-right">Inserted</TableHead>
                <TableHead className="text-right">Deleted</TableHead>
                <TableHead>Snapshot</TableHead>
                <TableHead>Error</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={10} className="text-center text-muted-foreground py-8">
                    No ingestion runs found
                    {activeSource !== "all" && ` for ${SOURCE_LABELS[activeSource] || activeSource}`}
                  </TableCell>
                </TableRow>
              ) : (
                filtered.map((run) => (
                  <TableRow key={run.run_id}>
                    <TableCell>
                      <Badge variant="outline" className="text-xs">
                        {SOURCE_LABELS[run.source] || run.source}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs">.{run.tld}</TableCell>
                    <TableCell>
                      <Badge
                        variant={statusVariant(run.status)}
                        className={run.status === "running" ? "animate-pulse" : ""}
                      >
                        {run.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs">
                      {new Date(run.started_at).toLocaleString()}
                    </TableCell>
                    <TableCell className="text-xs">
                      {run.finished_at ? new Date(run.finished_at).toLocaleString() : "—"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {run.domains_seen.toLocaleString()}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {run.domains_inserted.toLocaleString()}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {run.domains_deleted.toLocaleString()}
                    </TableCell>
                    <TableCell className="text-xs">
                      {run.snapshot_date || run.artifact_key || "—"}
                    </TableCell>
                    <TableCell className="max-w-[200px] truncate text-xs text-red-500">
                      {run.error_message || "—"}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
