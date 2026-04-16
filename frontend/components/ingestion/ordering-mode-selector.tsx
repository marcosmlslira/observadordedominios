"use client"

import { useState } from "react"
import { Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

export type OrderingMode = "corpus_first" | "priority_first" | "alphabetical"

const OPTIONS: { value: OrderingMode; label: string; description: string }[] = [
  {
    value: "corpus_first",
    label: "Menor corpus",
    description: "Processa TLDs com menos domínios primeiro",
  },
  {
    value: "priority_first",
    label: "Prioridade",
    description: "Respeita o campo de prioridade, depois tamanho do corpus",
  },
  {
    value: "alphabetical",
    label: "Alfabética",
    description: "Ordem alfabética pelo nome do TLD",
  },
]

interface OrderingModeSelectorProps {
  value: OrderingMode
  onSave: (mode: OrderingMode) => Promise<void>
}

export function OrderingModeSelector({ value, onSave }: OrderingModeSelectorProps) {
  const [saving, setSaving] = useState(false)

  async function handleSelect(mode: OrderingMode) {
    if (mode === value || saving) return
    setSaving(true)
    try {
      await onSave(mode)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">Ordem de execução</span>
        {saving && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
      </div>
      <div
        role="radiogroup"
        aria-label="Modo de ordenação dos TLDs"
        className="flex gap-2 flex-wrap"
      >
        {OPTIONS.map((opt) => {
          const active = opt.value === value
          return (
            <button
              key={opt.value}
              role="radio"
              aria-checked={active}
              aria-label={opt.description}
              disabled={saving}
              onClick={() => handleSelect(opt.value)}
              title={opt.description}
              className={cn(
                "rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors duration-150 cursor-pointer",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
                "disabled:pointer-events-none disabled:opacity-50",
                active
                  ? "bg-foreground text-background border-foreground"
                  : "bg-background text-muted-foreground border-border hover:border-foreground/40 hover:text-foreground"
              )}
            >
              {opt.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
