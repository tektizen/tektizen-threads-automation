import type { ContentItem, ContentStatus, MetricKey, PerformanceSnapshot } from './types'
import { FORMATS } from './config'

const MYT = 'Asia/Kuala_Lumpur'

export function fmtDateTime(iso?: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-MY', { timeZone: MYT, dateStyle: 'medium', timeStyle: 'short' })
}

export function fmtDate(iso?: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-MY', { timeZone: MYT, day: 'numeric', month: 'short' })
}

export function dayKey(iso: string) {
  // YYYY-MM-DD in Malaysia time
  return new Date(iso).toLocaleDateString('en-CA', { timeZone: MYT })
}

export function timeAgo(iso?: string | null) {
  if (!iso) return '—'
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  const m = Math.round(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.round(m / 60)
  if (h < 48) return `${h}h ago`
  return `${Math.round(h / 24)}d ago`
}

export function fmtDuration(ms?: number | null) {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms} ms`
  const s = ms / 1000
  return s < 60 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
}

export function fmtNumber(n?: number | null) {
  if (n == null) return '—'
  return new Intl.NumberFormat('en-MY', { notation: n >= 10000 ? 'compact' : 'standard' }).format(n)
}

export const formatLabel = (id: string) => FORMATS.find((f) => f.id === id)?.label ?? id
export const humanize = (s: string) => s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

export const STATUS_LABEL: Record<ContentStatus, string> = {
  DRAFT: 'Draft', IDEA: 'Idea', RESEARCH: 'Research', GENERATION: 'Generation', EVALUATION: 'Evaluation',
  REFINEMENT: 'Refinement', PENDING_APPROVAL: 'Pending approval', READY_TO_PUBLISH: 'Ready to publish',
  PUBLISHING: 'Publishing', PUBLISHED: 'Published', PUBLISH_UNCERTAIN: 'Needs reconciling',
  REJECTED: 'Rejected', FAILED: 'Failed', ARCHIVED: 'Archived',
}

export type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger'

export const STATUS_TONE: Record<ContentStatus, Tone> = {
  DRAFT: 'neutral', IDEA: 'neutral', RESEARCH: 'info', GENERATION: 'info', EVALUATION: 'info',
  REFINEMENT: 'info', PENDING_APPROVAL: 'warning', READY_TO_PUBLISH: 'info', PUBLISHING: 'info',
  PUBLISHED: 'success', PUBLISH_UNCERTAIN: 'danger', REJECTED: 'danger', FAILED: 'danger', ARCHIVED: 'neutral',
}

export function latestMetrics(perf: PerformanceSnapshot[]) {
  const latest = new Map<string, PerformanceSnapshot>()
  for (const s of perf) {
    const cur = latest.get(s.content_id)
    if (!cur || s.collected_at > cur.collected_at) latest.set(s.content_id, s)
  }
  return latest
}

export function engagement(m: PerformanceSnapshot['metrics']): number | null {
  const parts: (keyof typeof m)[] = ['likes', 'replies', 'reposts', 'quotes', 'shares']
  const known = parts.map((k) => m[k]).filter((v): v is number => typeof v === 'number')
  return known.length ? known.reduce((a, b) => a + b, 0) : null
}

export const METRIC_LABEL: Record<MetricKey, string> = {
  views: 'Views', likes: 'Likes', replies: 'Replies', reposts: 'Reposts', quotes: 'Quotes',
  shares: 'Shares', impressions: 'Impressions',
}

export const isLive = (c: ContentItem) => c.status !== 'ARCHIVED'
