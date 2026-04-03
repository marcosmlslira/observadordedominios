"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Play } from "lucide-react"

interface TriggerSyncDialogProps {
  onTrigger: (tld: string, force: boolean) => Promise<void>
  syncing: boolean
  syncError: string
  defaultTld?: string
}

export function TriggerSyncDialog({ onTrigger, syncing, syncError, defaultTld }: TriggerSyncDialogProps) {
  const [open, setOpen] = useState(false)
  const [tld, setTld] = useState(defaultTld || "net")
  const [force, setForce] = useState(false)

  async function handleSubmit() {
    try {
      await onTrigger(tld, force)
      setOpen(false)
    } catch {
      // error is shown via syncError prop
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (v && defaultTld) setTld(defaultTld) }}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Play className="h-3 w-3 mr-1" />
          Trigger CZDS Sync
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Trigger CZDS Sync</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 pt-2">
          <div className="space-y-2">
            <Label htmlFor="tld">TLD</Label>
            <Input
              id="tld"
              value={tld}
              onChange={(e) => setTld(e.target.value)}
              placeholder="net"
            />
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="force"
              checked={force}
              onChange={(e) => setForce(e.target.checked)}
              className="rounded"
            />
            <Label htmlFor="force">Force (ignore cooldown)</Label>
          </div>
          {syncError && (
            <p className="text-sm text-red-500">{syncError}</p>
          )}
          <Button onClick={handleSubmit} disabled={syncing || !tld} className="w-full">
            {syncing ? "Triggering..." : "Trigger Sync"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
