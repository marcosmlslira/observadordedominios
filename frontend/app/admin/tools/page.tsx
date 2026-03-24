"use client"

import { useState } from "react"
import Link from "next/link"
import { toolsApi } from "@/lib/api"
import { TOOL_DEFINITIONS } from "@/lib/tools"
import type { QuickAnalysisResponse, ToolDefinition, ToolType } from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { ToolResultRenderer } from "@/components/tools/result-renderers"
import { ToolResultEnvelope } from "@/components/tools/tool-result-envelope"
import {
  Globe,
  FileText,
  ShieldCheck,
  FileCode,
  Camera,
  AlertTriangle,
  Ban,
  Mail,
  Server,
  MapPin,
  Copy,
  Layers,
  Loader2,
  Zap,
  History,
} from "lucide-react"

const ICON_MAP: Record<string, React.ElementType> = {
  Globe,
  FileText,
  ShieldCheck,
  FileCode,
  Camera,
  AlertTriangle,
  Ban,
  Mail,
  Server,
  MapPin,
  Copy,
  Layers,
}

function ToolCard({ tool }: { tool: ToolDefinition }) {
  const Icon = ICON_MAP[tool.icon] || Globe
  return (
    <Link href={`/admin/tools/${tool.slug}`}>
      <Card className="hover:bg-muted/50 transition-colors cursor-pointer h-full">
        <CardContent className="p-4">
          <div className="flex items-start gap-3">
            <div className="rounded-md bg-secondary p-2">
              <Icon className="h-4 w-4" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium">{tool.name}</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {tool.description}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}

export default function ToolsHubPage() {
  const [target, setTarget] = useState("")
  const [loading, setLoading] = useState(false)
  const [qaResult, setQaResult] = useState<QuickAnalysisResponse | null>(null)
  const [error, setError] = useState("")

  const essential = TOOL_DEFINITIONS.filter((t) => t.category === "essential")
  const enrichment = TOOL_DEFINITIONS.filter((t) => t.category === "enrichment")

  async function runQuickAnalysis(e: React.FormEvent) {
    e.preventDefault()
    if (!target.trim()) return
    setLoading(true)
    setError("")
    setQaResult(null)
    try {
      const result = await toolsApi.quickAnalysis(target.trim().toLowerCase())
      setQaResult(result)
    } catch (err: any) {
      setError(err.message || "Quick Analysis failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Free Tools</h1>
        <Link href="/admin/tools/history">
          <Button variant="outline" size="sm">
            <History className="h-3 w-3 mr-1" />
            History
          </Button>
        </Link>
      </div>

      {/* Quick Analysis */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Zap className="h-4 w-4" />
            Quick Analysis
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Run multiple tools at once on a domain
          </p>
        </CardHeader>
        <CardContent>
          <form onSubmit={runQuickAnalysis} className="flex items-end gap-3">
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="qa-target" className="text-xs text-muted-foreground">
                Domain
              </Label>
              <Input
                id="qa-target"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                placeholder="example.com"
                disabled={loading}
              />
            </div>
            <Button type="submit" disabled={loading || !target.trim()}>
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin mr-1" />
              ) : (
                <Zap className="h-4 w-4 mr-1" />
              )}
              Run Analysis
            </Button>
          </form>
          {error && <p className="text-sm text-destructive mt-2">{error}</p>}
        </CardContent>
      </Card>

      {/* Quick Analysis Results */}
      {qaResult && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">
                Results for <span className="font-mono">{qaResult.target}</span>
              </CardTitle>
              <div className="flex items-center gap-2">
                <Badge variant={qaResult.status === "completed" ? "default" : "secondary"}>
                  {qaResult.status}
                </Badge>
                <span className="text-xs text-muted-foreground tabular-nums">
                  {qaResult.total_duration_ms}ms
                </span>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {Object.entries(qaResult.results).map(([toolType, toolResult]) => (
              <div key={toolType}>
                <ToolResultEnvelope
                  result={{
                    execution_id: qaResult.quick_analysis_id,
                    tool_type: toolType as ToolType,
                    target: qaResult.target,
                    status: toolResult.status,
                    duration_ms: toolResult.duration_ms,
                    cached: false,
                    result: toolResult.result,
                    error: toolResult.error,
                    executed_at: new Date().toISOString(),
                  }}
                  title={TOOL_DEFINITIONS.find((t) => t.type === toolType)?.name || toolType}
                >
                  {toolResult.result && (
                    <ToolResultRenderer
                      toolType={toolType as ToolType}
                      data={toolResult.result}
                    />
                  )}
                </ToolResultEnvelope>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Essential Tools */}
      <div>
        <h2 className="text-sm font-medium text-muted-foreground mb-3">
          Essential Tools
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {essential.map((tool) => (
            <ToolCard key={tool.type} tool={tool} />
          ))}
        </div>
      </div>

      {/* Enrichment Tools */}
      <div>
        <h2 className="text-sm font-medium text-muted-foreground mb-3">
          Enrichment Tools
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {enrichment.map((tool) => (
            <ToolCard key={tool.type} tool={tool} />
          ))}
        </div>
      </div>
    </div>
  )
}
