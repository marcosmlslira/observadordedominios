"use client"

import { useState } from "react"
import type { CzdsPolicyItem, TldDomainCount } from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
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
import { Play } from "lucide-react"

function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return n.toLocaleString()
}

function tldStatus(item: CzdsPolicyItem): "ok" | "suspended" | "failing" | "disabled" {
  if (!item.is_enabled) return "disabled"
  if (item.suspended_until && new Date(item.suspended_until) > new Date()) return "suspended"
  if ((item.failure_count ?? 0) > 0) return "failing"
  return "ok"
}

const statusConfig = {
  ok: { label: "OK", variant: "default" as const, className: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20" },
  suspended: { label: "Suspenso", variant: "secondary" as const, className: "bg-yellow-500/10 text-yellow-600 border-yellow-500/20" },
  failing: { label: "Falhando", variant: "destructive" as const, className: "bg-red-500/10 text-red-600 border-red-500/20" },
  disabled: { label: "Desabilitado", variant: "outline" as const, className: "text-muted-foreground" },
}

interface TldPolicyTableProps {
  items: CzdsPolicyItem[]
  domainCounts: TldDomainCount[]
  onPatch: (tld: string, fields: { is_enabled?: boolean; priority?: number; cooldown_hours?: number }) => Promise<void>
  onTriggerSync: (tld: string) => void
}

export function TldPolicyTable({ items, domainCounts, onPatch, onTriggerSync }: TldPolicyTableProps) {
  const [filter, setFilter] = useState("")
  const domainCountMap = new Map(domainCounts.map((d) => [d.tld, d.count]))

  const filtered = items.filter((item) =>
    filter ? item.tld.includes(filter.toLowerCase()) : true,
  )

  const enabledCount = items.filter((i) => i.is_enabled).length
  const suspendedCount = items.filter((i) => tldStatus(i) === "suspended").length
  const disabledCount = items.filter((i) => !i.is_enabled).length

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Input
          placeholder="Filtrar TLDs..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="max-w-xs"
        />
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="secondary">{enabledCount} enabled</Badge>
          {suspendedCount > 0 && <Badge variant="outline" className="border-yellow-500/30 text-yellow-600">{suspendedCount} suspended</Badge>}
          {disabledCount > 0 && <Badge variant="outline">{disabledCount} disabled</Badge>}
        </div>
      </div>

      <div className="rounded-xl border border-border overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[60px]">Ativo</TableHead>
              <TableHead>TLD</TableHead>
              <TableHead className="w-[80px]">Prioridade</TableHead>
              <TableHead className="w-[100px]">Cooldown (h)</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="w-[70px]">Falhas</TableHead>
              <TableHead className="text-right">Dominios</TableHead>
              <TableHead className="w-[60px]"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="text-center text-muted-foreground py-8">
                  {filter ? "Nenhum TLD encontrado" : "Nenhuma policy configurada"}
                </TableCell>
              </TableRow>
            ) : (
              filtered.map((item) => {
                const status = tldStatus(item)
                const config = statusConfig[status]
                const count = domainCountMap.get(item.tld)
                return (
                  <TableRow key={item.tld} className={!item.is_enabled ? "opacity-50" : ""}>
                    <TableCell>
                      <Switch
                        checked={item.is_enabled}
                        onCheckedChange={(checked) => onPatch(item.tld, { is_enabled: checked })}
                      />
                    </TableCell>
                    <TableCell className="font-mono text-sm">.{item.tld}</TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        defaultValue={item.priority}
                        className="h-7 w-16 text-xs"
                        onBlur={(e) => {
                          const val = parseInt(e.target.value, 10)
                          if (!isNaN(val) && val !== item.priority) {
                            onPatch(item.tld, { priority: val })
                          }
                        }}
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        defaultValue={item.cooldown_hours}
                        className="h-7 w-16 text-xs"
                        onBlur={(e) => {
                          const val = parseInt(e.target.value, 10)
                          if (!isNaN(val) && val !== item.cooldown_hours) {
                            onPatch(item.tld, { cooldown_hours: val })
                          }
                        }}
                      />
                    </TableCell>
                    <TableCell>
                      <Badge variant={config.variant} className={config.className}>
                        {config.label}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {(item.failure_count ?? 0) > 0 ? (
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger>
                              <Badge variant="destructive" className="text-xs">
                                {item.failure_count}
                              </Badge>
                            </TooltipTrigger>
                            <TooltipContent side="top" className="max-w-xs">
                              <p className="text-xs">{item.notes || "Sem detalhes"}</p>
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      ) : (
                        <span className="text-xs text-muted-foreground">0</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-sm">
                      {count !== undefined ? formatCount(count) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0"
                        onClick={() => onTriggerSync(item.tld)}
                        title={`Sync .${item.tld}`}
                      >
                        <Play className="h-3 w-3" />
                      </Button>
                    </TableCell>
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
