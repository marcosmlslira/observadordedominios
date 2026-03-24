"use client"

import { useCallback, useEffect, useState } from "react"
import { api } from "@/lib/api"
import type {
  Brand,
  BrandAliasRequest,
  BrandListResponse,
  CreateBrandRequest,
  ScanSummaryResponse,
} from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
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
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Plus, Search, Trash2, RefreshCw } from "lucide-react"

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
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
}

function buildAliasRequests(
  aliases: string,
  phrases: string,
): BrandAliasRequest[] {
  return [
    ...splitCsv(aliases).map((value) => ({ value, type: "brand_alias" as const })),
    ...splitCsv(phrases).map((value) => ({ value, type: "brand_phrase" as const })),
  ]
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
      const body: CreateBrandRequest = {
        brand_name: newName.trim(),
        primary_brand_name: newPrimaryBrand.trim() || undefined,
        official_domains: splitCsv(newOfficialDomains),
        aliases: buildAliasRequests(newAliases, newPhrases),
        keywords: splitCsv(newKeywords),
        tld_scope: splitCsv(newTlds),
      }
      await api.post("/v1/brands", body)
      setCreateOpen(false)
      setNewName("")
      setNewPrimaryBrand("")
      setNewOfficialDomains("")
      setNewAliases("")
      setNewPhrases("")
      setNewKeywords("")
      setNewTlds(DEFAULT_TLD_SCOPE)
      await fetchBrands()
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Create failed")
    } finally {
      setCreating(false)
    }
  }

  async function handleToggleActive(brand: Brand) {
    try {
      await api.patch(`/v1/brands/${brand.id}`, {
        is_active: !brand.is_active,
      })
      await fetchBrands()
    } catch {
      // ignore
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

  async function handleScan(brandId: string) {
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
        <Skeleton className="h-96 rounded-xl" />
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
                  <Input
                    id="brand-name"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="e.g. Growth Suplementos"
                    autoFocus
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="primary-brand-name">Primary Brand Name</Label>
                  <Input
                    id="primary-brand-name"
                    value={newPrimaryBrand}
                    onChange={(e) => setNewPrimaryBrand(e.target.value)}
                    placeholder="e.g. Growth Suplementos"
                  />
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="official-domains">Official Domains</Label>
                  <Input
                    id="official-domains"
                    value={newOfficialDomains}
                    onChange={(e) => setNewOfficialDomains(e.target.value)}
                    placeholder="e.g. gsuplementos.com.br, growth.com"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="brand-aliases">Brand Aliases</Label>
                  <Input
                    id="brand-aliases"
                    value={newAliases}
                    onChange={(e) => setNewAliases(e.target.value)}
                    placeholder="e.g. growth, gsuplementos"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="brand-phrases">Brand Phrases</Label>
                  <Input
                    id="brand-phrases"
                    value={newPhrases}
                    onChange={(e) => setNewPhrases(e.target.value)}
                    placeholder="e.g. growth suplementos"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="keywords">Support Keywords</Label>
                  <Input
                    id="keywords"
                    value={newKeywords}
                    onChange={(e) => setNewKeywords(e.target.value)}
                    placeholder="e.g. suplementos, whey"
                  />
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="tlds">TLD Scope</Label>
                  <Input
                    id="tlds"
                    value={newTlds}
                    onChange={(e) => setNewTlds(e.target.value)}
                    placeholder={DEFAULT_TLD_SCOPE}
                  />
                </div>
                {createError && (
                  <p className="text-sm text-error md:col-span-2">{createError}</p>
                )}
                <Button
                  onClick={handleCreate}
                  disabled={creating || !newName.trim()}
                  className="w-full md:col-span-2"
                >
                  {creating ? "Creating..." : "Create Profile"}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Profile</TableHead>
                <TableHead>Official Domains</TableHead>
                <TableHead>Aliases</TableHead>
                <TableHead>Support Keywords</TableHead>
                <TableHead>Seeds</TableHead>
                <TableHead>TLD Scope</TableHead>
                <TableHead>Active</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {brands.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={9}
                    className="py-8 text-center text-muted-foreground"
                  >
                    No monitoring profiles found. Create the first profile to start
                    scanning.
                  </TableCell>
                </TableRow>
              ) : (
                brands.map((brand) => (
                  <TableRow key={brand.id}>
                    <TableCell className="align-top">
                      <div className="space-y-1">
                        <div className="font-medium">{brand.brand_name}</div>
                        <div className="text-xs text-muted-foreground">
                          Primary: {brand.primary_brand_name}
                        </div>
                        <div className="font-mono text-[11px] text-muted-foreground">
                          {brand.brand_label}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="align-top">
                      <div className="flex max-w-56 flex-wrap gap-1">
                        {brand.official_domains.length === 0 ? (
                          <span className="text-xs text-muted-foreground">None</span>
                        ) : (
                          brand.official_domains.map((domain) => (
                            <Badge
                              key={domain.id}
                              variant={domain.is_primary ? "default" : "outline"}
                              className="text-[11px]"
                            >
                              {domain.domain_name}
                            </Badge>
                          ))
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="align-top">
                      <div className="flex max-w-56 flex-wrap gap-1">
                        {brand.aliases
                          .filter((alias) => alias.alias_type !== "support_keyword")
                          .map((alias) => (
                            <Badge key={alias.id} variant="secondary" className="text-[11px]">
                              {alias.alias_value}
                            </Badge>
                          ))}
                      </div>
                    </TableCell>
                    <TableCell className="align-top">
                      <div className="flex max-w-48 flex-wrap gap-1">
                        {brand.keywords.length === 0 ? (
                          <span className="text-xs text-muted-foreground">None</span>
                        ) : (
                          brand.keywords.map((keyword) => (
                            <Badge key={keyword} variant="outline" className="text-[11px]">
                              {keyword}
                            </Badge>
                          ))
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="align-top">
                      <div className="space-y-1 text-xs">
                        <div>{brand.seeds.length} total</div>
                        <div className="text-muted-foreground">
                          {brand.seeds.filter((seed) => seed.channel_scope === "registrable_domain" || seed.channel_scope === "both").length} scan seeds
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="align-top">
                      <div className="flex max-w-56 flex-wrap gap-1">
                        {brand.tld_scope.map((tld) => (
                          <Badge key={tld} variant="outline" className="font-mono text-[11px]">
                            .{tld}
                          </Badge>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell className="align-top">
                      <Switch
                        checked={brand.is_active}
                        onCheckedChange={() => handleToggleActive(brand)}
                      />
                    </TableCell>
                    <TableCell className="align-top text-xs">
                      {new Date(brand.created_at).toLocaleDateString()}
                    </TableCell>
                    <TableCell className="align-top text-right">
                      <div className="flex justify-end gap-1">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleScan(brand.id)}
                          title="Trigger scan"
                        >
                          <Search className="h-3 w-3" />
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setDeleteTarget(brand)}
                          title="Delete"
                          className="text-error"
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Dialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Profile</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Are you sure you want to delete{" "}
            <span className="font-medium text-foreground">
              {deleteTarget?.brand_name}
            </span>
            ? This action cannot be undone.
          </p>
          <div className="flex justify-end gap-2 pt-4">
            <Button
              variant="outline"
              onClick={() => setDeleteTarget(null)}
              disabled={deleting}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleting}
            >
              {deleting ? "Deleting..." : "Delete"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
