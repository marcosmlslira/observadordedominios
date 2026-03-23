"use client"

import { useCallback, useEffect, useState } from "react"
import { api } from "@/lib/api"
import type {
  Brand,
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

export default function BrandsPage() {
  const [brands, setBrands] = useState<Brand[]>([])
  const [loading, setLoading] = useState(true)

  // Create dialog
  const [createOpen, setCreateOpen] = useState(false)
  const [newName, setNewName] = useState("")
  const [newKeywords, setNewKeywords] = useState("")
  const [newTlds, setNewTlds] = useState(DEFAULT_TLD_SCOPE)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState("")

  // Delete dialog
  const [deleteTarget, setDeleteTarget] = useState<Brand | null>(null)
  const [deleting, setDeleting] = useState(false)

  const fetchBrands = useCallback(async () => {
    try {
      const data = await api.get<BrandListResponse>(
        "/v1/brands?active_only=false",
      )
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
        keywords: newKeywords
          .split(",")
          .map((k) => k.trim())
          .filter(Boolean),
        tld_scope: newTlds
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
      }
      await api.post("/v1/brands", body)
      setCreateOpen(false)
      setNewName("")
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
        <h1 className="text-2xl font-semibold">Monitored Brands</h1>
        <Skeleton className="h-96 rounded-xl" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Monitored Brands</h1>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchBrands}>
            <RefreshCw className="h-3 w-3 mr-1" />
            Refresh
          </Button>
          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger asChild>
              <Button size="sm">
                <Plus className="h-3 w-3 mr-1" />
                New Brand
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Create Monitored Brand</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 pt-2">
                <div className="space-y-2">
                  <Label htmlFor="brand-name">Brand Name</Label>
                  <Input
                    id="brand-name"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="e.g. My Company"
                    autoFocus
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="keywords">Keywords (comma-separated)</Label>
                  <Input
                    id="keywords"
                    value={newKeywords}
                    onChange={(e) => setNewKeywords(e.target.value)}
                    placeholder="e.g. mycompany, myco, my-company"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="tlds">TLD Scope (comma-separated)</Label>
                  <Input
                    id="tlds"
                    value={newTlds}
                    onChange={(e) => setNewTlds(e.target.value)}
                    placeholder={DEFAULT_TLD_SCOPE}
                  />
                </div>
                {createError && (
                  <p className="text-sm text-error">{createError}</p>
                )}
                <Button
                  onClick={handleCreate}
                  disabled={creating || !newName.trim()}
                  className="w-full"
                >
                  {creating ? "Creating..." : "Create Brand"}
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
                <TableHead>Name</TableHead>
                <TableHead>Label</TableHead>
                <TableHead>Keywords</TableHead>
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
                    colSpan={7}
                    className="text-center text-muted-foreground py-8"
                  >
                    No brands found. Create your first brand to start
                    monitoring.
                  </TableCell>
                </TableRow>
              ) : (
                brands.map((brand) => (
                  <TableRow key={brand.id}>
                    <TableCell className="font-medium">
                      {brand.brand_name}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {brand.brand_label}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {brand.keywords.map((kw) => (
                          <Badge key={kw} variant="secondary" className="text-xs">
                            {kw}
                          </Badge>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {brand.tld_scope.map((tld) => (
                          <Badge key={tld} variant="outline" className="text-xs font-mono">
                            .{tld}
                          </Badge>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Switch
                        checked={brand.is_active}
                        onCheckedChange={() => handleToggleActive(brand)}
                      />
                    </TableCell>
                    <TableCell className="text-xs">
                      {new Date(brand.created_at).toLocaleDateString()}
                    </TableCell>
                    <TableCell className="text-right">
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

      {/* Delete confirmation dialog */}
      <Dialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Brand</DialogTitle>
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
