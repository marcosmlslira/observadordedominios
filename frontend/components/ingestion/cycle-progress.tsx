"use client"

import type { IngestionCycleStatus } from "@/lib/types"
import { Card, CardContent } from "@/components/ui/card"
import { Loader2 } from "lucide-react"

function timeUntil(dateStr: string): string {
  const diff = new Date(dateStr).getTime() - Date.now()
  if (diff <= 0) return "now"
  const mins = Math.floor(diff / 60_000)
  if (mins < 60) return `${mins}min`
  const hours = Math.floor(mins / 60)
  const remainMins = mins % 60
  return remainMins > 0 ? `${hours}h ${remainMins}min` : `${hours}h`
}

function formatTime(dateStr: string | null): string {
  if (!dateStr) return "—"
  return new Date(dateStr).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
}

interface CycleProgressProps {
  cycleStatus: IngestionCycleStatus | null
}

export function CycleProgress({ cycleStatus }: CycleProgressProps) {
  if (!cycleStatus) return null

  const { czds_cycle: cycle, schedules } = cycleStatus
  const czdsSchedule = schedules.find((s) => s.source === "czds")
  const pct = cycle.total_tlds > 0
    ? Math.round(((cycle.completed_tlds + cycle.failed_tlds) / cycle.total_tlds) * 100)
    : 0

  if (cycle.is_active) {
    return (
      <Card className="border-blue-500/30 bg-blue-500/5">
        <CardContent className="py-3 px-4">
          <div className="flex items-center gap-3">
            <Loader2 className="h-4 w-4 text-blue-500 animate-spin shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <span className="text-sm font-medium">
                  {cycle.completed_tlds + cycle.failed_tlds}/{cycle.total_tlds} TLDs
                  {cycle.current_tld && (
                    <span className="text-muted-foreground"> — Processando <span className="font-mono text-blue-500">.{cycle.current_tld}</span></span>
                  )}
                </span>
                {cycle.estimated_completion_at && (
                  <span className="text-xs text-muted-foreground shrink-0">
                    ~{formatTime(cycle.estimated_completion_at)}
                  </span>
                )}
              </div>
              <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                <div
                  className="h-full rounded-full bg-blue-500 transition-all duration-500"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <div className="flex gap-3 mt-1.5 text-xs text-muted-foreground">
                <span className="text-emerald-500">{cycle.completed_tlds} ok</span>
                {cycle.failed_tlds > 0 && <span className="text-red-500">{cycle.failed_tlds} failed</span>}
                {cycle.skipped_tlds > 0 && <span className="text-yellow-500">{cycle.skipped_tlds} skipped</span>}
                {cycle.avg_tld_duration_seconds && (
                  <span>avg {Math.round(cycle.avg_tld_duration_seconds)}s/TLD</span>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

  // Idle state
  return (
    <Card className="border-border-subtle bg-background/70">
      <CardContent className="py-3 px-4">
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            {czdsSchedule?.next_run_at ? (
              <>
                Proximo ciclo CZDS: <span className="font-medium text-foreground">{formatTime(czdsSchedule.next_run_at)}</span>
                <span className="ml-1">(em {timeUntil(czdsSchedule.next_run_at)})</span>
              </>
            ) : (
              "Ciclo CZDS idle"
            )}
          </span>
          {cycle.completed_tlds > 0 && (
            <span className="text-xs text-muted-foreground">
              Ultimo ciclo: {cycle.completed_tlds}/{cycle.total_tlds} OK
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
