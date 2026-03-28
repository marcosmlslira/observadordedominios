"use client"

import { Badge } from "@/components/ui/badge"

interface LLMAssessment {
  risco_score: number
  categoria: string
  parecer_resumido: string
  principais_motivos: string[]
  recomendacao_acao: string
  confianca: number
}

interface LLMAssessmentCardProps {
  assessment: LLMAssessment
}

function acaoVariant(acao: string): "destructive" | "secondary" | "outline" {
  const lower = acao.toLowerCase()
  if (lower.includes("bloquear")) return "destructive"
  if (lower.includes("monitorar")) return "secondary"
  return "outline"
}

function riscoColor(score: number): string {
  if (score >= 75) return "text-destructive"
  if (score >= 45) return "text-yellow-600 dark:text-yellow-400"
  return "text-green-600 dark:text-green-400"
}

export function LLMAssessmentCard({ assessment }: LLMAssessmentCardProps) {
  const {
    risco_score,
    categoria,
    parecer_resumido,
    principais_motivos,
    recomendacao_acao,
    confianca,
  } = assessment

  return (
    <div className="space-y-3 rounded-lg border border-primary/20 bg-primary/5 p-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className={`text-3xl font-bold tabular-nums ${riscoColor(risco_score)}`}>
            {risco_score}
          </span>
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Parecer LLM
            </p>
            <Badge variant="secondary" className="text-xs">
              {categoria}
            </Badge>
          </div>
        </div>
        <Badge variant={acaoVariant(recomendacao_acao)} className="shrink-0">
          {recomendacao_acao}
        </Badge>
      </div>

      {/* Opinion text */}
      <p className="text-sm leading-relaxed text-foreground/90">{parecer_resumido}</p>

      {/* Key reasons */}
      {principais_motivos.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Principais Motivos
          </p>
          <ul className="space-y-1">
            {principais_motivos.map((motivo, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-muted-foreground">
                <span className="mt-0.5 shrink-0 text-primary">•</span>
                <span>{motivo}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Confidence */}
      <p className="text-[11px] text-muted-foreground">
        Confiança do modelo: {confianca}%
      </p>
    </div>
  )
}
