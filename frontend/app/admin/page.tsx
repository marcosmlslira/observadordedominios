"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { api } from "@/lib/api"
import type { BrandListResponse, SimilarityMetrics, SourceSummary } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Shield,
  Download,
  Search,
  Plus,
  CheckCircle2,
  XCircle,
  Loader2,
  Activity,
  AlertTriangle,
  Eye,
  Sparkles,
} from "lucide-react"

const SOURCE_LABELS: Record<string, string> = {
  czds: "CZDS",
  certstream: "CertStream",
  crtsh: "crt.sh",
  "crtsh-bulk": "crt.sh Bulk",
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

export default function DashboardPage() {
  const [brands, setBrands] = useState<BrandListResponse | null>(null)
  const [summaries, setSummaries] = useState<SourceSummary[]>([])
  const [simMetrics, setSimMetrics] = useState<SimilarityMetrics | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.get<BrandListResponse>("/v1/brands?active_only=false"),
      api.get<SourceSummary[]>("/v1/ingestion/summary"),
      api.get<SimilarityMetrics>("/v1/similarity/metrics").catch(() => null),
    ])
      .then(([b, s, m]) => {
        setBrands(b)
        setSummaries(s)
        setSimMetrics(m)
      })
      .finally(() => setLoading(false))
  }, [])

  const totalDomains = summaries.reduce(
    (acc, s) => acc + s.total_domains_inserted,
    0,
  )
  const totalRunning = summaries.reduce((acc, s) => acc + s.running_now, 0)
  const anyFailed = summaries.some(
    (s) => s.last_status === "failed" && s.failed_runs > 0,
  )

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28 rounded-xl" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Dashboard</h1>

      {/* Top summary cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Monitored Brands
            </CardTitle>
            <Shield className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{brands?.total ?? 0}</div>
            <p className="text-xs text-muted-foreground mt-1">
              {brands?.items.filter((b) => b.is_active).length ?? 0} active
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Domains Ingested
            </CardTitle>
            <Download className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold tabular-nums">
              {totalDomains.toLocaleString()}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {summaries.length} sources
              {totalRunning > 0 && (
                <span className="text-blue-500 ml-1">
                  ({totalRunning} running)
                </span>
              )}
              {anyFailed && (
                <span className="text-red-500 ml-1">
                  (has failures)
                </span>
              )}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Quick Actions
            </CardTitle>
            <Search className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent className="flex gap-2">
            <Button size="sm" asChild>
              <Link href="/admin/brands">
                <Plus className="h-3 w-3 mr-1" />
                New Brand
              </Link>
            </Button>
            <Button size="sm" variant="outline" asChild>
              <Link href="/admin/ingestion">View Ingestion</Link>
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Similarity threat intelligence cards */}
      {simMetrics && (
        <div>
          <h2 className="text-base font-semibold mb-3">Inteligência de Ameaças</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <Link href="/admin/matches?bucket=immediate_attention">
              <Card className="hover:border-red-400/50 transition-colors cursor-pointer border-red-200/30">
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    Ameaças Imediatas
                  </CardTitle>
                  <AlertTriangle className="h-4 w-4 text-red-500" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-red-600">
                    {simMetrics.totals.immediate_attention ?? 0}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    <Badge variant="destructive" className="text-[10px] px-1.5 py-0">Imediato</Badge>
                  </p>
                </CardContent>
              </Card>
            </Link>

            <Link href="/admin/matches?bucket=defensive_gap">
              <Card className="hover:border-orange-400/50 transition-colors cursor-pointer border-orange-200/30">
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    Defensive Gap
                  </CardTitle>
                  <Shield className="h-4 w-4 text-orange-500" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-orange-600">
                    {simMetrics.totals.defensive_gap ?? 0}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0 border-orange-300 text-orange-600">Defensivo</Badge>
                  </p>
                </CardContent>
              </Card>
            </Link>

            <Link href="/admin/matches?bucket=watchlist">
              <Card className="hover:border-yellow-400/50 transition-colors cursor-pointer border-yellow-200/30">
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    Watchlist
                  </CardTitle>
                  <Eye className="h-4 w-4 text-yellow-600" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-yellow-700">
                    {simMetrics.totals.watchlist ?? 0}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0 border-yellow-300 text-yellow-600">Watchlist</Badge>
                  </p>
                </CardContent>
              </Card>
            </Link>

            <Link href="/admin/matches">
              <Card className="hover:border-primary/50 transition-colors cursor-pointer">
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    Novos (7 dias)
                  </CardTitle>
                  <Sparkles className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {simMetrics.totals.new_last_7d ?? 0}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    <span className="text-blue-500">{simMetrics.totals.new_last_24h ?? 0}</span> nas últimas 24h
                  </p>
                </CardContent>
              </Card>
            </Link>
          </div>
        </div>
      )}

      {/* Per-source health */}
      <div>
        <h2 className="text-base font-semibold mb-3">Ingestion Sources</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {summaries.map((s) => (
            <Link key={s.source} href={`/admin/ingestion`}>
              <Card className="hover:border-primary/50 transition-colors cursor-pointer">
                <CardHeader className="flex flex-row items-center justify-between pb-1 pt-3 px-4">
                  <CardTitle className="text-sm font-medium">
                    {SOURCE_LABELS[s.source] || s.source}
                  </CardTitle>
                  <StatusIcon status={s.last_status} />
                </CardHeader>
                <CardContent className="px-4 pb-3">
                  <div className="text-lg font-bold tabular-nums">
                    {s.total_domains_inserted.toLocaleString()}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    domains inserted
                  </p>
                  <div className="flex items-center gap-2 mt-2 text-xs">
                    <Badge
                      variant={
                        s.last_status === "success"
                          ? "default"
                          : s.last_status === "failed"
                            ? "destructive"
                            : "secondary"
                      }
                      className="text-[10px] px-1.5 py-0"
                    >
                      {s.last_status || "—"}
                    </Badge>
                    <span className="text-muted-foreground">
                      {timeAgo(s.last_run_at)}
                    </span>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
          {summaries.length === 0 && (
            <p className="col-span-4 text-sm text-muted-foreground">
              No ingestion data yet. Deploy workers to start ingesting domains.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
