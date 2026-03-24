"use client"

import type { ToolType } from "@/lib/types"
import { DnsResult } from "./dns-result"
import { WhoisResult } from "./whois-result"
import { SslResult } from "./ssl-result"
import { HttpHeadersResult } from "./http-headers-result"
import { ScreenshotResult } from "./screenshot-result"
import { SuspiciousPageResult } from "./suspicious-page-result"
import { BlacklistResult } from "./blacklist-result"
import { EmailSecurityResult } from "./email-security-result"
import { ReverseIpResult } from "./reverse-ip-result"
import { GeolocationResult } from "./geolocation-result"
import { DomainSimilarityResult } from "./domain-similarity-result"
import { CloneDetectorResult } from "./clone-detector-result"

interface ToolResultRendererProps {
  toolType: ToolType
  data: Record<string, unknown>
}

export function ToolResultRenderer({ toolType, data }: ToolResultRendererProps) {
  switch (toolType) {
    case "dns_lookup":
      return <DnsResult data={data as any} />
    case "whois":
      return <WhoisResult data={data as any} />
    case "ssl_check":
      return <SslResult data={data as any} />
    case "http_headers":
      return <HttpHeadersResult data={data as any} />
    case "screenshot":
      return <ScreenshotResult data={data as any} />
    case "suspicious_page":
      return <SuspiciousPageResult data={data as any} />
    case "blacklist_check":
      return <BlacklistResult data={data as any} />
    case "email_security":
      return <EmailSecurityResult data={data as any} />
    case "reverse_ip":
      return <ReverseIpResult data={data as any} />
    case "ip_geolocation":
      return <GeolocationResult data={data as any} />
    case "domain_similarity":
      return <DomainSimilarityResult data={data as any} />
    case "website_clone":
      return <CloneDetectorResult data={data as any} />
    default:
      return (
        <pre className="text-xs overflow-auto max-h-96 bg-muted p-3 rounded-md">
          {JSON.stringify(data, null, 2)}
        </pre>
      )
  }
}
