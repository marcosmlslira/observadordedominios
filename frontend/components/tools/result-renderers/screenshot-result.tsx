"use client"

import { API_BASE_URL } from "@/lib/config"

interface ScreenshotData {
  screenshot_url: string | null
  s3_key: string | null
  page_title: string | null
  final_url: string | null
  viewport_width: number
  viewport_height: number
}

export function ScreenshotResult({ data }: { data: ScreenshotData }) {
  const resolvedUrl = data.screenshot_url
    ? data.screenshot_url.startsWith("http")
      ? data.screenshot_url
      : `${API_BASE_URL}${data.screenshot_url}`
    : null

  return (
    <div className="space-y-3">
      {data.page_title && (
        <div>
          <p className="text-xs text-muted-foreground">Page Title</p>
          <p className="text-sm">{data.page_title}</p>
        </div>
      )}
      {data.final_url && (
        <div>
          <p className="text-xs text-muted-foreground">Final URL</p>
          <p className="text-xs font-mono break-all">{data.final_url}</p>
        </div>
      )}
      {resolvedUrl ? (
        <div className="border rounded-lg overflow-hidden">
          <img
            src={resolvedUrl}
            alt="Website screenshot"
            className="w-full"
          />
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          Screenshot captured ({data.viewport_width}x{data.viewport_height})
          {data.s3_key ? ` — stored at ${data.s3_key}` : ""}
        </p>
      )}
    </div>
  )
}
