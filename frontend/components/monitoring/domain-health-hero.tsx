"use client"

import { useState } from "react"
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
} from "lucide-react"

// ── Safe data extractors ─────────────────────────────────

function safeStr(val: unknown): string | null {
  return typeof val === "string" ? val : null
}

function safeNum(val: unknown): number | null {
  return typeof val === "number" ? val : null
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
    case "ok": return "bg-emerald-50 dark:bg-emerald-950/20 border-emerald-200/80 dark:border-emerald-800/40"
    case "warning": return "bg-amber-50 dark:bg-amber-950/20 border-amber-200/80 dark:border-amber-800/40"
    case "critical": return "bg-red-50 dark:bg-red-950/20 border-red-200/80 dark:border-red-800/40"
    default: return "bg-muted/20 border-border"
  }
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

function overallMessage(status: string | undefined) {
  switch (status) {
    case "healthy": return "O domínio oficial está operacional e sem sinais relevantes de risco."
    case "warning": return "O domínio está ativo, mas há ajustes recomendados de segurança."
    case "critical": return "O domínio exige ação imediata para evitar exposição ou indisponibilidade."
    default: return "Aguardando primeira verificação de saúde para este domínio."
  }
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
      label: "Certificado",
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
      label: "Reputação",
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
              "flex flex-col gap-2 rounded-xl border p-3 text-left w-full transition-all duration-150",
              "hover:shadow-sm hover:scale-[1.01] active:scale-[0.99]",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              statusBgBorder(info.status)
            )}
          >
            <div className="flex items-center justify-between">
              <CheckTypeIcon type={info.key} className={cn("opacity-70", statusColorText(info.status))} />
              <StatusIcon status={info.status} />
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

// ── Modal row helper ─────────────────────────────────────

function ModalRow({
  label,
  value,
  status,
}: {
  label: string
  value: React.ReactNode
  status?: CheckStatus
}) {
  return (
    <div className="flex items-center justify-between py-2 border-b last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span
        className={cn(
          "text-sm font-medium",
          status ? statusColorText(status) : ""
        )}
      >
        {value}
      </span>
    </div>
  )
}

// ── Modal: DNS ───────────────────────────────────────────

function DnsModal({ domain }: { domain: DomainHealthCheck }) {
  const status = okToStatus(domain.dns?.ok)
  return (
    <div className="space-y-1">
      <ModalRow
        label="Status de resolução"
        value={status === "ok" ? "Resolve corretamente" : status === "unknown" ? "Não verificado" : "Falhou"}
        status={status}
      />
      <ModalRow
        label="Última verificação"
        value={
          domain.last_check_at
            ? new Date(domain.last_check_at).toLocaleString("pt-BR")
            : "—"
        }
      />
      <p className={cn("mt-3 text-xs rounded-lg px-3 py-2 border-l-2", overallBarStyle(status === "ok" ? "healthy" : status === "unknown" ? undefined : "warning"))}>
        {status === "ok"
          ? "Nenhuma ação necessária. O domínio resolve corretamente."
          : status === "unknown"
            ? "Aguardando a próxima verificação automática."
            : "Verifique os registros DNS do domínio no seu provedor de hospedagem."}
      </p>
    </div>
  )
}

// ── Modal: SSL / Certificate ─────────────────────────────

function SslModal({ domain }: { domain: DomainHealthCheck }) {
  const check = domain.ssl
  const status = okToStatus(check?.ok)
  const days = safeNum(check?.details?.["days_remaining"])

  const certStatus =
    check === undefined
      ? "unknown"
      : !check.ok
        ? "critical"
        : days !== null && days <= 7
          ? "critical"
          : days !== null && days <= 30
            ? "warning"
            : "ok"

  const recommendation =
    certStatus === "critical" && days !== null && days <= 7
      ? `O certificado expira em ${days} dias. Renovação imediata recomendada.`
      : certStatus === "warning"
        ? `O certificado expira em ${days} dias. Agende a renovação em breve.`
        : certStatus === "ok"
          ? "Certificado válido. Nenhuma ação necessária."
          : certStatus === "critical"
            ? "Certificado inválido. Verifique a configuração do servidor."
            : "Aguardando verificação do certificado."

  return (
    <div className="space-y-1">
      <ModalRow
        label="Validade"
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
      <ModalRow
        label="Última verificação"
        value={
          domain.last_check_at
            ? new Date(domain.last_check_at).toLocaleString("pt-BR")
            : "—"
        }
      />
      <p className={cn("mt-3 text-xs rounded-lg px-3 py-2 border-l-2", overallBarStyle(
        certStatus === "ok" ? "healthy" : certStatus === "warning" ? "warning" : certStatus === "critical" ? "critical" : undefined
      ))}>
        {recommendation}
      </p>
    </div>
  )
}

// ── Modal: Email security ────────────────────────────────

function EmailModal({ domain }: { domain: DomainHealthCheck }) {
  const check = domain.email_security
  const status: CheckStatus = check === undefined ? "unknown" : check.ok ? "ok" : "warning"
  const spoofingRisk = safeStr(check?.details?.["spoofing_risk"])

  return (
    <div className="space-y-1">
      <ModalRow
        label="Proteção geral"
        value={check === undefined ? "—" : check.ok ? "Protegido" : "Atenção"}
        status={status}
      />
      {spoofingRisk && (
        <ModalRow
          label="Risco de spoofing"
          value={spoofingRisk}
          status={spoofingRisk === "alto" ? "critical" : spoofingRisk === "médio" ? "warning" : "ok"}
        />
      )}
      <ModalRow
        label="Última verificação"
        value={
          domain.last_check_at
            ? new Date(domain.last_check_at).toLocaleString("pt-BR")
            : "—"
        }
      />
      <p className={cn("mt-3 text-xs rounded-lg px-3 py-2 border-l-2", overallBarStyle(
        status === "ok" ? "healthy" : status === "warning" ? "warning" : undefined
      ))}>
        {status === "ok"
          ? "SPF, DKIM e DMARC configurados corretamente. O domínio está protegido contra spoofing."
          : status === "unknown"
            ? "Aguardando verificação das proteções de e-mail."
            : "Revise as configurações de SPF, DKIM e DMARC no seu provedor de DNS para reduzir o risco de spoofing."}
      </p>
    </div>
  )
}

// ── Modal: HTTP Headers ──────────────────────────────────

function HeadersModal({ domain }: { domain: DomainHealthCheck }) {
  const check = domain.headers
  const status: CheckStatus = check === undefined ? "unknown" : check.ok ? "ok" : "warning"
  const score = safeStr(check?.details?.["score"])

  return (
    <div className="space-y-1">
      <ModalRow
        label="Avaliação geral"
        value={check === undefined ? "—" : check.ok ? "Completo" : "Parcial"}
        status={status}
      />
      {score && (
        <ModalRow
          label="Score"
          value={score}
          status={score === "good" ? "ok" : score === "poor" ? "critical" : "warning"}
        />
      )}
      <ModalRow
        label="Última verificação"
        value={
          domain.last_check_at
            ? new Date(domain.last_check_at).toLocaleString("pt-BR")
            : "—"
        }
      />
      <p className={cn("mt-3 text-xs rounded-lg px-3 py-2 border-l-2", overallBarStyle(
        status === "ok" ? "healthy" : status === "warning" ? "warning" : undefined
      ))}>
        {status === "ok"
          ? "Os headers de segurança estão presentes e protegem o site de ataques comuns."
          : status === "unknown"
            ? "Aguardando verificação dos headers de segurança."
            : "Adicione os headers de segurança ausentes na configuração do seu servidor web (ex: CSP, HSTS, X-Frame-Options)."}
      </p>
    </div>
  )
}

// ── Modal: Security / Reputation ─────────────────────────

function SecurityModal({ domain }: { domain: DomainHealthCheck }) {
  const checks: { label: string; ok: boolean | undefined; source: string }[] = [
    { label: "Blacklist", ok: domain.blacklist?.ok, source: "Listas gerais de abuso" },
    { label: "Safe Browsing", ok: domain.safe_browsing?.ok, source: "Google Safe Browsing" },
    { label: "URLhaus", ok: domain.urlhaus?.ok, source: "URLhaus — malware distribuído" },
    { label: "PhishTank", ok: domain.phishtank?.ok, source: "PhishTank — phishing" },
  ]

  const anyFailed = checks.some((c) => c.ok === false)
  const allUnknown = checks.every((c) => c.ok === undefined)

  return (
    <div className="space-y-1">
      {checks.map((c) => (
        <ModalRow
          key={c.label}
          label={c.label}
          value={
            c.ok === undefined ? (
              <span className="text-muted-foreground text-xs">Não verificado</span>
            ) : c.ok ? (
              "Limpo"
            ) : (
              "Detectado"
            )
          }
          status={c.ok === undefined ? "unknown" : c.ok ? "ok" : "critical"}
        />
      ))}
      <ModalRow
        label="Última verificação"
        value={
          domain.last_check_at
            ? new Date(domain.last_check_at).toLocaleString("pt-BR")
            : "—"
        }
      />
      <p className={cn("mt-3 text-xs rounded-lg px-3 py-2 border-l-2", overallBarStyle(
        allUnknown ? undefined : anyFailed ? "critical" : "healthy"
      ))}>
        {allUnknown
          ? "Aguardando verificação de reputação do domínio."
          : anyFailed
            ? "O domínio aparece em uma ou mais listas de abuso. Investigue imediatamente para evitar impacto na entrega de e-mails e acesso ao site."
            : "O domínio não aparece em nenhuma lista de abuso conhecida."}
      </p>
    </div>
  )
}

// ── Modal: Integrity ─────────────────────────────────────

function IntegrityModal({ domain }: { domain: DomainHealthCheck }) {
  const checks: { label: string; ok: boolean | undefined; description: string }[] = [
    { label: "Subdomain Takeover", ok: domain.takeover?.ok, description: "Risco de subdomínio apontando para serviço abandonado" },
    { label: "Página suspeita", ok: domain.suspicious_page?.ok, description: "Conteúdo suspeito identificado no site ativo" },
  ]

  const anyFailed = checks.some((c) => c.ok === false)
  const allUnknown = checks.every((c) => c.ok === undefined)

  return (
    <div className="space-y-1">
      {checks.map((c) => (
        <ModalRow
          key={c.label}
          label={c.label}
          value={
            c.ok === undefined ? (
              <span className="text-muted-foreground text-xs">Não verificado</span>
            ) : c.ok ? (
              "OK"
            ) : (
              "Alerta"
            )
          }
          status={c.ok === undefined ? "unknown" : c.ok ? "ok" : "critical"}
        />
      ))}
      <ModalRow
        label="Última verificação"
        value={
          domain.last_check_at
            ? new Date(domain.last_check_at).toLocaleString("pt-BR")
            : "—"
        }
      />
      <p className={cn("mt-3 text-xs rounded-lg px-3 py-2 border-l-2", overallBarStyle(
        allUnknown ? undefined : anyFailed ? "critical" : "healthy"
      ))}>
        {allUnknown
          ? "Aguardando verificação de integridade do domínio."
          : anyFailed
            ? "Foram detectados sinais de comprometimento. Verifique subdomínios e o conteúdo ativo do site."
            : "Nenhum sinal de comprometimento ou conteúdo suspeito detectado."}
      </p>
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
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <CheckTypeIcon type={checkKey} className="text-muted-foreground" />
            {MODAL_TITLES[checkKey]}
            <span className="font-mono text-sm font-normal text-muted-foreground">
              — {domain.domain_name}
            </span>
          </DialogTitle>
        </DialogHeader>
        <div className="mt-1">
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

// ── Secondary domain row ─────────────────────────────────

function SecondaryDomainRow({ d }: { d: DomainHealthCheck }) {
  const domainStatus =
    d.overall_status === "healthy"
      ? "ok"
      : d.overall_status === "critical"
        ? "critical"
        : d.overall_status === "warning"
          ? "warning"
          : "unknown"
  return (
    <div className="flex items-center justify-between py-1.5 text-sm">
      <span className="font-mono text-xs text-muted-foreground">{d.domain_name}</span>
      <div className="flex items-center gap-1.5">
        <StatusIcon status={domainStatus} />
        <span className={cn("text-xs", statusColorText(domainStatus))}>
          {overallLabel(d.overall_status)}
        </span>
      </div>
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

            {/* Right: Status + actions */}
            <div className="flex flex-col items-end gap-2 shrink-0">
              <div
                className={cn(
                  "flex items-center gap-1.5 rounded-lg border px-3 py-1.5",
                  overallBadgeStyle(overallHealth)
                )}
              >
                {overallStatusIcon(overallHealth)}
                <span className="text-sm font-semibold">{overallLabel(overallHealth)}</span>
              </div>
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
                    Nova verificação
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
              <div className="divide-y">
                {secondaryDomains.map((d) => (
                  <SecondaryDomainRow key={d.domain_id} d={d} />
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
