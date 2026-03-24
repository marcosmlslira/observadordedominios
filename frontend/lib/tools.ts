import type { ToolDefinition, ToolType } from "./types"

export const TOOL_DEFINITIONS: ToolDefinition[] = [
  {
    type: "dns_lookup",
    name: "DNS Lookup",
    description: "Query DNS records (A, AAAA, MX, NS, TXT, CNAME, SOA)",
    slug: "dns-lookup",
    icon: "Globe",
    category: "essential",
  },
  {
    type: "whois",
    name: "WHOIS Lookup",
    description: "Registration data, registrar, dates, and nameservers",
    slug: "whois",
    icon: "FileText",
    category: "essential",
  },
  {
    type: "ssl_check",
    name: "SSL Certificate",
    description: "Verify certificate validity, chain, and expiration",
    slug: "ssl-check",
    icon: "ShieldCheck",
    category: "essential",
  },
  {
    type: "http_headers",
    name: "HTTP Headers",
    description: "Analyze security headers and redirect chain",
    slug: "http-headers",
    icon: "FileCode",
    category: "essential",
  },
  {
    type: "screenshot",
    name: "Screenshot",
    description: "Capture a visual snapshot of the website",
    slug: "screenshot",
    icon: "Camera",
    category: "essential",
  },
  {
    type: "suspicious_page",
    name: "Suspicious Page",
    description: "Detect phishing signals, credential harvesting, brand impersonation",
    slug: "suspicious-page",
    icon: "AlertTriangle",
    category: "essential",
  },
  {
    type: "blacklist_check",
    name: "Blacklist Check",
    description: "Check domain against DNS-based blacklists",
    slug: "blacklist-check",
    icon: "Ban",
    category: "enrichment",
  },
  {
    type: "email_security",
    name: "Email Security",
    description: "Verify SPF, DMARC, and DKIM configuration",
    slug: "email-security",
    icon: "Mail",
    category: "enrichment",
  },
  {
    type: "reverse_ip",
    name: "Reverse IP",
    description: "Find other domains hosted on the same IP",
    slug: "reverse-ip",
    icon: "Server",
    category: "enrichment",
  },
  {
    type: "ip_geolocation",
    name: "IP Geolocation",
    description: "Locate the IP address geographically",
    slug: "ip-geolocation",
    icon: "MapPin",
    category: "enrichment",
  },
  {
    type: "domain_similarity",
    name: "Domain Similarity",
    description: "Generate typosquatting and homoglyph variations",
    slug: "domain-similarity",
    icon: "Copy",
    category: "enrichment",
  },
  {
    type: "website_clone",
    name: "Clone Detector",
    description: "Compare website against reference sites for cloning",
    slug: "website-clone",
    icon: "Layers",
    category: "enrichment",
  },
]

export function getToolBySlug(slug: string): ToolDefinition | undefined {
  return TOOL_DEFINITIONS.find((t) => t.slug === slug)
}

export function getToolByType(type: ToolType): ToolDefinition | undefined {
  return TOOL_DEFINITIONS.find((t) => t.type === type)
}

export const SLUG_TO_TYPE: Record<string, ToolType> = Object.fromEntries(
  TOOL_DEFINITIONS.map((t) => [t.slug, t.type]),
) as Record<string, ToolType>
