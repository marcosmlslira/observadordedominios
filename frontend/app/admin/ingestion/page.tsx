"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { api } from "@/lib/api"
import type { IngestionRun, TriggerSyncResponse } from "@/lib/types"
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
import { Play, RefreshCw } from "lucide-react"

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

export default function IngestionPage() {
  const [runs, setRuns] = useState<IngestionRun[]>([])
  const [loading, setLoading] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [syncTld, setSyncTld] = useState("net")
  const [syncForce, setSyncForce] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [syncError, setSyncError] = useState("")
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchRuns = useCallback(async () => {
    try {
      const data = await api.get<IngestionRun[]>("/v1/czds/runs?limit=50")
      setRuns(data)
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    fetchRuns().then(() => setLoading(false))
  }, [fetchRuns])

  // Auto-refresh when there are running/queued runs
  useEffect(() => {
    const hasActive = runs.some(
      (r) => r.status === "running" || r.status === "queued",
    )
    if (hasActive && !pollRef.current) {
      pollRef.current = setInterval(fetchRuns, 10_000)
    } else if (!hasActive && pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [runs, fetchRuns])

  async function handleTriggerSync() {
    setSyncing(true)
    setSyncError("")
    try {
      await api.post<TriggerSyncResponse>("/v1/czds/trigger-sync", {
        tld: syncTld,
        force: syncForce,
      })
      setDialogOpen(false)
      await fetchRuns()
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : "Sync failed")
    } finally {
      setSyncing(false)
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold">Ingestion Runs</h1>
        <Skeleton className="h-96 rounded-xl" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Ingestion Runs</h1>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchRuns}>
            <RefreshCw className="h-3 w-3 mr-1" />
            Refresh
          </Button>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button size="sm">
                <Play className="h-3 w-3 mr-1" />
                Trigger Sync
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
                  <p className="text-sm text-error">{syncError}</p>
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

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
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
                  <TableCell colSpan={8} className="text-center text-muted-foreground py-8">
                    No ingestion runs found
                  </TableCell>
                </TableRow>
              ) : (
                runs.map((run) => (
                  <TableRow key={run.run_id}>
                    <TableCell className="font-mono">.{run.tld}</TableCell>
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
                    <TableCell className="max-w-[200px] truncate text-xs text-error">
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
