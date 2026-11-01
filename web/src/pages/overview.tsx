import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { CheckSquare, FileText, Percent, Send, XCircle } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { EmptyState, LoadingPage, PageHeader, Pill, StatCard, StatusBadge } from '@/components/common'
import { AXIS, BAR_RADIUS, ChartCard, ChartTooltip, GRID, HBAR_RADIUS, SERIES } from '@/components/charts'
import { useRepo } from '@/lib/data'
import { AGENTS } from '@/lib/config'
import { dayKey, engagement, fmtDate, fmtDuration, formatLabel, humanize, latestMetrics, timeAgo } from '@/lib/format'
import { cn } from '@/lib/utils'

const DAYS = 30

function lastDays(n: number) {
  const out: string[] = []
  for (let i = n - 1; i >= 0; i--) out.push(dayKey(new Date(Date.now() - i * 86400000).toISOString()))
  return out
}

export default function Overview() {
  const repo = useRepo()
  const view = useMemo(() => {
    if (!repo) return null
    const content = repo.content
    const days = lastDays(DAYS)
    const generatedByDay = new Map(days.map((d) => [d, 0]))
    const publishedByDay = new Map(days.map((d) => [d, 0]))
    for (const c of content) {
      const d = dayKey(c.created_at)
      if (generatedByDay.has(d) && c.origin !== 'studio') generatedByDay.set(d, generatedByDay.get(d)! + 1)
      const p = c.publishing?.published_at
      if (c.status === 'PUBLISHED' && p && publishedByDay.has(dayKey(p))) publishedByDay.set(dayKey(p), publishedByDay.get(dayKey(p))! + 1)
    }
    const activity = days.map((d) => ({ day: fmtDate(d + 'T12:00:00Z'), generated: generatedByDay.get(d)!, published: publishedByDay.get(d)! }))

    const formats = new Map<string, number>()
    for (const c of content) if (c.status !== 'ARCHIVED') formats.set(c.format, (formats.get(c.format) ?? 0) + 1)
    const formatData = [...formats].map(([k, v]) => ({ format: formatLabel(k), count: v })).sort((a, b) => b.count - a.count)

    const metrics = latestMetrics(repo.performance)
    const byId = new Map(content.map((c) => [c.id, c]))
    const perf = [...metrics.values()].map((s) => ({ snap: s, item: byId.get(s.content_id) })).filter((x) => x.item)
    const engagementSeries = perf
      .filter((x) => x.snap.published_at)
      .sort((a, b) => a.snap.published_at!.localeCompare(b.snap.published_at!))
      .map((x) => ({ label: fmtDate(x.snap.published_at), engagement: engagement(x.snap.metrics) }))
    const topicAgg = new Map<string, { sum: number; n: number }>()
    for (const x of perf) {
      const e = engagement(x.snap.metrics)
      if (e == null) continue
      const a = topicAgg.get(x.item!.topic) ?? { sum: 0, n: 0 }
      topicAgg.set(x.item!.topic, { sum: a.sum + e, n: a.n + 1 })
    }
    const topicData = [...topicAgg].map(([t, a]) => ({ topic: t.length > 28 ? t.slice(0, 27) + '…' : t, avg: Math.round(a.sum / a.n), n: a.n }))
      .sort((a, b) => b.avg - a.avg).slice(0, 6)
    const hookData = perf.map((x) => ({ hook: x.item!.draft?.hook ?? '', e: engagement(x.snap.metrics) }))
      .filter((h) => h.e != null && h.hook).sort((a, b) => b.e! - a.e!).slice(0, 5)

    const decided = repo.approvals.filter((a) => a.status === 'applied' && ['approve', 'edit_approve', 'reject'].includes(a.action))
    const approved = decided.filter((a) => a.action !== 'reject').length
    return {
      total: content.filter((c) => c.origin !== 'studio' || c.status !== 'DRAFT').length,
      published: content.filter((c) => c.status === 'PUBLISHED').length,
      pending: content.filter((c) => c.status === 'PENDING_APPROVAL').length,
      rejected: content.filter((c) => c.status === 'REJECTED').length,
      approvalRate: decided.length ? Math.round((approved / decided.length) * 100) : null,
      decided: decided.length,
      activity, formatData, engagementSeries, topicData, hookData,
      hasActivity: activity.some((a) => a.generated || a.published),
      recentRuns: [...repo.runs].sort((a, b) => b.started_at.localeCompare(a.started_at)).slice(0, 5),
      recentPublished: content.filter((c) => c.status === 'PUBLISHED')
        .sort((a, b) => (b.publishing?.published_at ?? '').localeCompare(a.publishing?.published_at ?? '')).slice(0, 4),
      insights: Object.entries(repo.memory.categories).flatMap(([cat, items]) => items.map((i) => ({ ...i, cat })))
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 5),
    }
  }, [repo])

  if (!repo || !view) return <LoadingPage />
  const s = repo.settings

  return (
    <>
      <PageHeader title="Overview" description="Content production, approvals, publishing, and what the system has learned so far." />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard label="Content generated" value={view.total} icon={FileText} />
        <StatCard label="Published" value={view.published} icon={Send} />
        <StatCard label="Pending approval" value={view.pending} icon={CheckSquare}
          hint={view.pending ? <Link to="/approvals" className="text-primary hover:underline">Review now →</Link> : 'Inbox clear'} />
        <StatCard label="Rejected" value={view.rejected} icon={XCircle} />
        <StatCard label="Approval rate" value={view.approvalRate == null ? '—' : `${view.approvalRate}%`} icon={Percent}
          hint={view.decided ? `approved ÷ decided (${view.decided} decisions)` : 'No decisions yet'} />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="gap-3 lg:col-span-1">
          <CardHeader><CardTitle className="text-sm font-medium">Configuration</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row label="Approval mode">
              <Pill tone={s.approval.mode === 'auto_publish' ? 'warning' : 'success'}>
                {s.approval.mode === 'auto_publish' ? 'Automatic publishing' : 'Human approval'}
              </Pill>
            </Row>
            <Row label="Publishing">
              <Pill tone={s.publishing.kill_switch ? 'danger' : 'success'}>{s.publishing.kill_switch ? 'Kill switch ON' : 'Enabled'}</Pill>
            </Row>
            <Row label="Threads account">@{s.publishing.threads_username}</Row>
            <Row label="Max posts / run">{s.publishing.max_posts_per_run}</Row>
            <Row label="Daily items">{s.generation.items_per_daily_run}</Row>
            <Row label="Model">{s.ai.model}</Row>
            <Row label="Quality gates">{s.quality.min_overall} / {s.quality.min_factuality} / {s.quality.min_brand}</Row>
          </CardContent>
        </Card>

        <Card className="gap-3 lg:col-span-2">
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="text-sm font-medium">Recent automation runs</CardTitle>
            <Link to="/runs" className="text-xs text-primary hover:underline">All runs</Link>
          </CardHeader>
          <CardContent>
            {view.recentRuns.length === 0 ? <EmptyState title="No runs yet">Runs appear after the first workflow executes.</EmptyState> : (
              <ul className="divide-y text-sm">
                {view.recentRuns.map((r) => (
                  <li key={r.id} className="flex items-center gap-3 py-2">
                    <Pill tone={r.status === 'success' ? 'success' : r.status === 'failed' ? 'danger' : 'warning'}>{r.status}</Pill>
                    <span className="truncate">{r.workflow}</span>
                    <span className="ml-auto shrink-0 text-xs text-muted-foreground">{r.ai_requests ?? 0} AI · {fmtDuration(r.duration_ms)} · {timeAgo(r.started_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <h2 className="mt-8 mb-3 text-sm font-medium text-muted-foreground">Production (last {DAYS} days)</h2>
      <div className="grid gap-4 lg:grid-cols-3">
        <ChartCard title="Content generated" description="Automated and manual generations per day" empty={!view.hasActivity}
          emptyText="Charts fill in after the daily workflow has run.">
          <ResponsiveContainer>
            <BarChart data={view.activity} barCategoryGap={2}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="day" {...AXIS} interval={6} />
              <YAxis {...AXIS} allowDecimals={false} width={24} />
              <Tooltip cursor={{ fill: 'var(--accent)' }} content={<ChartTooltip />} />
              <Bar isAnimationActive={false} dataKey="generated" name="Generated" fill={SERIES[0]} radius={BAR_RADIUS} maxBarSize={18} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Publishing activity" description="Posts published to Threads per day" empty={!view.hasActivity}
          emptyText="Nothing published yet.">
          <ResponsiveContainer>
            <BarChart data={view.activity} barCategoryGap={2}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="day" {...AXIS} interval={6} />
              <YAxis {...AXIS} allowDecimals={false} width={24} />
              <Tooltip cursor={{ fill: 'var(--accent)' }} content={<ChartTooltip />} />
              <Bar isAnimationActive={false} dataKey="published" name="Published" fill={SERIES[0]} radius={BAR_RADIUS} maxBarSize={18} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Format distribution" description="All non-archived content" empty={view.formatData.length === 0}>
          <ResponsiveContainer>
            <BarChart data={view.formatData} layout="vertical" margin={{ left: 8 }}>
              <XAxis type="number" {...AXIS} allowDecimals={false} hide />
              <YAxis type="category" dataKey="format" {...AXIS} width={120} />
              <Tooltip cursor={{ fill: 'var(--accent)' }} content={<ChartTooltip />} />
              <Bar isAnimationActive={false} dataKey="count" name="Items" fill={SERIES[0]} radius={HBAR_RADIUS} maxBarSize={16}
                label={{ position: 'right', fill: 'var(--muted-foreground)', fontSize: 11 }} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <h2 className="mt-8 mb-3 text-sm font-medium text-muted-foreground">Performance (latest Zernio metrics)</h2>
      <div className="grid gap-4 lg:grid-cols-3">
        <ChartCard title="Engagement per post" description="Engagement = likes + replies + reposts + shares, where reported"
          empty={view.engagementSeries.length === 0} emptyText="Metrics appear after posts are published and the performance workflow runs."
          footer="Views are on the Performance Analytics page (different scale).">
          <ResponsiveContainer>
            <LineChart data={view.engagementSeries}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="label" {...AXIS} />
              <YAxis {...AXIS} width={36} allowDecimals={false} />
              <Tooltip content={<ChartTooltip formatter={(v) => (v == null ? 'n/a' : String(v))} />} />
              <Line isAnimationActive={false} dataKey="engagement" name="Engagement" stroke={SERIES[0]} strokeWidth={2} dot={{ r: 4 }} connectNulls={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Topic performance" description="Average engagement per topic" empty={view.topicData.length === 0}
          emptyText="Needs published posts with metrics.">
          <ResponsiveContainer>
            <BarChart data={view.topicData} layout="vertical" margin={{ left: 8 }}>
              <XAxis type="number" {...AXIS} hide />
              <YAxis type="category" dataKey="topic" {...AXIS} width={150} />
              <Tooltip cursor={{ fill: 'var(--accent)' }} content={<ChartTooltip />} />
              <Bar isAnimationActive={false} dataKey="avg" name="Avg engagement" fill={SERIES[0]} radius={HBAR_RADIUS} maxBarSize={16} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <Card className="gap-3">
          <CardHeader><CardTitle className="text-sm font-medium">Hook performance</CardTitle></CardHeader>
          <CardContent>
            {view.hookData.length === 0 ? <EmptyState title="No data yet">Needs published posts with metrics.</EmptyState> : (
              <ol className="space-y-2 text-sm">
                {view.hookData.map((h, i) => (
                  <li key={i} className="flex gap-3">
                    <span className="w-10 shrink-0 text-right font-medium tabular-nums">{h.e}</span>
                    <span className="line-clamp-2 text-muted-foreground">{h.hook}</span>
                  </li>
                ))}
              </ol>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="mt-8 grid gap-4 lg:grid-cols-3">
        <Card className="gap-3">
          <CardHeader><CardTitle className="text-sm font-medium">AI agents</CardTitle></CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              {AGENTS.map((a) => {
                const st = repo.agents[a.id]
                return (
                  <li key={a.id} className="flex items-center gap-2">
                    <span className={cn('size-2 rounded-full', !st ? 'bg-muted-foreground/40' : st.last_status === 'failed' ? 'bg-destructive' : 'bg-success')} />
                    <span>{a.name}</span>
                    <span className="ml-auto text-xs text-muted-foreground">{st ? `${st.successes}/${st.executions} ok · ${timeAgo(st.last_execution_at)}` : 'not run yet'}</span>
                  </li>
                )
              })}
            </ul>
          </CardContent>
        </Card>
        <Card className="gap-3">
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="text-sm font-medium">Recently published</CardTitle>
            <Link to="/publishing" className="text-xs text-primary hover:underline">History</Link>
          </CardHeader>
          <CardContent>
            {view.recentPublished.length === 0 ? <EmptyState title="Nothing published yet" /> : (
              <ul className="space-y-3 text-sm">
                {view.recentPublished.map((c) => (
                  <li key={c.id}>
                    <div className="line-clamp-2">{c.draft?.hook}</div>
                    <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                      <StatusBadge status={c.status} /> {timeAgo(c.publishing?.published_at)}
                      {c.publishing?.url && <a className="text-primary hover:underline" href={c.publishing.url} target="_blank" rel="noreferrer">open</a>}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        <Card className="gap-3">
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="text-sm font-medium">Latest learning insights</CardTitle>
            <Link to="/memory" className="text-xs text-primary hover:underline">Memory</Link>
          </CardHeader>
          <CardContent>
            {view.insights.length === 0 ? <EmptyState title="No insights yet">The Learning Analyst adds insights after approvals, rejections, and metrics.</EmptyState> : (
              <ul className="space-y-3 text-sm">
                {view.insights.map((i) => (
                  <li key={i.id}>
                    <div>{i.text}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">{humanize(i.cat)} · {i.confidence} confidence · {timeAgo(i.updated_at)}</div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="flex items-center justify-between gap-3"><span className="text-muted-foreground">{label}</span><span className="truncate text-right">{children}</span></div>
}
