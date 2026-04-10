"use client"

interface SparkRun {
  status: "success" | "failed" | "running" | null
  duration_seconds: number | null
}

interface SparkbarProps {
  runs: SparkRun[]  // up to 10, oldest first
  maxRuns?: number
}

export function Sparkbar({ runs, maxRuns = 10 }: SparkbarProps) {
  // Pad to maxRuns with empty slots
  const slots: SparkRun[] = [
    ...Array(Math.max(0, maxRuns - runs.length)).fill({ status: null, duration_seconds: null }),
    ...runs.slice(-maxRuns),
  ]

  // Normalize heights: max duration = full height (20px), empty = 4px
  const maxDuration = Math.max(
    1,
    ...slots.map((s) => s.duration_seconds ?? 0)
  )
  const MIN_HEIGHT = 4
  const MAX_HEIGHT = 20

  return (
    <div className="flex gap-[2px] items-end h-5" title="últimas 10 ingestões (mais antiga → mais recente)">
      {slots.map((slot, i) => {
        const height =
          slot.duration_seconds != null
            ? MIN_HEIGHT + ((slot.duration_seconds / maxDuration) * (MAX_HEIGHT - MIN_HEIGHT))
            : MIN_HEIGHT

        const color =
          slot.status === "success"
            ? "bg-green-500"
            : slot.status === "failed"
            ? "bg-red-500"
            : slot.status === "running"
            ? "bg-blue-400 animate-pulse"
            : "bg-muted"

        const tooltip =
          slot.status != null
            ? `${slot.status} · ${slot.duration_seconds != null ? Math.round(slot.duration_seconds) + "s" : "?"}`
            : "sem dado"

        return (
          <div
            key={i}
            className={`w-[5px] rounded-sm ${color}`}
            style={{ height: `${Math.round(height)}px` }}
            title={tooltip}
          />
        )
      })}
    </div>
  )
}
