"use client"

import { useState } from "react"
import { useParams } from "next/navigation"
import Link from "next/link"
import { toolsApi } from "@/lib/api"
import { getToolBySlug } from "@/lib/tools"
import type { ToolResponse } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { ToolExecutionForm } from "@/components/tools/tool-execution-form"
import { ToolResultEnvelope } from "@/components/tools/tool-result-envelope"
import { ToolResultRenderer } from "@/components/tools/result-renderers"
import { ArrowLeft, RefreshCw } from "lucide-react"

export default function ToolPage() {
  const params = useParams()
  const slug = params.tool as string
  const tool = getToolBySlug(slug)

  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ToolResponse | null>(null)
  const [error, setError] = useState("")

  if (!tool) {
    return (
      <div className="space-y-4">
        <Link href="/admin/tools">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="h-3 w-3 mr-1" />
            Back to Tools
          </Button>
        </Link>
        <p className="text-muted-foreground">Tool not found: {slug}</p>
      </div>
    )
  }

  async function handleSubmit(target: string, force: boolean) {
    setLoading(true)
    setError("")
    setResult(null)
    try {
      const resp = await toolsApi.run(slug, target, force)
      setResult(resp)
    } catch (err: any) {
      setError(err.message || "Tool execution failed")
    } finally {
      setLoading(false)
    }
  }

  function handleForceRerun() {
    if (!result) return
    setLoading(true)
    setError("")
    toolsApi
      .run(slug, result.target, true)
      .then(setResult)
      .catch((err: any) => setError(err.message || "Re-run failed"))
      .finally(() => setLoading(false))
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Link href="/admin/tools">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="h-3 w-3 mr-1" />
            Back
          </Button>
        </Link>
        <div>
          <h1 className="text-2xl font-semibold">{tool.name}</h1>
          <p className="text-sm text-muted-foreground">{tool.description}</p>
        </div>
      </div>

      <ToolExecutionForm
        onSubmit={handleSubmit}
        loading={loading}
        placeholder={tool.type === "website_clone" ? "target.com|reference.com" : "example.com"}
      />

      {error && <p className="text-sm text-destructive">{error}</p>}

      {result && (
        <div className="space-y-3">
          {result.cached && (
            <div className="flex justify-end">
              <Button
                variant="outline"
                size="sm"
                onClick={handleForceRerun}
                disabled={loading}
              >
                <RefreshCw className="h-3 w-3 mr-1" />
                Force Re-run
              </Button>
            </div>
          )}
          <ToolResultEnvelope result={result} title={tool.name}>
            {result.result && (
              <ToolResultRenderer
                toolType={tool.type}
                data={result.result}
              />
            )}
          </ToolResultEnvelope>
        </div>
      )}
    </div>
  )
}
