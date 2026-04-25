"use client"

import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"

interface CronConfigCardProps {
  initialCron: string
  onSave: (cron: string) => Promise<void>
}

function parseCronDescription(cron: string): string {
  const parts = cron.trim().split(/\s+/)
  if (parts.length !== 5) return cron
  const [min, hour] = parts
  if (min.match(/^\d+$/) && hour.match(/^\d+$/)) {
    return `Todo dia às ${hour.padStart(2, "0")}:${min.padStart(2, "0")} UTC`
  }
  return cron
}

function validateCron(cron: string): string | null {
  const parts = cron.trim().split(/\s+/)
  if (parts.length !== 5) return "Cron deve ter 5 partes (ex: 0 7 * * *)"
  return null
}

export function CronConfigCard({
  initialCron,
  onSave,
}: CronConfigCardProps) {
  const [cron, setCron] = useState(initialCron)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  async function handleSave() {
    const validationError = validateCron(cron)
    if (validationError) {
      setError(validationError)
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onSave(cron)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch {
      setError("Erro ao salvar. Tente novamente.")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium uppercase tracking-wide text-muted-foreground">
          Agendamento
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-3">
          <Label className="text-sm text-muted-foreground whitespace-nowrap">
            Expressão cron
          </Label>
          <Input
            value={cron}
            onChange={(e) => {
              setCron(e.target.value)
              setError(null)
              setSaved(false)
            }}
            className="font-mono w-36 h-8 text-sm"
            placeholder="0 7 * * *"
          />
          <span className="text-xs text-muted-foreground">
            {validateCron(cron) ? "" : parseCronDescription(cron)}
          </span>
          <Button
            size="sm"
            variant="outline"
            onClick={handleSave}
            disabled={saving || cron === initialCron}
            className="ml-auto h-8"
          >
            {saving ? "Salvando…" : saved ? "Salvo ✓" : "Salvar"}
          </Button>
        </div>
        {error && <p className="text-xs text-destructive mt-2">{error}</p>}
      </CardContent>
    </Card>
  )
}
