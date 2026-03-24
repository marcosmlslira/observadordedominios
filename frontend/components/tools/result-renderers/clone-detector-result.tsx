"use client"

import { Badge } from "@/components/ui/badge"
import { Copy, AlertTriangle, CheckCircle, XCircle } from "lucide-react"

interface CloneDetectorResult {
  target: string
  reference: string
  overall_score: number
  visual_score: number | null
  text_score: number | null
  structural_score: number | null
  verdict: "likely_clone" | "suspicious" | "low_similarity" | "not_similar" | "error"
  errors: string[] | null
}

const VERDICT_CONFIG = {
  likely_clone: { label: "Likely Clone", variant: "destructive" as const, icon: Copy },
  suspicious: { label: "Suspicious", variant: "outline" as const, icon: AlertTriangle },
  low_similarity: { label: "Low Similarity", variant: "secondary" as const, icon: CheckCircle },
  not_similar: { label: "Not Similar", variant: "default" as const, icon: CheckCircle },
  error: { label: "Error", variant: "outline" as const, icon: XCircle },
}

function ScoreBar({ label, score }: { label: string; score: number | null }) {
  if (score == null) return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-muted-foreground">{label}</span>
        <span className="text-muted-foreground">N/A</span>
      </div>
    </div>
  )
  const pct = Math.round(score * 100)
  const color = pct >= 75 ? "bg-red-500" : pct >= 50 ? "bg-yellow-500" : "bg-green-500"
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-muted-foreground">{label}</span>
        <span className="tabular-nums">{pct}%</span>
      </div>
      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export function CloneDetectorResult({ data }: { data: CloneDetectorResult }) {
  const config = VERDICT_CONFIG[data.verdict] ?? VERDICT_CONFIG.error
  const Icon = config.icon
  const overallPct = Math.round(data.overall_score * 100)

  return (
    <div className="space-y-4">
      {/* Verdict */}
      <div className="flex items-center gap-3 p-3 rounded-md bg-muted/50">
        <Icon className="h-5 w-5 shrink-0" />
        <div className="flex-1">
          <p className="text-sm font-medium">Overall similarity: {overallPct}%</p>
          <p className="text-xs text-muted-foreground">
            {data.target} vs {data.reference}
          </p>
        </div>
        <Badge variant={config.variant}>{config.label}</Badge>
      </div>

      {/* Score bars */}
      <div className="space-y-3">
        <ScoreBar label="Visual (40%)" score={data.visual_score} />
        <ScoreBar label="Text (35%)" score={data.text_score} />
        <ScoreBar label="Structure (25%)" score={data.structural_score} />
      </div>

      {/* Errors */}
      {data.errors && data.errors.length > 0 && (
        <div className="space-y-1">
          {data.errors.map((e, i) => (
            <p key={i} className="text-xs text-muted-foreground">{e}</p>
          ))}
        </div>
      )}
    </div>
  )
}
