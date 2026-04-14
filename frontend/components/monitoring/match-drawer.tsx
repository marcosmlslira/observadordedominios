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
    case "immediate_attention": return "Imediato"
    case "defensive_gap": return "Gap Defensivo"
    case "watchlist": return "Watchlist"
    default: return "Não classificado"
  }
}

function riskLabel(risk: string | null) {
  switch (risk) {
    case "critical": return "Crítico"
    case "high": return "Alto"
    case "medium": return "Médio"
    case "low": return "Baixo"
    default: return risk ?? "—"
  }
}

function riskVariant(risk: string | null) {
  switch (risk) {
    case "critical":
    case "high": return "destructive" as const
    case "medium": return "secondary" as const
    default: return "outline" as const
  }
}

function severityVariant(severity: string) {
  switch (severity) {
    case "critical":
    case "high": return "destructive" as const
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
  const [markingOwned, setMarkingOwned] = useState(false)

  useEffect(() => {
    if (!match) return
    setEditStatus("new")
    setEditNotes("")
    setEventsLoading(true)
    monitoringApi
      .getMatchEvents(match.id)
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

  async function handleMarkOwned() {
    if (!match) return
    setMarkingOwned(true)
    try {
      await monitoringApi.markOwned(match.id, true)
      onStatusUpdated()
      onClose()
    } catch {
      // ignore
    } finally {
      setMarkingOwned(false)
    }
  }

  return (
    <Dialog open={!!match} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        {match && (
          <>
            <DialogHeader>
              <DialogTitle className="font-mono text-base">
                {match.domain_name}
              </DialogTitle>
              <div className="flex flex-wrap gap-2 pt-1">
                <Badge variant={bucketVariant(match.derived_bucket)}>
                  {bucketLabel(match.derived_bucket)}
                </Badge>
                {match.derived_risk && (
                  <Badge variant={riskVariant(match.derived_risk)}>
                    {riskLabel(match.derived_risk)}
                  </Badge>
                )}
                {match.auto_disposition && (
                  <Badge variant="outline" className="text-[11px]">
                    auto: {match.auto_disposition}
                  </Badge>
                )}
              </div>
            </DialogHeader>

            <div className="space-y-5">
              {/* Self-owned domain banner */}
              {match.auto_disposition === "self_owned" && (
                <div className="flex items-start gap-2 rounded-lg border border-green-200 bg-green-50 px-3 py-2.5 text-sm text-green-800">
                  <span className="mt-0.5 shrink-0">🏢</span>
                  <div>
                    <p className="font-medium">Domínio da empresa</p>
                    {match.auto_disposition_reason && (
                      <p className="text-xs text-green-700 mt-0.5">{match.auto_disposition_reason}</p>
                    )}
                  </div>
                </div>
              )}
              {/* Scores */}
              <div className="grid grid-cols-2 gap-3 rounded-lg border bg-muted/30 p-3 text-sm">
                <div>
                  <p className="text-xs text-muted-foreground">Score Derivado</p>
                  <p className="font-semibold text-lg">
                    {match.derived_score != null
                      ? `${(match.derived_score * 100).toFixed(0)}%`
                      : "—"}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Score de Similaridade</p>
                  <p className="font-semibold text-lg">
                    {(match.score_final * 100).toFixed(0)}%
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Primeira Detecção</p>
                  <p className="text-xs">
                    {new Date(match.first_detected_at).toLocaleDateString("pt-BR")}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Registrado em</p>
                  <p className="text-xs">
                    {new Date(match.domain_first_seen).toLocaleDateString("pt-BR")}
                  </p>
                </div>
              </div>

              {/* Active Signals */}
              {match.active_signals.length > 0 && (
                <div>
                  <p className="text-sm font-medium mb-2">Sinais Ativos</p>
                  <div className="space-y-2">
                    {match.active_signals.map((signal) => (
                      <div
                        key={signal.code}
                        className="rounded-md border bg-background p-2.5"
                      >
                        <div className="flex items-center gap-2">
                          {signal.severity && (
                            <Badge
                              variant={severityVariant(signal.severity)}
                              className="text-[10px]"
                            >
                              {signal.severity}
                            </Badge>
                          )}
                          <span className="text-xs font-mono font-medium">
                            {signal.code}
                          </span>
                          {signal.source_tool && (
                            <span className="text-xs text-muted-foreground ml-auto">
                              {signal.source_tool}
                            </span>
                          )}
                        </div>
                        {signal.description && (
                          <p className="mt-1 text-xs text-muted-foreground">
                            {signal.description}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* LLM Assessment */}
              {match.llm_assessment && (
                <div className="rounded-lg border bg-muted/20 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium">Avaliação IA</p>
                    <div className="flex items-center gap-2">
                      <Badge
                        variant={
                          match.llm_assessment.risco_score >= 70
                            ? "destructive"
                            : match.llm_assessment.risco_score >= 40
                              ? "secondary"
                              : "outline"
                        }
                      >
                        Risco {match.llm_assessment.risco_score}/100
                      </Badge>
                      <Badge variant="outline" className="text-[11px]">
                        {match.llm_assessment.categoria}
                      </Badge>
                    </div>
                  </div>
                  <p className="text-sm">{match.llm_assessment.parecer_resumido}</p>
                  {match.llm_assessment.principais_motivos.length > 0 && (
                    <ul className="space-y-1">
                      {match.llm_assessment.principais_motivos.map((m, i) => (
                        <li key={i} className="text-xs text-muted-foreground flex gap-2">
                          <span className="text-foreground">·</span>
                          {m}
                        </li>
                      ))}
                    </ul>
                  )}
                  <div className="rounded-md bg-background p-2 text-xs">
                    <span className="text-muted-foreground">Recomendação: </span>
                    {match.llm_assessment.recomendacao_acao}
                  </div>
                </div>
              )}

              {/* Event Timeline */}
              <div>
                <p className="text-sm font-medium mb-2">Linha do Tempo</p>
                {eventsLoading ? (
                  <Skeleton className="h-20" />
                ) : events.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    Nenhum evento registrado ainda.
                  </p>
                ) : (
                  <div className="space-y-2 max-h-48 overflow-y-auto">
                    {events.map((ev) => (
                      <div key={ev.id} className="flex gap-3 text-xs">
                        <span className="text-muted-foreground shrink-0 tabular-nums">
                          {new Date(ev.created_at).toLocaleDateString()}
                        </span>
                        <div>
                          <Badge variant="outline" className="text-[10px] mr-1">
                            {ev.event_source}
                          </Badge>
                          <span className="font-medium">{ev.event_type}</span>
                          {ev.tool_name && (
                            <span className="text-muted-foreground ml-1">
                              — {ev.tool_name}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Status Update */}
              <div className="border-t pt-4 space-y-3">
                <p className="text-sm font-medium">Revisão</p>
                <div className="space-y-2">
                  <Label className="text-xs">Status</Label>
                  <Select value={editStatus} onValueChange={setEditStatus}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="new">Novo</SelectItem>
                      <SelectItem value="reviewing">Em revisão</SelectItem>
                      <SelectItem value="dismissed">Descartado</SelectItem>
                      <SelectItem value="confirmed_threat">Ameaça confirmada</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">Observações</Label>
                  <Input
                    value={editNotes}
                    onChange={(e) => setEditNotes(e.target.value)}
                    placeholder="Observações de revisão (opcional)..."
                  />
                </div>
                <Button onClick={handleSave} disabled={saving} className="w-full">
                  {saving ? "Salvando..." : "Atualizar Status"}
                </Button>
                {match.auto_disposition !== "self_owned" && (
                  <Button
                    variant="outline"
                    onClick={handleMarkOwned}
                    disabled={markingOwned}
                    className="w-full border-green-400 text-green-700 hover:bg-green-50"
                  >
                    {markingOwned ? "Marcando..." : "✓ Este domínio é meu"}
                  </Button>
                )}
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
