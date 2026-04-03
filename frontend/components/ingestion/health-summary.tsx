"use client"

import type { HealthSummary as HealthSummaryType, TldDomainCount } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return n.toLocaleString()
}

interface HealthSummaryProps {
  health: HealthSummaryType | null
  domainCounts: TldDomainCount[]
}

export function HealthSummaryCards({ health, domainCounts }: HealthSummaryProps) {
  const totalDomains = domainCounts.reduce((sum, d) => sum + d.count, 0)
  const totalEnabled = health?.total_tlds_enabled ?? 0

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
      {/* Health bar card */}
      <Card>
        <CardHeader className="pb-1 pt-3 px-4">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Saude do Corpus
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-3">
          <div className="text-lg font-bold tabular-nums">
            {health?.tlds_ok ?? 0} OK
            <span className="text-sm font-normal text-muted-foreground ml-1">
              / {health?.tlds_suspended ?? 0} suspensos / {health?.tlds_failing ?? 0} com falha
            </span>
          </div>
          {totalEnabled > 0 && (
            <div className="mt-2 h-2 w-full rounded-full bg-muted overflow-hidden flex">
              <div
                className="h-full bg-emerald-500 transition-all"
                style={{ width: `${((health?.tlds_ok ?? 0) / totalEnabled) * 100}%` }}
              />
              <div
                className="h-full bg-yellow-500 transition-all"
                style={{ width: `${((health?.tlds_suspended ?? 0) / totalEnabled) * 100}%` }}
              />
              <div
                className="h-full bg-red-500 transition-all"
                style={{ width: `${((health?.tlds_failing ?? 0) / totalEnabled) * 100}%` }}
              />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Total corpus card */}
      <Card>
        <CardHeader className="pb-1 pt-3 px-4">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Corpus Total
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-3">
          <div className="text-2xl font-bold tabular-nums">
            {formatCount(totalDomains)}
          </div>
          <p className="text-xs text-muted-foreground">
            {domainCounts.length} TLDs cobertos
          </p>
        </CardContent>
      </Card>

      {/* TLDs enabled */}
      <Card>
        <CardHeader className="pb-1 pt-3 px-4">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            TLDs Habilitados
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-3">
          <div className="text-2xl font-bold tabular-nums">
            {totalEnabled}
          </div>
          <p className="text-xs text-muted-foreground">
            monitorados ativamente
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
