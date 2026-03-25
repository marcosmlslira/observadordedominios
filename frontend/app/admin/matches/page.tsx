"use client"

import { useCallback, useEffect, useState } from "react"
import { api, toolsApi } from "@/lib/api"
import type {
  Brand,
  BrandListResponse,
  MatchListResponse,
  QuickAnalysisResponse,
  SimilarityMatch,
  ToolType,
} from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { ToolResultRenderer } from "@/components/tools/result-renderers"
import { ToolResultEnvelope } from "@/components/tools/tool-result-envelope"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { RefreshCw } from "lucide-react"

function riskVariant(risk: string) {
  switch (risk) {
    case "critical":
      return "destructive" as const
    case "high":
      return "destructive" as const
    case "medium":
      return "secondary" as const
    case "low":
      return "outline" as const
    default:
      return "outline" as const
  }
}

function statusVariant(status: string) {
  switch (status) {
    case "confirmed_threat":
      return "destructive" as const
    case "reviewing":
      return "secondary" as const
    case "dismissed":
      return "outline" as const
    default:
      return "default" as const
  }
}

function attentionVariant(bucket: string | null) {
  switch (bucket) {
    case "immediate_attention":
      return "destructive" as const
    case "defensive_gap":
      return "secondary" as const
    case "watchlist":
      return "outline" as const
    default:
      return "outline" as const
  }
}

function attentionLabel(bucket: string | null) {
  switch (bucket) {
    case "immediate_attention":
      return "Look Now"
    case "defensive_gap":
      return "Defensive Gap"
    case "watchlist":
      return "Watchlist"
    default:
      return "Unclassified"
  }
}

const ALL_FILTER_VALUE = "all"
const STATUSES = ["new", "reviewing", "dismissed", "confirmed_threat"]
const RISK_LEVELS = ["low", "medium", "high", "critical"]
const ATTENTION_BUCKETS = [
  "immediate_attention",
  "defensive_gap",
  "watchlist",
]
const MATCH_ENRICHMENT_TOOLS: ToolType[] = [
  "whois",
  "http_headers",
  "suspicious_page",
  "email_security",
  "ip_geolocation",
]

export default function MatchesPage() {
  const [brands, setBrands] = useState<Brand[]>([])
  const [selectedBrand, setSelectedBrand] = useState<string>("")
  const [matches, setMatches] = useState<SimilarityMatch[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [matchesLoading, setMatchesLoading] = useState(false)

  // Filters
  const [statusFilter, setStatusFilter] = useState("")
  const [riskFilter, setRiskFilter] = useState("")
  const [attentionFilter, setAttentionFilter] = useState("")
  const [offset, setOffset] = useState(0)
  const limit = 50

  // Detail/edit dialog
  const [selectedMatch, setSelectedMatch] = useState<SimilarityMatch | null>(
    null,
  )
  const [editStatus, setEditStatus] = useState("")
  const [editNotes, setEditNotes] = useState("")
  const [saving, setSaving] = useState(false)
  const [enriching, setEnriching] = useState(false)
  const [enrichment, setEnrichment] = useState<QuickAnalysisResponse | null>(
    null,
  )

  useEffect(() => {
    api
      .get<BrandListResponse>("/v1/brands?active_only=false")
      .then((data) => {
        setBrands(data.items)
        if (data.items.length > 0) {
          setSelectedBrand(data.items[0].id)
        }
      })
      .finally(() => setLoading(false))
  }, [])

  const fetchMatches = useCallback(async () => {
    if (!selectedBrand) return
    setMatchesLoading(true)
    try {
      const params = new URLSearchParams()
      params.set("limit", String(limit))
      params.set("offset", String(offset))
      if (statusFilter) params.set("status", statusFilter)
      if (riskFilter) params.set("risk_level", riskFilter)
      if (attentionFilter) params.set("attention_bucket", attentionFilter)

      const data = await api.get<MatchListResponse>(
        `/v1/brands/${selectedBrand}/matches?${params}`,
      )
      setMatches(data.items)
      setTotal(data.total)
    } catch {
      // ignore
    } finally {
      setMatchesLoading(false)
    }
  }, [selectedBrand, statusFilter, riskFilter, attentionFilter, offset])

  useEffect(() => {
    fetchMatches()
  }, [fetchMatches])

  // Reset offset when filters change
  useEffect(() => {
    setOffset(0)
  }, [selectedBrand, statusFilter, riskFilter, attentionFilter])

  const bucketCounts = matches.reduce(
    (acc, match) => {
      const bucket = match.attention_bucket || "watchlist"
      acc[bucket] = (acc[bucket] || 0) + 1
      return acc
    },
    {} as Record<string, number>,
  )

  function openDetail(match: SimilarityMatch) {
    setSelectedMatch(match)
    setEditStatus(match.status)
    setEditNotes(match.notes || "")
    setEnrichment(null)
  }

  async function handleSaveStatus() {
    if (!selectedMatch) return
    setSaving(true)
    try {
      await api.patch(`/v1/matches/${selectedMatch.id}`, {
        status: editStatus,
        notes: editNotes || null,
      })
      setSelectedMatch(null)
      await fetchMatches()
    } catch {
      // ignore
    } finally {
      setSaving(false)
    }
  }

  async function handleQuickAnalysis() {
    if (!selectedMatch) return
    setEnriching(true)
    try {
      const result = await toolsApi.quickAnalysis(
        `${selectedMatch.domain_name}.${selectedMatch.tld}`,
        MATCH_ENRICHMENT_TOOLS,
      )
      setEnrichment(result)
    } catch {
      setEnrichment(null)
    } finally {
      setEnriching(false)
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold">Similarity Matches</h1>
        <Skeleton className="h-96 rounded-xl" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Similarity Matches</h1>
        <Button variant="outline" size="sm" onClick={fetchMatches}>
          <RefreshCw className="h-3 w-3 mr-1" />
          Refresh
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="w-60">
          <Label className="text-xs text-muted-foreground">Brand</Label>
          <Select value={selectedBrand} onValueChange={setSelectedBrand}>
            <SelectTrigger>
              <SelectValue placeholder="Select brand" />
            </SelectTrigger>
            <SelectContent>
              {brands.map((b) => (
                <SelectItem key={b.id} value={b.id}>
                  {b.brand_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="w-40">
          <Label className="text-xs text-muted-foreground">Status</Label>
          <Select
            value={statusFilter || ALL_FILTER_VALUE}
            onValueChange={(value) =>
              setStatusFilter(value === ALL_FILTER_VALUE ? "" : value)
            }
          >
            <SelectTrigger>
              <SelectValue placeholder="All" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_FILTER_VALUE}>All</SelectItem>
              {STATUSES.map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="w-40">
          <Label className="text-xs text-muted-foreground">Risk Level</Label>
          <Select
            value={riskFilter || ALL_FILTER_VALUE}
            onValueChange={(value) =>
              setRiskFilter(value === ALL_FILTER_VALUE ? "" : value)
            }
          >
            <SelectTrigger>
              <SelectValue placeholder="All" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_FILTER_VALUE}>All</SelectItem>
              {RISK_LEVELS.map((r) => (
                <SelectItem key={r} value={r}>
                  {r}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="w-44">
          <Label className="text-xs text-muted-foreground">Attention</Label>
          <Select
            value={attentionFilter || ALL_FILTER_VALUE}
            onValueChange={(value) =>
              setAttentionFilter(value === ALL_FILTER_VALUE ? "" : value)
            }
          >
            <SelectTrigger>
              <SelectValue placeholder="All" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_FILTER_VALUE}>All</SelectItem>
              {ATTENTION_BUCKETS.map((bucket) => (
                <SelectItem key={bucket} value={bucket}>
                  {attentionLabel(bucket)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        {ATTENTION_BUCKETS.map((bucket) => (
          <Card key={bucket}>
            <CardContent className="flex items-center justify-between py-4">
              <div className="space-y-1">
                <p className="text-sm font-medium">{attentionLabel(bucket)}</p>
                <p className="text-xs text-muted-foreground">
                  {bucket === "immediate_attention"
                    ? "Likely deserves analyst attention now."
                    : bucket === "defensive_gap"
                      ? "Brand protection or portfolio gap."
                      : "Low-signal items for background tracking."}
                </p>
              </div>
              <Badge variant={attentionVariant(bucket)}>
                {bucketCounts[bucket] || 0}
              </Badge>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Results */}
      <Card>
        <CardContent className="p-0">
          {matchesLoading ? (
            <div className="p-8">
              <Skeleton className="h-64" />
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Domain</TableHead>
                  <TableHead>TLD</TableHead>
                  <TableHead>Attention</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>Risk</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>First Detected</TableHead>
                  <TableHead>Reasons</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {matches.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={8}
                      className="text-center text-muted-foreground py-8"
                    >
                      {selectedBrand
                        ? "No matches found for this brand"
                        : "Select a brand to view matches"}
                    </TableCell>
                  </TableRow>
                ) : (
                  matches.map((match) => (
                    <TableRow
                      key={match.id}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => openDetail(match)}
                    >
                      <TableCell className="font-mono text-sm">
                        {match.domain_name}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        .{match.tld}
                      </TableCell>
                      <TableCell>
                        <Badge variant={attentionVariant(match.attention_bucket)}>
                          {attentionLabel(match.attention_bucket)}
                        </Badge>
                      </TableCell>
                      <TableCell className="tabular-nums">
                        <div className="space-y-1">
                          <div>{(match.score_final * 100).toFixed(0)}%</div>
                          {match.actionability_score != null && (
                            <div className="text-[11px] text-muted-foreground">
                              Action {(match.actionability_score * 100).toFixed(0)}%
                            </div>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={riskVariant(match.risk_level)}>
                          {match.risk_level}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={statusVariant(match.status)}>
                          {match.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs">
                        {new Date(match.first_detected_at).toLocaleDateString()}
                      </TableCell>
                      <TableCell className="max-w-[200px]">
                        <div className="flex flex-wrap gap-1">
                          {match.reasons.slice(0, 3).map((r) => (
                            <Badge
                              key={r}
                              variant="outline"
                              className="text-[10px]"
                            >
                              {r}
                            </Badge>
                          ))}
                          {match.reasons.length > 3 && (
                            <Badge variant="outline" className="text-[10px]">
                              +{match.reasons.length - 3}
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {total > limit && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Showing {offset + 1}-{Math.min(offset + limit, total)} of {total}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - limit))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={offset + limit >= total}
              onClick={() => setOffset(offset + limit)}
            >
              Next
            </Button>
          </div>
        </div>
      )}

      {/* Match detail / review dialog */}
      <Dialog
        open={!!selectedMatch}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedMatch(null)
            setEnrichment(null)
          }
        }}
      >
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="font-mono">
              {selectedMatch?.domain_name}.{selectedMatch?.tld}
            </DialogTitle>
          </DialogHeader>
          {selectedMatch && (
            <div className="space-y-4">
              {/* Scores */}
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <span className="text-muted-foreground">Attention:</span>{" "}
                  <Badge variant={attentionVariant(selectedMatch.attention_bucket)}>
                    {attentionLabel(selectedMatch.attention_bucket)}
                  </Badge>
                </div>
                {selectedMatch.actionability_score != null && (
                  <div>
                    <span className="text-muted-foreground">Actionability:</span>{" "}
                    <span className="font-medium">
                      {(selectedMatch.actionability_score * 100).toFixed(1)}%
                    </span>
                  </div>
                )}
                <div>
                  <span className="text-muted-foreground">Final Score:</span>{" "}
                  <span className="font-medium">
                    {(selectedMatch.score_final * 100).toFixed(1)}%
                  </span>
                </div>
                <div>
                  <span className="text-muted-foreground">Risk:</span>{" "}
                  <Badge variant={riskVariant(selectedMatch.risk_level)}>
                    {selectedMatch.risk_level}
                  </Badge>
                </div>
                {selectedMatch.score_trigram != null && (
                  <div>
                    <span className="text-muted-foreground">Trigram:</span>{" "}
                    {(selectedMatch.score_trigram * 100).toFixed(0)}%
                  </div>
                )}
                {selectedMatch.score_levenshtein != null && (
                  <div>
                    <span className="text-muted-foreground">Levenshtein:</span>{" "}
                    {(selectedMatch.score_levenshtein * 100).toFixed(0)}%
                  </div>
                )}
                {selectedMatch.score_brand_hit != null && (
                  <div>
                    <span className="text-muted-foreground">Brand Hit:</span>{" "}
                    {(selectedMatch.score_brand_hit * 100).toFixed(0)}%
                  </div>
                )}
                {selectedMatch.score_keyword != null && (
                  <div>
                    <span className="text-muted-foreground">Keyword:</span>{" "}
                    {(selectedMatch.score_keyword * 100).toFixed(0)}%
                  </div>
                )}
                {selectedMatch.score_homograph != null && (
                  <div>
                    <span className="text-muted-foreground">Homograph:</span>{" "}
                    {(selectedMatch.score_homograph * 100).toFixed(0)}%
                  </div>
                )}
              </div>

              {/* Reasons */}
              <div>
                <Label className="text-xs text-muted-foreground">Reasons</Label>
                <div className="flex flex-wrap gap-1 mt-1">
                  {selectedMatch.reasons.map((r) => (
                    <Badge key={r} variant="outline" className="text-xs">
                      {r}
                    </Badge>
                  ))}
                </div>
              </div>

              {selectedMatch.attention_reasons &&
                selectedMatch.attention_reasons.length > 0 && (
                  <div>
                    <Label className="text-xs text-muted-foreground">
                      Why It Matters
                    </Label>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {selectedMatch.attention_reasons.map((reason) => (
                        <Badge
                          key={reason}
                          variant="secondary"
                          className="text-xs"
                        >
                          {reason}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

              {selectedMatch.recommended_action && (
                <div className="rounded-lg border bg-muted/30 p-3 text-sm">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Recommended Action
                  </p>
                  <p className="mt-1">{selectedMatch.recommended_action}</p>
                </div>
              )}

              {selectedMatch.enrichment_summary && (
                <div className="space-y-3 rounded-lg border bg-muted/20 p-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">Auto Enrichment</p>
                      <p className="text-xs text-muted-foreground">
                        Selective tool-based signals applied during similarity processing.
                      </p>
                    </div>
                    <Badge variant="outline">
                      {selectedMatch.enrichment_status || "unknown"}
                    </Badge>
                  </div>

                  {selectedMatch.enrichment_summary.signals &&
                    selectedMatch.enrichment_summary.signals.length > 0 && (
                      <div className="space-y-2">
                        <Label className="text-xs text-muted-foreground">
                          Operational Signals
                        </Label>
                        <div className="space-y-2">
                          {selectedMatch.enrichment_summary.signals.map((signal) => (
                            <div
                              key={signal.code}
                              className="rounded-md border bg-background/70 p-2"
                            >
                              <div className="flex items-center gap-2">
                                <Badge variant="secondary" className="text-[10px]">
                                  {signal.severity}
                                </Badge>
                                <span className="text-xs font-medium">
                                  {signal.code}
                                </span>
                              </div>
                              <p className="mt-1 text-xs text-muted-foreground">
                                {signal.description}
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                  {selectedMatch.enrichment_summary.tools && (
                    <div className="space-y-2">
                      <Label className="text-xs text-muted-foreground">
                        Tool Facts
                      </Label>
                      <div className="grid gap-2 md:grid-cols-2">
                        {Object.entries(selectedMatch.enrichment_summary.tools).map(
                          ([toolName, toolData]) => (
                            <div
                              key={toolName}
                              className="rounded-md border bg-background/70 p-2 text-xs"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <span className="font-medium">{toolName}</span>
                                <Badge variant="outline">
                                  {toolData.status || "unknown"}
                                </Badge>
                              </div>
                              {toolData.error ? (
                                <p className="mt-1 text-destructive">{toolData.error}</p>
                              ) : (
                                <pre className="mt-1 whitespace-pre-wrap break-words text-muted-foreground">
                                  {JSON.stringify(toolData.summary ?? {}, null, 2)}
                                </pre>
                              )}
                            </div>
                          ),
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}

              <div className="border-t pt-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">Operational Enrichment</p>
                    <p className="text-xs text-muted-foreground">
                      Run focused checks to confirm whether this is an active threat,
                      a defensive registration, or just background noise.
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleQuickAnalysis}
                    disabled={enriching}
                  >
                    {enriching ? "Running..." : "Run Quick Analysis"}
                  </Button>
                </div>

                {enrichment && (
                  <div className="space-y-3">
                    <div className="rounded-lg border bg-muted/20 p-3 text-xs text-muted-foreground">
                      Quick analysis finished in {enrichment.total_duration_ms}ms.
                      Focus first on `Suspicious Page`, `Email Security`, and `WHOIS`.
                    </div>
                    {MATCH_ENRICHMENT_TOOLS.map((toolType) => {
                      const entry = enrichment.results[toolType]
                      if (!entry) return null

                      if (entry.status !== "completed" || !entry.result) {
                        return (
                          <div
                            key={toolType}
                            className="rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive"
                          >
                            {toolType} did not return a usable result.
                          </div>
                        )
                      }

                      return (
                        <ToolResultEnvelope
                          key={toolType}
                          title={toolType}
                          result={{
                            execution_id: enrichment.quick_analysis_id,
                            tool_type: toolType,
                            target: enrichment.target,
                            status: entry.status,
                            duration_ms: entry.duration_ms ?? null,
                            cached: false,
                            result: entry.result,
                            error: entry.error ?? null,
                            executed_at: new Date().toISOString(),
                          }}
                        >
                          <ToolResultRenderer toolType={toolType} data={entry.result} />
                        </ToolResultEnvelope>
                      )
                    })}
                  </div>
                )}
              </div>

              {/* Review form */}
              <div className="border-t pt-4 space-y-3">
                <div className="space-y-2">
                  <Label>Status</Label>
                  <Select value={editStatus} onValueChange={setEditStatus}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="new">new</SelectItem>
                      <SelectItem value="reviewing">reviewing</SelectItem>
                      <SelectItem value="dismissed">dismissed</SelectItem>
                      <SelectItem value="confirmed_threat">
                        confirmed_threat
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Notes</Label>
                  <Input
                    value={editNotes}
                    onChange={(e) => setEditNotes(e.target.value)}
                    placeholder="Optional review notes..."
                  />
                </div>
                <Button
                  onClick={handleSaveStatus}
                  disabled={saving}
                  className="w-full"
                >
                  {saving ? "Saving..." : "Update Status"}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
