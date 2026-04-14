# Frontend Monitoring UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat brands table and disconnected matches page with a monitoring-first UI: brand card grid → brand detail page with stacked sections → match drawer with evidence cards.

**Architecture:** Add monitoring pipeline types to `types.ts` and API helpers to `api.ts`; refactor brands list page to card grid; create new dynamic route `/admin/brands/[id]`; embed a sheet-based match drawer component; remove the now-redundant `/admin/matches` page and its nav entry.

**Tech Stack:** Next.js App Router, shadcn/ui (Card, Badge, Sheet, Collapsible, Tabs, Skeleton), Lucide icons, TypeScript

---

## File Map

| Status | Path | Responsibility |
|--------|------|----------------|
| Modify | `frontend/lib/types.ts` | Add monitoring pipeline types (MonitoringSummary, MatchSnapshot, BrandHealth, CycleResponse, MonitoringEvent) |
| Modify | `frontend/lib/api.ts` | Add `monitoringApi` helper (getBrandHealth, getCycles, getMatchSnapshots, getMatchEvents) |
| Modify | `frontend/app/admin/brands/page.tsx` | Replace table with card grid; each card shows health badge + threat counters |
| Create | `frontend/app/admin/brands/[id]/page.tsx` | Brand detail: header, today's cycle, domain health (collapsible), threats list, config (collapsible), history (collapsible) |
| Create | `frontend/components/monitoring/match-drawer.tsx` | Sheet drawer with 5 evidence cards + LLM assessment + status update form |
| Modify | `frontend/app/admin/layout.tsx` | Remove "Similarity Matches" nav item |
| Delete | `frontend/app/admin/matches/page.tsx` | Removed — functionality moves into brand detail page |

---

### Task 1: Add TypeScript types for monitoring pipeline

**Files:**
- Modify: `frontend/lib/types.ts`

The backend `GET /v1/brands` now returns `monitoring_summary` on each brand. The detail endpoints
`GET /v1/brands/{id}/health`, `GET /v1/brands/{id}/cycles`, `GET /v1/brands/{id}/matches?include_llm=true`,
and `GET /v1/matches/{id}/events` return new shapes. Add all types to `frontend/lib/types.ts`.

- [ ] **Step 1: Add monitoring pipeline types**

Append after the existing `// ── Scan ──` block in `frontend/lib/types.ts`:

```typescript
// ── Monitoring Pipeline ─────────────────────────────

export interface CycleSummary {
  id: string
  status: string
  finished_at: string | null
  scan_job_id: string | null
}

export interface ThreatCounts {
  immediate_attention: number
  defensive_gap: number
  watchlist: number
}

export interface MonitoringSummary {
  latest_cycle: CycleSummary | null
  threat_counts: ThreatCounts
  overall_health: "healthy" | "warning" | "critical" | "unknown"
}

// Brand now has monitoring_summary field
// (add to existing Brand interface)

export interface DomainCheckDetail {
  ok: boolean
  details?: Record<string, unknown>
}

export interface DomainHealthCheck {
  domain_id: string
  domain_name: string
  is_primary: boolean
  overall_status: string
  dns?: DomainCheckDetail
  ssl?: DomainCheckDetail
  email_security?: DomainCheckDetail
  headers?: DomainCheckDetail
  takeover?: DomainCheckDetail
  blacklist?: DomainCheckDetail
  safe_browsing?: DomainCheckDetail
  urlhaus?: DomainCheckDetail
  phishtank?: DomainCheckDetail
  suspicious_page?: DomainCheckDetail
  last_check_at: string | null
}

export interface BrandHealthResponse {
  domains: DomainHealthCheck[]
}

export interface MonitoringCycleResponse {
  id: string
  brand_id: string
  cycle_date: string
  status: string
  domains_checked: number | null
  threats_found: number | null
  finished_at: string | null
  scan_job_id: string | null
  created_at: string
}

export interface CycleListResponse {
  items: MonitoringCycleResponse[]
  total: number
}

export interface SignalSchema {
  code: string
  severity: string
  label: string
  description: string
  data: Record<string, unknown> | null
}

export interface MatchSnapshot {
  id: string
  brand_id: string
  domain_name: string
  tld: string
  label: string
  score_final: number
  attention_bucket: string | null
  matched_rule: string | null
  auto_disposition: string | null
  auto_disposition_reason: string | null
  first_detected_at: string
  domain_first_seen: string
  derived_score: number | null
  derived_bucket: string | null
  derived_risk: string | null
  derived_disposition: string | null
  active_signals: SignalSchema[]
  signal_codes: string[]
  llm_assessment: {
    risco_score: number
    categoria: string
    parecer_resumido: string
    principais_motivos: string[]
    recomendacao_acao: string
    confianca: number
  } | null
  state_fingerprint: string | null
  last_derived_at: string | null
}

export interface MatchSnapshotListResponse {
  items: MatchSnapshot[]
  total: number
}

export interface MonitoringEvent {
  id: string
  match_id: string
  event_type: string
  severity: string
  summary: string
  detail: Record<string, unknown> | null
  tool_name: string | null
  signal_code: string | null
  created_at: string
}

export interface EventListResponse {
  items: MonitoringEvent[]
  total: number
}
```

- [ ] **Step 2: Add `monitoring_summary` to Brand interface**

In the existing `Brand` interface (around line 30), add before `is_active`:

```typescript
  monitoring_summary?: MonitoringSummary
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/types.ts
git commit -m "feat(frontend): add monitoring pipeline TypeScript types"
```

---

### Task 2: Add monitoring API helpers

**Files:**
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Append `monitoringApi` to `frontend/lib/api.ts`**

Add after the `ingestionApi` block:

```typescript
// ── Monitoring API ──────────────────────────────────

export const monitoringApi = {
  getBrandHealth: (brandId: string) =>
    api.get<import("./types").BrandHealthResponse>(`/v1/brands/${brandId}/health`),

  getCycles: (brandId: string, limit = 30, offset = 0) =>
    api.get<import("./types").CycleListResponse>(
      `/v1/brands/${brandId}/cycles?limit=${limit}&offset=${offset}`
    ),

  getMatchSnapshots: (
    brandId: string,
    params?: { bucket?: string; limit?: number; offset?: number }
  ) => {
    const qs = new URLSearchParams({ include_llm: "true" })
    if (params?.bucket) qs.set("bucket", params.bucket)
    if (params?.limit != null) qs.set("limit", String(params.limit))
    if (params?.offset != null) qs.set("offset", String(params.offset))
    return api.get<import("./types").MatchSnapshotListResponse>(
      `/v1/brands/${brandId}/matches?${qs}`
    )
  },

  getMatchEvents: (matchId: string, limit = 50) =>
    api.get<import("./types").EventListResponse>(
      `/v1/matches/${matchId}/events?limit=${limit}`
    ),

  updateMatchStatus: (matchId: string, status: string, notes?: string) =>
    api.patch<import("./types").SimilarityMatch>(`/v1/matches/${matchId}`, {
      status,
      notes: notes || null,
    }),
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(frontend): add monitoringApi helper functions"
```

---

### Task 3: Refactor brands list page to card grid

**Files:**
- Modify: `frontend/app/admin/brands/page.tsx`

Replace the `<Table>` rendering of brands with a responsive card grid. Each card shows:
- Brand name + label + active/inactive badge
- Health badge (overall_health from monitoring_summary)
- Three threat counters (immediate_attention in red, defensive_gap in yellow, watchlist in gray)
- Official domains as small badges
- "View" link → `/admin/brands/{id}`
- Scan button (existing logic preserved)

The create-brand dialog and delete dialog remain intact.

- [ ] **Step 1: Rewrite brands list page**

Replace the full content of `frontend/app/admin/brands/page.tsx` with:

```tsx
"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { api } from "@/lib/api"
import type {
  Brand,
  BrandAliasRequest,
  BrandListResponse,
  ScanSummaryResponse,
} from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Plus, Search, Trash2, RefreshCw, ArrowRight, AlertTriangle, ShieldAlert, Eye } from "lucide-react"

const DEFAULT_TLD_SCOPE =
  "com,net,org,xyz,online,site,store,top,info,tech,space,website,fun," +
  "club,vip,icu,live,digital,world,today,email,solutions,services," +
  "support,group,company,center,zone,agency,systems,network,works," +
  "tools,io,ai,dev,app,cloud,software,co,biz,shop,sale,deals,market," +
  "finance,financial,money,credit,loan,bank,capital,fund,exchange," +
  "trading,pay,cash,us,uk,ca,au,de,fr,es,it,nl,eu,asia,news,media," +
  "blog,press,link,click,one,pro,name,life,plus,now,global,expert," +
  "academy,education,school,host,hosting,domains,security,safe," +
  "protect,chat,social,community,team,studio,design,marketing," +
  "consulting,partners,ventures,holdings,international"

function splitCsv(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean)
}

function buildAliasRequests(aliases: string, phrases: string): BrandAliasRequest[] {
  return [
    ...splitCsv(aliases).map((value) => ({ value, type: "brand_alias" as const })),
    ...splitCsv(phrases).map((value) => ({ value, type: "brand_phrase" as const })),
  ]
}

function healthVariant(health: string | undefined) {
  switch (health) {
    case "critical": return "destructive" as const
    case "warning": return "secondary" as const
    case "healthy": return "outline" as const
    default: return "outline" as const
  }
}

function healthLabel(health: string | undefined) {
  switch (health) {
    case "critical": return "Critical"
    case "warning": return "Warning"
    case "healthy": return "Healthy"
    default: return "Unknown"
  }
}

export default function BrandsPage() {
  const [brands, setBrands] = useState<Brand[]>([])
  const [loading, setLoading] = useState(true)

  const [createOpen, setCreateOpen] = useState(false)
  const [newName, setNewName] = useState("")
  const [newPrimaryBrand, setNewPrimaryBrand] = useState("")
  const [newOfficialDomains, setNewOfficialDomains] = useState("")
  const [newAliases, setNewAliases] = useState("")
  const [newPhrases, setNewPhrases] = useState("")
  const [newKeywords, setNewKeywords] = useState("")
  const [newTlds, setNewTlds] = useState(DEFAULT_TLD_SCOPE)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState("")

  const [deleteTarget, setDeleteTarget] = useState<Brand | null>(null)
  const [deleting, setDeleting] = useState(false)

  const fetchBrands = useCallback(async () => {
    try {
      const data = await api.get<BrandListResponse>("/v1/brands?active_only=false")
      setBrands(data.items)
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    fetchBrands().then(() => setLoading(false))
  }, [fetchBrands])

  async function handleCreate() {
    setCreating(true)
    setCreateError("")
    try {
      await api.post("/v1/brands", {
        brand_name: newName.trim(),
        primary_brand_name: newPrimaryBrand.trim() || undefined,
        official_domains: splitCsv(newOfficialDomains),
        aliases: buildAliasRequests(newAliases, newPhrases),
        keywords: splitCsv(newKeywords),
        tld_scope: splitCsv(newTlds),
      })
      setCreateOpen(false)
      setNewName(""); setNewPrimaryBrand(""); setNewOfficialDomains("")
      setNewAliases(""); setNewPhrases(""); setNewKeywords("")
      setNewTlds(DEFAULT_TLD_SCOPE)
      await fetchBrands()
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Create failed")
    } finally {
      setCreating(false)
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await api.delete(`/v1/brands/${deleteTarget.id}`)
      setDeleteTarget(null)
      await fetchBrands()
    } catch {
      // ignore
    } finally {
      setDeleting(false)
    }
  }

  async function handleScan(e: React.MouseEvent, brandId: string) {
    e.preventDefault()
    try {
      await api.post<ScanSummaryResponse>(`/v1/brands/${brandId}/scan`)
    } catch {
      // ignore
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold">Monitoring Profiles</h1>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-48 rounded-xl" />)}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Monitoring Profiles</h1>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchBrands}>
            <RefreshCw className="mr-1 h-3 w-3" />
            Refresh
          </Button>
          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger asChild>
              <Button size="sm">
                <Plus className="mr-1 h-3 w-3" />
                New Profile
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl">
              <DialogHeader>
                <DialogTitle>Create Monitoring Profile</DialogTitle>
              </DialogHeader>
              <div className="grid gap-4 pt-2 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="brand-name">Profile Name</Label>
                  <Input id="brand-name" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="e.g. Growth Suplementos" autoFocus />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="primary-brand-name">Primary Brand Name</Label>
                  <Input id="primary-brand-name" value={newPrimaryBrand} onChange={(e) => setNewPrimaryBrand(e.target.value)} placeholder="e.g. Growth Suplementos" />
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="official-domains">Official Domains</Label>
                  <Input id="official-domains" value={newOfficialDomains} onChange={(e) => setNewOfficialDomains(e.target.value)} placeholder="e.g. gsuplementos.com.br, growth.com" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="brand-aliases">Brand Aliases</Label>
                  <Input id="brand-aliases" value={newAliases} onChange={(e) => setNewAliases(e.target.value)} placeholder="e.g. growth, gsuplementos" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="brand-phrases">Brand Phrases</Label>
                  <Input id="brand-phrases" value={newPhrases} onChange={(e) => setNewPhrases(e.target.value)} placeholder="e.g. growth suplementos" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="keywords">Support Keywords</Label>
                  <Input id="keywords" value={newKeywords} onChange={(e) => setNewKeywords(e.target.value)} placeholder="e.g. suplementos, whey" />
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="tlds">TLD Scope</Label>
                  <Input id="tlds" value={newTlds} onChange={(e) => setNewTlds(e.target.value)} />
                </div>
                {createError && <p className="text-sm text-destructive md:col-span-2">{createError}</p>}
                <Button onClick={handleCreate} disabled={creating || !newName.trim()} className="w-full md:col-span-2">
                  {creating ? "Creating..." : "Create Profile"}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {brands.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            No monitoring profiles yet. Create the first one to start scanning.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {brands.map((brand) => {
            const summary = brand.monitoring_summary
            const threats = summary?.threat_counts
            const health = summary?.overall_health
            return (
              <Link key={brand.id} href={`/admin/brands/${brand.id}`} className="group block">
                <Card className="h-full transition-shadow hover:shadow-md">
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="font-semibold leading-tight truncate">{brand.brand_name}</p>
                        <p className="font-mono text-[11px] text-muted-foreground mt-0.5">{brand.brand_label}</p>
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        {!brand.is_active && <Badge variant="outline" className="text-[10px]">inactive</Badge>}
                        <Badge variant={healthVariant(health)} className="text-[11px]">
                          {healthLabel(health)}
                        </Badge>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {/* Threat counters */}
                    <div className="grid grid-cols-3 gap-2 text-center">
                      <div className="rounded-md bg-destructive/10 px-2 py-1.5">
                        <p className="text-lg font-bold text-destructive leading-none">{threats?.immediate_attention ?? 0}</p>
                        <p className="text-[10px] text-muted-foreground mt-0.5">Immediate</p>
                      </div>
                      <div className="rounded-md bg-secondary/50 px-2 py-1.5">
                        <p className="text-lg font-bold leading-none">{threats?.defensive_gap ?? 0}</p>
                        <p className="text-[10px] text-muted-foreground mt-0.5">Defensive</p>
                      </div>
                      <div className="rounded-md bg-muted px-2 py-1.5">
                        <p className="text-lg font-bold leading-none">{threats?.watchlist ?? 0}</p>
                        <p className="text-[10px] text-muted-foreground mt-0.5">Watchlist</p>
                      </div>
                    </div>

                    {/* Official domains */}
                    <div className="flex flex-wrap gap-1">
                      {brand.official_domains.slice(0, 3).map((d) => (
                        <Badge key={d.id} variant={d.is_primary ? "default" : "outline"} className="text-[11px] font-mono">
                          {d.domain_name}
                        </Badge>
                      ))}
                      {brand.official_domains.length > 3 && (
                        <Badge variant="outline" className="text-[11px]">+{brand.official_domains.length - 3}</Badge>
                      )}
                    </div>

                    {/* Footer row */}
                    <div className="flex items-center justify-between pt-1">
                      <div className="flex gap-1">
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-[11px]"
                          onClick={(e) => handleScan(e, brand.id)}
                          title="Trigger scan"
                        >
                          <Search className="h-3 w-3 mr-1" />
                          Scan
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-[11px] text-destructive"
                          onClick={(e) => { e.preventDefault(); setDeleteTarget(brand) }}
                          title="Delete"
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                      <span className="text-xs text-muted-foreground group-hover:text-foreground flex items-center gap-1 transition-colors">
                        View <ArrowRight className="h-3 w-3" />
                      </span>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            )
          })}
        </div>
      )}

      <Dialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Delete Profile</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">
            Are you sure you want to delete <span className="font-medium text-foreground">{deleteTarget?.brand_name}</span>? This cannot be undone.
          </p>
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="outline" onClick={() => setDeleteTarget(null)} disabled={deleting}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleting}>{deleting ? "Deleting..." : "Delete"}</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/app/admin/brands/page.tsx
git commit -m "feat(frontend): replace brands table with monitoring card grid"
```

---

### Task 4: Create match drawer component

**Files:**
- Create: `frontend/components/monitoring/match-drawer.tsx`

A shadcn Sheet (side panel) displaying a `MatchSnapshot`. Has:
- Header: domain name + TLD, derived_bucket badge, derived_risk badge
- Score row: derived_score, score_final
- Active signals list (severity + code + description)
- LLM assessment card (risco_score, categoria, parecer_resumido, principais_motivos, recomendacao_acao)
- Event timeline (loads `GET /v1/matches/{id}/events` on mount)
- Status update form (Select + Notes + Save button)

**Note:** shadcn Sheet is not yet in the UI components list. Check if it exists at `frontend/components/ui/sheet.tsx`. If not, add it by running `npx shadcn@latest add sheet` inside the frontend container, or manually create the file using the shadcn sheet primitive pattern. The safest approach without running containers is to use Dialog instead of Sheet — implement as a wide Dialog (`max-w-2xl` side panel feel) using the existing Dialog component.

- [ ] **Step 1: Create directory and component**

Create `frontend/components/monitoring/match-drawer.tsx`:

```tsx
"use client"

import { useEffect, useState } from "react"
import { monitoringApi } from "@/lib/api"
import type { MatchSnapshot, MonitoringEvent } from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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

function bucketVariant(bucket: string | null) {
  switch (bucket) {
    case "immediate_attention": return "destructive" as const
    case "defensive_gap": return "secondary" as const
    default: return "outline" as const
  }
}

function bucketLabel(bucket: string | null) {
  switch (bucket) {
    case "immediate_attention": return "Immediate Attention"
    case "defensive_gap": return "Defensive Gap"
    case "watchlist": return "Watchlist"
    default: return "Unclassified"
  }
}

function riskVariant(risk: string | null) {
  switch (risk) {
    case "critical": case "high": return "destructive" as const
    case "medium": return "secondary" as const
    default: return "outline" as const
  }
}

function severityVariant(severity: string) {
  switch (severity) {
    case "critical": case "high": return "destructive" as const
    case "medium": return "secondary" as const
    default: return "outline" as const
  }
}

interface Props {
  match: MatchSnapshot | null
  onClose: () => void
  onStatusUpdated: () => void
}

export function MatchDrawer({ match, onClose, onStatusUpdated }: Props) {
  const [events, setEvents] = useState<MonitoringEvent[]>([])
  const [eventsLoading, setEventsLoading] = useState(false)
  const [editStatus, setEditStatus] = useState("new")
  const [editNotes, setEditNotes] = useState("")
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!match) return
    setEditStatus("new")
    setEditNotes("")
    setEventsLoading(true)
    monitoringApi.getMatchEvents(match.id)
      .then((data) => setEvents(data.items))
      .catch(() => setEvents([]))
      .finally(() => setEventsLoading(false))
  }, [match?.id])

  async function handleSave() {
    if (!match) return
    setSaving(true)
    try {
      await monitoringApi.updateMatchStatus(match.id, editStatus, editNotes || undefined)
      onStatusUpdated()
      onClose()
    } catch {
      // ignore
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={!!match} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        {match && (
          <>
            <DialogHeader>
              <DialogTitle className="font-mono text-base">
                {match.domain_name}.{match.tld}
              </DialogTitle>
              <div className="flex flex-wrap gap-2 pt-1">
                <Badge variant={bucketVariant(match.derived_bucket)}>{bucketLabel(match.derived_bucket)}</Badge>
                {match.derived_risk && <Badge variant={riskVariant(match.derived_risk)}>{match.derived_risk}</Badge>}
                {match.auto_disposition && (
                  <Badge variant="outline" className="text-[11px]">auto: {match.auto_disposition}</Badge>
                )}
              </div>
            </DialogHeader>

            <div className="space-y-5">
              {/* Scores */}
              <div className="grid grid-cols-2 gap-3 rounded-lg border bg-muted/30 p-3 text-sm">
                <div>
                  <p className="text-xs text-muted-foreground">Derived Score</p>
                  <p className="font-semibold text-lg">
                    {match.derived_score != null ? `${(match.derived_score * 100).toFixed(0)}%` : "—"}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Similarity Score</p>
                  <p className="font-semibold text-lg">{(match.score_final * 100).toFixed(0)}%</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">First Detected</p>
                  <p className="text-xs">{new Date(match.first_detected_at).toLocaleDateString()}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Domain Registered</p>
                  <p className="text-xs">{new Date(match.domain_first_seen).toLocaleDateString()}</p>
                </div>
              </div>

              {/* Active Signals */}
              {match.active_signals.length > 0 && (
                <div>
                  <p className="text-sm font-medium mb-2">Active Signals</p>
                  <div className="space-y-2">
                    {match.active_signals.map((signal) => (
                      <div key={signal.code} className="rounded-md border bg-background p-2.5">
                        <div className="flex items-center gap-2">
                          <Badge variant={severityVariant(signal.severity)} className="text-[10px]">
                            {signal.severity}
                          </Badge>
                          <span className="text-xs font-mono font-medium">{signal.code}</span>
                          <span className="text-xs text-muted-foreground ml-auto">{signal.label}</span>
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">{signal.description}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* LLM Assessment */}
              {match.llm_assessment && (
                <div className="rounded-lg border bg-muted/20 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium">LLM Assessment</p>
                    <div className="flex items-center gap-2">
                      <Badge variant={match.llm_assessment.risco_score >= 70 ? "destructive" : match.llm_assessment.risco_score >= 40 ? "secondary" : "outline"}>
                        Risk {match.llm_assessment.risco_score}/100
                      </Badge>
                      <Badge variant="outline" className="text-[11px]">{match.llm_assessment.categoria}</Badge>
                    </div>
                  </div>
                  <p className="text-sm">{match.llm_assessment.parecer_resumido}</p>
                  {match.llm_assessment.principais_motivos.length > 0 && (
                    <ul className="space-y-1">
                      {match.llm_assessment.principais_motivos.map((m, i) => (
                        <li key={i} className="text-xs text-muted-foreground flex gap-2">
                          <span className="text-foreground">·</span>{m}
                        </li>
                      ))}
                    </ul>
                  )}
                  <div className="rounded-md bg-background p-2 text-xs">
                    <span className="text-muted-foreground">Recommendation: </span>
                    {match.llm_assessment.recomendacao_acao}
                  </div>
                </div>
              )}

              {/* Event Timeline */}
              <div>
                <p className="text-sm font-medium mb-2">Event Timeline</p>
                {eventsLoading ? (
                  <Skeleton className="h-20" />
                ) : events.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No events recorded yet.</p>
                ) : (
                  <div className="space-y-2 max-h-48 overflow-y-auto">
                    {events.map((ev) => (
                      <div key={ev.id} className="flex gap-3 text-xs">
                        <span className="text-muted-foreground shrink-0 tabular-nums">
                          {new Date(ev.created_at).toLocaleDateString()}
                        </span>
                        <div>
                          <Badge variant={severityVariant(ev.severity)} className="text-[10px] mr-1">{ev.severity}</Badge>
                          <span className="font-medium">{ev.event_type}</span>
                          {ev.summary && <span className="text-muted-foreground ml-1">— {ev.summary}</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Status Update */}
              <div className="border-t pt-4 space-y-3">
                <p className="text-sm font-medium">Review</p>
                <div className="space-y-2">
                  <Label className="text-xs">Status</Label>
                  <Select value={editStatus} onValueChange={setEditStatus}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="new">new</SelectItem>
                      <SelectItem value="reviewing">reviewing</SelectItem>
                      <SelectItem value="dismissed">dismissed</SelectItem>
                      <SelectItem value="confirmed_threat">confirmed_threat</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">Notes</Label>
                  <Input value={editNotes} onChange={(e) => setEditNotes(e.target.value)} placeholder="Optional review notes..." />
                </div>
                <Button onClick={handleSave} disabled={saving} className="w-full">
                  {saving ? "Saving..." : "Update Status"}
                </Button>
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/components/monitoring/match-drawer.tsx
git commit -m "feat(frontend): add MatchDrawer component with signals, LLM assessment, and events"
```

---

### Task 5: Create brand detail page

**Files:**
- Create: `frontend/app/admin/brands/[id]/page.tsx`

Stacked sections:
1. **Header** — brand name, health badge, threat counts, "Trigger Scan" button, back link
2. **Today's Cycle** — latest cycle status badge, domains_checked, threats_found, finished_at
3. **Domain Health** (always visible) — table of domain checks
4. **Threats** — bucket filter tabs, paginated list, opens `MatchDrawer` on row click
5. **Config** (collapsed by default, uses shadcn Collapsible) — keywords, TLD scope, aliases, notes
6. **Cycle History** (collapsed by default) — recent cycles table

- [ ] **Step 1: Create the page**

Create `frontend/app/admin/brands/[id]/page.tsx`:

```tsx
"use client"

import { useCallback, useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { api, monitoringApi } from "@/lib/api"
import type {
  Brand,
  BrandHealthResponse,
  CycleListResponse,
  MatchSnapshot,
  MatchSnapshotListResponse,
  ScanSummaryResponse,
} from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { MatchDrawer } from "@/components/monitoring/match-drawer"
import { ArrowLeft, Search, CheckCircle, XCircle, AlertCircle, Minus, ChevronDown, ChevronUp } from "lucide-react"

const BUCKETS = [
  { value: "", label: "All" },
  { value: "immediate_attention", label: "Immediate" },
  { value: "defensive_gap", label: "Defensive Gap" },
  { value: "watchlist", label: "Watchlist" },
]

function healthVariant(health: string | undefined) {
  switch (health) {
    case "critical": return "destructive" as const
    case "warning": return "secondary" as const
    case "healthy": return "outline" as const
    default: return "outline" as const
  }
}

function CheckIcon({ ok }: { ok: boolean | undefined }) {
  if (ok === undefined) return <Minus className="h-3 w-3 text-muted-foreground" />
  if (ok) return <CheckCircle className="h-3 w-3 text-green-500" />
  return <XCircle className="h-3 w-3 text-destructive" />
}

function bucketVariant(bucket: string | null) {
  switch (bucket) {
    case "immediate_attention": return "destructive" as const
    case "defensive_gap": return "secondary" as const
    default: return "outline" as const
  }
}

function bucketLabel(bucket: string | null) {
  switch (bucket) {
    case "immediate_attention": return "Immediate"
    case "defensive_gap": return "Defensive Gap"
    case "watchlist": return "Watchlist"
    default: return bucket ?? "—"
  }
}

function CollapsibleSection({ title, defaultOpen = false, children }: {
  title: string
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <Card>
      <CardHeader
        className="cursor-pointer select-none py-3"
        onClick={() => setOpen((v) => !v)}
      >
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">{title}</CardTitle>
          {open ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
        </div>
      </CardHeader>
      {open && <CardContent>{children}</CardContent>}
    </Card>
  )
}

export default function BrandDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()

  const [brand, setBrand] = useState<Brand | null>(null)
  const [health, setHealth] = useState<BrandHealthResponse | null>(null)
  const [cycles, setCycles] = useState<CycleListResponse | null>(null)
  const [snapshots, setSnapshots] = useState<MatchSnapshotListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [snapshotsLoading, setSnapshotsLoading] = useState(false)

  const [selectedBucket, setSelectedBucket] = useState("")
  const [offset, setOffset] = useState(0)
  const limit = 50

  const [selectedMatch, setSelectedMatch] = useState<MatchSnapshot | null>(null)
  const [scanning, setScanning] = useState(false)

  const fetchBrand = useCallback(async () => {
    const [b, h, c] = await Promise.all([
      api.get<Brand>(`/v1/brands/${id}`),
      monitoringApi.getBrandHealth(id),
      monitoringApi.getCycles(id, 30, 0),
    ])
    setBrand(b)
    setHealth(h)
    setCycles(c)
  }, [id])

  const fetchSnapshots = useCallback(async () => {
    setSnapshotsLoading(true)
    try {
      const data = await monitoringApi.getMatchSnapshots(id, {
        bucket: selectedBucket || undefined,
        limit,
        offset,
      })
      setSnapshots(data)
    } catch {
      // ignore
    } finally {
      setSnapshotsLoading(false)
    }
  }, [id, selectedBucket, offset])

  useEffect(() => {
    fetchBrand().finally(() => setLoading(false))
  }, [fetchBrand])

  useEffect(() => {
    fetchSnapshots()
  }, [fetchSnapshots])

  // Reset offset when bucket changes
  useEffect(() => { setOffset(0) }, [selectedBucket])

  async function handleScan() {
    setScanning(true)
    try {
      await api.post<ScanSummaryResponse>(`/v1/brands/${id}/scan`)
    } catch {
      // ignore
    } finally {
      setScanning(false)
    }
  }

  if (loading || !brand) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32 rounded-xl" />
        <Skeleton className="h-64 rounded-xl" />
      </div>
    )
  }

  const summary = brand.monitoring_summary
  const threats = summary?.threat_counts
  const latestCycle = summary?.latest_cycle

  return (
    <div className="space-y-4">
      {/* Back */}
      <Button variant="ghost" size="sm" onClick={() => router.push("/admin/brands")} className="-ml-2">
        <ArrowLeft className="h-4 w-4 mr-1" />
        Monitoring Profiles
      </Button>

      {/* Header card */}
      <Card>
        <CardContent className="pt-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-xl font-semibold">{brand.brand_name}</h1>
                <Badge variant={healthVariant(summary?.overall_health)}>
                  {summary?.overall_health ?? "unknown"}
                </Badge>
                {!brand.is_active && <Badge variant="outline">inactive</Badge>}
              </div>
              <p className="font-mono text-xs text-muted-foreground mt-0.5">{brand.brand_label}</p>
            </div>
            <Button size="sm" variant="outline" onClick={handleScan} disabled={scanning}>
              <Search className="h-3 w-3 mr-1" />
              {scanning ? "Queuing..." : "Trigger Scan"}
            </Button>
          </div>

          {/* Threat counters */}
          <div className="grid grid-cols-3 gap-3 mt-4 max-w-sm">
            <div className="rounded-lg bg-destructive/10 p-3 text-center">
              <p className="text-2xl font-bold text-destructive leading-none">{threats?.immediate_attention ?? 0}</p>
              <p className="text-xs text-muted-foreground mt-1">Immediate</p>
            </div>
            <div className="rounded-lg bg-secondary/50 p-3 text-center">
              <p className="text-2xl font-bold leading-none">{threats?.defensive_gap ?? 0}</p>
              <p className="text-xs text-muted-foreground mt-1">Defensive</p>
            </div>
            <div className="rounded-lg bg-muted p-3 text-center">
              <p className="text-2xl font-bold leading-none">{threats?.watchlist ?? 0}</p>
              <p className="text-xs text-muted-foreground mt-1">Watchlist</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Latest cycle */}
      {latestCycle && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Latest Monitoring Cycle</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-4 text-sm">
              <div>
                <p className="text-xs text-muted-foreground">Status</p>
                <Badge variant={latestCycle.status === "completed" ? "outline" : "secondary"} className="mt-0.5">
                  {latestCycle.status}
                </Badge>
              </div>
              {latestCycle.finished_at && (
                <div>
                  <p className="text-xs text-muted-foreground">Finished</p>
                  <p className="text-xs mt-0.5">{new Date(latestCycle.finished_at).toLocaleString()}</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Domain Health */}
      {health && health.domains.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Domain Health</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Domain</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-center">DNS</TableHead>
                  <TableHead className="text-center">SSL</TableHead>
                  <TableHead className="text-center">Email</TableHead>
                  <TableHead className="text-center">Headers</TableHead>
                  <TableHead className="text-center">Blacklist</TableHead>
                  <TableHead>Last Check</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {health.domains.map((d) => (
                  <TableRow key={d.domain_id}>
                    <TableCell className="font-mono text-xs">
                      {d.domain_name}
                      {d.is_primary && <Badge variant="outline" className="ml-1 text-[10px]">primary</Badge>}
                    </TableCell>
                    <TableCell>
                      <Badge variant={d.overall_status === "healthy" ? "outline" : d.overall_status === "critical" ? "destructive" : "secondary"} className="text-[11px]">
                        {d.overall_status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-center"><CheckIcon ok={d.dns?.ok} /></TableCell>
                    <TableCell className="text-center"><CheckIcon ok={d.ssl?.ok} /></TableCell>
                    <TableCell className="text-center"><CheckIcon ok={d.email_security?.ok} /></TableCell>
                    <TableCell className="text-center"><CheckIcon ok={d.headers?.ok} /></TableCell>
                    <TableCell className="text-center"><CheckIcon ok={d.blacklist?.ok} /></TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {d.last_check_at ? new Date(d.last_check_at).toLocaleDateString() : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Threats / Match Snapshots */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <CardTitle className="text-sm font-medium">Threats</CardTitle>
            <div className="flex gap-1">
              {BUCKETS.map((b) => (
                <Button
                  key={b.value}
                  variant={selectedBucket === b.value ? "default" : "outline"}
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => setSelectedBucket(b.value)}
                >
                  {b.label}
                </Button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {snapshotsLoading ? (
            <div className="p-6"><Skeleton className="h-40" /></div>
          ) : !snapshots || snapshots.items.length === 0 ? (
            <p className="p-6 text-center text-sm text-muted-foreground">
              No threats found{selectedBucket ? ` in "${bucketLabel(selectedBucket)}"` : ""}.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Domain</TableHead>
                  <TableHead>Bucket</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>Risk</TableHead>
                  <TableHead>Signals</TableHead>
                  <TableHead>Detected</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {snapshots.items.map((snap) => (
                  <TableRow
                    key={snap.id}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => setSelectedMatch(snap)}
                  >
                    <TableCell className="font-mono text-sm">
                      {snap.domain_name}.{snap.tld}
                    </TableCell>
                    <TableCell>
                      <Badge variant={bucketVariant(snap.derived_bucket)} className="text-[11px]">
                        {bucketLabel(snap.derived_bucket)}
                      </Badge>
                    </TableCell>
                    <TableCell className="tabular-nums text-sm">
                      {snap.derived_score != null ? `${(snap.derived_score * 100).toFixed(0)}%` : "—"}
                    </TableCell>
                    <TableCell>
                      {snap.derived_risk && (
                        <Badge variant={snap.derived_risk === "critical" || snap.derived_risk === "high" ? "destructive" : "secondary"} className="text-[11px]">
                          {snap.derived_risk}
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {snap.signal_codes.slice(0, 3).map((code) => (
                          <Badge key={code} variant="outline" className="text-[10px] font-mono">{code}</Badge>
                        ))}
                        {snap.signal_codes.length > 3 && (
                          <Badge variant="outline" className="text-[10px]">+{snap.signal_codes.length - 3}</Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {new Date(snap.first_detected_at).toLocaleDateString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {/* Pagination */}
          {snapshots && snapshots.total > limit && (
            <div className="flex items-center justify-between border-t px-4 py-3">
              <p className="text-xs text-muted-foreground">
                {offset + 1}–{Math.min(offset + limit, snapshots.total)} of {snapshots.total}
              </p>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>Previous</Button>
                <Button variant="outline" size="sm" disabled={offset + limit >= snapshots.total} onClick={() => setOffset(offset + limit)}>Next</Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Config (collapsible) */}
      <CollapsibleSection title="Brand Configuration">
        <div className="space-y-3 text-sm">
          <div>
            <p className="text-xs text-muted-foreground mb-1">Official Domains</p>
            <div className="flex flex-wrap gap-1">
              {brand.official_domains.map((d) => (
                <Badge key={d.id} variant={d.is_primary ? "default" : "outline"} className="font-mono text-[11px]">{d.domain_name}</Badge>
              ))}
            </div>
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-1">Keywords</p>
            <div className="flex flex-wrap gap-1">
              {brand.keywords.length === 0 ? <span className="text-muted-foreground text-xs">None</span> : brand.keywords.map((k) => <Badge key={k} variant="outline" className="text-[11px]">{k}</Badge>)}
            </div>
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-1">Aliases</p>
            <div className="flex flex-wrap gap-1">
              {brand.aliases.filter(a => a.alias_type !== "support_keyword").map((a) => (
                <Badge key={a.id} variant="secondary" className="text-[11px]">{a.alias_value}</Badge>
              ))}
            </div>
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-1">TLD Scope ({brand.tld_scope.length} TLDs)</p>
            <div className="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
              {brand.tld_scope.map((tld) => <Badge key={tld} variant="outline" className="font-mono text-[11px]">.{tld}</Badge>)}
            </div>
          </div>
          {brand.notes && (
            <div>
              <p className="text-xs text-muted-foreground mb-1">Notes</p>
              <p className="text-xs">{brand.notes}</p>
            </div>
          )}
        </div>
      </CollapsibleSection>

      {/* Cycle History (collapsible) */}
      {cycles && cycles.items.length > 0 && (
        <CollapsibleSection title={`Cycle History (${cycles.total})`}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Domains Checked</TableHead>
                <TableHead>Threats Found</TableHead>
                <TableHead>Finished</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {cycles.items.map((c) => (
                <TableRow key={c.id}>
                  <TableCell className="text-xs">{c.cycle_date}</TableCell>
                  <TableCell>
                    <Badge variant={c.status === "completed" ? "outline" : "secondary"} className="text-[11px]">{c.status}</Badge>
                  </TableCell>
                  <TableCell className="text-sm">{c.domains_checked ?? "—"}</TableCell>
                  <TableCell className="text-sm">{c.threats_found ?? "—"}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {c.finished_at ? new Date(c.finished_at).toLocaleString() : "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CollapsibleSection>
      )}

      {/* Match Drawer */}
      <MatchDrawer
        match={selectedMatch}
        onClose={() => setSelectedMatch(null)}
        onStatusUpdated={fetchSnapshots}
      />
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/app/admin/brands/[id]/page.tsx frontend/components/monitoring/
git commit -m "feat(frontend): add brand detail page with stacked sections and match drawer"
```

---

### Task 6: Remove matches page and update nav

**Files:**
- Delete: `frontend/app/admin/matches/page.tsx`
- Modify: `frontend/app/admin/layout.tsx`

- [ ] **Step 1: Remove the matches page file**

Delete `frontend/app/admin/matches/page.tsx` — its functionality now lives in the brand detail page.

- [ ] **Step 2: Remove "Similarity Matches" from nav**

In `frontend/app/admin/layout.tsx`, remove from the `navItems` array:

```typescript
  { href: "/admin/matches", label: "Similarity Matches", icon: Search },
```

Also remove the `Search` import from lucide if it's no longer used.

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add frontend/app/admin/layout.tsx
git rm frontend/app/admin/matches/page.tsx
git commit -m "feat(frontend): remove matches page, move functionality to brand detail"
```

---

## Done Criteria

- `/admin/brands` renders a responsive card grid with health badges and threat counters
- Clicking a brand card navigates to `/admin/brands/{id}`
- Brand detail page shows: header, latest cycle status, domain health table, threats list with bucket filter, config section, cycle history
- Clicking a match row opens the `MatchDrawer` with signals, LLM assessment, event timeline, and status update
- `/admin/matches` route is gone; nav no longer shows "Similarity Matches"
- `npx tsc --noEmit` passes with no new errors
