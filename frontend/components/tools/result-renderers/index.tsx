"use client"

import type { ToolType } from "@/lib/types"
import { DnsResult } from "./dns-result"
import { WhoisResult } from "./whois-result"
import { SslResult } from "./ssl-result"
import { HttpHeadersResult } from "./http-headers-result"
import { ScreenshotResult } from "./screenshot-result"
import { SuspiciousPageResult } from "./suspicious-page-result"

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
    default:
      return (
        <pre className="text-xs overflow-auto max-h-96 bg-muted p-3 rounded-md">
          {JSON.stringify(data, null, 2)}
        </pre>
      )
  }
}
