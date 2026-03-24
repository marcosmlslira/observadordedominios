"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { toolsApi } from "@/lib/api"
import { TOOL_DEFINITIONS } from "@/lib/tools"
import type { HistoryItem, HistoryListResponse, ToolType } from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ArrowLeft, RefreshCw } from "lucide-react"

const ALL_VALUE = "all"

function statusVariant(status: string) {
  switch (status) {
    case "completed":
      return "default" as const
    case "failed":
      return "destructive" as const
    case "timeout":
      return "secondary" as const
    default:
      return "outline" as const
  }
}

export default function HistoryPage() {
  const [items, setItems] = useState<HistoryItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [targetFilter, setTargetFilter] = useState("")
  const [toolFilter, setToolFilter] = useState("")
  const [offset, setOffset] = useState(0)
  const limit = 20

  const fetchHistory = useCallback(async () => {
    setLoading(true)
    try {
      const data = await toolsApi.history({
        target: targetFilter || undefined,
        tool_type: toolFilter || undefined,
        limit,
        offset,
      })
      setItems(data.items)
      setTotal(data.total)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [targetFilter, toolFilter, offset])

  useEffect(() => {
    fetchHistory()
  }, [fetchHistory])

  useEffect(() => {
    setOffset(0)
  }, [targetFilter, toolFilter])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href="/admin/tools">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="h-3 w-3 mr-1" />
              Back
            </Button>
          </Link>
          <h1 className="text-2xl font-semibold">Execution History</h1>
        </div>
        <Button variant="outline" size="sm" onClick={fetchHistory}>
          <RefreshCw className="h-3 w-3 mr-1" />
          Refresh
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="w-60">
          <Label className="text-xs text-muted-foreground">Target</Label>
          <Input
            value={targetFilter}
            onChange={(e) => setTargetFilter(e.target.value)}
            placeholder="Filter by domain..."
          />
        </div>
        <div className="w-48">
          <Label className="text-xs text-muted-foreground">Tool</Label>
          <Select
            value={toolFilter || ALL_VALUE}
            onValueChange={(v) => setToolFilter(v === ALL_VALUE ? "" : v)}
          >
            <SelectTrigger>
              <SelectValue placeholder="All tools" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_VALUE}>All tools</SelectItem>
              {TOOL_DEFINITIONS.map((t) => (
                <SelectItem key={t.type} value={t.type}>
                  {t.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-8">
              <Skeleton className="h-64" />
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tool</TableHead>
                  <TableHead>Target</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Date</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={6}
                      className="text-center text-muted-foreground py-8"
                    >
                      No executions found
                    </TableCell>
                  </TableRow>
                ) : (
                  items.map((item) => {
                    const toolDef = TOOL_DEFINITIONS.find(
                      (t) => t.type === item.tool_type,
                    )
                    return (
                      <TableRow key={item.execution_id}>
                        <TableCell className="text-sm">
                          {toolDef ? (
                            <Link
                              href={`/admin/tools/${toolDef.slug}`}
                              className="hover:underline"
                            >
                              {toolDef.name}
                            </Link>
                          ) : (
                            item.tool_type
                          )}
                        </TableCell>
                        <TableCell className="font-mono text-sm">
                          {item.target}
                        </TableCell>
                        <TableCell>
                          <Badge variant={statusVariant(item.status)}>
                            {item.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs tabular-nums text-muted-foreground">
                          {item.duration_ms != null ? `${item.duration_ms}ms` : "—"}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className="text-xs">
                            {item.triggered_by}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {new Date(item.created_at).toLocaleString()}
                        </TableCell>
                      </TableRow>
                    )
                  })
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {total > limit && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Showing {offset + 1}-{Math.min(offset + limit, total)} of {total}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - limit))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={offset + limit >= total}
              onClick={() => setOffset(offset + limit)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
