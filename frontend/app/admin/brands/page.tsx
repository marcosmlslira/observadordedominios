"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { api } from "@/lib/api"
import type {
  Brand,
  BrandAliasRequest,
  BrandListResponse,
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
import { Plus, Search, Trash2, RefreshCw, ArrowRight } from "lucide-react"

const DEFAULT_TLD_SCOPE =
  "com,net,org,com.br,net.br,org.br,xyz,online,site,store,top,info,tech,space,website,fun," +
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
  const router = useRouter()
  const [brands, setBrands] = useState<Brand[]>([])
  const [loading, setLoading] = useState(true)

  const [createOpen, setCreateOpen] = useState(false)
  const [newName, setNewName] = useState("")
  const [newPrimaryBrand, setNewPrimaryBrand] = useState("")
  const [newOfficialDomains, setNewOfficialDomains] = useState("")
  const [newAliases, setNewAliases] = useState("")
  const [newPhrases, setNewPhrases] = useState("")
  const [newKeywords, setNewKeywords] = useState("")
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
      const created = await api.post<Brand>("/v1/brands", {
        brand_name: newName.trim(),
        primary_brand_name: newPrimaryBrand.trim() || undefined,
        official_domains: splitCsv(newOfficialDomains),
        aliases: buildAliasRequests(newAliases, newPhrases),
        keywords: splitCsv(newKeywords),
        tld_scope: splitCsv(DEFAULT_TLD_SCOPE),
      })
      setCreateOpen(false)
      setNewName("")
      setNewPrimaryBrand("")
      setNewOfficialDomains("")
      setNewAliases("")
      setNewPhrases("")
      setNewKeywords("")
      // Trigger first scan (best-effort) then navigate to brand detail
      try {
        await api.post(`/v1/brands/${created.id}/scan`)
      } catch {
        // scan trigger failure is non-blocking
      }
      router.push(`/admin/brands/${created.id}`)
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Falha ao criar perfil")
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
      await api.post(`/v1/brands/${brandId}/scan`)
    } catch {
      // ignore
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold">Perfis de Monitoramento</h1>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-48 rounded-xl" />)}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Perfis de Monitoramento</h1>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchBrands}>
            <RefreshCw className="mr-1 h-3 w-3" />
            Atualizar
          </Button>
          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger asChild>
              <Button size="sm">
                <Plus className="mr-1 h-3 w-3" />
                Novo Perfil
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>Criar Perfil de Monitoramento</DialogTitle>
              </DialogHeader>
              <div className="grid gap-4 pt-2 md:grid-cols-2">
                <div className="space-y-1">
                  <Label htmlFor="brand-name">Nome do Perfil</Label>
                  <Input
                    id="brand-name"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="ex: PicPay"
                    autoFocus
                  />
                  <p className="text-xs text-muted-foreground">Identificador interno deste perfil de monitoramento.</p>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="primary-brand-name">Nome da Marca</Label>
                  <Input
                    id="primary-brand-name"
                    value={newPrimaryBrand}
                    onChange={(e) => setNewPrimaryBrand(e.target.value)}
                    placeholder="ex: PicPay"
                  />
                  <p className="text-xs text-muted-foreground">Nome que aparece nos domínios. Usado na varredura de similaridade.</p>
                </div>
                <div className="space-y-1 md:col-span-2">
                  <Label htmlFor="official-domains">Domínios Oficiais</Label>
                  <Input
                    id="official-domains"
                    value={newOfficialDomains}
                    onChange={(e) => setNewOfficialDomains(e.target.value)}
                    placeholder="ex: picpay.com, picpay.com.br"
                  />
                  <p className="text-xs text-muted-foreground">Seus domínios legítimos, separados por vírgula. Serão excluídos dos alertas de ameaça.</p>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="brand-aliases">Variações do Nome</Label>
                  <Input
                    id="brand-aliases"
                    value={newAliases}
                    onChange={(e) => setNewAliases(e.target.value)}
                    placeholder="ex: pic-pay, picpay app"
                  />
                  <p className="text-xs text-muted-foreground">Abreviações e grafias alternativas da marca.</p>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="brand-phrases">Frases Associadas</Label>
                  <Input
                    id="brand-phrases"
                    value={newPhrases}
                    onChange={(e) => setNewPhrases(e.target.value)}
                    placeholder="ex: picpay carteira digital"
                  />
                  <p className="text-xs text-muted-foreground">Frases completas que identificam a marca.</p>
                </div>
                <div className="space-y-1 md:col-span-2">
                  <Label htmlFor="keywords">Palavras-chave de Apoio</Label>
                  <Input
                    id="keywords"
                    value={newKeywords}
                    onChange={(e) => setNewKeywords(e.target.value)}
                    placeholder="ex: pagamento, carteira, pix"
                  />
                  <p className="text-xs text-muted-foreground">Termos relacionados ao negócio para detectar domínios temáticos suspeitos.</p>
                </div>

                {createError && (
                  <p className="text-sm text-destructive md:col-span-2">{createError}</p>
                )}
                <Button
                  onClick={handleCreate}
                  disabled={creating || !newName.trim() || !newOfficialDomains.trim()}
                  className="w-full md:col-span-2"
                >
                  {creating ? "Criando e iniciando varredura..." : "Criar e Iniciar Varredura"}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {brands.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            Nenhum perfil de monitoramento ainda. Crie o primeiro para iniciar as varreduras.
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
                        {!brand.is_active && (
                          <Badge variant="outline" className="text-[10px]">inactive</Badge>
                        )}
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
                        <p className="text-lg font-bold text-destructive leading-none">
                          {threats?.immediate_attention ?? 0}
                        </p>
                        <p className="text-[10px] text-muted-foreground mt-0.5">Imediato</p>
                      </div>
                      <div className="rounded-md bg-secondary/50 px-2 py-1.5">
                        <p className="text-lg font-bold leading-none">
                          {threats?.defensive_gap ?? 0}
                        </p>
                        <p className="text-[10px] text-muted-foreground mt-0.5">Defensivo</p>
                      </div>
                      <div className="rounded-md bg-muted px-2 py-1.5">
                        <p className="text-lg font-bold leading-none">
                          {threats?.watchlist ?? 0}
                        </p>
                        <p className="text-[10px] text-muted-foreground mt-0.5">Watchlist</p>
                      </div>
                    </div>

                    {/* Official domains */}
                    <div className="flex flex-wrap gap-1">
                      {brand.official_domains.slice(0, 3).map((d) => (
                        <Badge
                          key={d.id}
                          variant={d.is_primary ? "default" : "outline"}
                          className="text-[11px] font-mono"
                        >
                          {d.domain_name}
                        </Badge>
                      ))}
                      {brand.official_domains.length > 3 && (
                        <Badge variant="outline" className="text-[11px]">
                          +{brand.official_domains.length - 3}
                        </Badge>
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
                          Varrer
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-[11px] text-destructive"
                          onClick={(e) => {
                            e.preventDefault()
                            setDeleteTarget(brand)
                          }}
                          title="Delete"
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                      <span className="text-xs text-muted-foreground group-hover:text-foreground flex items-center gap-1 transition-colors">
                        Ver <ArrowRight className="h-3 w-3" />
                      </span>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            )
          })}
        </div>
      )}

      <Dialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Excluir Perfil</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Tem certeza que deseja excluir{" "}
            <span className="font-medium text-foreground">
              {deleteTarget?.brand_name}
            </span>
            ? Esta ação não pode ser desfeita.
          </p>
          <div className="flex justify-end gap-2 pt-4">
            <Button
              variant="outline"
              onClick={() => setDeleteTarget(null)}
              disabled={deleting}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleting}
            >
              {deleting ? "Excluindo..." : "Excluir"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
