"use client"

import { Badge } from "@/components/ui/badge"
import { CheckCircle, XCircle, AlertCircle } from "lucide-react"

interface SpfResult {
  present: boolean
  record: string | null
  policy: string | null
  includes: string[]
  issues: string[]
}

interface DmarcResult {
  present: boolean
  record: string | null
  policy: string | null
  subdomain_policy: string | null
  percentage: number | null
  rua: string | null
  issues: string[]
}

interface DkimResult {
  found: boolean
  selectors_found: { selector: string; record: string }[]
  selectors_checked: string[]
}

interface SpoofingRisk {
  score: number
  level: "low" | "medium" | "high" | "critical"
}

interface EmailSecurityResult {
  domain: string
  spf: SpfResult
  dmarc: DmarcResult
  dkim: DkimResult
  spoofing_risk: SpoofingRisk
}

const RISK_VARIANT = {
  low: "default",
  medium: "secondary",
  high: "outline",
  critical: "destructive",
} as const

function StatusIcon({ ok }: { ok: boolean }) {
  return ok
    ? <CheckCircle className="h-4 w-4 text-green-500" />
    : <XCircle className="h-4 w-4 text-red-500" />
}

function IssueList({ issues }: { issues: string[] }) {
  if (!issues.length) return null
  return (
    <ul className="mt-1 space-y-0.5">
      {issues.map((issue, i) => (
        <li key={i} className="text-xs text-yellow-700 dark:text-yellow-400 flex items-start gap-1">
          <AlertCircle className="h-3 w-3 mt-0.5 shrink-0" />
          {issue}
        </li>
      ))}
    </ul>
  )
}

export function EmailSecurityResult({ data }: { data: EmailSecurityResult }) {
  const { spf, dmarc, dkim, spoofing_risk } = data

  return (
    <div className="space-y-4">
      {/* Overall risk */}
      <div className="flex items-center justify-between p-3 rounded-md bg-muted/50">
        <div>
          <p className="text-sm font-medium">Spoofing Risk</p>
          <p className="text-xs text-muted-foreground">Score: {spoofing_risk.score}/100</p>
        </div>
        <Badge variant={RISK_VARIANT[spoofing_risk.level]}>
          {spoofing_risk.level}
        </Badge>
      </div>

      {/* SPF */}
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <StatusIcon ok={spf.present} />
          <span className="text-sm font-medium">SPF</span>
          {spf.policy && (
            <Badge variant="outline" className="text-xs">{spf.policy}</Badge>
          )}
        </div>
        {spf.record && (
          <p className="text-xs font-mono text-muted-foreground bg-muted p-2 rounded truncate">
            {spf.record}
          </p>
        )}
        {spf.includes.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1">
            {spf.includes.map((inc) => (
              <Badge key={inc} variant="outline" className="text-xs font-mono">{inc}</Badge>
            ))}
          </div>
        )}
        <IssueList issues={spf.issues} />
      </div>

      {/* DMARC */}
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <StatusIcon ok={dmarc.present} />
          <span className="text-sm font-medium">DMARC</span>
          {dmarc.policy && (
            <Badge variant="outline" className="text-xs">{dmarc.policy}</Badge>
          )}
          {dmarc.percentage != null && dmarc.percentage < 100 && (
            <Badge variant="secondary" className="text-xs">{dmarc.percentage}%</Badge>
          )}
        </div>
        {dmarc.record && (
          <p className="text-xs font-mono text-muted-foreground bg-muted p-2 rounded truncate">
            {dmarc.record}
          </p>
        )}
        {dmarc.rua && (
          <p className="text-xs text-muted-foreground">Reports → {dmarc.rua}</p>
        )}
        <IssueList issues={dmarc.issues} />
      </div>

      {/* DKIM */}
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <StatusIcon ok={dkim.found} />
          <span className="text-sm font-medium">DKIM</span>
          {dkim.found && (
            <Badge variant="outline" className="text-xs">
              {dkim.selectors_found.length} selector{dkim.selectors_found.length !== 1 ? "s" : ""} found
            </Badge>
          )}
        </div>
        {dkim.selectors_found.length > 0 && (
          <div className="space-y-1">
            {dkim.selectors_found.map((s) => (
              <div key={s.selector}>
                <Badge variant="secondary" className="text-xs mr-1">{s.selector}</Badge>
                <span className="text-xs font-mono text-muted-foreground">{s.record}</span>
              </div>
            ))}
          </div>
        )}
        {!dkim.found && (
          <p className="text-xs text-muted-foreground">
            No DKIM selectors found (checked {dkim.selectors_checked.length} common selectors)
          </p>
        )}
      </div>
    </div>
  )
}
