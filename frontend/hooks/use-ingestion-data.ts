"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { api, ingestionApi } from "@/lib/api"
import type {
  CtBulkChunk,
  CtBulkJob,
  CzdsPolicyItem,
  CzdsPolicyResponse,
  IngestionCycleStatus,
  IngestionRun,
  SourceSummary,
  TldCoverage,
  TldDomainCount,
  TriggerSyncResponse,
} from "@/lib/types"

export interface IngestionData {
  // Data
  runs: IngestionRun[]
  allRuns: IngestionRun[]
  summaries: SourceSummary[]
  coverage: TldCoverage[]
  domainCounts: TldDomainCount[]
  policyItems: CzdsPolicyItem[]
  policySource: "database" | "env"
  policyTlds: string[]
  bulkJobs: CtBulkJob[]
  bulkChunks: CtBulkChunk[]
  cycleStatus: IngestionCycleStatus | null
  loading: boolean

  // Filters
  activeSource: string
  setActiveSource: (source: string) => void
  selectedBulkJobId: string
  setSelectedBulkJobId: (id: string) => void

  // Actions
  fetchData: () => Promise<void>
  triggerSync: (tld: string, force: boolean) => Promise<void>
  savePolicy: (tlds: string[]) => Promise<void>
  patchPolicy: (tld: string, fields: { is_enabled?: boolean; priority?: number; cooldown_hours?: number }) => Promise<void>
  startBulkJob: (tlds: string[], dryRun: boolean) => Promise<void>
  resumeBulkJob: (jobId: string) => Promise<void>
  cancelBulkJob: (jobId: string) => Promise<void>

  // Action states
  syncing: boolean
  policySaving: boolean
  bulkBusy: boolean
  syncError: string
  policyError: string
  bulkError: string
}

export function useIngestionData(): IngestionData {
  const [runs, setRuns] = useState<IngestionRun[]>([])
  const [allRuns, setAllRuns] = useState<IngestionRun[]>([])
  const [summaries, setSummaries] = useState<SourceSummary[]>([])
  const [coverage, setCoverage] = useState<TldCoverage[]>([])
  const [domainCounts, setDomainCounts] = useState<TldDomainCount[]>([])
  const [policyItems, setPolicyItems] = useState<CzdsPolicyItem[]>([])
  const [policySource, setPolicySource] = useState<"database" | "env">("env")
  const [policyTlds, setPolicyTlds] = useState<string[]>([])
  const [bulkJobs, setBulkJobs] = useState<CtBulkJob[]>([])
  const [bulkChunks, setBulkChunks] = useState<CtBulkChunk[]>([])
  const [cycleStatus, setCycleStatus] = useState<IngestionCycleStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeSource, setActiveSource] = useState("all")
  const [selectedBulkJobId, setSelectedBulkJobId] = useState("")

  const [syncing, setSyncing] = useState(false)
  const [policySaving, setPolicySaving] = useState(false)
  const [bulkBusy, setBulkBusy] = useState(false)
  const [syncError, setSyncError] = useState("")
  const [policyError, setPolicyError] = useState("")
  const [bulkError, setBulkError] = useState("")

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchData = useCallback(async () => {
    try {
      const sourceParam = activeSource === "all" ? "" : `&source=${activeSource}`
      const emptyCzdsPolicy: CzdsPolicyResponse = { source: "env", tlds: [], items: [] }
      const [runsData, allRunsData, summaryData, policyData, coverageData, countsData, cycleData] =
        await Promise.all([
          api.get<IngestionRun[]>(`/v1/ingestion/runs?limit=50${sourceParam}`),
          api.get<IngestionRun[]>("/v1/ingestion/runs?limit=200"),
          api.get<SourceSummary[]>("/v1/ingestion/summary"),
          api.get<CzdsPolicyResponse>("/v1/czds/policy").catch(() => emptyCzdsPolicy),
          ingestionApi.getCoverage().catch(() => [] as TldCoverage[]),
          api.get<TldDomainCount[]>("/v1/ingestion/domain-counts").catch(() => [] as TldDomainCount[]),
          ingestionApi.getCycleStatus().catch(() => null),
        ])
      setRuns(runsData)
      setAllRuns(allRunsData)
      setSummaries(summaryData)
      setPolicyItems(policyData.items)
      setPolicyTlds(policyData.tlds)
      setPolicySource(policyData.source)
      setCoverage(coverageData)
      setBulkJobs([])
      setBulkChunks([])
      setDomainCounts(countsData)
      setCycleStatus(cycleData)
    } catch {
      // ignore
    }
  }, [activeSource])

  useEffect(() => {
    setLoading(true)
    fetchData().then(() => setLoading(false))
  }, [fetchData])

  // Auto-refresh polling
  useEffect(() => {
    const hasActiveRuns = runs.some((r) => r.status === "running" || r.status === "queued")
    const hasActiveBulk = bulkJobs.some((job) =>
      ["pending", "running", "cancel_requested"].includes(job.status),
    )
    const hasActive = hasActiveRuns || hasActiveBulk
    if (hasActive && !pollRef.current) {
      pollRef.current = setInterval(fetchData, 10_000)
    } else if (!hasActive && pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [bulkJobs, fetchData, runs])

  const triggerSync = useCallback(async (tld: string, force: boolean) => {
    setSyncing(true)
    setSyncError("")
    try {
      await api.post<TriggerSyncResponse>("/v1/czds/trigger-sync", { tld, force })
      await fetchData()
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : "Sync failed")
      throw err
    } finally {
      setSyncing(false)
    }
  }, [fetchData])

  const savePolicy = useCallback(async (tlds: string[]) => {
    setPolicySaving(true)
    setPolicyError("")
    try {
      const response = await api.put<CzdsPolicyResponse>("/v1/czds/policy", { tlds })
      setPolicyItems(response.items)
      setPolicyTlds(response.tlds)
      setPolicySource(response.source)
    } catch (err) {
      setPolicyError(err instanceof Error ? err.message : "Failed to save policy")
      throw err
    } finally {
      setPolicySaving(false)
    }
  }, [])

  const patchPolicy = useCallback(async (tld: string, fields: { is_enabled?: boolean; priority?: number; cooldown_hours?: number }) => {
    try {
      await ingestionApi.patchPolicy(tld, fields)
      await fetchData()
    } catch (err) {
      setPolicyError(err instanceof Error ? err.message : "Failed to update policy")
      throw err
    }
  }, [fetchData])

  const startBulkJob = useCallback(async (tlds: string[], dryRun: boolean) => {
    setBulkBusy(true)
    setBulkError("")
    try {
      const job = await ingestionApi.startBulkJob({ tlds, dry_run: dryRun })
      setSelectedBulkJobId(job.job_id)
      await fetchData()
    } catch (err) {
      setBulkError(err instanceof Error ? err.message : "Failed to start bulk job")
      throw err
    } finally {
      setBulkBusy(false)
    }
  }, [fetchData])

  const resumeBulkJob = useCallback(async (jobId: string) => {
    setBulkBusy(true)
    setBulkError("")
    try {
      await ingestionApi.resumeBulkJob(jobId)
      setSelectedBulkJobId(jobId)
      await fetchData()
    } catch (err) {
      setBulkError(err instanceof Error ? err.message : "Failed to resume bulk job")
      throw err
    } finally {
      setBulkBusy(false)
    }
  }, [fetchData])

  const cancelBulkJob = useCallback(async (jobId: string) => {
    setBulkBusy(true)
    setBulkError("")
    try {
      await ingestionApi.cancelBulkJob(jobId)
      await fetchData()
    } catch (err) {
      setBulkError(err instanceof Error ? err.message : "Failed to cancel bulk job")
      throw err
    } finally {
      setBulkBusy(false)
    }
  }, [fetchData])

  return {
    runs, allRuns, summaries, coverage, domainCounts,
    policyItems, policySource, policyTlds,
    bulkJobs, bulkChunks, cycleStatus, loading,
    activeSource, setActiveSource,
    selectedBulkJobId, setSelectedBulkJobId,
    fetchData, triggerSync, savePolicy, patchPolicy,
    startBulkJob, resumeBulkJob, cancelBulkJob,
    syncing, policySaving, bulkBusy,
    syncError, policyError, bulkError,
  }
}
