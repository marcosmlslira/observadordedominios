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
import { CheckCircle2, XCircle, AlertTriangle, ArrowRight } from "lucide-react"

interface SecurityHeader {
  name: string
  value: string | null
  present: boolean
  severity: "good" | "warning" | "critical"
  description: string | null
}

interface RedirectHop {
  url: string
  status_code: number
}

interface HttpHeadersData {
  final_url: string
  status_code: number
  headers: Record<string, string>
  security_headers: SecurityHeader[]
  redirect_chain: RedirectHop[]
  server: string | null
  content_type: string | null
}

function severityIcon(severity: string) {
  switch (severity) {
    case "good":
      return <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
    case "warning":
      return <AlertTriangle className="h-3.5 w-3.5 text-yellow-500" />
    case "critical":
      return <XCircle className="h-3.5 w-3.5 text-destructive" />
    default:
      return null
  }
}

export function HttpHeadersResult({ data }: { data: HttpHeadersData }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <p className="text-xs text-muted-foreground">Final URL</p>
          <p className="font-mono text-xs break-all">{data.final_url}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Status</p>
          <Badge variant={data.status_code < 400 ? "default" : "destructive"}>
            {data.status_code}
          </Badge>
        </div>
        {data.server && (
          <div>
            <p className="text-xs text-muted-foreground">Server</p>
            <p className="text-sm">{data.server}</p>
          </div>
        )}
      </div>

      {/* Security Headers */}
      {data.security_headers.length > 0 && (
        <div>
          <p className="text-xs text-muted-foreground mb-2">Security Headers</p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8"></TableHead>
                <TableHead>Header</TableHead>
                <TableHead>Value</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.security_headers.map((sh) => (
                <TableRow key={sh.name}>
                  <TableCell>{severityIcon(sh.severity)}</TableCell>
                  <TableCell className="text-sm font-medium">{sh.name}</TableCell>
                  <TableCell className="text-xs font-mono text-muted-foreground break-all max-w-[300px]">
                    {sh.present ? sh.value : "Not set"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Redirect Chain */}
      {data.redirect_chain.length > 0 && (
        <div>
          <p className="text-xs text-muted-foreground mb-2">
            Redirect Chain ({data.redirect_chain.length} hop{data.redirect_chain.length > 1 ? "s" : ""})
          </p>
          <div className="space-y-1">
            {data.redirect_chain.map((hop, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <Badge variant="outline" className="tabular-nums">
                  {hop.status_code}
                </Badge>
                <ArrowRight className="h-3 w-3 text-muted-foreground" />
                <span className="font-mono break-all">{hop.url}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
