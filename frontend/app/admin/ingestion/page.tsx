"use client"

import { useState } from "react"
import { useIngestionData } from "@/hooks/use-ingestion-data"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { RefreshCw } from "lucide-react"

import { IngestionRunGrid } from "@/components/ingestion-run-grid"
import { CycleProgress } from "@/components/ingestion/cycle-progress"
import { HealthSummaryCards } from "@/components/ingestion/health-summary"
import { SourceHealthCards } from "@/components/ingestion/source-health-cards"
import { TldPolicyTable } from "@/components/ingestion/tld-policy-table"
import { RunsTable } from "@/components/ingestion/runs-table"
import { TldCoverageTable } from "@/components/ingestion/tld-coverage-table"
import { BulkCrtshPanel } from "@/components/ingestion/bulk-crtsh-panel"
import { TriggerSyncDialog } from "@/components/ingestion/trigger-sync-dialog"

export default function IngestionPage() {
  const data = useIngestionData()
  const [syncDialogTld, setSyncDialogTld] = useState("net")

  if (data.loading) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold">Ingestion Monitoring</h1>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-96 rounded-xl" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Ingestion Monitoring</h1>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={data.fetchData}>
            <RefreshCw className="h-3 w-3 mr-1" />
            Refresh
          </Button>
          <TriggerSyncDialog
            onTrigger={data.triggerSync}
            syncing={data.syncing}
            syncError={data.syncError}
            defaultTld={syncDialogTld}
          />
        </div>
      </div>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Visao Geral</TabsTrigger>
          <TabsTrigger value="runs">Execucoes</TabsTrigger>
          <TabsTrigger value="coverage">Cobertura por TLD</TabsTrigger>
          <TabsTrigger value="bulk">Bulk crt.sh</TabsTrigger>
        </TabsList>

        {/* Tab 1: Visao Geral */}
        <TabsContent value="overview" className="space-y-4 mt-4">
          <CycleProgress cycleStatus={data.cycleStatus} />

          <HealthSummaryCards
            health={data.cycleStatus?.health ?? null}
            domainCounts={data.domainCounts}
          />

          <SourceHealthCards
            summaries={data.summaries}
            activeSource={data.activeSource}
            onSourceClick={data.setActiveSource}
          />

          <Card className="border-border-subtle bg-background/70">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Run History</CardTitle>
              <p className="text-sm text-muted-foreground">
                Last 30 executions per source. Hover a cell for details.
              </p>
            </CardHeader>
            <CardContent>
              <IngestionRunGrid runs={data.allRuns} />
            </CardContent>
          </Card>

          <Card className="border-border-subtle bg-background/70">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">CZDS TLD Policy</CardTitle>
              <p className="text-sm text-muted-foreground">
                Toggle, priorize e configure cada TLD individualmente.
              </p>
            </CardHeader>
            <CardContent>
              <TldPolicyTable
                items={data.policyItems}
                domainCounts={data.domainCounts}
                onPatch={data.patchPolicy}
                onTriggerSync={(tld) => { setSyncDialogTld(tld) }}
              />
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 2: Execucoes */}
        <TabsContent value="runs" className="space-y-4 mt-4">
          <RunsTable
            runs={data.runs}
            activeSource={data.activeSource}
            onSourceChange={data.setActiveSource}
          />
        </TabsContent>

        {/* Tab 3: Cobertura por TLD */}
        <TabsContent value="coverage" className="mt-4">
          <TldCoverageTable
            coverage={data.coverage}
            domainCounts={data.domainCounts}
          />
        </TabsContent>

        {/* Tab 4: Bulk crt.sh */}
        <TabsContent value="bulk" className="mt-4">
          <BulkCrtshPanel
            bulkJobs={data.bulkJobs}
            bulkChunks={data.bulkChunks}
            selectedBulkJobId={data.selectedBulkJobId}
            onSelectJob={data.setSelectedBulkJobId}
            onStartJob={data.startBulkJob}
            onResumeJob={data.resumeBulkJob}
            onCancelJob={data.cancelBulkJob}
            busy={data.bulkBusy}
            error={data.bulkError}
          />
        </TabsContent>
      </Tabs>
    </div>
  )
}
