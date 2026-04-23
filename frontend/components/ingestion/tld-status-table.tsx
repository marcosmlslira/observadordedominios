"use client"

import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { CheckCircle2, XCircle, Loader2, HelpCircle, AlertCircle } from "lucide-react"
import type { TldStatusItem, TldStatusCategory } from "@/lib/types"

interface Props {
  items: TldStatusItem[]
  ok_count: number
  failed_count: number
  running_count: number
  never_run_count: number
}

function StatusBadge({ status }: { status: TldStatusCategory }) {
  switch (status) {
    case "ok":
      return (
        <Badge variant="outline" className="gap-1 border-emerald-200 bg-emerald-50 text-emerald-700">
          <CheckCircle2 className="h-3 w-3" aria-hidden />
          OK
        </Badge>
      )
    case "running":
      return (
        <Badge variant="outline" className="gap-1 border-blue-200 bg-blue-50 text-blue-700">
          <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
          Rodando
        </Badge>
      )
    case "failed":
      return (
        <Badge variant="outline" className="gap-1 border-red-200 bg-red-50 text-red-700">
          <XCircle className="h-3 w-3" aria-hidden />
          Falha
        </Badge>
      )
    case "never_run":
      return (
        <Badge variant="outline" className="gap-1 border-zinc-200 bg-zinc-50 text-zinc-500">
          <HelpCircle className="h-3 w-3" aria-hidden />
          Nunca
        </Badge>
      )
  }
}

function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return n.toLocaleString()
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "—"
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return "agora"
  if (mins < 60) return `${mins}min atrás`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h atrás`
  return `${Math.floor(hours / 24)}d atrás`
}

export function TldStatusTable({ items, ok_count, failed_count, running_count, never_run_count }: Props) {
  return (
    <div className="space-y-3">
      {/* Summary counts */}
      <div className="flex flex-wrap gap-2 text-xs" role="status" aria-label="Resumo de status por TLD">
        <Badge variant="outline" className="border-emerald-200 bg-emerald-50 text-emerald-700">
          OK: {ok_count}
        </Badge>
        {running_count > 0 && (
          <Badge variant="outline" className="border-blue-200 bg-blue-50 text-blue-700">
            <Loader2 className="h-3 w-3 animate-spin mr-1" aria-hidden />
            Rodando: {running_count}
          </Badge>
        )}
        {failed_count > 0 && (
          <Badge variant="outline" className="border-red-200 bg-red-50 text-red-700">
            <AlertCircle className="h-3 w-3 mr-1" aria-hidden />
            Falhas: {failed_count}
          </Badge>
        )}
        {never_run_count > 0 && (
          <Badge variant="outline" className="border-zinc-200 bg-zinc-50 text-zinc-500">
            Nunca: {never_run_count}
          </Badge>
        )}
      </div>

      {/* Table */}
      <div className="rounded-lg border overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-32">TLD</TableHead>
              <TableHead className="w-28">Status hoje</TableHead>
              <TableHead className="w-28 text-right">Novos</TableHead>
              <TableHead className="w-28 text-right">Removidos</TableHead>
              <TableHead>Última execução</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-sm text-muted-foreground py-8">
                  Nenhum TLD configurado para esta fonte.
                </TableCell>
              </TableRow>
            ) : (
              items.map((item) => (
                <TableRow key={item.tld} className={!item.is_enabled ? "opacity-50" : ""}>
                  <TableCell className="font-mono text-xs font-medium">.{item.tld}</TableCell>
                  <TableCell>
                    {item.error_message ? (
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span>
                              <StatusBadge status={item.status} />
                            </span>
                          </TooltipTrigger>
                          <TooltipContent side="right" className="max-w-xs text-xs">
                            <p>{item.error_message}</p>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    ) : (
                      <StatusBadge status={item.status} />
                    )}
                  </TableCell>
                  <TableCell className="text-right text-sm tabular-nums">
                    {item.domains_inserted_today > 0
                      ? <span className="text-emerald-600 font-medium">+{formatCount(item.domains_inserted_today)}</span>
                      : <span className="text-muted-foreground">—</span>
                    }
                  </TableCell>
                  <TableCell className="text-right text-sm tabular-nums">
                    {item.domains_deleted_today > 0
                      ? <span className="text-red-500 font-medium">-{formatCount(item.domains_deleted_today)}</span>
                      : <span className="text-muted-foreground">—</span>
                    }
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {timeAgo(item.last_run_at)}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
