"use client"

import { useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { AlertTriangle } from "lucide-react"

interface DomainVariant {
  domain: string
  type: string
}

interface DomainSimilarityResult {
  domain: string
  variants: DomainVariant[]
  registered: DomainVariant[]
  registered_count: number
  total_generated: number
}

const TYPE_LABELS: Record<string, string> = {
  omission: "Omission",
  duplication_or_insertion: "Duplicate/Insert",
  substitution: "Substitution",
  hyphen: "Hyphen",
  tld_variation: "TLD",
  prefix: "Prefix",
  suffix: "Suffix",
  prefix_hyphen: "Prefix+Hyphen",
  suffix_hyphen: "Suffix+Hyphen",
  unknown: "Other",
}

export function DomainSimilarityResult({ data }: { data: DomainSimilarityResult }) {
  const [search, setSearch] = useState("")
  const [showAll, setShowAll] = useState(false)

  const registered = data.registered ?? []
  const allVariants = data.variants ?? []

  const filtered = allVariants.filter((v) =>
    !search || v.domain.includes(search.toLowerCase())
  )
  const displayed = showAll ? filtered : filtered.slice(0, 50)

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="flex items-center gap-4 p-3 rounded-md bg-muted/50">
        <AlertTriangle className="h-4 w-4 text-yellow-500 shrink-0" />
        <div className="flex-1">
          <p className="text-sm font-medium">
            {registered.length} registered variants found
          </p>
          <p className="text-xs text-muted-foreground">
            {data.total_generated} total variations generated
          </p>
        </div>
      </div>

      {/* Registered — always shown */}
      {registered.length > 0 && (
        <div>
          <p className="text-xs font-medium text-destructive mb-2">
            Registered domains ({registered.length})
          </p>
          <div className="flex flex-wrap gap-1">
            {registered.map((v) => (
              <div key={v.domain} className="flex items-center gap-1">
                <Badge variant="destructive" className="text-xs font-mono font-normal">
                  {v.domain}
                </Badge>
                <Badge variant="outline" className="text-xs">{TYPE_LABELS[v.type] ?? v.type}</Badge>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* All variants */}
      {allVariants.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-medium text-muted-foreground">All variants</p>
            <Input
              className="h-7 w-48 text-xs"
              placeholder="Filter..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="flex flex-wrap gap-1 max-h-64 overflow-y-auto">
            {displayed.map((v) => {
              const isRegistered = registered.some((r) => r.domain === v.domain)
              return (
                <Badge
                  key={v.domain}
                  variant={isRegistered ? "destructive" : "outline"}
                  className="text-xs font-mono font-normal"
                >
                  {v.domain}
                </Badge>
              )
            })}
          </div>
          {filtered.length > 50 && !showAll && (
            <Button
              variant="ghost"
              size="sm"
              className="mt-2 text-xs"
              onClick={() => setShowAll(true)}
            >
              Show all {filtered.length} variants
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
