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
import { ShieldCheck, ShieldAlert } from "lucide-react"

interface BlacklistListing {
  name: string
  zone: string
  category: string
  listed: boolean
}

interface BlacklistResult {
  domain: string
  ip: string | null
  listed_count: number
  total_checked: number
  risk_level: "clean" | "low" | "medium" | "high"
  listings: BlacklistListing[]
}

const RISK_COLORS = {
  clean: "default",
  low: "secondary",
  medium: "outline",
  high: "destructive",
} as const

export function BlacklistResult({ data }: { data: BlacklistResult }) {
  const listed = data.listings.filter((l) => l.listed)
  const clean = data.listings.filter((l) => !l.listed)

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="flex items-center gap-4 p-3 rounded-md bg-muted/50">
        {data.listed_count === 0 ? (
          <ShieldCheck className="h-5 w-5 text-green-500 shrink-0" />
        ) : (
          <ShieldAlert className="h-5 w-5 text-red-500 shrink-0" />
        )}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium">
            {data.listed_count === 0
              ? "Not listed on any blacklist"
              : `Listed on ${data.listed_count} of ${data.total_checked} blacklists`}
          </p>
          {data.ip && (
            <p className="text-xs text-muted-foreground font-mono">{data.ip}</p>
          )}
        </div>
        <Badge variant={RISK_COLORS[data.risk_level]}>
          {data.risk_level}
        </Badge>
      </div>

      {/* Listed entries first */}
      {listed.length > 0 && (
        <div>
          <p className="text-xs font-medium text-destructive mb-2">Listed ({listed.length})</p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Blacklist</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Zone</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {listed.map((l) => (
                <TableRow key={l.zone}>
                  <TableCell className="font-medium text-sm">{l.name}</TableCell>
                  <TableCell><Badge variant="outline" className="text-xs">{l.category}</Badge></TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">{l.zone}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Clean entries */}
      <details className="group">
        <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">
          Clean ({clean.length} blacklists checked)
        </summary>
        <div className="mt-2 flex flex-wrap gap-1">
          {clean.map((l) => (
            <Badge key={l.zone} variant="outline" className="text-xs font-normal">
              {l.name}
            </Badge>
          ))}
        </div>
      </details>
    </div>
  )
}
