"use client"

import { Badge } from "@/components/ui/badge"

interface WhoisData {
  domain_name: string | null
  registrar: string | null
  creation_date: string | null
  expiration_date: string | null
  updated_date: string | null
  name_servers: string[]
  status: string[]
  registrant_name: string | null
  registrant_organization: string | null
  registrant_country: string | null
  dnssec: string | null
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-sm">{value}</p>
    </div>
  )
}

export function WhoisResult({ data }: { data: WhoisData }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Domain" value={data.domain_name} />
        <Field label="Registrar" value={data.registrar} />
        <Field label="Created" value={data.creation_date} />
        <Field label="Expires" value={data.expiration_date} />
        <Field label="Updated" value={data.updated_date} />
        <Field label="DNSSEC" value={data.dnssec} />
        <Field label="Registrant" value={data.registrant_name} />
        <Field label="Organization" value={data.registrant_organization} />
        <Field label="Country" value={data.registrant_country} />
      </div>

      {data.name_servers.length > 0 && (
        <div>
          <p className="text-xs text-muted-foreground mb-1">Nameservers</p>
          <div className="flex flex-wrap gap-1">
            {data.name_servers.map((ns) => (
              <Badge key={ns} variant="secondary" className="text-xs font-mono">
                {ns}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {data.status.length > 0 && (
        <div>
          <p className="text-xs text-muted-foreground mb-1">Status</p>
          <div className="flex flex-wrap gap-1">
            {data.status.map((s) => (
              <Badge key={s} variant="outline" className="text-xs">
                {s}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
