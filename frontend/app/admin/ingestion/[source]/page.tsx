import { SourceConfigPage } from "@/components/ingestion/source-config-page"

const VALID_SOURCES = ["czds", "certstream", "openintel"]

interface Props {
  params: { source: string }
}

export default function IngestionSourcePage({ params }: Props) {
  if (!VALID_SOURCES.includes(params.source)) {
    return (
      <div className="p-8 text-muted-foreground">
        Fonte desconhecida: {params.source}
      </div>
    )
  }
  return <SourceConfigPage source={params.source} />
}

export function generateStaticParams() {
  return VALID_SOURCES.map((source) => ({ source }))
}
