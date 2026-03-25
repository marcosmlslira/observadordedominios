"use client"

import { Badge } from "@/components/ui/badge"
import { AlertTriangle, CheckCircle2, ShieldAlert } from "lucide-react"

interface Signal {
  category: string
  description: string
  severity: "low" | "medium" | "high" | "critical"
}

interface SuspiciousPageData {
  risk_score: number
  risk_level: "safe" | "low" | "medium" | "high" | "critical"
  signals: Signal[]
  page_title: string | null
  final_url: string | null
  http_status: number | null
  page_disposition: "live" | "parked" | "challenge" | "unreachable" | null
  has_login_form: boolean
  has_credential_inputs: boolean
  external_resource_count: number
}

function riskVariant(level: string) {
  switch (level) {
    case "critical":
    case "high":
      return "destructive" as const
    case "medium":
      return "secondary" as const
    default:
      return "outline" as const
  }
}

function severityColor(severity: string) {
  switch (severity) {
    case "critical":
      return "text-red-600"
    case "high":
      return "text-orange-500"
    case "medium":
      return "text-yellow-500"
    default:
      return "text-muted-foreground"
  }
}

export function SuspiciousPageResult({ data }: { data: SuspiciousPageData }) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        {data.risk_level === "safe" ? (
          <CheckCircle2 className="h-6 w-6 text-green-500" />
        ) : (
          <ShieldAlert className="h-6 w-6 text-destructive" />
        )}
        <div>
          <div className="flex items-center gap-2">
            <span className="font-medium text-lg">
              {(data.risk_score * 100).toFixed(0)}%
            </span>
            <Badge variant={riskVariant(data.risk_level)}>
              {data.risk_level}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">Risk Score</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 text-sm">
        <div>
          <p className="text-xs text-muted-foreground">Disposition</p>
          <p>{data.page_disposition ?? "unknown"}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">HTTP Status</p>
          <p>{data.http_status ?? "N/A"}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Login Form</p>
          <p>{data.has_login_form ? "Yes" : "No"}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Credential Inputs</p>
          <p>{data.has_credential_inputs ? "Yes" : "No"}</p>
        </div>
      </div>

      {data.final_url && (
        <div>
          <p className="text-xs text-muted-foreground">Final URL</p>
          <p className="text-xs font-mono break-all">{data.final_url}</p>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 text-sm">
        <div>
          <p className="text-xs text-muted-foreground">External Resources</p>
          <p>{data.external_resource_count}</p>
        </div>
      </div>

      {data.signals.length > 0 && (
        <div>
          <p className="text-xs text-muted-foreground mb-2">
            Signals ({data.signals.length})
          </p>
          <div className="space-y-2">
            {data.signals.map((signal, i) => (
              <div
                key={i}
                className="flex items-start gap-2 text-sm border-l-2 pl-3 py-1"
                style={{
                  borderColor:
                    signal.severity === "critical"
                      ? "rgb(220, 38, 38)"
                      : signal.severity === "high"
                        ? "rgb(249, 115, 22)"
                        : signal.severity === "medium"
                          ? "rgb(234, 179, 8)"
                          : "rgb(156, 163, 175)",
                }}
              >
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-[10px]">
                      {signal.category}
                    </Badge>
                    <Badge
                      variant={riskVariant(signal.severity)}
                      className="text-[10px]"
                    >
                      {signal.severity}
                    </Badge>
                  </div>
                  <p className="text-sm mt-1">{signal.description}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
