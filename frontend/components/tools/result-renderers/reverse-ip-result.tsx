"use client"

import { Badge } from "@/components/ui/badge"
import { Server } from "lucide-react"

interface ReverseIpResult {
  domain: string
  ip: string | null
  domains: string[]
  total: number
  truncated?: boolean
  error?: string
}

export function ReverseIpResult({ data }: { data: ReverseIpResult }) {
  if (data.error && !data.domains.length) {
    return <p className="text-sm text-muted-foreground">{data.error}</p>
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 p-3 rounded-md bg-muted/50">
        <Server className="h-4 w-4 text-muted-foreground shrink-0" />
        <div>
          <p className="text-sm font-medium">
            {data.total} domain{data.total !== 1 ? "s" : ""} on this server
          </p>
          {data.ip && (
            <p className="text-xs font-mono text-muted-foreground">{data.ip}</p>
          )}
        </div>
        {data.truncated && (
          <Badge variant="secondary" className="text-xs ml-auto">Truncated</Badge>
        )}
      </div>

      {data.domains.length > 0 ? (
        <div className="flex flex-wrap gap-1 max-h-64 overflow-y-auto">
          {data.domains.map((d) => (
            <Badge key={d} variant="outline" className="text-xs font-mono font-normal">
              {d}
            </Badge>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No other domains found on this IP.</p>
      )}
    </div>
  )
}
