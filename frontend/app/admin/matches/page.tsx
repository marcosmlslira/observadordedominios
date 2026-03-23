"use client"

import { useCallback, useEffect, useState } from "react"
import { api } from "@/lib/api"
import type {
  Brand,
  BrandListResponse,
  MatchListResponse,
  SimilarityMatch,
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

const ALL_FILTER_VALUE = "all"
const STATUSES = ["new", "reviewing", "dismissed", "confirmed_threat"]
const RISK_LEVELS = ["low", "medium", "high", "critical"]

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
  const [offset, setOffset] = useState(0)
  const limit = 50

  // Detail/edit dialog
  const [selectedMatch, setSelectedMatch] = useState<SimilarityMatch | null>(
    null,
  )
  const [editStatus, setEditStatus] = useState("")
  const [editNotes, setEditNotes] = useState("")
  const [saving, setSaving] = useState(false)

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
  }, [selectedBrand, statusFilter, riskFilter, offset])

  useEffect(() => {
    fetchMatches()
  }, [fetchMatches])

  // Reset offset when filters change
  useEffect(() => {
    setOffset(0)
  }, [selectedBrand, statusFilter, riskFilter])

  function openDetail(match: SimilarityMatch) {
    setSelectedMatch(match)
    setEditStatus(match.status)
    setEditNotes(match.notes || "")
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
                      colSpan={7}
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
                      <TableCell className="tabular-nums">
                        {(match.score_final * 100).toFixed(0)}%
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
        onOpenChange={(open) => !open && setSelectedMatch(null)}
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
