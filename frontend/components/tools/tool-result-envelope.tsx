"use client"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { ToolResponse } from "@/lib/types"
import { AlertCircle, CheckCircle2, Clock, Timer } from "lucide-react"

interface ToolResultEnvelopeProps {
  result: ToolResponse
  title?: string
  children: React.ReactNode
}

function statusIcon(status: string) {
  switch (status) {
    case "completed":
      return <CheckCircle2 className="h-4 w-4 text-green-500" />
    case "failed":
      return <AlertCircle className="h-4 w-4 text-destructive" />
    case "timeout":
      return <Clock className="h-4 w-4 text-yellow-500" />
    default:
      return <Timer className="h-4 w-4 text-muted-foreground animate-spin" />
  }
}

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

export function ToolResultEnvelope({
  result,
  title,
  children,
}: ToolResultEnvelopeProps) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            {statusIcon(result.status)}
            {title || result.tool_type}
          </CardTitle>
          <div className="flex items-center gap-2">
            {result.cached && (
              <Badge variant="outline" className="text-xs">
                Cached
              </Badge>
            )}
            <Badge variant={statusVariant(result.status)} className="text-xs">
              {result.status}
            </Badge>
            {result.duration_ms != null && (
              <span className="text-xs text-muted-foreground tabular-nums">
                {result.duration_ms}ms
              </span>
            )}
          </div>
        </div>
        <p className="text-sm text-muted-foreground font-mono">
          {result.target}
        </p>
      </CardHeader>
      <CardContent>
        {result.status === "failed" || result.status === "timeout" ? (
          <p className="text-sm text-destructive">{result.error}</p>
        ) : (
          children
        )}
      </CardContent>
    </Card>
  )
}
