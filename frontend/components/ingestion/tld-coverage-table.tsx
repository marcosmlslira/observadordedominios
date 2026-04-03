"use client"

import { useMemo, useState } from "react"
import type { TldCoverage, TldDomainCount } from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return n.toLocaleString()
}

type SortKey = "tld" | "count" | "source" | "priority"
type SortDir = "asc" | "desc"

interface TldCoverageTableProps {
  coverage: TldCoverage[]
  domainCounts: TldDomainCount[]
}

export function TldCoverageTable({ coverage, domainCounts }: TldCoverageTableProps) {
  const [filter, setFilter] = useState("")
  const [sortKey, setSortKey] = useState<SortKey>("count")
  const [sortDir, setSortDir] = useState<SortDir>("desc")

  const domainCountMap = useMemo(() => new Map(domainCounts.map((d) => [d.tld, d.count])), [domainCounts])
  const totalDomains = useMemo(() => domainCounts.reduce((sum, d) => sum + d.count, 0), [domainCounts])

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc")
    } else {
      setSortKey(key)
      setSortDir(key === "tld" ? "asc" : "desc")
    }
  }

  const sorted = useMemo(() => {
    const filtered = filter
      ? coverage.filter((item) => item.tld.includes(filter.toLowerCase()))
      : [...coverage]

    return filtered.sort((a, b) => {
      let cmp = 0
      switch (sortKey) {
        case "tld":
          cmp = a.tld.localeCompare(b.tld)
          break
        case "count":
          cmp = (domainCountMap.get(a.tld) ?? 0) - (domainCountMap.get(b.tld) ?? 0)
          break
        case "source":
          cmp = a.effective_source.localeCompare(b.effective_source)
          break
        case "priority":
          cmp = a.priority_group.localeCompare(b.priority_group)
          break
      }
      return sortDir === "asc" ? cmp : -cmp
    })
  }, [coverage, filter, sortKey, sortDir, domainCountMap])

  const maxCount = useMemo(
    () => Math.max(...domainCounts.map((d) => d.count), 1),
    [domainCounts],
  )

  const sortIndicator = (key: SortKey) => {
    if (sortKey !== key) return ""
    return sortDir === "asc" ? " ↑" : " ↓"
  }

  return (
    <Card className="border-border-subtle bg-background/70">
      <CardHeader className="pb-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="text-base">
            Cobertura por TLD{" "}
            <span className="text-sm font-normal text-muted-foreground">
              ({coverage.length})
            </span>
          </CardTitle>
          <Input
            placeholder="Filtrar TLDs..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="max-w-xs"
          />
        </div>
      </CardHeader>
      <CardContent>
        <div className="rounded-xl border border-border overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="cursor-pointer select-none" onClick={() => handleSort("tld")}>
                  TLD{sortIndicator("tld")}
                </TableHead>
                <TableHead className="cursor-pointer select-none text-right" onClick={() => handleSort("count")}>
                  Dominios{sortIndicator("count")}
                </TableHead>
                <TableHead>% Corpus</TableHead>
                <TableHead className="cursor-pointer select-none" onClick={() => handleSort("source")}>
                  Source{sortIndicator("source")}
                </TableHead>
                <TableHead>CZDS</TableHead>
                <TableHead>CT</TableHead>
                <TableHead className="cursor-pointer select-none" onClick={() => handleSort("priority")}>
                  Priority{sortIndicator("priority")}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="py-6 text-center text-muted-foreground">
                    No coverage data available
                  </TableCell>
                </TableRow>
              ) : (
                sorted.map((item) => {
                  const count = domainCountMap.get(item.tld)
                  const pct = count && totalDomains > 0 ? ((count / totalDomains) * 100) : 0
                  const barWidth = count ? (count / maxCount) * 100 : 0
                  const hasData = count !== undefined
                  return (
                    <TableRow key={item.tld} className={hasData ? "" : "opacity-50"}>
                      <TableCell className="font-mono text-xs">.{item.tld}</TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-2">
                          <div className="hidden sm:block w-24 h-2 rounded-full bg-muted overflow-hidden">
                            <div
                              className="h-full rounded-full bg-primary/60 transition-all"
                              style={{ width: `${barWidth}%` }}
                            />
                          </div>
                          <span className="tabular-nums text-sm font-medium min-w-[60px] text-right">
                            {hasData ? formatCount(count) : "—"}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="tabular-nums text-xs text-muted-foreground">
                        {pct > 0 ? `${pct.toFixed(1)}%` : "—"}
                      </TableCell>
                      <TableCell>
                        <Badge variant={item.effective_source === "ct_fallback" ? "secondary" : "outline"}>
                          {item.effective_source === "ct_fallback" ? "CT fallback" : "CZDS"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs">{item.czds_available ? "yes" : "no"}</TableCell>
                      <TableCell className="text-xs">{item.ct_enabled ? "yes" : "off"}</TableCell>
                      <TableCell className="text-xs">{item.priority_group}</TableCell>
                    </TableRow>
                  )
                })
              )}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}
