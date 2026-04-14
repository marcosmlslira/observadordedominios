"use client"

import { useCallback, useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import Link from "next/link"
import { api, monitoringApi } from "@/lib/api"
import type { Brand, BrandListResponse, MatchSnapshot, MatchSnapshotListResponse } from "@/lib/types"
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
import { AlertTriangle, Shield, Eye, Inbox } from "lucide-react"

const BUCKETS = [
  { value: "", label: "Todas as Ameaças", icon: null },
  { value: "immediate_attention", label: "Imediato", icon: AlertTriangle },
  { value: "defensive_gap", label: "Gap Defensivo", icon: Shield },
  { value: "watchlist", label: "Watchlist", icon: Eye },
]

function bucketVariant(bucket: string | null) {
  switch (bucket) {
    case "immediate_attention": return "destructive" as const
    case "defensive_gap": return "secondary" as const
    default: return "outline" as const
  }
}

function bucketLabel(bucket: string | null) {
  switch (bucket) {
    case "immediate_attention": return "Imediato"
    case "defensive_gap": return "Gap Defensivo"
    case "watchlist": return "Watchlist"
    default: return bucket ?? "—"
  }
}

export default function MatchesPage() {
  const searchParams = useSearchParams()
  const router = useRouter()

  const initialBucket = searchParams.get("bucket") ?? ""
  const [selectedBucket, setSelectedBucket] = useState(initialBucket)
  const [offset, setOffset] = useState(0)
  const limit = 50

  const [data, setData] = useState<MatchSnapshotListResponse | null>(null)
  const [brandsById, setBrandsById] = useState<Record<string, Brand>>({})
  const [loading, setLoading] = useState(true)
  const [selectedMatch, setSelectedMatch] = useState<MatchSnapshot | null>(null)

  // Load brands once for name resolution
  useEffect(() => {
    api.get<BrandListResponse>("/v1/brands?active_only=false&limit=200")
      .then((res) => {
        const map: Record<string, Brand> = {}
        for (const b of res.items) map[b.id] = b
        setBrandsById(map)
      })
      .catch(() => {})
  }, [])

  const fetchMatches = useCallback(async () => {
    setLoading(true)
    try {
      const result = await monitoringApi.listAllMatches({
        bucket: selectedBucket || undefined,
        limit,
        offset,
      })
      setData(result)
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [selectedBucket, offset])

  useEffect(() => {
    fetchMatches()
  }, [fetchMatches])

  useEffect(() => {
    setOffset(0)
  }, [selectedBucket])

  function handleBucketChange(bucket: string) {
    setSelectedBucket(bucket)
    router.replace(`/admin/matches${bucket ? `?bucket=${bucket}` : ""}`, { scroll: false })
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Threat Intelligence</h1>
        <p className="text-sm text-muted-foreground mt-1">
          All detected threats across monitored brands
        </p>
      </div>

      {/* Bucket filters */}
      <div className="flex flex-wrap gap-2">
        {BUCKETS.map(({ value, label, icon: Icon }) => (
          <Button
            key={value}
            variant={selectedBucket === value ? "default" : "outline"}
            size="sm"
            onClick={() => handleBucketChange(value)}
            className="gap-1.5"
          >
            {Icon && <Icon className="h-3.5 w-3.5" />}
            {label}
          </Button>
        ))}
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">
            {selectedBucket ? bucketLabel(selectedBucket) : "Todas as Ameaças"}
            {data && (
              <span className="ml-2 font-normal text-muted-foreground">
                ({data.total.toLocaleString()})
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-4 space-y-2">
              {[1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} className="h-10 rounded" />
              ))}
            </div>
          ) : !data || data.items.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-3">
              <Inbox className="h-8 w-8" />
              <p className="text-sm">No threats found for this filter.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Domain</TableHead>
                  <TableHead>Brand</TableHead>
                  <TableHead>Bucket</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>Risk</TableHead>
                  <TableHead>Signals</TableHead>
                  <TableHead>Detected</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((snap) => (
                  <TableRow
                    key={snap.id}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => setSelectedMatch(snap)}
                  >
                    <TableCell className="font-mono text-sm">
                      {snap.domain_name}
                    </TableCell>
                    <TableCell>
                      <Link
                        href={`/admin/brands/${snap.brand_id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="text-xs text-primary hover:underline"
                      >
                        {brandsById[snap.brand_id]?.brand_name ?? snap.brand_id.slice(0, 8) + "…"}
                      </Link>
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

          {data && data.total > limit && (
            <div className="flex items-center justify-between border-t px-4 py-3">
              <p className="text-xs text-muted-foreground">
                {offset + 1}–{Math.min(offset + limit, data.total)} of {data.total}
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
                  disabled={offset + limit >= data.total}
                  onClick={() => setOffset(offset + limit)}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <MatchDrawer
        match={selectedMatch}
        onClose={() => setSelectedMatch(null)}
        onStatusUpdated={fetchMatches}
      />
    </div>
  )
}
