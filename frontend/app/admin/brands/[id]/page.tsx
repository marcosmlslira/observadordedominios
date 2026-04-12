"use client"

import { useCallback, useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { api, monitoringApi } from "@/lib/api"
import type {
  Brand,
  BrandHealthResponse,
  CycleListResponse,
  MatchSnapshot,
  MatchSnapshotListResponse,
  ScanSummaryResponse,
} from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { MatchDrawer } from "@/components/monitoring/match-drawer"
import {
  ArrowLeft,
  Search,
  CheckCircle,
  XCircle,
  Minus,
  ChevronDown,
  ChevronUp,
} from "lucide-react"

const BUCKETS = [
  { value: "", label: "All" },
  { value: "immediate_attention", label: "Immediate" },
  { value: "defensive_gap", label: "Defensive Gap" },
  { value: "watchlist", label: "Watchlist" },
]

function healthVariant(health: string | undefined) {
  switch (health) {
    case "critical": return "destructive" as const
    case "warning": return "secondary" as const
    case "healthy": return "outline" as const
    default: return "outline" as const
  }
}

function bucketVariant(bucket: string | null) {
  switch (bucket) {
    case "immediate_attention": return "destructive" as const
    case "defensive_gap": return "secondary" as const
    default: return "outline" as const
  }
}

function bucketLabel(bucket: string | null) {
  switch (bucket) {
    case "immediate_attention": return "Immediate"
    case "defensive_gap": return "Defensive Gap"
    case "watchlist": return "Watchlist"
    default: return bucket ?? "—"
  }
}

function CheckIcon({ ok }: { ok: boolean | undefined }) {
  if (ok === undefined) return <Minus className="h-3 w-3 text-muted-foreground" />
  if (ok) return <CheckCircle className="h-3 w-3 text-green-500" />
  return <XCircle className="h-3 w-3 text-destructive" />
}

function CollapsibleSection({
  title,
  defaultOpen = false,
  children,
}: {
  title: string
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <Card>
      <CardHeader
        className="cursor-pointer select-none py-3"
        onClick={() => setOpen((v) => !v)}
      >
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">{title}</CardTitle>
          {open ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          )}
        </div>
      </CardHeader>
      {open && <CardContent>{children}</CardContent>}
    </Card>
  )
}

export default function BrandDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()

  const [brand, setBrand] = useState<Brand | null>(null)
  const [health, setHealth] = useState<BrandHealthResponse | null>(null)
  const [cycles, setCycles] = useState<CycleListResponse | null>(null)
  const [snapshots, setSnapshots] = useState<MatchSnapshotListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [snapshotsLoading, setSnapshotsLoading] = useState(false)

  const [selectedBucket, setSelectedBucket] = useState("")
  const [offset, setOffset] = useState(0)
  const limit = 50

  const [selectedMatch, setSelectedMatch] = useState<MatchSnapshot | null>(null)
  const [scanning, setScanning] = useState(false)

  const fetchBrand = useCallback(async () => {
    const [b, h, c] = await Promise.all([
      api.get<Brand>(`/v1/brands/${id}`),
      monitoringApi.getBrandHealth(id),
      monitoringApi.getCycles(id, 30, 0),
    ])
    setBrand(b)
    setHealth(h)
    setCycles(c)
  }, [id])

  const fetchSnapshots = useCallback(async () => {
    setSnapshotsLoading(true)
    try {
      const data = await monitoringApi.getMatchSnapshots(id, {
        bucket: selectedBucket || undefined,
        limit,
        offset,
      })
      setSnapshots(data)
    } catch {
      // ignore
    } finally {
      setSnapshotsLoading(false)
    }
  }, [id, selectedBucket, offset])

  useEffect(() => {
    fetchBrand().finally(() => setLoading(false))
  }, [fetchBrand])

  useEffect(() => {
    fetchSnapshots()
  }, [fetchSnapshots])

  // Reset offset when bucket filter changes
  useEffect(() => {
    setOffset(0)
  }, [selectedBucket])

  async function handleScan() {
    setScanning(true)
    try {
      await api.post<ScanSummaryResponse>(`/v1/brands/${id}/scan`)
    } catch {
      // ignore
    } finally {
      setScanning(false)
    }
  }

  if (loading || !brand) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32 rounded-xl" />
        <Skeleton className="h-64 rounded-xl" />
      </div>
    )
  }

  const summary = brand.monitoring_summary
  const threats = summary?.threat_counts
  const latestCycle = summary?.latest_cycle

  return (
    <div className="space-y-4">
      {/* Back navigation */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => router.push("/admin/brands")}
        className="-ml-2"
      >
        <ArrowLeft className="h-4 w-4 mr-1" />
        Monitoring Profiles
      </Button>

      {/* Header card */}
      <Card>
        <CardContent className="pt-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-xl font-semibold">{brand.brand_name}</h1>
                <Badge variant={healthVariant(summary?.overall_health)}>
                  {summary?.overall_health ?? "unknown"}
                </Badge>
                {!brand.is_active && <Badge variant="outline">inactive</Badge>}
              </div>
              <p className="font-mono text-xs text-muted-foreground mt-0.5">
                {brand.brand_label}
              </p>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={handleScan}
              disabled={scanning}
            >
              <Search className="h-3 w-3 mr-1" />
              {scanning ? "Queuing..." : "Trigger Scan"}
            </Button>
          </div>

          {/* Threat counters */}
          <div className="grid grid-cols-3 gap-3 mt-4 max-w-sm">
            <div className="rounded-lg bg-destructive/10 p-3 text-center">
              <p className="text-2xl font-bold text-destructive leading-none">
                {threats?.immediate_attention ?? 0}
              </p>
              <p className="text-xs text-muted-foreground mt-1">Immediate</p>
            </div>
            <div className="rounded-lg bg-secondary/50 p-3 text-center">
              <p className="text-2xl font-bold leading-none">
                {threats?.defensive_gap ?? 0}
              </p>
              <p className="text-xs text-muted-foreground mt-1">Defensive</p>
            </div>
            <div className="rounded-lg bg-muted p-3 text-center">
              <p className="text-2xl font-bold leading-none">
                {threats?.watchlist ?? 0}
              </p>
              <p className="text-xs text-muted-foreground mt-1">Watchlist</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Latest cycle status */}
      {latestCycle && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Latest Monitoring Cycle</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-4 text-sm">
              <div>
                <p className="text-xs text-muted-foreground">Date</p>
                <p className="text-xs mt-0.5">{latestCycle.cycle_date}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Health</p>
                <Badge
                  variant={latestCycle.health_status === "completed" ? "outline" : "secondary"}
                  className="mt-0.5"
                >
                  {latestCycle.health_status}
                </Badge>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Scan</p>
                <Badge
                  variant={latestCycle.scan_status === "completed" ? "outline" : "secondary"}
                  className="mt-0.5"
                >
                  {latestCycle.scan_status}
                </Badge>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Threats</p>
                <p className="text-xs mt-0.5 font-semibold">{latestCycle.threats_detected}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">New Matches</p>
                <p className="text-xs mt-0.5">{latestCycle.new_matches_count}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Domain Health */}
      {health && health.domains.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Domain Health</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Domain</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-center">DNS</TableHead>
                  <TableHead className="text-center">SSL</TableHead>
                  <TableHead className="text-center">Email</TableHead>
                  <TableHead className="text-center">Headers</TableHead>
                  <TableHead className="text-center">Blacklist</TableHead>
                  <TableHead>Last Check</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {health.domains.map((d) => (
                  <TableRow key={d.domain_id}>
                    <TableCell className="font-mono text-xs">
                      {d.domain_name}
                      {d.is_primary && (
                        <Badge variant="outline" className="ml-1 text-[10px]">
                          primary
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          d.overall_status === "healthy"
                            ? "outline"
                            : d.overall_status === "critical"
                              ? "destructive"
                              : "secondary"
                        }
                        className="text-[11px]"
                      >
                        {d.overall_status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-center">
                      <CheckIcon ok={d.dns?.ok} />
                    </TableCell>
                    <TableCell className="text-center">
                      <CheckIcon ok={d.ssl?.ok} />
                    </TableCell>
                    <TableCell className="text-center">
                      <CheckIcon ok={d.email_security?.ok} />
                    </TableCell>
                    <TableCell className="text-center">
                      <CheckIcon ok={d.headers?.ok} />
                    </TableCell>
                    <TableCell className="text-center">
                      <CheckIcon ok={d.blacklist?.ok} />
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {d.last_check_at
                        ? new Date(d.last_check_at).toLocaleDateString()
                        : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Threats / Match Snapshots */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <CardTitle className="text-sm font-medium">Threats</CardTitle>
            <div className="flex gap-1">
              {BUCKETS.map((b) => (
                <Button
                  key={b.value}
                  variant={selectedBucket === b.value ? "default" : "outline"}
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => setSelectedBucket(b.value)}
                >
                  {b.label}
                </Button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {snapshotsLoading ? (
            <div className="p-6">
              <Skeleton className="h-40" />
            </div>
          ) : !snapshots || snapshots.items.length === 0 ? (
            <p className="p-6 text-center text-sm text-muted-foreground">
              No threats found
              {selectedBucket ? ` in "${bucketLabel(selectedBucket)}"` : ""}.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Domain</TableHead>
                  <TableHead>Bucket</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>Risk</TableHead>
                  <TableHead>Signals</TableHead>
                  <TableHead>Detected</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {snapshots.items.map((snap) => (
                  <TableRow
                    key={snap.id}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => setSelectedMatch(snap)}
                  >
                    <TableCell className="font-mono text-sm">
                      {snap.domain_name}.{snap.tld}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={bucketVariant(snap.derived_bucket)}
                        className="text-[11px]"
                      >
                        {bucketLabel(snap.derived_bucket)}
                      </Badge>
                    </TableCell>
                    <TableCell className="tabular-nums text-sm">
                      {snap.derived_score != null
                        ? `${(snap.derived_score * 100).toFixed(0)}%`
                        : "—"}
                    </TableCell>
                    <TableCell>
                      {snap.derived_risk && (
                        <Badge
                          variant={
                            snap.derived_risk === "critical" ||
                            snap.derived_risk === "high"
                              ? "destructive"
                              : "secondary"
                          }
                          className="text-[11px]"
                        >
                          {snap.derived_risk}
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {snap.signal_codes.slice(0, 3).map((code) => (
                          <Badge
                            key={code}
                            variant="outline"
                            className="text-[10px] font-mono"
                          >
                            {code}
                          </Badge>
                        ))}
                        {snap.signal_codes.length > 3 && (
                          <Badge variant="outline" className="text-[10px]">
                            +{snap.signal_codes.length - 3}
                          </Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {new Date(snap.first_detected_at).toLocaleDateString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {/* Pagination */}
          {snapshots && snapshots.total > limit && (
            <div className="flex items-center justify-between border-t px-4 py-3">
              <p className="text-xs text-muted-foreground">
                {offset + 1}–{Math.min(offset + limit, snapshots.total)} of{" "}
                {snapshots.total}
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - limit))}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={offset + limit >= snapshots.total}
                  onClick={() => setOffset(offset + limit)}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Brand Configuration (collapsible) */}
      <CollapsibleSection title="Brand Configuration">
        <div className="space-y-3 text-sm">
          <div>
            <p className="text-xs text-muted-foreground mb-1">Official Domains</p>
            <div className="flex flex-wrap gap-1">
              {brand.official_domains.map((d) => (
                <Badge
                  key={d.id}
                  variant={d.is_primary ? "default" : "outline"}
                  className="font-mono text-[11px]"
                >
                  {d.domain_name}
                </Badge>
              ))}
            </div>
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-1">Keywords</p>
            <div className="flex flex-wrap gap-1">
              {brand.keywords.length === 0 ? (
                <span className="text-muted-foreground text-xs">None</span>
              ) : (
                brand.keywords.map((k) => (
                  <Badge key={k} variant="outline" className="text-[11px]">
                    {k}
                  </Badge>
                ))
              )}
            </div>
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-1">Aliases</p>
            <div className="flex flex-wrap gap-1">
              {brand.aliases
                .filter((a) => a.alias_type !== "support_keyword")
                .map((a) => (
                  <Badge key={a.id} variant="secondary" className="text-[11px]">
                    {a.alias_value}
                  </Badge>
                ))}
            </div>
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-1">
              TLD Scope ({brand.tld_scope.length} TLDs)
            </p>
            <div className="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
              {brand.tld_scope.map((tld) => (
                <Badge key={tld} variant="outline" className="font-mono text-[11px]">
                  .{tld}
                </Badge>
              ))}
            </div>
          </div>
          {brand.notes && (
            <div>
              <p className="text-xs text-muted-foreground mb-1">Notes</p>
              <p className="text-xs">{brand.notes}</p>
            </div>
          )}
        </div>
      </CollapsibleSection>

      {/* Cycle History (collapsible) */}
      {cycles && cycles.items.length > 0 && (
        <CollapsibleSection title={`Cycle History (${cycles.total})`}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Health</TableHead>
                <TableHead>Scan</TableHead>
                <TableHead>Enrichment</TableHead>
                <TableHead>Threats</TableHead>
                <TableHead>New Matches</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {cycles.items.map((c) => (
                <TableRow key={c.id}>
                  <TableCell className="text-xs">{c.cycle_date}</TableCell>
                  <TableCell>
                    <Badge
                      variant={c.health_status === "completed" ? "outline" : "secondary"}
                      className="text-[11px]"
                    >
                      {c.health_status}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={c.scan_status === "completed" ? "outline" : "secondary"}
                      className="text-[11px]"
                    >
                      {c.scan_status}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={c.enrichment_status === "completed" ? "outline" : "secondary"}
                      className="text-[11px]"
                    >
                      {c.enrichment_status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm font-medium">{c.threats_detected}</TableCell>
                  <TableCell className="text-sm">{c.new_matches_count}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CollapsibleSection>
      )}

      {/* Match Drawer */}
      <MatchDrawer
        match={selectedMatch}
        onClose={() => setSelectedMatch(null)}
        onStatusUpdated={fetchSnapshots}
      />
    </div>
  )
}
