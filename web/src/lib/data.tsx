import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { DEMO_MODE, REPO } from './config'
import { getToken, latestSha, readFile } from './github'
import type { Collection, LearningMemory, RepoData, Settings } from './types'

const FILES = {
  settings: 'data/settings.json',
  content: 'data/content.json',
  ideas: 'data/ideas.json',
  approvals: 'data/approvals.json',
  publishing: 'data/publishing_history.json',
  performance: 'data/performance.json',
  memory: 'data/learning_memory.json',
  runs: 'data/automation_runs.json',
  agents: 'data/agent_metrics.json',
} as const

interface DataState {
  data: RepoData | null
  sha: string | null
  loading: boolean
  error: string | null
  fileErrors: Record<string, string>
  lastLoaded: Date | null
  demo: boolean
  refresh: () => Promise<void>
  readText: (path: string) => Promise<string>
}

const DataContext = createContext<DataState | null>(null)

function emptyMemory(): LearningMemory {
  return { schema_version: 1, updated_at: null, categories: {}, history: [] }
}

async function loadJson<T>(path: string, ref: string, fallback: T, errors: Record<string, string>): Promise<T> {
  try {
    return JSON.parse(await readFile(path, ref)) as T
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e)
    // A missing file is normal on a fresh install; anything else is surfaced.
    if (!message.includes('not found')) errors[path] = message
    return fallback
  }
}

async function loadAll(ref: string): Promise<{ data: RepoData; errors: Record<string, string> }> {
  const errors: Record<string, string> = {}
  const col = <T,>(path: string) => loadJson<Collection<T>>(path, ref, { schema_version: 1, updated_at: null, items: [] }, errors)
  const [settings, content, ideas, approvals, publishing, performance, memory, runs, agents] = await Promise.all([
    loadJson<Settings | null>(FILES.settings, ref, null, errors),
    col<RepoData['content'][number]>(FILES.content),
    col<RepoData['ideas'][number]>(FILES.ideas),
    col<RepoData['approvals'][number]>(FILES.approvals),
    col<RepoData['publishing'][number]>(FILES.publishing),
    col<RepoData['performance'][number]>(FILES.performance),
    loadJson<LearningMemory>(FILES.memory, ref, emptyMemory(), errors),
    col<RepoData['runs'][number]>(FILES.runs),
    loadJson<{ agents: RepoData['agents'] }>(FILES.agents, ref, { agents: {} }, errors),
  ])
  if (!settings) throw new Error('data/settings.json could not be loaded. Run "python -m tektizen init" and push.')
  return {
    data: {
      settings, content: content.items, ideas: ideas.items, approvals: approvals.items,
      publishing: publishing.items, performance: performance.items, memory, runs: runs.items, agents: agents.agents,
    },
    errors,
  }
}

export function DataProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<RepoData | null>(null)
  const [sha, setSha] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [fileErrors, setFileErrors] = useState<Record<string, string>>({})
  const [lastLoaded, setLastLoaded] = useState<Date | null>(null)
  const shaRef = useRef<string | null>(null)

  const load = useCallback(async (force: boolean) => {
    if (DEMO_MODE) {
      const { demoData } = await import('../demo/demoData')
      setData(demoData)
      setSha('demo')
      setLoading(false)
      setLastLoaded(new Date())
      return
    }
    try {
      let ref: string
      try {
        ref = await latestSha()
      } catch {
        ref = REPO.branch // rate-limited: fall back to the (CDN-cached) branch
      }
      if (!force && ref === shaRef.current) return
      const result = await loadAll(ref)
      shaRef.current = ref
      setSha(ref)
      setData(result.data)
      setFileErrors(result.errors)
      setError(null)
      setLastLoaded(new Date())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load(true)
    // Unauthenticated GitHub API allows 60 requests/hour; poll gently without a token.
    const interval = window.setInterval(() => load(false), getToken() ? 30_000 : 120_000)
    return () => window.clearInterval(interval)
  }, [load])

  const readText = useCallback(async (path: string) => {
    if (DEMO_MODE) {
      const { demoMarkdown } = await import('../demo/demoData')
      return demoMarkdown(path)
    }
    return readFile(path, shaRef.current || REPO.branch)
  }, [])

  const value = useMemo<DataState>(() => ({
    data, sha, loading, error, fileErrors, lastLoaded, demo: DEMO_MODE,
    refresh: () => load(true), readText,
  }), [data, sha, loading, error, fileErrors, lastLoaded, load, readText])

  return <DataContext.Provider value={value}>{children}</DataContext.Provider>
}

export function useData() {
  const ctx = useContext(DataContext)
  if (!ctx) throw new Error('useData must be used inside DataProvider')
  return ctx
}

/** Repository data, or null while loading. Pages render their own skeleton/empty states. */
export function useRepo(): RepoData | null {
  return useData().data
}
