"use client"

import { Suspense, useCallback, useEffect, useRef, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import Link from "next/link"
import { toolsApi } from "@/lib/api"
import { TOOL_DEFINITIONS } from "@/lib/tools"
import type { ToolDefinition, ToolResponse, ToolType } from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { ToolResultRenderer } from "@/components/tools/result-renderers"
import { ToolResultEnvelope } from "@/components/tools/tool-result-envelope"
import {
  Globe, FileText, ShieldCheck, FileCode, Camera, AlertTriangle,
  Ban, Mail, Server, MapPin, Copy, Layers, Loader2, Zap, History,
} from "lucide-react"

const ICON_MAP: Record<string, React.ElementType> = {
  Globe, FileText, ShieldCheck, FileCode, Camera, AlertTriangle,
  Ban, Mail, Server, MapPin, Copy, Layers,
}

// Tools included in Quick Analysis by default
const QA_DEFAULT_TOOLS: ToolType[] = [
  "dns_lookup", "whois", "ssl_check", "http_headers",
]

type ToolResultMap = Record<string, { status: "pending" | "running" | "done" | "error"; result?: ToolResponse }>

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
              <p className="text-xs text-muted-foreground mt-0.5">{tool.description}</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}

export default function ToolsHubPage() {
  return (
    <Suspense>
      <ToolsHubContent />
    </Suspense>
  )
}

function ToolsHubContent() {
  const searchParams = useSearchParams()
  const router = useRouter()

  const [target, setTarget] = useState(searchParams.get("q") ?? "")
  const [selectedTools, setSelectedTools] = useState<ToolType[]>(QA_DEFAULT_TOOLS)
  const [running, setRunning] = useState(false)
  const [results, setResults] = useState<ToolResultMap>({})
  const [startedAt, setStartedAt] = useState<number | null>(null)
  const [totalMs, setTotalMs] = useState<number | null>(null)
  const abortRef = useRef(false)

  const essential = TOOL_DEFINITIONS.filter((t) => t.category === "essential")
  const enrichment = TOOL_DEFINITIONS.filter((t) => t.category === "enrichment")

  // Auto-run if ?q= is present
  useEffect(() => {
    const q = searchParams.get("q")
    if (q) {
      setTarget(q)
      // small delay to let state settle
      setTimeout(() => runAnalysis(q), 100)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function toggleTool(type: ToolType) {
    setSelectedTools((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    )
  }

  async function runAnalysis(overrideTarget?: string) {
    const t = (overrideTarget ?? target).trim().toLowerCase()
      .replace(/^https?:\/\//, "").replace(/^www\./, "").split("/")[0]
    if (!t || selectedTools.length === 0) return

    abortRef.current = false
    setRunning(true)
    setTotalMs(null)
    const t0 = performance.now()
    setStartedAt(t0)

    // Initialize all selected tools as "pending" immediately
    const initial: ToolResultMap = {}
    for (const tool of selectedTools) {
      initial[tool] = { status: "pending" }
    }
    setResults(initial)

    // Run all tools in parallel, updating results as each completes
    await Promise.allSettled(
      selectedTools.map(async (toolType) => {
        if (abortRef.current) return

        const toolDef = TOOL_DEFINITIONS.find((d) => d.type === toolType)
        if (!toolDef) return

        setResults((prev) => ({ ...prev, [toolType]: { status: "running" } }))

        try {
          const resp = await toolsApi.run(toolDef.slug, t, false)
          if (!abortRef.current) {
            setResults((prev) => ({ ...prev, [toolType]: { status: "done", result: resp } }))
          }
        } catch (err: any) {
          if (!abortRef.current) {
            setResults((prev) => ({ ...prev, [toolType]: { status: "error", result: undefined } }))
          }
        }
      })
    )

    setTotalMs(Math.round(performance.now() - t0))
    setRunning(false)
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    // Clear q param from URL without navigation
    if (searchParams.get("q")) router.replace("/admin/tools")
    runAnalysis()
  }

  const hasResults = Object.keys(results).length > 0
  const doneCount = Object.values(results).filter((r) => r.status === "done" || r.status === "error").length

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
            Run multiple tools in parallel on a domain
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <form onSubmit={handleSubmit} className="flex items-end gap-3">
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="qa-target" className="text-xs text-muted-foreground">
                Domain
              </Label>
              <Input
                id="qa-target"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                placeholder="example.com"
                disabled={running}
              />
            </div>
            <Button type="submit" disabled={running || !target.trim() || selectedTools.length === 0}>
              {running ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-1" />
                  {doneCount}/{selectedTools.length}
                </>
              ) : (
                <>
                  <Zap className="h-4 w-4 mr-1" />
                  Run Analysis
                </>
              )}
            </Button>
          </form>

          {/* Tool selector */}
          <div>
            <p className="text-xs text-muted-foreground mb-2">Tools to run</p>
            <div className="flex flex-wrap gap-x-4 gap-y-2">
              {TOOL_DEFINITIONS.filter((t) => t.type !== "website_clone").map((t) => (
                <label key={t.type} className="flex items-center gap-1.5 cursor-pointer">
                  <Checkbox
                    checked={selectedTools.includes(t.type)}
                    onCheckedChange={() => toggleTool(t.type)}
                    disabled={running}
                    className="h-3 w-3"
                  />
                  <span className="text-xs">{t.name}</span>
                </label>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Live Results */}
      {hasResults && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">
                Results for <span className="font-mono">{target.replace(/^https?:\/\//, "").replace(/^www\./, "").split("/")[0]}</span>
              </CardTitle>
              <div className="flex items-center gap-2">
                {running ? (
                  <Badge variant="secondary">
                    <Loader2 className="h-3 w-3 animate-spin mr-1" />
                    {doneCount}/{selectedTools.length}
                  </Badge>
                ) : (
                  <Badge variant="default">completed</Badge>
                )}
                {totalMs != null && (
                  <span className="text-xs text-muted-foreground tabular-nums">{totalMs}ms</span>
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {selectedTools.map((toolType) => {
              const entry = results[toolType]
              const toolDef = TOOL_DEFINITIONS.find((t) => t.type === toolType)
              if (!entry) return null

              if (entry.status === "pending" || entry.status === "running") {
                return (
                  <div key={toolType} className="space-y-2">
                    <div className="flex items-center gap-2">
                      <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
                      <span className="text-sm text-muted-foreground">{toolDef?.name ?? toolType}</span>
                    </div>
                    <Skeleton className="h-10" />
                  </div>
                )
              }

              if (entry.status === "error" || !entry.result) {
                return (
                  <div key={toolType} className="p-3 rounded-md border border-destructive/30 bg-destructive/5">
                    <p className="text-xs text-destructive font-medium">{toolDef?.name ?? toolType} — failed</p>
                  </div>
                )
              }

              return (
                <ToolResultEnvelope
                  key={toolType}
                  result={entry.result}
                  title={toolDef?.name ?? toolType}
                >
                  {entry.result.result && (
                    <ToolResultRenderer toolType={toolType} data={entry.result.result} />
                  )}
                </ToolResultEnvelope>
              )
            })}
          </CardContent>
        </Card>
      )}

      {/* Essential Tools */}
      <div>
        <h2 className="text-sm font-medium text-muted-foreground mb-3">Essential Tools</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {essential.map((tool) => <ToolCard key={tool.type} tool={tool} />)}
        </div>
      </div>

      {/* Enrichment Tools */}
      <div>
        <h2 className="text-sm font-medium text-muted-foreground mb-3">Enrichment Tools</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {enrichment.map((tool) => <ToolCard key={tool.type} tool={tool} />)}
        </div>
      </div>
    </div>
  )
}
