"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Loader2, Play } from "lucide-react"

interface ToolExecutionFormProps {
  onSubmit: (target: string, force: boolean) => void
  loading: boolean
  placeholder?: string
  initialValue?: string
}

export function ToolExecutionForm({
  onSubmit,
  loading,
  placeholder = "example.com",
  initialValue,
}: ToolExecutionFormProps) {
  const [target, setTarget] = useState(initialValue ?? "")

  useEffect(() => {
    if (initialValue) setTarget(initialValue)
  }, [initialValue])

  function normalize(value: string): string {
    return value.trim().toLowerCase()
      .replace(/^https?:\/\//, "")
      .replace(/^www\./, "")
      .split("/")[0]
      .split("?")[0]
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!target.trim()) return
    onSubmit(normalize(target), false)
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-end gap-3">
      <div className="flex-1 space-y-1.5">
        <Label htmlFor="target" className="text-xs text-muted-foreground">
          Domain or IP
        </Label>
        <Input
          id="target"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          placeholder={placeholder}
          disabled={loading}
          autoFocus
        />
      </div>
      <Button type="submit" disabled={loading || !target.trim()}>
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin mr-1" />
        ) : (
          <Play className="h-4 w-4 mr-1" />
        )}
        Analyze
      </Button>
    </form>
  )
}
