"use client"

import { useMemo, useState } from "react"
import { Play, Loader2, ChevronsUpDown, ChevronUp, ChevronDown } from "lucide-react"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Sparkbar } from "./sparkbar"
import type { TldMetricsRow } from "@/lib/types"

type SortKey =
  | "execution_order"
  | "tld"
  | "priority"
  | "last_successful_run_at"
  | "last_duration_seconds"
  | "last_domains_inserted"
  | "domains_inserted_total"
  | "last_seen_at"
  | "openintel_last_verification_at"
  | "openintel_last_available_snapshot_date"
  | "openintel_last_ingested_snapshot_date"
  | "openintel_status"
type SortDir = "asc" | "desc"

interface TldMetricsTableProps {
  rows: TldMetricsRow[]
  source: string
  /** If true, show the Priority column with inline edit */
  showPriority?: boolean
  onToggle: (tld: string, enabled: boolean) => Promise<void>
  onPatchPriority?: (tld: string, priority: number) => Promise<void>
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

function formatUtcDateTime(iso: string | null | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return "—"
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: "UTC",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(d)
}

function formatSnapshotDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—"
  const parts = dateStr.split("-")
  if (parts.length !== 3) return dateStr
  return `${parts[2]}/${parts[1]}/${parts[0]}`
}

function openintelStatusLabel(status: TldMetricsRow["openintel_status"]): string {
  switch (status) {
    case "new_snapshot_ingested":
      return "Novo arquivo ingerido"
    case "up_to_date_no_new_snapshot":
      return "Em dia (sem novo arquivo)"
    case "delayed":
      return "Atrasado"
    case "failed":
      return "Falha na execução"
    case "no_data":
      return "Sem dados ainda"
    default:
      return "Sem dados ainda"
  }
}

function openintelStatusClass(status: TldMetricsRow["openintel_status"]): string {
  switch (status) {
    case "new_snapshot_ingested":
      return "border-emerald-200 bg-emerald-50 text-emerald-700"
    case "up_to_date_no_new_snapshot":
      return "border-blue-200 bg-blue-50 text-blue-700"
    case "delayed":
      return "border-amber-200 bg-amber-50 text-amber-700"
    case "failed":
      return "border-red-200 bg-red-50 text-red-700"
    default:
      return "border-slate-200 bg-slate-50 text-slate-700"
  }
}

function SortIcon({ col, sortKey, dir }: { col: SortKey; sortKey: SortKey; dir: SortDir }) {
  if (col !== sortKey) return <ChevronsUpDown className="ml-1 h-3 w-3 opacity-40 inline-block" />
  return dir === "asc"
    ? <ChevronUp className="ml-1 h-3 w-3 inline-block" />
    : <ChevronDown className="ml-1 h-3 w-3 inline-block" />
}

export function TldMetricsTable({
  rows,
  source,
  showPriority = false,
  onToggle,
  onPatchPriority,
  onTrigger,
  onEnableAll,
  onDisableAll,
}: TldMetricsTableProps) {
  const isOpenintel = source === "openintel"
  const [filter, setFilter] = useState("")
  const [toggling, setToggling] = useState<Set<string>>(new Set())
  const [triggering, setTriggering] = useState<Set<string>>(new Set())
  const [triggered, setTriggered] = useState<Set<string>>(new Set())
  const [savingPriority, setSavingPriority] = useState<Set<string>>(new Set())
  const [editingPriority, setEditingPriority] = useState<Record<string, string>>({})

  // Default sort: execution_order (the order the server returns rows)
  const [sortKey, setSortKey] = useState<SortKey>("execution_order")
  const [sortDir, setSortDir] = useState<SortDir>("asc")

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    } else {
      setSortKey(key)
      setSortDir("asc")
    }
  }

  const sorted = useMemo(() => {
    const base = rows.filter((r) => r.tld.toLowerCase().includes(filter.toLowerCase()))
    if (sortKey === "execution_order") return base // preserve server order

    return [...base].sort((a, b) => {
      let cmp = 0
      switch (sortKey) {
        case "tld":
          cmp = a.tld.localeCompare(b.tld)
          break
        case "priority":
          cmp = (a.priority ?? Number.MAX_SAFE_INTEGER) - (b.priority ?? Number.MAX_SAFE_INTEGER)
          break
        case "last_successful_run_at":
          cmp = (a.last_successful_run_at ?? "").localeCompare(b.last_successful_run_at ?? "")
          break
        case "last_duration_seconds":
          cmp = (a.last_duration_seconds ?? -1) - (b.last_duration_seconds ?? -1)
          break
        case "last_domains_inserted":
          cmp = (a.last_domains_inserted ?? -1) - (b.last_domains_inserted ?? -1)
          break
        case "domains_inserted_total":
          cmp = (a.domains_inserted_total ?? -1) - (b.domains_inserted_total ?? -1)
          break
        case "last_seen_at":
          cmp = (a.last_seen_at ?? "").localeCompare(b.last_seen_at ?? "")
          break
        case "openintel_last_verification_at":
          cmp = (a.openintel_last_verification_at ?? "").localeCompare(b.openintel_last_verification_at ?? "")
          break
        case "openintel_last_available_snapshot_date":
          cmp = (a.openintel_last_available_snapshot_date ?? "").localeCompare(b.openintel_last_available_snapshot_date ?? "")
          break
        case "openintel_last_ingested_snapshot_date":
          cmp = (a.openintel_last_ingested_snapshot_date ?? "").localeCompare(b.openintel_last_ingested_snapshot_date ?? "")
          break
        case "openintel_status":
          cmp = (a.openintel_status ?? "").localeCompare(b.openintel_status ?? "")
          break
      }
      return sortDir === "asc" ? cmp : -cmp
    })
  }, [rows, filter, sortKey, sortDir])

  const activeCount = rows.filter((r) => r.is_enabled).length
  const baseColCount = isOpenintel ? 7 : 6  // TLD + Ativo + source-specific columns
  const colSpan = baseColCount + (showPriority ? 1 : 0) + (onTrigger ? 1 : 0)

  async function handleToggle(tld: string, enabled: boolean) {
    setToggling((prev) => new Set(prev).add(tld))
    try {
      await onToggle(tld, enabled)
    } finally {
      setToggling((prev) => { const n = new Set(prev); n.delete(tld); return n })
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

  function handlePriorityChange(tld: string, value: string) {
    setEditingPriority((prev) => ({ ...prev, [tld]: value }))
  }

  async function commitPriority(tld: string) {
    if (!onPatchPriority) return
    const raw = editingPriority[tld]
    if (raw === undefined) return
    const num = parseInt(raw, 10)
    if (!Number.isFinite(num) || num < 1) return
    setSavingPriority((prev) => new Set(prev).add(tld))
    try {
      await onPatchPriority(tld, num)
    } finally {
      setSavingPriority((prev) => { const n = new Set(prev); n.delete(tld); return n })
      setEditingPriority((prev) => { const { [tld]: _, ...rest } = prev; return rest })
    }
  }

  function handlePriorityKeyDown(e: React.KeyboardEvent<HTMLInputElement>, tld: string) {
    if (e.key === "Enter") commitPriority(tld)
    if (e.key === "Escape") setEditingPriority((prev) => { const { [tld]: _, ...rest } = prev; return rest })
  }

  function SortableHead({
    col,
    className,
    children,
  }: {
    col: SortKey
    className?: string
    children: React.ReactNode
  }) {
    return (
      <TableHead
        className={`cursor-pointer select-none text-xs ${className ?? ""}`}
        onClick={() => handleSort(col)}
        aria-sort={sortKey === col ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
      >
        {children}
        <SortIcon col={col} sortKey={sortKey} dir={sortDir} />
      </TableHead>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
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
              <SortableHead col="tld" className="font-mono">TLD</SortableHead>
              <TableHead className="text-center text-xs">Ativo</TableHead>
              {showPriority && (
                <SortableHead col="priority" className="text-right">Prioridade</SortableHead>
              )}
              {isOpenintel ? (
                <>
                  <SortableHead col="last_domains_inserted" className="text-right">Inseridos</SortableHead>
                  <SortableHead col="openintel_last_verification_at" className="text-center">Última verificação</SortableHead>
                  <SortableHead col="openintel_last_available_snapshot_date" className="text-center">Último snapshot disponível</SortableHead>
                  <SortableHead col="openintel_last_ingested_snapshot_date" className="text-center">Último snapshot ingerido</SortableHead>
                  <SortableHead col="openintel_status" className="text-center">Situação</SortableHead>
                </>
              ) : (
                <>
                  <SortableHead col="last_duration_seconds" className="text-right">Duração</SortableHead>
                  <SortableHead col="last_domains_inserted" className="text-right">Inseridos</SortableHead>
                  <SortableHead col="last_successful_run_at" className="text-center">Última OK</SortableHead>
                  <TableHead className="text-center text-xs">Últimas 10</TableHead>
                </>
              )}
              {onTrigger && <TableHead className="text-center text-xs">Trigger</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((row) => (
              <TableRow key={row.tld} className={row.is_enabled ? "" : "opacity-50"}>
                <TableCell className="font-mono text-sm font-medium">{row.tld}</TableCell>
                <TableCell className="text-center">
                  <Switch
                    checked={row.is_enabled}
                    disabled={toggling.has(row.tld)}
                    onCheckedChange={(checked) => handleToggle(row.tld, checked)}
                  />
                </TableCell>
                {showPriority && (
                  <TableCell className="text-right">
                    <Input
                      type="number"
                      min={1}
                      className="h-6 w-16 text-xs text-right tabular-nums ml-auto"
                      value={editingPriority[row.tld] ?? (row.priority ?? "")}
                      aria-label={`Prioridade do TLD ${row.tld}`}
                      disabled={savingPriority.has(row.tld)}
                      onChange={(e) => handlePriorityChange(row.tld, e.target.value)}
                      onBlur={() => commitPriority(row.tld)}
                      onKeyDown={(e) => handlePriorityKeyDown(e, row.tld)}
                      placeholder="—"
                    />
                  </TableCell>
                )}
                {isOpenintel ? (
                  <>
                    <TableCell className="text-right text-xs tabular-nums">
                      {formatCount(row.last_domains_inserted)}
                    </TableCell>
                    <TableCell className="text-center text-xs text-muted-foreground">
                      {formatUtcDateTime(row.openintel_last_verification_at)}
                    </TableCell>
                    <TableCell className="text-center text-xs text-muted-foreground">
                      {formatSnapshotDate(row.openintel_last_available_snapshot_date)}
                    </TableCell>
                    <TableCell className="text-center text-xs text-muted-foreground">
                      {formatSnapshotDate(row.openintel_last_ingested_snapshot_date)}
                    </TableCell>
                    <TableCell className="text-center">
                      <div className="space-y-1">
                        <Badge variant="outline" className={openintelStatusClass(row.openintel_status)}>
                          {openintelStatusLabel(row.openintel_status)}
                        </Badge>
                        {row.openintel_status === "failed" && row.openintel_last_error_message && (
                          <p className="max-w-[220px] truncate text-[11px] text-red-600 mx-auto" title={row.openintel_last_error_message}>
                            {row.openintel_last_error_message}
                          </p>
                        )}
                      </div>
                    </TableCell>
                  </>
                ) : (
                  <>
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
                  </>
                )}
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
            {sorted.length === 0 && (
              <TableRow>
                <TableCell colSpan={colSpan} className="text-center text-xs text-muted-foreground py-6">
                  Nenhum TLD encontrado
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <p className="text-xs text-muted-foreground">
        {isOpenintel
          ? "Inseridos: quantidade da última execução do TLD · Última verificação exibida em UTC · Azul = em dia sem novo arquivo · Verde = novo arquivo ingerido · Amarelo = atrasado · Vermelho = falha"
          : "Barras: altura proporcional à duração · verde = sucesso · vermelho = erro · cinza = sem dado"}
        {showPriority && " · Prioridade: menor número = processado primeiro · Enter ou foco perdido para salvar"}
      </p>
    </div>
  )
}
