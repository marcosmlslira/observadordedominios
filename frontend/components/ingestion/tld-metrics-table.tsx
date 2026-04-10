"use client"

import { useMemo, useState } from "react"
import { Play, Loader2 } from "lucide-react"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import { Switch } from "@/components/ui/switch"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Sparkbar } from "./sparkbar"
import type { TldMetricsRow } from "@/lib/types"

interface TldMetricsTableProps {
  rows: TldMetricsRow[]
  source: string
  onToggle: (tld: string, enabled: boolean) => Promise<void>
  onTrigger?: (tld: string) => Promise<void>
  onEnableAll: () => void
  onDisableAll: () => void
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return "—"
  if (seconds < 60) return `${Math.round(seconds)}s`
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}m ${s}s`
}

function formatCount(n: number | null): string {
  if (n == null) return "—"
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return `${n}`
}

function formatDate(iso: string | null): string {
  if (!iso) return "—"
  const d = new Date(iso)
  const now = new Date()
  const diffH = (now.getTime() - d.getTime()) / 3_600_000
  if (diffH < 24) return `hoje ${d.getUTCHours().toString().padStart(2, "0")}:${d.getUTCMinutes().toString().padStart(2, "0")}`
  if (diffH < 48) return "ontem"
  return d.toLocaleDateString("pt-BR")
}

export function TldMetricsTable({
  rows,
  source,
  onToggle,
  onTrigger,
  onEnableAll,
  onDisableAll,
}: TldMetricsTableProps) {
  const [filter, setFilter] = useState("")
  const [toggling, setToggling] = useState<Set<string>>(new Set())
  const [triggering, setTriggering] = useState<Set<string>>(new Set())
  const [triggered, setTriggered] = useState<Set<string>>(new Set())

  const filtered = useMemo(
    () => rows.filter((r) => r.tld.includes(filter.toLowerCase())),
    [rows, filter]
  )

  const activeCount = rows.filter((r) => r.is_enabled).length

  async function handleToggle(tld: string, enabled: boolean) {
    setToggling((prev) => new Set(prev).add(tld))
    try {
      await onToggle(tld, enabled)
    } finally {
      setToggling((prev) => {
        const next = new Set(prev)
        next.delete(tld)
        return next
      })
    }
  }

  async function handleTrigger(tld: string) {
    if (!onTrigger) return
    setTriggering((prev) => new Set(prev).add(tld))
    try {
      await onTrigger(tld)
      setTriggered((prev) => new Set(prev).add(tld))
      setTimeout(() => setTriggered((prev) => { const n = new Set(prev); n.delete(tld); return n }), 3000)
    } finally {
      setTriggering((prev) => { const n = new Set(prev); n.delete(tld); return n })
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">
          {activeCount} ativos de {rows.length}
        </span>
        <Input
          placeholder="Filtrar TLDs…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="h-7 w-40 text-xs"
        />
        <Button variant="outline" size="sm" className="h-7 text-xs" onClick={onEnableAll}>
          Habilitar todos
        </Button>
        <Button variant="outline" size="sm" className="h-7 text-xs" onClick={onDisableAll}>
          Desabilitar todos
        </Button>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="font-mono text-xs">TLD</TableHead>
              <TableHead className="text-center text-xs">Ativo</TableHead>
              <TableHead className="text-right text-xs">Duração</TableHead>
              <TableHead className="text-right text-xs">Inseridos</TableHead>
              <TableHead className="text-center text-xs">Última OK</TableHead>
              <TableHead className="text-center text-xs">Últimas 10</TableHead>
              {onTrigger && <TableHead className="text-center text-xs">Trigger</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((row) => (
              <TableRow key={row.tld} className={row.is_enabled ? "" : "opacity-50"}>
                <TableCell className="font-mono text-sm font-medium">{row.tld}</TableCell>
                <TableCell className="text-center">
                  <Switch
                    checked={row.is_enabled}
                    disabled={toggling.has(row.tld)}
                    onCheckedChange={(checked) => handleToggle(row.tld, checked)}
                  />
                </TableCell>
                <TableCell className="text-right text-xs tabular-nums text-muted-foreground">
                  {formatDuration(row.last_duration_seconds)}
                </TableCell>
                <TableCell className="text-right text-xs tabular-nums">
                  {formatCount(row.last_domains_inserted)}
                </TableCell>
                <TableCell className="text-center text-xs text-muted-foreground">
                  {formatDate(row.last_successful_run_at)}
                </TableCell>
                <TableCell className="text-center">
                  <Sparkbar
                    runs={row.recent_runs.map((r) => ({
                      status: r.status,
                      duration_seconds: r.duration_seconds,
                    }))}
                  />
                </TableCell>
                {onTrigger && (
                  <TableCell className="text-center">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6"
                      disabled={triggering.has(row.tld) || triggered.has(row.tld)}
                      onClick={() => handleTrigger(row.tld)}
                      title={triggered.has(row.tld) ? "Na fila" : `Executar ${row.tld} agora`}
                    >
                      {triggering.has(row.tld) ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : triggered.has(row.tld) ? (
                        <span className="text-[10px] text-green-600">✓</span>
                      ) : (
                        <Play className="h-3 w-3" />
                      )}
                    </Button>
                  </TableCell>
                )}
              </TableRow>
            ))}
            {filtered.length === 0 && (
              <TableRow>
                <TableCell colSpan={onTrigger ? 7 : 6} className="text-center text-xs text-muted-foreground py-6">
                  Nenhum TLD encontrado
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <p className="text-xs text-muted-foreground">
        Barras: altura proporcional à duração · verde = sucesso · vermelho = erro · cinza = sem dado
      </p>
    </div>
  )
}
