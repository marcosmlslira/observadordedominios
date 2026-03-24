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

interface DnsRecord {
  type: string
  name: string
  value: string
  ttl: number | null
}

interface DnsLookupResult {
  records: DnsRecord[]
  nameservers: string[]
  resolution_time_ms: number | null
}

export function DnsResult({ data }: { data: DnsLookupResult }) {
  const recordsByType = data.records.reduce(
    (acc, r) => {
      ;(acc[r.type] = acc[r.type] || []).push(r)
      return acc
    },
    {} as Record<string, DnsRecord[]>,
  )

  return (
    <div className="space-y-4">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-20">Type</TableHead>
            <TableHead>Value</TableHead>
            <TableHead className="w-20 text-right">TTL</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.records.length === 0 ? (
            <TableRow>
              <TableCell colSpan={3} className="text-center text-muted-foreground">
                No DNS records found
              </TableCell>
            </TableRow>
          ) : (
            data.records.map((r, i) => (
              <TableRow key={i}>
                <TableCell>
                  <Badge variant="outline" className="text-xs font-mono">
                    {r.type}
                  </Badge>
                </TableCell>
                <TableCell className="font-mono text-sm break-all">
                  {r.value}
                </TableCell>
                <TableCell className="text-right text-xs tabular-nums text-muted-foreground">
                  {r.ttl ?? "—"}
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>

      {data.nameservers.length > 0 && (
        <div>
          <p className="text-xs text-muted-foreground mb-1">Nameservers</p>
          <div className="flex flex-wrap gap-1">
            {data.nameservers.map((ns) => (
              <Badge key={ns} variant="secondary" className="text-xs font-mono">
                {ns}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
