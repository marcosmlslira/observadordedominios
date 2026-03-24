"use client"

interface ScreenshotData {
  screenshot_url: string | null
  s3_key: string | null
  page_title: string | null
  final_url: string | null
  viewport_width: number
  viewport_height: number
}

export function ScreenshotResult({ data }: { data: ScreenshotData }) {
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
      {data.screenshot_url ? (
        <div className="border rounded-lg overflow-hidden">
          <img
            src={data.screenshot_url}
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
