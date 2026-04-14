"use client"

import { useState } from "react"
import type { ReactNode } from "react"
import type { Brand, BrandHealthResponse, DomainHealthCheck } from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import {
  Globe,
  Shield,
  Mail,
  Code2,
  ShieldAlert,
  Lock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Minus,
  RefreshCw,
  Loader2,
  Clock,
  CalendarDays,
  ChevronRight,
} from "lucide-react"

// ── Safe data extractors ─────────────────────────────────

function safeStr(val: unknown): string | null {
  return typeof val === "string" ? val : null
}

function safeNum(val: unknown): number | null {
  return typeof val === "number" ? val : null
}

function safeArr(val: unknown): unknown[] {
  return Array.isArray(val) ? val : []
}

function safeBool(val: unknown): boolean | null {
  return typeof val === "boolean" ? val : null
}

function safeObj(val: unknown): Record<string, unknown> | null {
  return val !== null && val !== undefined && typeof val === "object" && !Array.isArray(val)
    ? (val as Record<string, unknown>)
    : null
}

// ── Status types ─────────────────────────────────────────

type CheckStatus = "ok" | "warning" | "critical" | "unknown"

function statusColorText(status: CheckStatus) {
  switch (status) {
    case "ok": return "text-emerald-600 dark:text-emerald-400"
    case "warning": return "text-amber-600 dark:text-amber-400"
    case "critical": return "text-red-600 dark:text-red-400"
    default: return "text-muted-foreground"
  }
}

function statusBgBorder(status: CheckStatus) {
  switch (status) {
    case "ok":       return "bg-background dark:bg-card border-border/60"
    case "warning":  return "bg-amber-50/80 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800/70"
    case "critical": return "bg-red-50/80 dark:bg-red-950/30 border-red-200 dark:border-red-800/70"
    default:         return "bg-muted/30 border-border/50"
  }
}

function statusLeftAccent(status: CheckStatus) {
  if (status === "warning")  return "border-l-[3px] border-l-amber-400 dark:border-l-amber-500"
  if (status === "critical") return "border-l-[3px] border-l-red-400 dark:border-l-red-500"
  return ""
}

function StatusIcon({ status, size = "sm" }: { status: CheckStatus; size?: "sm" | "md" }) {
  const cls = size === "md" ? "h-4 w-4" : "h-3.5 w-3.5"
  if (status === "ok") return <CheckCircle2 className={cn(cls, "text-emerald-500")} />
  if (status === "warning") return <AlertTriangle className={cn(cls, "text-amber-500")} />
  if (status === "critical") return <XCircle className={cn(cls, "text-red-500")} />
  return <Minus className={cn(cls, "text-muted-foreground")} />
}

function okToStatus(ok: boolean | undefined): CheckStatus {
  if (ok === undefined) return "unknown"
  return ok ? "ok" : "critical"
}

// ── Overall health helpers ───────────────────────────────

function overallLabel(status: string | undefined) {
  switch (status) {
    case "healthy": return "Saudável"
    case "warning": return "Atenção"
    case "critical": return "Crítico"
    default: return "Desconhecido"
  }
}

function buildSummaryMessage(domain: DomainHealthCheck | null, status: string | undefined): string {
  if (!domain || !status || status === "unknown") {
    return "Aguardando primeira verificação de saúde para este domínio."
  }
  if (status === "healthy") {
    return "O domínio oficial está operacional e sem sinais relevantes de risco."
  }
  if (status === "critical") {
    const issues: string[] = []
    if (!domain.dns?.ok) issues.push("DNS")
    if (!domain.ssl?.ok) issues.push("certificado SSL")
    if (domain.blacklist?.ok === false || domain.safe_browsing?.ok === false || domain.urlhaus?.ok === false || domain.phishtank?.ok === false) issues.push("reputação em listas de segurança")
    if (domain.takeover?.ok === false || domain.suspicious_page?.ok === false) issues.push("integridade do domínio")
    if (issues.length === 0) return "O domínio exige ação imediata para evitar exposição ou indisponibilidade."
    if (issues.length === 1) return `O domínio exige ação imediata — problema crítico em ${issues[0]}.`
    const last = issues.pop()!
    return `O domínio exige ação imediata — problemas críticos em ${issues.join(", ")} e ${last}.`
  }
  // warning — build specific message
  const issues: string[] = []
  if (!domain.headers?.ok) issues.push("headers de segurança")
  if (!domain.email_security?.ok) issues.push("proteção de e-mail")
  if (domain.ssl?.ok && (safeNum(domain.ssl?.details?.["days_remaining"]) ?? 999) <= 30) issues.push("certificado SSL próximo da expiração")
  if (!domain.dns?.ok) issues.push("configuração DNS")
  if (issues.length === 0) return "O domínio está ativo com ajustes recomendados de segurança."
  if (issues.length === 1) return `O domínio está ativo e protegido, mas encontramos ajustes recomendados em ${issues[0]}.`
  const last = issues.pop()!
  return `O domínio está ativo, mas encontramos ajustes recomendados em ${issues.join(", ")} e ${last}.`
}

function overallMessage(status: string | undefined) {
  return buildSummaryMessage(null, status)
}

function overallBarStyle(status: string | undefined): string {
  switch (status) {
    case "healthy": return "border-l-emerald-500 bg-emerald-50/50 dark:bg-emerald-950/10 text-emerald-800 dark:text-emerald-300"
    case "warning": return "border-l-amber-500 bg-amber-50/50 dark:bg-amber-950/10 text-amber-800 dark:text-amber-300"
    case "critical": return "border-l-red-500 bg-red-50/50 dark:bg-red-950/10 text-red-800 dark:text-red-300"
    default: return "border-l-muted-foreground/30 bg-muted/20 text-muted-foreground"
  }
}

function overallBadgeStyle(status: string | undefined): string {
  switch (status) {
    case "healthy": return "bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-700"
    case "warning": return "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-700"
    case "critical": return "bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border-red-200 dark:border-red-700"
    default: return "bg-muted/50 text-muted-foreground border-border"
  }
}

function overallStatusIcon(status: string | undefined) {
  if (status === "healthy") return <CheckCircle2 className="h-4 w-4 text-emerald-500" />
  if (status === "warning") return <AlertTriangle className="h-4 w-4 text-amber-500" />
  if (status === "critical") return <XCircle className="h-4 w-4 text-red-500" />
  return <Minus className="h-4 w-4 text-muted-foreground" />
}

// ── Domain selector ──────────────────────────────────────

function findPrimaryDomain(domains: DomainHealthCheck[]): DomainHealthCheck | null {
  if (domains.length === 0) return null
  return domains.find((d) => d.is_primary) ?? domains[0]
}

// ── Check card data ──────────────────────────────────────

interface CheckCardInfo {
  key: string
  label: string
  status: CheckStatus
  summary: string
  microtext: string
  tooltip: string
}

function buildCheckCards(d: DomainHealthCheck): CheckCardInfo[] {
  // DNS
  const dnsStatus = okToStatus(d.dns?.ok)

  // SSL + certificate validity
  const sslDays = safeNum(d.ssl?.details?.["days_remaining"])
  let sslStatus: CheckStatus
  if (d.ssl === undefined) {
    sslStatus = "unknown"
  } else if (!d.ssl.ok) {
    sslStatus = "critical"
  } else if (sslDays !== null && sslDays <= 7) {
    sslStatus = "critical"
  } else if (sslDays !== null && sslDays <= 30) {
    sslStatus = "warning"
  } else {
    sslStatus = "ok"
  }
  const sslSummary =
    d.ssl === undefined ? "Não verificado" : d.ssl.ok ? "Válido" : "Inválido"
  const sslMicrotext =
    d.ssl === undefined
      ? "Aguardando verificação"
      : sslDays !== null
        ? `${sslDays} dias restantes`
        : d.ssl.ok
          ? "Certificado ativo"
          : "Certificado com problema"

  // Email security
  const spoofingRisk = safeStr(d.email_security?.details?.["spoofing_risk"])
  const emailStatus: CheckStatus =
    d.email_security === undefined ? "unknown" : d.email_security.ok ? "ok" : "warning"
  const emailSummary =
    d.email_security === undefined
      ? "Não verificado"
      : d.email_security.ok
        ? "Protegido"
        : "Atenção"
  const emailMicrotext =
    d.email_security === undefined
      ? "Aguardando verificação"
      : d.email_security.ok
        ? "SPF, DKIM e DMARC ok"
        : spoofingRisk
          ? `Spoofing: ${spoofingRisk}`
          : "Verificar proteções de e-mail"

  // HTTP Headers
  const headersScore = safeStr(d.headers?.details?.["score"])
  const headersStatus: CheckStatus =
    d.headers === undefined ? "unknown" : d.headers.ok ? "ok" : "warning"
  const headersSummary =
    d.headers === undefined ? "Não verificado" : d.headers.ok ? "Completo" : "Parcial"
  const headersMicrotext =
    d.headers === undefined
      ? "Aguardando verificação"
      : headersScore
        ? `Score: ${headersScore}`
        : d.headers.ok
          ? "Todos headers presentes"
          : "Headers de segurança ausentes"

  // Security reputation (blacklist + safe_browsing + urlhaus + phishtank)
  const repChecks = [d.blacklist?.ok, d.safe_browsing?.ok, d.urlhaus?.ok, d.phishtank?.ok]
  const repAllUndefined = repChecks.every((v) => v === undefined)
  const repAnyFailed = repChecks.some((v) => v === false)
  const securityStatus: CheckStatus = repAllUndefined ? "unknown" : repAnyFailed ? "critical" : "ok"
  const securitySummary = repAllUndefined ? "Não verificado" : repAnyFailed ? "Detectado" : "Limpo"
  const securityMicrotext = repAllUndefined
    ? "Aguardando verificação"
    : repAnyFailed
      ? "Presente em lista(s) de abuso"
      : "0 ocorrências em listas"

  // Integrity (takeover + suspicious_page)
  const intChecks = [d.takeover?.ok, d.suspicious_page?.ok]
  const intAllUndefined = intChecks.every((v) => v === undefined)
  const intAnyFailed = intChecks.some((v) => v === false)
  const integrityStatus: CheckStatus = intAllUndefined ? "unknown" : intAnyFailed ? "critical" : "ok"
  const integritySummary = intAllUndefined ? "Não verificado" : intAnyFailed ? "Alerta" : "OK"
  const integrityMicrotext = intAllUndefined
    ? "Aguardando verificação"
    : intAnyFailed
      ? "Verificar takeover ou página suspeita"
      : "Sem sinais de comprometimento"

  return [
    {
      key: "dns",
      label: "DNS",
      status: dnsStatus,
      summary: dnsStatus === "ok" ? "OK" : dnsStatus === "unknown" ? "Não verificado" : "Falhou",
      microtext:
        dnsStatus === "ok"
          ? "Resolve corretamente"
          : dnsStatus === "unknown"
            ? "Aguardando verificação"
            : "Verificar configuração de DNS",
      tooltip:
        "Verifica se o domínio resolve corretamente e responde com a configuração esperada de registros.",
    },
    {
      key: "ssl",
      label: "SSL",
      status: sslStatus,
      summary: sslSummary,
      microtext: sslMicrotext,
      tooltip:
        "Valida o certificado SSL do site e mostra quantos dias faltam para expirar. Expirado ou inválido gera alerta no navegador.",
    },
    {
      key: "email",
      label: "E-mail",
      status: emailStatus,
      summary: emailSummary,
      microtext: emailMicrotext,
      tooltip:
        "Avalia as proteções contra uso indevido do domínio em e-mails falsos: SPF, DKIM e DMARC.",
    },
    {
      key: "headers",
      label: "Headers",
      status: headersStatus,
      summary: headersSummary,
      microtext: headersMicrotext,
      tooltip:
        "Cabeçalhos de segurança HTTP que o servidor envia para proteger navegadores de ataques comuns.",
    },
    {
      key: "security",
      label: "Blacklist",
      status: securityStatus,
      summary: securitySummary,
      microtext: securityMicrotext,
      tooltip:
        "Confere se o domínio aparece em listas de spam, phishing ou malware (Blacklist, Safe Browsing, URLhaus, PhishTank).",
    },
    {
      key: "integrity",
      label: "Integridade",
      status: integrityStatus,
      summary: integritySummary,
      microtext: integrityMicrotext,
      tooltip:
        "Detecta sinais de comprometimento do domínio, como tentativas de subdomain takeover ou página suspeita ativa.",
    },
  ]
}

// ── Check icon mapper ────────────────────────────────────

function CheckTypeIcon({ type, className }: { type: string; className?: string }) {
  const cls = cn("h-4 w-4", className)
  switch (type) {
    case "dns": return <Globe className={cls} />
    case "ssl": return <Lock className={cls} />
    case "email": return <Mail className={cls} />
    case "headers": return <Code2 className={cls} />
    case "security": return <ShieldAlert className={cls} />
    case "integrity": return <Shield className={cls} />
    default: return <Globe className={cls} />
  }
}

// ── Check Mini Card ──────────────────────────────────────

function CheckMiniCard({ info, onClick }: { info: CheckCardInfo; onClick: () => void }) {
  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            onClick={onClick}
            className={cn(
              "group flex flex-col gap-2 rounded-xl border p-3 text-left w-full transition-all duration-150",
              "hover:shadow-md hover:scale-[1.02] active:scale-[0.99]",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              statusBgBorder(info.status),
              statusLeftAccent(info.status)
            )}
          >
            <div className="flex items-center justify-between">
              <CheckTypeIcon type={info.key} className={cn("opacity-70", statusColorText(info.status))} />
              <div className="flex items-center gap-1">
                <StatusIcon status={info.status} />
                <ChevronRight className="h-3 w-3 opacity-0 group-hover:opacity-50 transition-opacity text-muted-foreground" />
              </div>
            </div>
            <div className="space-y-0.5">
              <p className="text-[11px] font-medium text-muted-foreground leading-none uppercase tracking-wide">
                {info.label}
              </p>
              <p className={cn("text-sm font-semibold leading-tight", statusColorText(info.status))}>
                {info.summary}
              </p>
              <p className="text-[11px] text-muted-foreground leading-tight">{info.microtext}</p>
            </div>
          </button>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-[200px] text-xs leading-relaxed text-center">
          {info.tooltip}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

// ── Modal helpers ────────────────────────────────────────

function ModalRow({
  label,
  value,
  status,
}: {
  label: string
  value: ReactNode
  status?: CheckStatus
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-2 border-b last:border-0">
      <span className="text-xs text-muted-foreground shrink-0">{label}</span>
      <span className={cn("text-xs font-medium text-right", status ? statusColorText(status) : "")}>
        {value}
      </span>
    </div>
  )
}

function ModalSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">
        {title}
      </p>
      <div className="rounded-lg border bg-muted/20 px-3 py-1">
        {children}
      </div>
    </div>
  )
}

function RawCollapsible({ data }: { data: Record<string, unknown> }) {
  const [open, setOpen] = useState(false)
  if (!data || Object.keys(data).filter(k => data[k] !== undefined && data[k] !== null).length === 0) return null
  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-[11px] text-muted-foreground hover:text-foreground transition-colors py-1"
      >
        <ChevronRight className={cn("h-3 w-3 transition-transform", open && "rotate-90")} />
        Dados brutos (JSON)
      </button>
      {open && (
        <pre className="mt-1 text-[11px] font-mono bg-muted/40 border rounded-lg p-3 overflow-x-auto overflow-y-auto max-h-48 whitespace-pre-wrap break-all leading-relaxed">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  )
}

// ── Modal: DNS ───────────────────────────────────────────

function DnsModal({ domain }: { domain: DomainHealthCheck }) {
  const check = domain.dns
  const status = okToStatus(check?.ok)
  const details = safeObj(check?.details) ?? {}
  const records = safeArr(details["records"])
  const nameservers = safeArr(details["nameservers"])
  const resolutionMs = safeNum(details["resolution_time_ms"])

  // Group records by type
  const recordsByType: Record<string, { value: string; ttl?: number }[]> = {}
  for (const r of records) {
    const obj = safeObj(r)
    if (!obj) continue
    const type = safeStr(obj["type"]) ?? "OTHER"
    if (!recordsByType[type]) recordsByType[type] = []
    recordsByType[type].push({
      value: safeStr(obj["value"]) ?? "—",
      ttl: safeNum(obj["ttl"]) ?? undefined,
    })
  }

  const typeOrder = ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA", "CAA"]
  const sortedTypes = [
    ...typeOrder.filter((t) => recordsByType[t]),
    ...Object.keys(recordsByType).filter((t) => !typeOrder.includes(t)),
  ]

  return (
    <div className="space-y-4">
      {/* Summary */}
      <ModalSection title="Resumo">
        <ModalRow
          label="Resolução"
          value={status === "ok" ? "Resolve corretamente" : status === "unknown" ? "Não verificado" : "Falhou"}
          status={status}
        />
        {resolutionMs !== null && (
          <ModalRow label="Tempo de resposta" value={`${resolutionMs} ms`} />
        )}
        <ModalRow
          label="Última verificação"
          value={domain.last_check_at ? new Date(domain.last_check_at).toLocaleString("pt-BR") : "—"}
        />
      </ModalSection>

      {/* Records grouped by type */}
      {sortedTypes.length > 0 && sortedTypes.map((type) => (
        <ModalSection key={type} title={`Registros ${type}`}>
          {recordsByType[type].map((rec, i) => (
            <ModalRow
              key={i}
              label={rec.ttl !== undefined ? `TTL ${rec.ttl}s` : `#${i + 1}`}
              value={<span className="font-mono text-[11px] break-all">{rec.value}</span>}
            />
          ))}
        </ModalSection>
      ))}

      {/* Nameservers */}
      {nameservers.length > 0 && (
        <ModalSection title="Servidores de Nome (NS)">
          {nameservers.map((ns, i) => (
            <ModalRow key={i} label={`NS ${i + 1}`} value={<span className="font-mono text-[11px]">{safeStr(ns) ?? "—"}</span>} />
          ))}
        </ModalSection>
      )}

      {/* Recommendation */}
      <p className={cn("text-xs rounded-lg px-3 py-2 border-l-2", overallBarStyle(status === "ok" ? "healthy" : status === "unknown" ? undefined : "critical"))}>
        {status === "ok"
          ? "Nenhuma ação necessária. O domínio resolve corretamente."
          : status === "unknown"
            ? "Aguardando a próxima verificação automática."
            : "Verifique os registros DNS no seu provedor de hospedagem."}
      </p>

      <RawCollapsible data={details} />
    </div>
  )
}

// ── Modal: SSL / Certificate ─────────────────────────────

function SslModal({ domain }: { domain: DomainHealthCheck }) {
  const check = domain.ssl
  const details = safeObj(check?.details) ?? {}
  const cert = safeObj(details["certificate"]) ?? {}
  const issues = safeArr(details["issues"])
  const sanEntries = safeArr(cert["san"] ?? details["san_entries"])
  const days = safeNum(cert["days_remaining"] ?? details["days_remaining"])
  const protocol = safeStr(details["protocol_version"])
  const cipher = safeStr(details["cipher_suite"])
  const chainLen = safeNum(details["chain_length"])
  const selfSigned = safeBool(details["self_signed"] ?? cert["self_signed"])
  const issuer = safeStr(cert["issuer"] ?? details["issuer"])
  const subject = safeStr(cert["subject"] ?? details["subject"])
  const notBefore = safeStr(cert["not_before"])
  const notAfter = safeStr(cert["not_after"] ?? cert["expires_at"] ?? details["expires_at"])
  const serial = safeStr(cert["serial_number"])
  const version = safeNum(cert["version"])
  const ocsp = safeStr(cert["ocsp_status"])

  const certStatus: CheckStatus =
    check === undefined ? "unknown"
    : !check.ok ? "critical"
    : days !== null && days <= 7 ? "critical"
    : days !== null && days <= 30 ? "warning"
    : "ok"

  const fmtDate = (d: string | null) => {
    if (!d) return "—"
    try { return new Date(d).toLocaleDateString("pt-BR") } catch { return d }
  }

  return (
    <div className="space-y-4">
      {/* Summary */}
      <ModalSection title="Resumo">
        <ModalRow
          label="Status"
          value={check === undefined ? "—" : check.ok ? "Válido" : "Inválido"}
          status={certStatus}
        />
        {days !== null && (
          <ModalRow
            label="Dias restantes"
            value={`${days} dias`}
            status={days <= 7 ? "critical" : days <= 30 ? "warning" : "ok"}
          />
        )}
        <ModalRow label="Última verificação" value={domain.last_check_at ? new Date(domain.last_check_at).toLocaleString("pt-BR") : "—"} />
      </ModalSection>

      {/* Certificate details */}
      {(issuer || subject || notBefore || notAfter || serial) && (
        <ModalSection title="Detalhes do certificado">
          {issuer && <ModalRow label="Emissor (Issuer)" value={<span className="font-mono text-[11px] break-all">{issuer}</span>} />}
          {subject && <ModalRow label="Domínio (Subject)" value={<span className="font-mono text-[11px] break-all">{subject}</span>} />}
          {notBefore && <ModalRow label="Emitido em" value={fmtDate(notBefore)} />}
          {notAfter && <ModalRow label="Expira em" value={fmtDate(notAfter)} status={certStatus} />}
          {serial && <ModalRow label="Serial" value={<span className="font-mono text-[11px]">{serial}</span>} />}
          {version !== null && <ModalRow label="Versão X.509" value={`v${version}`} />}
          {ocsp && <ModalRow label="OCSP" value={ocsp} />}
        </ModalSection>
      )}

      {/* SANs */}
      {sanEntries.length > 0 && (
        <ModalSection title={`SANs — ${sanEntries.length} entrada${sanEntries.length !== 1 ? "s" : ""}`}>
          {sanEntries.map((san, i) => (
            <ModalRow key={i} label={`SAN ${i + 1}`} value={<span className="font-mono text-[11px]">{safeStr(san) ?? "—"}</span>} />
          ))}
        </ModalSection>
      )}

      {/* Technical */}
      {(protocol || cipher || chainLen !== null || selfSigned !== null) && (
        <ModalSection title="Segurança da conexão">
          {protocol && <ModalRow label="Protocolo" value={<span className="font-mono text-[11px]">{protocol}</span>} />}
          {cipher && <ModalRow label="Cipher suite" value={<span className="font-mono text-[11px] break-all">{cipher}</span>} />}
          {chainLen !== null && <ModalRow label="Comprimento da cadeia" value={`${chainLen} certificado${chainLen !== 1 ? "s" : ""}`} />}
          {selfSigned !== null && (
            <ModalRow
              label="Self-signed"
              value={selfSigned ? "Sim" : "Não"}
              status={selfSigned ? "warning" : "ok"}
            />
          )}
        </ModalSection>
      )}

      {/* Issues */}
      {issues.length > 0 && (
        <ModalSection title="Problemas detectados">
          {issues.map((issue, i) => (
            <ModalRow key={i} label={`#${i + 1}`} value={<span className="text-amber-600 dark:text-amber-400">{safeStr(issue) ?? String(issue)}</span>} />
          ))}
        </ModalSection>
      )}

      {/* Recommendation */}
      <p className={cn("text-xs rounded-lg px-3 py-2 border-l-2", overallBarStyle(
        certStatus === "ok" ? "healthy" : certStatus === "warning" ? "warning" : certStatus === "critical" ? "critical" : undefined
      ))}>
        {certStatus === "critical" && days !== null && days <= 7
          ? `O certificado expira em ${days} dias. Renovação imediata recomendada.`
          : certStatus === "warning"
            ? `O certificado expira em ${days} dias. Agende a renovação em breve.`
            : certStatus === "ok"
              ? "Certificado válido. Nenhuma ação necessária."
              : certStatus === "critical"
                ? "Certificado inválido. Verifique a configuração do servidor."
                : "Aguardando verificação do certificado."}
      </p>

      <RawCollapsible data={details} />
    </div>
  )
}

// ── Modal: Email security ────────────────────────────────

function EmailModal({ domain }: { domain: DomainHealthCheck }) {
  const check = domain.email_security
  const details = safeObj(check?.details) ?? {}
  const spf = safeObj(details["spf"]) ?? {}
  const dmarc = safeObj(details["dmarc"]) ?? {}
  const dkim = safeObj(details["dkim"]) ?? {}
  const mtaSts = safeObj(details["mta_sts"]) ?? {}
  const spoofing = safeObj(details["spoofing_risk"]) ?? {}
  const spoofingLevel = safeStr(spoofing["level"]) ?? safeStr(details["spoofing_risk"])
  const spoofingScore = safeNum(spoofing["score"])

  const spfPresent = safeBool(spf["present"])
  const dkimFound = safeBool(dkim["found"])
  const dmarcPresent = safeBool(dmarc["present"])

  const protocolStatus = (present: boolean | null): CheckStatus =>
    present === null ? "unknown" : present ? "ok" : "critical"

  const spfIssues = safeArr(spf["issues"])
  const dmarcIssues = safeArr(dmarc["issues"])
  const dkimSelectors = safeArr(dkim["selectors_found"])

  const overallStatus: CheckStatus =
    check === undefined ? "unknown"
    : check.ok ? "ok"
    : spoofingLevel === "alto" ? "critical"
    : "warning"

  return (
    <div className="space-y-4">
      {/* Summary */}
      <ModalSection title="Resumo">
        <ModalRow
          label="Proteção geral"
          value={check === undefined ? "—" : check.ok ? "Protegido" : "Atenção"}
          status={overallStatus}
        />
        {spoofingLevel && (
          <ModalRow
            label="Risco de spoofing"
            value={spoofingLevel}
            status={spoofingLevel === "alto" ? "critical" : spoofingLevel === "médio" || spoofingLevel === "medium" || spoofingLevel === "high" ? "warning" : "ok"}
          />
        )}
        {spoofingScore !== null && <ModalRow label="Score de risco" value={String(spoofingScore)} />}
        <ModalRow label="Última verificação" value={domain.last_check_at ? new Date(domain.last_check_at).toLocaleString("pt-BR") : "—"} />
      </ModalSection>

      {/* SPF */}
      <ModalSection title="SPF — Sender Policy Framework">
        <ModalRow label="Configurado" value={spfPresent === null ? "—" : spfPresent ? "Sim" : "Não"} status={protocolStatus(spfPresent)} />
        {safeStr(spf["record"]) && (
          <ModalRow label="Registro TXT" value={<span className="font-mono text-[11px] break-all">{safeStr(spf["record"])}</span>} />
        )}
        {safeStr(spf["policy"]) && <ModalRow label="Política" value={safeStr(spf["policy"])} />}
        {safeArr(spf["includes"]).length > 0 && (
          <ModalRow label="Includes" value={<span className="font-mono text-[11px]">{safeArr(spf["includes"]).map(s => safeStr(s)).join(", ")}</span>} />
        )}
        {spfIssues.length > 0 && spfIssues.map((issue, i) => (
          <ModalRow key={i} label="Problema" value={<span className="text-amber-600 dark:text-amber-400 text-[11px]">{safeStr(issue) ?? String(issue)}</span>} />
        ))}
      </ModalSection>

      {/* DKIM */}
      <ModalSection title="DKIM — DomainKeys Identified Mail">
        <ModalRow label="Configurado" value={dkimFound === null ? "—" : dkimFound ? "Sim" : "Não"} status={protocolStatus(dkimFound)} />
        {dkimSelectors.length > 0 && (
          <ModalRow label="Seletores encontrados" value={<span className="font-mono text-[11px]">{dkimSelectors.map(s => safeStr(s)).join(", ")}</span>} />
        )}
        {safeArr(dkim["selectors_checked"]).length > 0 && (
          <ModalRow label="Seletores verificados" value={<span className="font-mono text-[11px]">{safeArr(dkim["selectors_checked"]).map(s => safeStr(s)).join(", ")}</span>} />
        )}
      </ModalSection>

      {/* DMARC */}
      <ModalSection title="DMARC — Domain-based Message Authentication">
        <ModalRow label="Configurado" value={dmarcPresent === null ? "—" : dmarcPresent ? "Sim" : "Não"} status={protocolStatus(dmarcPresent)} />
        {safeStr(dmarc["record"]) && (
          <ModalRow label="Registro TXT" value={<span className="font-mono text-[11px] break-all">{safeStr(dmarc["record"])}</span>} />
        )}
        {safeStr(dmarc["policy"]) && <ModalRow label="Política p=" value={safeStr(dmarc["policy"])} />}
        {safeStr(dmarc["subdomain_policy"]) && <ModalRow label="Subdomínio sp=" value={safeStr(dmarc["subdomain_policy"])} />}
        {safeNum(dmarc["percentage"]) !== null && <ModalRow label="Porcentagem pct=" value={`${safeNum(dmarc["percentage"])}%`} />}
        {safeStr(dmarc["rua"]) && <ModalRow label="Relatório RUA" value={<span className="font-mono text-[11px] break-all">{safeStr(dmarc["rua"])}</span>} />}
        {safeStr(dmarc["ruf"]) && <ModalRow label="Relatório RUF" value={<span className="font-mono text-[11px] break-all">{safeStr(dmarc["ruf"])}</span>} />}
        {dmarcIssues.length > 0 && dmarcIssues.map((issue, i) => (
          <ModalRow key={i} label="Problema" value={<span className="text-amber-600 dark:text-amber-400 text-[11px]">{safeStr(issue) ?? String(issue)}</span>} />
        ))}
      </ModalSection>

      {/* MTA-STS */}
      {Object.keys(mtaSts).length > 0 && (
        <ModalSection title="MTA-STS — Mail Transfer Agent Strict Transport Security">
          {safeBool(mtaSts["has_record"]) !== null && (
            <ModalRow label="Registro DNS" value={safeBool(mtaSts["has_record"]) ? "Presente" : "Ausente"} status={safeBool(mtaSts["has_record"]) ? "ok" : "warning"} />
          )}
          {safeBool(mtaSts["has_policy_file"]) !== null && (
            <ModalRow label="Arquivo de política" value={safeBool(mtaSts["has_policy_file"]) ? "Presente" : "Ausente"} status={safeBool(mtaSts["has_policy_file"]) ? "ok" : "warning"} />
          )}
          {safeStr(mtaSts["mode"]) && <ModalRow label="Modo" value={safeStr(mtaSts["mode"])} />}
          {safeStr(mtaSts["policy_id"]) && <ModalRow label="Policy ID" value={<span className="font-mono text-[11px]">{safeStr(mtaSts["policy_id"])}</span>} />}
        </ModalSection>
      )}

      {/* Recommendation */}
      <p className={cn("text-xs rounded-lg px-3 py-2 border-l-2", overallBarStyle(
        overallStatus === "ok" ? "healthy" : overallStatus === "warning" ? "warning" : overallStatus === "critical" ? "critical" : undefined
      ))}>
        {overallStatus === "ok"
          ? "SPF, DKIM e DMARC configurados corretamente. O domínio está protegido contra spoofing."
          : overallStatus === "unknown"
            ? "Aguardando verificação das proteções de e-mail."
            : "Revise as configurações de SPF, DKIM e DMARC no seu provedor de DNS para reduzir o risco de spoofing."}
      </p>

      <RawCollapsible data={details} />
    </div>
  )
}

// ── Modal: HTTP Headers ──────────────────────────────────

function HeadersModal({ domain }: { domain: DomainHealthCheck }) {
  const check = domain.headers
  const details = safeObj(check?.details) ?? {}
  const secHeaders = safeArr(details["security_headers"])
  const redirectChain = safeArr(details["redirect_chain"])
  const score = safeStr(details["score"])
  const finalUrl = safeStr(details["final_url"])
  const httpStatus = safeNum(details["status_code"])
  const server = safeStr(details["server"])
  const contentType = safeStr(details["content_type"])

  const present = secHeaders.filter(h => safeBool(safeObj(h)?.["present"]) === true)
  const absent = secHeaders.filter(h => safeBool(safeObj(h)?.["present"]) !== true)

  const overallStatus: CheckStatus =
    check === undefined ? "unknown"
    : check.ok ? "ok"
    : score === "poor" ? "critical"
    : "warning"

  const severityBadge = (sev: string | null) => {
    if (!sev) return null
    const map: Record<string, string> = {
      high: "text-red-600 dark:text-red-400",
      medium: "text-amber-600 dark:text-amber-400",
      low: "text-blue-600 dark:text-blue-400",
    }
    return <span className={cn("text-[11px] font-medium capitalize", map[sev.toLowerCase()] ?? "text-muted-foreground")}>{sev}</span>
  }

  return (
    <div className="space-y-4">
      {/* Summary */}
      <ModalSection title="Resumo">
        <ModalRow
          label="Avaliação geral"
          value={check === undefined ? "—" : score ?? (check.ok ? "Completo" : "Parcial")}
          status={overallStatus}
        />
        <ModalRow
          label="Headers presentes"
          value={`${present.length} de ${secHeaders.length}`}
          status={present.length === secHeaders.length ? "ok" : present.length === 0 ? "critical" : "warning"}
        />
        <ModalRow label="Última verificação" value={domain.last_check_at ? new Date(domain.last_check_at).toLocaleString("pt-BR") : "—"} />
      </ModalSection>

      {/* HTTP info */}
      {(finalUrl || httpStatus !== null || server || contentType) && (
        <ModalSection title="Informações HTTP">
          {finalUrl && <ModalRow label="URL final" value={<span className="font-mono text-[11px] break-all">{finalUrl}</span>} />}
          {httpStatus !== null && <ModalRow label="Status HTTP" value={String(httpStatus)} status={httpStatus < 400 ? "ok" : "critical"} />}
          {server && <ModalRow label="Servidor" value={<span className="font-mono text-[11px]">{server}</span>} />}
          {contentType && <ModalRow label="Content-Type" value={<span className="font-mono text-[11px]">{contentType}</span>} />}
        </ModalSection>
      )}

      {/* Security headers */}
      {secHeaders.length > 0 && (
        <ModalSection title={`Headers de segurança (${present.length}/${secHeaders.length} presentes)`}>
          {secHeaders.map((h, i) => {
            const obj = safeObj(h) ?? {}
            const name = safeStr(obj["name"]) ?? `Header ${i + 1}`
            const isPresent = safeBool(obj["present"]) === true
            const value = safeStr(obj["value"])
            const severity = safeStr(obj["severity"])
            return (
              <div key={i} className="py-2 border-b last:border-0 space-y-0.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-mono">{name}</span>
                  <div className="flex items-center gap-2">
                    {!isPresent && severityBadge(severity)}
                    <span className={cn("text-xs font-medium", isPresent ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400")}>
                      {isPresent ? "Presente" : "Ausente"}
                    </span>
                  </div>
                </div>
                {value && (
                  <p className="text-[11px] font-mono text-muted-foreground break-all pl-2 border-l-2 border-border/40">{value}</p>
                )}
              </div>
            )
          })}
        </ModalSection>
      )}

      {/* Redirect chain */}
      {redirectChain.length > 0 && (
        <ModalSection title={`Cadeia de redirecionamentos (${redirectChain.length})`}>
          {redirectChain.map((r, i) => {
            const obj = safeObj(r) ?? {}
            const url = safeStr(obj["url"]) ?? "—"
            const code = safeNum(obj["status_code"])
            return (
              <div key={i} className="py-2 border-b last:border-0 flex items-start justify-between gap-2">
                <span className="font-mono text-[11px] text-muted-foreground break-all flex-1">{url}</span>
                {code !== null && <span className="text-xs font-medium shrink-0">{code}</span>}
              </div>
            )
          })}
        </ModalSection>
      )}

      {/* Recommendation */}
      <p className={cn("text-xs rounded-lg px-3 py-2 border-l-2", overallBarStyle(
        overallStatus === "ok" ? "healthy" : overallStatus === "warning" ? "warning" : overallStatus === "critical" ? "critical" : undefined
      ))}>
        {absent.length === 0
          ? "Os headers de segurança estão presentes e protegem o site de ataques comuns."
          : `Adicione os headers ausentes: ${absent.map(h => safeStr(safeObj(h)?.["name"])).filter(Boolean).join(", ")}.`}
      </p>

      <RawCollapsible data={details} />
    </div>
  )
}

// ── Modal: Security / Blacklist ───────────────────────────

function SecurityModal({ domain }: { domain: DomainHealthCheck }) {
  const blDetails = safeObj(domain.blacklist?.details) ?? {}
  const sbDetails = safeObj(domain.safe_browsing?.details) ?? {}
  const uhDetails = safeObj(domain.urlhaus?.details) ?? {}
  const ptDetails = safeObj(domain.phishtank?.details) ?? {}

  const listedCount = safeNum(blDetails["listed_count"]) ?? 0
  const totalChecked = safeNum(blDetails["total_checked"])
  const listings = safeArr(blDetails["listings"])
  const riskLevel = safeStr(blDetails["risk_level"])

  const sources: { label: string; source: string; ok: boolean | undefined; details: Record<string, unknown> }[] = [
    { label: "Blacklist DNSBL", source: "Listas gerais de abuso", ok: domain.blacklist?.ok, details: blDetails },
    { label: "Google Safe Browsing", source: "Malware e phishing", ok: domain.safe_browsing?.ok, details: sbDetails },
    { label: "URLhaus", source: "Distribuição de malware", ok: domain.urlhaus?.ok, details: uhDetails },
    { label: "PhishTank", source: "Campanhas de phishing", ok: domain.phishtank?.ok, details: ptDetails },
  ]

  const anyFailed = sources.some((c) => c.ok === false)
  const allUnknown = sources.every((c) => c.ok === undefined)

  return (
    <div className="space-y-4">
      {/* Summary */}
      <ModalSection title="Resumo geral">
        {totalChecked !== null && (
          <ModalRow
            label="Listas verificadas"
            value={`${listedCount} ocorrência${listedCount !== 1 ? "s" : ""} em ${totalChecked}`}
            status={listedCount > 0 ? "critical" : "ok"}
          />
        )}
        {riskLevel && (
          <ModalRow
            label="Nível de risco"
            value={riskLevel}
            status={riskLevel === "high" || riskLevel === "alto" ? "critical" : riskLevel === "medium" || riskLevel === "médio" ? "warning" : "ok"}
          />
        )}
        <ModalRow label="Última verificação" value={domain.last_check_at ? new Date(domain.last_check_at).toLocaleString("pt-BR") : "—"} />
      </ModalSection>

      {/* Sources overview */}
      <ModalSection title="Fontes consultadas">
        {sources.map((s) => (
          <div key={s.label} className="py-2 border-b last:border-0">
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="text-xs font-medium">{s.label}</p>
                <p className="text-[11px] text-muted-foreground">{s.source}</p>
              </div>
              <span className={cn("text-xs font-semibold shrink-0",
                s.ok === undefined ? "text-muted-foreground"
                : s.ok ? "text-emerald-600 dark:text-emerald-400"
                : "text-red-600 dark:text-red-400"
              )}>
                {s.ok === undefined ? "—" : s.ok ? "Limpo" : "Detectado"}
              </span>
            </div>
          </div>
        ))}
      </ModalSection>

      {/* DNSBL listings detail */}
      {listings.length > 0 && (
        <ModalSection title={`Detalhes DNSBL — ${listings.length} lista${listings.length !== 1 ? "s" : ""}`}>
          {listings.map((item, i) => {
            const obj = safeObj(item) ?? {}
            const name = safeStr(obj["name"]) ?? `Lista ${i + 1}`
            const listed = safeBool(obj["listed"]) === true
            const category = safeStr(obj["category"])
            const zone = safeStr(obj["zone"])
            return (
              <div key={i} className="py-2 border-b last:border-0">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex-1">
                    <p className="text-xs font-medium">{name}</p>
                    {(category || zone) && (
                      <p className="text-[11px] text-muted-foreground font-mono">{[category, zone].filter(Boolean).join(" · ")}</p>
                    )}
                  </div>
                  <span className={cn("text-xs font-semibold shrink-0", listed ? "text-red-600 dark:text-red-400" : "text-emerald-600 dark:text-emerald-400")}>
                    {listed ? "Listado" : "Limpo"}
                  </span>
                </div>
              </div>
            )
          })}
        </ModalSection>
      )}

      {/* Recommendation */}
      <p className={cn("text-xs rounded-lg px-3 py-2 border-l-2", overallBarStyle(
        allUnknown ? undefined : anyFailed ? "critical" : "healthy"
      ))}>
        {allUnknown
          ? "Aguardando verificação de reputação do domínio."
          : anyFailed
            ? "O domínio aparece em uma ou mais listas de abuso. Investigue imediatamente para evitar impacto na entrega de e-mails e acesso ao site."
            : "O domínio não aparece em nenhuma lista de abuso conhecida."}
      </p>

      <RawCollapsible data={blDetails} />
    </div>
  )
}

// ── Modal: Integrity ─────────────────────────────────────

function IntegrityModal({ domain }: { domain: DomainHealthCheck }) {
  const takeoverDetails = safeObj(domain.takeover?.details) ?? {}
  const susPageDetails = safeObj(domain.suspicious_page?.details) ?? {}

  const anyFailed = domain.takeover?.ok === false || domain.suspicious_page?.ok === false
  const allUnknown = domain.takeover === undefined && domain.suspicious_page === undefined

  const renderDetails = (title: string, ok: boolean | undefined, details: Record<string, unknown>) => {
    const entries = Object.entries(details).filter(([, v]) => v !== null && v !== undefined)
    return (
      <ModalSection title={title}>
        <ModalRow
          label="Status"
          value={ok === undefined ? "—" : ok ? "OK" : "Alerta"}
          status={ok === undefined ? "unknown" : ok ? "ok" : "critical"}
        />
        {entries.map(([key, value]) => {
          const label = key.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase())
          if (Array.isArray(value)) {
            if (value.length === 0) return null
            return (
              <ModalRow
                key={key}
                label={label}
                value={
                  <div className="flex flex-col items-end gap-0.5">
                    {value.map((v, i) => (
                      <span key={i} className="font-mono text-[11px] break-all">{typeof v === "string" ? v : JSON.stringify(v)}</span>
                    ))}
                  </div>
                }
              />
            )
          }
          if (typeof value === "boolean") {
            return <ModalRow key={key} label={label} value={value ? "Sim" : "Não"} status={value ? "warning" : "ok"} />
          }
          if (typeof value === "string" || typeof value === "number") {
            return <ModalRow key={key} label={label} value={<span className="font-mono text-[11px] break-all">{String(value)}</span>} />
          }
          return null
        })}
      </ModalSection>
    )
  }

  return (
    <div className="space-y-4">
      {renderDetails("Subdomain Takeover", domain.takeover?.ok, takeoverDetails)}
      {renderDetails("Página Suspeita", domain.suspicious_page?.ok, susPageDetails)}

      <p className={cn("text-xs rounded-lg px-3 py-2 border-l-2", overallBarStyle(
        allUnknown ? undefined : anyFailed ? "critical" : "healthy"
      ))}>
        {allUnknown
          ? "Aguardando verificação de integridade do domínio."
          : anyFailed
            ? "Foram detectados sinais de comprometimento. Verifique subdomínios e o conteúdo ativo do site."
            : "Nenhum sinal de comprometimento ou conteúdo suspeito detectado."}
      </p>

      {(Object.keys(takeoverDetails).length > 0 || Object.keys(susPageDetails).length > 0) && (
        <RawCollapsible data={{ takeover: takeoverDetails, suspicious_page: susPageDetails }} />
      )}
    </div>
  )
}

// ── Check Detail Modal dispatcher ────────────────────────

const MODAL_TITLES: Record<string, string> = {
  dns: "DNS",
  ssl: "Certificado SSL",
  email: "Segurança de E-mail",
  headers: "Headers de Segurança",
  security: "Reputação e Blacklists",
  integrity: "Integridade do Domínio",
}

function CheckDetailModal({
  checkKey,
  domain,
  onClose,
}: {
  checkKey: string
  domain: DomainHealthCheck
  onClose: () => void
}) {
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <CheckTypeIcon type={checkKey} className="text-muted-foreground" />
            {MODAL_TITLES[checkKey]}
            <span className="font-mono text-sm font-normal text-muted-foreground">
              — {domain.domain_name}
            </span>
          </DialogTitle>
        </DialogHeader>
        <div className="mt-1 overflow-y-auto max-h-[calc(80vh-8rem)] pr-1">
          {checkKey === "dns" && <DnsModal domain={domain} />}
          {checkKey === "ssl" && <SslModal domain={domain} />}
          {checkKey === "email" && <EmailModal domain={domain} />}
          {checkKey === "headers" && <HeadersModal domain={domain} />}
          {checkKey === "security" && <SecurityModal domain={domain} />}
          {checkKey === "integrity" && <IntegrityModal domain={domain} />}
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ── Secondary domain chip ────────────────────────────────

function SecondaryDomainChip({ d }: { d: DomainHealthCheck }) {
  const domainStatus: CheckStatus =
    d.overall_status === "healthy" ? "ok"
    : d.overall_status === "critical" ? "critical"
    : d.overall_status === "warning" ? "warning"
    : "unknown"
  return (
    <div className={cn(
      "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs",
      statusBgBorder(domainStatus)
    )}>
      <StatusIcon status={domainStatus} size="sm" />
      <span className="font-mono">{d.domain_name}</span>
    </div>
  )
}

// ── Main export ──────────────────────────────────────────

interface DomainHealthHeroProps {
  brand: Brand
  health: BrandHealthResponse | null
  scanning: boolean
  onScan: () => void
}

export function DomainHealthHero({ brand, health, scanning, onScan }: DomainHealthHeroProps) {
  const [openModal, setOpenModal] = useState<string | null>(null)
  const [modalDomain, setModalDomain] = useState<DomainHealthCheck | null>(null)

  const overallHealth = brand.monitoring_summary?.overall_health
  const primaryDomain = health ? findPrimaryDomain(health.domains) : null
  const secondaryDomains = health?.domains.filter((d) => !d.is_primary) ?? []

  const checkCards = primaryDomain ? buildCheckCards(primaryDomain) : []

  const monitoredSince = brand.created_at
    ? new Date(brand.created_at).toLocaleDateString("pt-BR", { month: "short", year: "numeric" })
    : "—"

  const lastCheckAt = primaryDomain?.last_check_at
    ? new Date(primaryDomain.last_check_at).toLocaleString("pt-BR", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : null

  function openCheckModal(checkKey: string, domain: DomainHealthCheck) {
    setOpenModal(checkKey)
    setModalDomain(domain)
  }

  const isPrimaryChecked = primaryDomain && primaryDomain.overall_status !== "unknown"
  const officialCount = brand.official_domains.length

  return (
    <>
      <Card className="overflow-hidden">
        {/* Header */}
        <CardContent className="pt-5 pb-4">
          <div className="flex flex-wrap items-start justify-between gap-4">
            {/* Left: Identity */}
            <div className="min-w-0">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1">
                {brand.brand_name}
              </p>
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="font-mono text-2xl font-bold tracking-tight leading-none">
                  {brand.official_domains.find((d) => d.is_primary)?.domain_name ??
                    brand.official_domains[0]?.domain_name ??
                    brand.brand_label}
                </h1>
                {brand.official_domains.some((d) => d.is_primary) && (
                  <Badge
                    variant="outline"
                    className="text-[10px] py-0 h-5 border-blue-200 dark:border-blue-800 text-blue-600 dark:text-blue-400 bg-blue-50/50 dark:bg-blue-950/20"
                  >
                    Primário
                  </Badge>
                )}
                {/* Status badge inline — reading flow: domain → Primário → Status */}
                {overallHealth && (
                  <div
                    className={cn(
                      "flex items-center gap-1 rounded-lg border px-2 py-0.5",
                      overallBadgeStyle(overallHealth)
                    )}
                  >
                    {overallStatusIcon(overallHealth)}
                    <span className="text-xs font-semibold">{overallLabel(overallHealth)}</span>
                  </div>
                )}
                {!brand.is_active && (
                  <Badge variant="outline" className="text-[10px] py-0 h-5">
                    Inativo
                  </Badge>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2 text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <CalendarDays className="h-3 w-3" />
                  Perfil desde {monitoredSince}
                </span>
                {lastCheckAt && (
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    Última checagem {lastCheckAt}
                  </span>
                )}
                {officialCount > 1 && (
                  <span>{officialCount} domínios oficiais</span>
                )}
              </div>
            </div>

            {/* Right: Actions only */}
            <div className="flex flex-col items-end gap-2 shrink-0">
              <Button
                size="sm"
                onClick={onScan}
                disabled={scanning}
                className="h-8"
              >
                {scanning ? (
                  <>
                    <Loader2 className="h-3 w-3 mr-1.5 animate-spin" />
                    Aguardando…
                  </>
                ) : (
                  <>
                    <RefreshCw className="h-3 w-3 mr-1.5" />
                    Executar nova verificação
                  </>
                )}
              </Button>
            </div>
          </div>

          {/* Status summary bar */}
          {(isPrimaryChecked || overallHealth) && (
            <div
              className={cn(
                "mt-4 rounded-lg border-l-2 px-3 py-2 text-xs leading-relaxed",
                overallBarStyle(overallHealth)
              )}
            >
              {overallMessage(overallHealth)}
            </div>
          )}

          {/* 6 mini-cards */}
          {primaryDomain && checkCards.length > 0 ? (
            <div className="mt-4 grid grid-cols-3 sm:grid-cols-6 gap-2">
              {checkCards.map((info) => (
                <CheckMiniCard
                  key={info.key}
                  info={info}
                  onClick={() => openCheckModal(info.key, primaryDomain)}
                />
              ))}
            </div>
          ) : (
            <div className="mt-4 flex items-center gap-2 rounded-lg bg-muted/30 border border-dashed px-4 py-3 text-sm text-muted-foreground">
              <Minus className="h-4 w-4 shrink-0" />
              Aguardando primeira verificação de saúde deste domínio.
            </div>
          )}

          {/* Secondary domains summary */}
          {secondaryDomains.length > 0 && (
            <div className="mt-4 border-t pt-3">
              <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide mb-1">
                Outros domínios monitorados
              </p>
              <div className="flex flex-wrap gap-2">
                {secondaryDomains.map((d) => (
                  <SecondaryDomainChip key={d.domain_id} d={d} />
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Detail modal */}
      {openModal && modalDomain && (
        <CheckDetailModal
          checkKey={openModal}
          domain={modalDomain}
          onClose={() => {
            setOpenModal(null)
            setModalDomain(null)
          }}
        />
      )}
    </>
  )
}
