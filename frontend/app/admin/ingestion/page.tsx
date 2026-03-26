"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { api, ingestionApi } from "@/lib/api"
import type {
  CtBulkChunk,
  CtBulkJob,
  CzdsPolicyResponse,
  IngestionRun,
  SourceSummary,
  TldCoverage,
  TriggerSyncResponse,
} from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Play,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Loader2,
  Activity,
  Save,
  PauseCircle,
  PlayCircle,
} from "lucide-react"

const SOURCE_LABELS: Record<string, string> = {
  czds: "CZDS",
  certstream: "CertStream",
  crtsh: "crt.sh",
  "crtsh-bulk": "crt.sh Bulk",
}

const ALL_SOURCES = ["all", "czds", "certstream", "crtsh", "crtsh-bulk"] as const
const SUMMARY_SOURCES = ALL_SOURCES.filter((source) => source !== "all")

function statusVariant(status: string) {
  switch (status) {
    case "success":
      return "default" as const
    case "running":
    case "queued":
      return "secondary" as const
    case "failed":
      return "destructive" as const
    default:
      return "outline" as const
  }
}

function sourceLabel(source: string) {
  return SOURCE_LABELS[source] || source
}

function sourceSummary(summaryMap: Map<string, SourceSummary>, source: string): SourceSummary {
  return (
    summaryMap.get(source) || {
      source,
      total_runs: 0,
      successful_runs: 0,
      failed_runs: 0,
      running_now: 0,
      last_run_at: null,
      last_success_at: null,
      last_status: null,
      total_domains_seen: 0,
      total_domains_inserted: 0,
      mode: null,
      status_hint: null,
      next_expected_run_hint: null,
      bulk_job_status: null,
      bulk_chunks_total: 0,
      bulk_chunks_done: 0,
      bulk_chunks_error: 0,
      bulk_chunks_pending: 0,
    }
  )
}

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

export default function IngestionPage() {
  const [runs, setRuns] = useState<IngestionRun[]>([])
  const [summaries, setSummaries] = useState<SourceSummary[]>([])
  const [coverage, setCoverage] = useState<TldCoverage[]>([])
  const [bulkJobs, setBulkJobs] = useState<CtBulkJob[]>([])
  const [bulkChunks, setBulkChunks] = useState<CtBulkChunk[]>([])
  const [selectedBulkJobId, setSelectedBulkJobId] = useState<string>("")
  const [loading, setLoading] = useState(true)
  const [activeSource, setActiveSource] = useState<string>("all")
  const [dialogOpen, setDialogOpen] = useState(false)
  const [syncTld, setSyncTld] = useState("net")
  const [syncForce, setSyncForce] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [syncError, setSyncError] = useState("")
  const [policyText, setPolicyText] = useState("")
  const [policySource, setPolicySource] = useState<"database" | "env">("env")
  const [policySaving, setPolicySaving] = useState(false)
  const [policyError, setPolicyError] = useState("")
  const [bulkText, setBulkText] = useState("")
  const [bulkDryRun, setBulkDryRun] = useState(false)
  const [bulkBusy, setBulkBusy] = useState(false)
  const [bulkError, setBulkError] = useState("")
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchData = useCallback(async () => {
    try {
      const sourceParam = activeSource === "all" ? "" : `&source=${activeSource}`
      const [runsData, summaryData, policyData, coverageData, bulkJobsData] = await Promise.all([
        api.get<IngestionRun[]>(`/v1/ingestion/runs?limit=50${sourceParam}`),
        api.get<SourceSummary[]>("/v1/ingestion/summary"),
        api.get<CzdsPolicyResponse>("/v1/czds/policy"),
        ingestionApi.getCoverage(),
        ingestionApi.listBulkJobs(),
      ])
      setRuns(runsData)
      setSummaries(summaryData)
      setPolicyText(policyData.tlds.join("\n"))
      setPolicySource(policyData.source)
      setCoverage(coverageData)
      setBulkJobs(bulkJobsData)
      const currentJobId = selectedBulkJobId || bulkJobsData[0]?.job_id || ""
      if (!selectedBulkJobId && bulkJobsData[0]) {
        setSelectedBulkJobId(bulkJobsData[0].job_id)
      }
      if (currentJobId) {
        const chunkData = await ingestionApi.getBulkChunks(currentJobId)
        setBulkChunks(chunkData)
      } else {
        setBulkChunks([])
      }
    } catch {
      // ignore
    }
  }, [activeSource, selectedBulkJobId])

  const fetchBulkChunks = useCallback(async (jobId: string) => {
    if (!jobId) {
      setBulkChunks([])
      return
    }
    try {
      const items = await ingestionApi.getBulkChunks(jobId)
      setBulkChunks(items)
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    setLoading(true)
    fetchData().then(() => setLoading(false))
  }, [fetchData])

  // Auto-refresh when there are running runs
  useEffect(() => {
    const hasActiveRuns = runs.some(
      (r) => r.status === "running" || r.status === "queued",
    )
    const hasActiveBulk = bulkJobs.some((job) =>
      ["pending", "running", "cancel_requested"].includes(job.status),
    )
    const hasActive = hasActiveRuns || hasActiveBulk
    if (hasActive && !pollRef.current) {
      pollRef.current = setInterval(fetchData, 10_000)
    } else if (!hasActive && pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [bulkJobs, fetchData, runs])

  async function handleTriggerSync() {
    setSyncing(true)
    setSyncError("")
    try {
      await api.post<TriggerSyncResponse>("/v1/czds/trigger-sync", {
        tld: syncTld,
        force: syncForce,
      })
      setDialogOpen(false)
      await fetchData()
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : "Sync failed")
    } finally {
      setSyncing(false)
    }
  }

  async function handleSavePolicy() {
    setPolicySaving(true)
    setPolicyError("")

    try {
      const tlds = policyText
        .split(/[\s,]+/)
        .map((item) => item.trim().toLowerCase().replace(/^\./, ""))
        .filter(Boolean)

      const response = await api.put<CzdsPolicyResponse>("/v1/czds/policy", {
        tlds,
      })

      setPolicyText(response.tlds.join("\n"))
      setPolicySource(response.source)
    } catch (err) {
      setPolicyError(err instanceof Error ? err.message : "Failed to save policy")
    } finally {
      setPolicySaving(false)
    }
  }

  async function handleStartBulkJob() {
    setBulkBusy(true)
    setBulkError("")
    try {
      const tlds = bulkText
        .split(/[\s,]+/)
        .map((item) => item.trim().toLowerCase().replace(/^\./, ""))
        .filter(Boolean)
      const job = await ingestionApi.startBulkJob({ tlds, dry_run: bulkDryRun })
      setSelectedBulkJobId(job.job_id)
      await fetchData()
      await fetchBulkChunks(job.job_id)
    } catch (err) {
      setBulkError(err instanceof Error ? err.message : "Failed to start bulk job")
    } finally {
      setBulkBusy(false)
    }
  }

  async function handleResumeBulkJob(jobId: string) {
    setBulkBusy(true)
    setBulkError("")
    try {
      await ingestionApi.resumeBulkJob(jobId)
      setSelectedBulkJobId(jobId)
      await fetchData()
      await fetchBulkChunks(jobId)
    } catch (err) {
      setBulkError(err instanceof Error ? err.message : "Failed to resume bulk job")
    } finally {
      setBulkBusy(false)
    }
  }

  async function handleCancelBulkJob(jobId: string) {
    setBulkBusy(true)
    setBulkError("")
    try {
      await ingestionApi.cancelBulkJob(jobId)
      await fetchData()
      await fetchBulkChunks(jobId)
    } catch (err) {
      setBulkError(err instanceof Error ? err.message : "Failed to cancel bulk job")
    } finally {
      setBulkBusy(false)
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold">Ingestion Monitoring</h1>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-96 rounded-xl" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Ingestion Monitoring</h1>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchData}>
            <RefreshCw className="h-3 w-3 mr-1" />
            Refresh
          </Button>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button size="sm">
                <Play className="h-3 w-3 mr-1" />
                Trigger CZDS Sync
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Trigger CZDS Sync</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 pt-2">
                <div className="space-y-2">
                  <Label htmlFor="tld">TLD</Label>
                  <Input
                    id="tld"
                    value={syncTld}
                    onChange={(e) => setSyncTld(e.target.value)}
                    placeholder="net"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="force"
                    checked={syncForce}
                    onChange={(e) => setSyncForce(e.target.checked)}
                    className="rounded"
                  />
                  <Label htmlFor="force">Force (ignore cooldown)</Label>
                </div>
                {syncError && (
                  <p className="text-sm text-red-500">{syncError}</p>
                )}
                <Button
                  onClick={handleTriggerSync}
                  disabled={syncing || !syncTld}
                  className="w-full"
                >
                  {syncing ? "Triggering..." : "Trigger Sync"}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      <Card className="border-border-subtle bg-background/70">
        <CardHeader className="pb-3">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-1">
              <CardTitle className="text-base">CZDS Scope</CardTitle>
              <p className="text-sm text-muted-foreground">
                One worker, one queue. The order below is the exact priority order
                used by the CZDS ingestor.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="outline">
                Source: {policySource === "database" ? "database" : "env fallback"}
              </Badge>
              <Badge variant="secondary">
                {policyText
                  .split(/[\s,]+/)
                  .map((item) => item.trim())
                  .filter(Boolean).length}{" "}
                active TLDs
              </Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <textarea
            value={policyText}
            onChange={(e) => setPolicyText(e.target.value)}
            spellCheck={false}
            className="min-h-[220px] w-full rounded-xl border border-border bg-background px-3 py-3 font-mono text-sm leading-6 outline-none transition focus-visible:ring-2 focus-visible:ring-primary/40"
            placeholder={"com\nnet\norg"}
          />
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="space-y-1 text-xs text-muted-foreground">
              <p>
                Save updates `czds_tld_policy` immediately. New order applies to the
                next worker cycle.
              </p>
              <p>
                For an immediate single-TLD run, keep using <span className="font-medium">Trigger CZDS Sync</span>.
              </p>
              {policyError && <p className="text-red-500">{policyError}</p>}
            </div>
            <Button
              onClick={handleSavePolicy}
              disabled={policySaving || !policyText.trim()}
              className="min-w-40"
            >
              <Save className="mr-2 h-4 w-4" />
              {policySaving ? "Saving..." : "Save CZDS Scope"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="border-border-subtle bg-background/70">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Effective TLD Coverage</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="rounded-xl border border-border overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>TLD</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>CZDS</TableHead>
                  <TableHead>CT</TableHead>
                  <TableHead>Priority</TableHead>
                  <TableHead>Last stream</TableHead>
                  <TableHead>Last crt.sh</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {coverage.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="py-6 text-center text-muted-foreground">
                      No coverage data available
                    </TableCell>
                  </TableRow>
                ) : (
                  coverage.map((item) => (
                    <TableRow key={item.tld}>
                      <TableCell className="font-mono text-xs">.{item.tld}</TableCell>
                      <TableCell>
                        <Badge variant={item.effective_source === "ct_fallback" ? "secondary" : "outline"}>
                          {item.effective_source === "ct_fallback" ? "CT fallback" : "CZDS"}
                        </Badge>
                        {item.fallback_reason && (
                          <p className="mt-1 text-xs text-muted-foreground">{item.fallback_reason}</p>
                        )}
                      </TableCell>
                      <TableCell>{item.czds_available ? "available" : "no"}</TableCell>
                      <TableCell>{item.ct_enabled ? "enabled" : "off"}</TableCell>
                      <TableCell>{item.priority_group}</TableCell>
                      <TableCell className="text-xs">{item.last_ct_stream_seen_at ? new Date(item.last_ct_stream_seen_at).toLocaleString() : "—"}</TableCell>
                      <TableCell className="text-xs">{item.last_crtsh_success_at ? new Date(item.last_crtsh_success_at).toLocaleString() : "—"}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

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
                  checked={bulkDryRun}
                  onChange={(e) => setBulkDryRun(e.target.checked)}
                  className="rounded"
                />
                <Label htmlFor="bulk-dry-run">Dry run</Label>
              </div>
              {bulkError && <p className="text-sm text-red-500">{bulkError}</p>}
              <Button onClick={handleStartBulkJob} disabled={bulkBusy}>
                <PlayCircle className="mr-2 h-4 w-4" />
                {bulkBusy ? "Starting..." : "Start Bulk Job"}
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
                      onClick={() => setSelectedBulkJobId(job.job_id)}
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
                          disabled={bulkBusy || !["failed", "success", "cancelled"].includes(job.status)}
                          onClick={(e) => {
                            e.stopPropagation()
                            void handleResumeBulkJob(job.job_id)
                          }}
                        >
                          Resume
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={bulkBusy || !["pending", "running", "cancel_requested"].includes(job.status)}
                          onClick={(e) => {
                            e.stopPropagation()
                            void handleCancelBulkJob(job.job_id)
                          }}
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

      {/* Source health cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {SUMMARY_SOURCES.map((source) => {
          const s = sourceSummary(new Map(summaries.map((item) => [item.source, item])), source)
          return (
          <Card
            key={s.source}
            className={`cursor-pointer transition-colors ${
              activeSource === s.source ? "ring-2 ring-primary" : ""
            }`}
            onClick={() =>
              setActiveSource(activeSource === s.source ? "all" : s.source)
            }
          >
            <CardHeader className="flex flex-row items-center justify-between pb-1 pt-3 px-4">
              <CardTitle className="text-sm font-medium">
                {sourceLabel(s.source)}
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
                  <span className="text-blue-500">
                    {s.running_now} running
                  </span>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Last: {timeAgo(s.last_run_at)}
              </p>
              {s.status_hint && (
                <p className="mt-1 text-xs text-muted-foreground">
                  {s.status_hint}
                </p>
              )}
              {s.next_expected_run_hint && (
                <p className="mt-1 text-xs text-muted-foreground">
                  Next expected: {new Date(s.next_expected_run_hint).toLocaleString()}
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

      {/* Source filter tabs */}
      <div className="flex gap-1 border-b border-border-subtle">
        {ALL_SOURCES.map((src) => (
          <button
            key={src}
            onClick={() => setActiveSource(src)}
            className={`px-3 py-1.5 text-sm transition-colors border-b-2 ${
              activeSource === src
                ? "border-primary text-foreground font-medium"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {src === "all" ? "All Sources" : sourceLabel(src)}
          </button>
        ))}
      </div>

      {/* Runs table */}
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
                <TableHead>Error</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={9}
                    className="text-center text-muted-foreground py-8"
                  >
                    No ingestion runs found
                    {activeSource !== "all" && ` for ${sourceLabel(activeSource)}`}
                  </TableCell>
                </TableRow>
              ) : (
                runs.map((run) => (
                  <TableRow key={run.run_id}>
                    <TableCell>
                      <Badge variant="outline" className="text-xs">
                        {sourceLabel(run.source)}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      .{run.tld}
                    </TableCell>
                    <TableCell>
                      <Badge variant={statusVariant(run.status)}>
                        {run.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs">
                      {new Date(run.started_at).toLocaleString()}
                    </TableCell>
                    <TableCell className="text-xs">
                      {run.finished_at
                        ? new Date(run.finished_at).toLocaleString()
                        : "—"}
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
