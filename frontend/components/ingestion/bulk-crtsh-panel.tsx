"use client"

import { useState } from "react"
import type { CtBulkChunk, CtBulkJob } from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { PauseCircle, PlayCircle } from "lucide-react"

function statusVariant(status: string) {
  switch (status) {
    case "success":
    case "done": return "default" as const
    case "running":
    case "queued":
    case "pending": return "secondary" as const
    case "failed":
    case "error": return "destructive" as const
    default: return "outline" as const
  }
}

interface BulkCrtshPanelProps {
  bulkJobs: CtBulkJob[]
  bulkChunks: CtBulkChunk[]
  selectedBulkJobId: string
  onSelectJob: (jobId: string) => void
  onStartJob: (tlds: string[], dryRun: boolean) => Promise<void>
  onResumeJob: (jobId: string) => Promise<void>
  onCancelJob: (jobId: string) => Promise<void>
  busy: boolean
  error: string
}

export function BulkCrtshPanel({
  bulkJobs, bulkChunks, selectedBulkJobId,
  onSelectJob, onStartJob, onResumeJob, onCancelJob,
  busy, error,
}: BulkCrtshPanelProps) {
  const [bulkText, setBulkText] = useState("")
  const [dryRun, setDryRun] = useState(false)

  async function handleStart() {
    const tlds = bulkText
      .split(/[\s,]+/)
      .map((item) => item.trim().toLowerCase().replace(/^\./, ""))
      .filter(Boolean)
    await onStartJob(tlds, dryRun)
  }

  return (
    <Card className="border-border-subtle bg-background/70">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">crt.sh Bulk Backfill</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="space-y-3">
            <Label htmlFor="bulk-tlds">Target TLDs</Label>
            <textarea
              id="bulk-tlds"
              value={bulkText}
              onChange={(e) => setBulkText(e.target.value)}
              spellCheck={false}
              className="min-h-[120px] w-full rounded-xl border border-border bg-background px-3 py-3 font-mono text-sm leading-6 outline-none transition focus-visible:ring-2 focus-visible:ring-primary/40"
              placeholder={"br\nio\nde"}
            />
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="bulk-dry-run"
                checked={dryRun}
                onChange={(e) => setDryRun(e.target.checked)}
                className="rounded"
              />
              <Label htmlFor="bulk-dry-run">Dry run</Label>
            </div>
            {error && <p className="text-sm text-red-500">{error}</p>}
            <Button onClick={handleStart} disabled={busy}>
              <PlayCircle className="mr-2 h-4 w-4" />
              {busy ? "Starting..." : "Start Bulk Job"}
            </Button>
          </div>

          <div className="space-y-3">
            <Label>Recent jobs</Label>
            <div className="space-y-2">
              {bulkJobs.length === 0 ? (
                <p className="text-sm text-muted-foreground">No bulk jobs yet</p>
              ) : (
                bulkJobs.map((job) => (
                  <button
                    key={job.job_id}
                    type="button"
                    onClick={() => onSelectJob(job.job_id)}
                    className={`w-full rounded-xl border p-3 text-left transition ${
                      selectedBulkJobId === job.job_id ? "border-primary bg-primary/5" : "border-border"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <Badge variant={statusVariant(job.status)}>{job.status}</Badge>
                      <span className="text-xs text-muted-foreground">{job.done_chunks}/{job.total_chunks} chunks</span>
                    </div>
                    <p className="mt-2 text-xs text-muted-foreground">
                      {job.resolved_tlds.join(", ") || "auto fallback scope"}
                    </p>
                    <div className="mt-3 flex gap-2">
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={busy || !["failed", "success", "cancelled"].includes(job.status)}
                        onClick={(e) => { e.stopPropagation(); void onResumeJob(job.job_id) }}
                      >
                        Resume
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={busy || !["pending", "running", "cancel_requested"].includes(job.status)}
                        onClick={(e) => { e.stopPropagation(); void onCancelJob(job.job_id) }}
                      >
                        <PauseCircle className="mr-1 h-3 w-3" />
                        Cancel
                      </Button>
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>
        </div>

        {selectedBulkJobId && (
          <div className="rounded-xl border border-border overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>TLD</TableHead>
                  <TableHead>Chunk</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Depth</TableHead>
                  <TableHead className="text-right">Raw</TableHead>
                  <TableHead className="text-right">Inserted</TableHead>
                  <TableHead>Error</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {bulkChunks.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="py-6 text-center text-muted-foreground">
                      No chunks loaded for this job
                    </TableCell>
                  </TableRow>
                ) : (
                  bulkChunks.slice(0, 200).map((chunk) => (
                    <TableRow key={chunk.chunk_id}>
                      <TableCell className="font-mono text-xs">.{chunk.target_tld}</TableCell>
                      <TableCell className="font-mono text-xs">{chunk.chunk_key}</TableCell>
                      <TableCell><Badge variant={statusVariant(chunk.status)}>{chunk.status}</Badge></TableCell>
                      <TableCell>{chunk.depth}</TableCell>
                      <TableCell className="text-right tabular-nums">{chunk.raw_domains.toLocaleString()}</TableCell>
                      <TableCell className="text-right tabular-nums">{chunk.inserted_domains.toLocaleString()}</TableCell>
                      <TableCell className="max-w-[280px] truncate text-xs text-red-500">
                        {chunk.last_error_excerpt || "—"}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
