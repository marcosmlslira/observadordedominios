"use client"

import { Badge } from "@/components/ui/badge"
import { CheckCircle2, XCircle, AlertTriangle } from "lucide-react"

interface SslData {
  is_valid: boolean
  certificate: {
    subject: string | null
    issuer: string | null
    serial_number: string | null
    not_before: string | null
    not_after: string | null
    days_remaining: number | null
    san: string[]
    signature_algorithm: string | null
    version: number | null
  } | null
  chain_length: number | null
  protocol_version: string | null
  cipher_suite: string | null
  issues: string[]
}

function Field({ label, value }: { label: string; value: string | number | null | undefined }) {
  if (value == null) return null
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-sm">{String(value)}</p>
    </div>
  )
}

export function SslResult({ data }: { data: SslData }) {
  const cert = data.certificate
  const daysRemaining = cert?.days_remaining

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        {data.is_valid ? (
          <CheckCircle2 className="h-5 w-5 text-green-500" />
        ) : (
          <XCircle className="h-5 w-5 text-destructive" />
        )}
        <span className="font-medium">
          {data.is_valid ? "Valid Certificate" : "Invalid Certificate"}
        </span>
        {daysRemaining != null && (
          <Badge
            variant={daysRemaining < 30 ? "destructive" : "secondary"}
            className="text-xs"
          >
            {daysRemaining} days remaining
          </Badge>
        )}
      </div>

      {cert && (
        <div className="grid grid-cols-2 gap-3">
          <Field label="Subject" value={cert.subject} />
          <Field label="Issuer" value={cert.issuer} />
          <Field label="Not Before" value={cert.not_before} />
          <Field label="Not After" value={cert.not_after} />
          <Field label="Protocol" value={data.protocol_version} />
          <Field label="Cipher Suite" value={data.cipher_suite} />
          <Field label="Serial Number" value={cert.serial_number} />
          <Field label="Chain Length" value={data.chain_length} />
        </div>
      )}

      {cert && cert.san.length > 0 && (
        <div>
          <p className="text-xs text-muted-foreground mb-1">
            Subject Alternative Names ({cert.san.length})
          </p>
          <div className="flex flex-wrap gap-1">
            {cert.san.slice(0, 20).map((s) => (
              <Badge key={s} variant="outline" className="text-xs font-mono">
                {s}
              </Badge>
            ))}
            {cert.san.length > 20 && (
              <Badge variant="outline" className="text-xs">
                +{cert.san.length - 20} more
              </Badge>
            )}
          </div>
        </div>
      )}

      {data.issues.length > 0 && (
        <div>
          <p className="text-xs text-muted-foreground mb-1">Issues</p>
          <div className="space-y-1">
            {data.issues.map((issue, i) => (
              <div key={i} className="flex items-start gap-2 text-sm">
                <AlertTriangle className="h-3.5 w-3.5 text-yellow-500 mt-0.5 shrink-0" />
                <span>{issue}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
