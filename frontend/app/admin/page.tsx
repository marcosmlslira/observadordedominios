"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { api } from "@/lib/api"
import type { BrandListResponse, IngestionRun } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Shield, Download, Search, Plus } from "lucide-react"

function statusColor(status: string) {
  switch (status) {
    case "success":
      return "default"
    case "running":
    case "queued":
      return "secondary"
    case "failed":
      return "destructive"
    default:
      return "outline"
  }
}

export default function DashboardPage() {
  const [brands, setBrands] = useState<BrandListResponse | null>(null)
  const [runs, setRuns] = useState<IngestionRun[] | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.get<BrandListResponse>("/v1/brands?active_only=false"),
      api.get<IngestionRun[]>("/v1/czds/runs?limit=5"),
    ])
      .then(([b, r]) => {
        setBrands(b)
        setRuns(r)
      })
      .finally(() => setLoading(false))
  }, [])

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

      {/* Summary cards */}
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
              Recent Ingestion Runs
            </CardTitle>
            <Download className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{runs?.length ?? 0}</div>
            <p className="text-xs text-muted-foreground mt-1">
              {runs?.filter((r) => r.status === "success").length ?? 0} successful
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
              <Link href="/admin/ingestion">Trigger Sync</Link>
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Recent runs */}
      {runs && runs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recent Ingestion Runs</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {runs.map((run) => (
                <div
                  key={run.run_id}
                  className="flex items-center justify-between text-sm py-2 border-b border-border-subtle last:border-0"
                >
                  <div className="flex items-center gap-3">
                    <Badge variant={statusColor(run.status)}>
                      {run.status}
                    </Badge>
                    <span className="font-mono text-xs">.{run.tld}</span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {run.domains_seen.toLocaleString()} domains seen
                    {run.finished_at && (
                      <> &middot; {new Date(run.finished_at).toLocaleString()}</>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
