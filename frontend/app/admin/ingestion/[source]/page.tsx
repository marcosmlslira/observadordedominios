import { SourceConfigPage } from "@/components/ingestion/source-config-page"

const VALID_SOURCES = ["czds", "openintel"]

interface Props {
  params: Promise<{ source: string }>
}

export default async function IngestionSourcePage({ params }: Props) {
  const { source } = await params
  if (!VALID_SOURCES.includes(source)) {
    return (
      <div className="p-8 text-muted-foreground">
        Fonte desconhecida: {source}
      </div>
    )
  }
  return <SourceConfigPage source={source} />
}

export function generateStaticParams() {
  return VALID_SOURCES.map((source) => ({ source }))
}
