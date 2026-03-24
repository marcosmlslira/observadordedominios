"use client"

import { MapPin } from "lucide-react"
import { Badge } from "@/components/ui/badge"

interface GeolocationResult {
  domain: string
  ip: string | null
  country?: string | null
  country_code?: string | null
  region?: string | null
  city?: string | null
  latitude?: number | null
  longitude?: number | null
  isp?: string | null
  org?: string | null
  asn?: string | null
  source?: string
  error?: string
}

export function GeolocationResult({ data }: { data: GeolocationResult }) {
  if (data.error && !data.country) {
    return <p className="text-sm text-muted-foreground">{data.error}</p>
  }

  const rows = [
    { label: "IP", value: data.ip },
    { label: "Country", value: data.country && data.country_code ? `${data.country} (${data.country_code})` : data.country },
    { label: "Region", value: data.region },
    { label: "City", value: data.city },
    { label: "Coordinates", value: data.latitude != null && data.longitude != null ? `${data.latitude}, ${data.longitude}` : null },
    { label: "ISP", value: data.isp },
    { label: "Organization", value: data.org },
    { label: "ASN", value: data.asn },
  ].filter((r) => r.value)

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 p-3 rounded-md bg-muted/50">
        <MapPin className="h-4 w-4 text-muted-foreground shrink-0" />
        <div>
          <p className="text-sm font-medium">
            {[data.city, data.region, data.country].filter(Boolean).join(", ") || "Unknown location"}
          </p>
          {data.ip && <p className="text-xs font-mono text-muted-foreground">{data.ip}</p>}
        </div>
        {data.source && (
          <Badge variant="outline" className="text-xs ml-auto">{data.source}</Badge>
        )}
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        {rows.map(({ label, value }) => (
          <div key={label}>
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="font-mono text-xs mt-0.5">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
