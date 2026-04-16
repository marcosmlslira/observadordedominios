"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Activity, AlertCircle, CheckCircle2, Clock, RefreshCw, Wifi } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ingestionApi } from "@/lib/api"
import type { IngestionRun } from "@/lib/types"

function formatDomains(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return `${n}`
}

function formatDuration(start: string, end?: string | null): string {
  const ms = (end ? new Date(end) : new Date()).getTime() - new Date(start).getTime()
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  const rem = s % 60
  return `${m}m ${rem}s`
}

function formatRelative(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const diffH = (now.getTime() - d.getTime()) / 3_600_000
  if (diffH < 1) {
    const m = Math.round(diffH * 60)
    return `há ${m}min`
  }
  if (diffH < 24) return `há ${Math.round(diffH)}h`
  if (diffH < 48) return "ontem"
  return d.toLocaleDateString("pt-BR")
}

function StatusBadge({ status }: { status: string }) {
  if (status === "running") {
    return (
      <Badge className="gap-1 bg-green-500/15 text-green-600 border-green-500/30 animate-pulse">
        <Wifi className="h-3 w-3" />
        Streaming
      </Badge>
    )
  }
  if (status === "success") {
    return (
      <Badge className="gap-1 bg-blue-500/15 text-blue-600 border-blue-500/30">
        <CheckCircle2 className="h-3 w-3" />
        Concluída
      </Badge>
    )
  }
  return (
    <Badge className="gap-1 bg-orange-500/15 text-orange-600 border-orange-500/30">
      <AlertCircle className="h-3 w-3" />
      Reconectando
    </Badge>
  )
}

interface SessionRowProps {
  run: IngestionRun
  isCurrent?: boolean
}

function SessionRow({ run, isCurrent }: SessionRowProps) {
  const [elapsed, setElapsed] = useState(() => formatDuration(run.started_at, run.finished_at))

  useEffect(() => {
    if (run.status !== "running") return
    const id = setInterval(() => {
      setElapsed(formatDuration(run.started_at, null))
    }, 1000)
    return () => clearInterval(id)
  }, [run.started_at, run.status])

  return (
    <div
      className={`flex items-center justify-between gap-3 px-3 py-2 rounded-lg text-sm ${
        isCurrent ? "bg-muted/60" : ""
      }`}
    >
      <div className="flex items-center gap-2 min-w-0">
        <StatusBadge status={run.status} />
        <span className="text-muted-foreground text-xs shrink-0">
          {formatRelative(run.started_at)}
        </span>
        {run.error_message && !isCurrent && (
          <span className="text-xs text-muted-foreground/60 truncate">
            {run.error_message.slice(0, 60)}
          </span>
        )}
      </div>

      <div className="flex items-center gap-4 shrink-0 text-xs">
        <span className="flex items-center gap-1 text-muted-foreground">
          <Clock className="h-3 w-3" />
          {elapsed}
        </span>
        <span className="flex items-center gap-1 font-medium tabular-nums">
          <Activity className="h-3 w-3 text-muted-foreground" />
          {formatDomains(run.domains_inserted)} inseridos
        </span>
      </div>
    </div>
  )
}

interface CertStreamSessionCardProps {
  className?: string
}

export function CertStreamSessionCard({ className }: CertStreamSessionCardProps) {
  const [sessions, setSessions] = useState<IngestionRun[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    else setRefreshing(true)
    try {
      const runs = await ingestionApi.getRuns({ source: "certstream", tld: "multi", limit: 8 })
      setSessions(runs)
    } catch {
      // silently ignore
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    load()
    // Auto-refresh every 15s while a session is running
    intervalRef.current = setInterval(() => load(true), 15_000)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [load])

  const current = sessions.find((s) => s.status === "running")
  const history = sessions.filter((s) => s.status !== "running")

  const totalDomainsAllSessions = sessions.reduce((a, s) => a + (s.domains_inserted ?? 0), 0)

  return (
    <div className={`rounded-xl border bg-card ${className ?? ""}`}>
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <div className="flex items-center gap-2">
          <Wifi className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium">Sessões de Streaming</span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0"
          onClick={() => load(true)}
          disabled={loading || refreshing}
          aria-label="Atualizar sessões"
        >
          <RefreshCw className={`h-3 w-3 ${refreshing ? "animate-spin" : ""}`} />
        </Button>
      </div>

      <div className="p-3">
        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-9 rounded-lg bg-muted/40 animate-pulse" />
            ))}
          </div>
        ) : sessions.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-4">
            Nenhuma sessão registrada ainda.
          </p>
        ) : (
          <div className="space-y-1">
            {current && (
              <>
                <SessionRow run={current} isCurrent />
                {history.length > 0 && (
                  <div className="my-2 border-t" />
                )}
              </>
            )}
            {history.map((run) => (
              <SessionRow key={run.run_id} run={run} />
            ))}
          </div>
        )}

        {sessions.length > 0 && (
          <div className="mt-3 pt-3 border-t flex items-center justify-between text-xs text-muted-foreground">
            <span>{sessions.length} sessões exibidas</span>
            <span className="font-medium tabular-nums">
              {formatDomains(totalDomainsAllSessions)} domínios no total
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
