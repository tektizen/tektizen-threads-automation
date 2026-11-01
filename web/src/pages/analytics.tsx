import { useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { BarChart3 } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { EmptyState, LoadingPage, PageHeader } from '@/components/common'
import { AXIS, BAR_RADIUS, ChartCard, ChartTooltip, GRID, HBAR_RADIUS, SERIES } from '@/components/charts'
import { ContentDetailSheet } from '@/components/content-detail'
import { useRepo } from '@/lib/data'
import { engagement, fmtDate, fmtNumber, formatLabel, latestMetrics, METRIC_LABEL } from '@/lib/format'
import type { MetricKey } from '@/lib/types'

type Measure = MetricKey | 'engagement'
const MEASURES: Measure[] = ['views', 'likes', 'replies', 'shares', 'reposts', 'quotes', 'engagement']
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MIN_GROUP = 1

function label(m: Measure) {
  return m === 'engagement' ? 'Engagement' : METRIC_LABEL[m]
}

export default function Analytics() {
  const repo = useRepo()
  const [measure, setMeasure] = useState<Measure>('views')
  const [selected, setSelected] = useState<string | null>(null)

  const rows = useMemo(() => {
    if (!repo) return []
    const byId = new Map(repo.content.map((c) => [c.id, c]))
    return [...latestMetrics(repo.performance).values()]
      .map((s) => ({ snap: s, item: byId.get(s.content_id)! }))
      .filter((r) => r.item)
      .sort((a, b) => (b.snap.published_at ?? '').localeCompare(a.snap.published_at ?? ''))
  }, [repo])

  const value = (r: (typeof rows)[number]) => (measure === 'engagement' ? engagement(r.snap.metrics) : r.snap.metrics[measure] ?? null)
  const known = rows.filter((r) => value(r) != null)

  const group = (key: (r: (typeof rows)[number]) => string) => {
    const agg = new Map<string, { sum: number; n: number }>()
    for (const r of known) {
      const k = key(r)
      const a = agg.get(k) ?? { sum: 0, n: 0 }
      agg.set(k, { sum: a.sum + value(r)!, n: a.n + 1 })
    }
    return [...agg].filter(([, a]) => a.n >= MIN_GROUP)
      .map(([k, a]) => ({ key: k.length > 30 ? k.slice(0, 29) + '…' : k, avg: Math.round(a.sum / a.n), n: a.n }))
      .sort((a, b) => b.avg - a.avg)
  }

  if (!repo) return <LoadingPage />
  const trend = [...known].reverse().map((r) => ({ label: fmtDate(r.snap.published_at), value: value(r) }))
  const byKind = group((r) => (r.item.format === 'thread' ? 'Thread' : 'Single post'))
  const byFormat = group((r) => formatLabel(r.item.format))
  const byTopic = group((r) => r.item.topic).slice(0, 8)
  const byDay = group((r) => WEEKDAYS[new Date(r.snap.published_at ?? r.snap.collected_at).getDay()])
  const unavailable = rows.length - known.length
  const tip = <Tooltip cursor={{ fill: 'var(--accent)' }} content={<ChartTooltip formatter={(v) => (v == null ? 'n/a' : fmtNumber(Number(v)))} />} />

  return (
    <>
      <PageHeader title="Performance Analytics"
        description="Latest metrics per published post, from Zernio. “n/a” means the metric is not available on Threads or your plan. It is not the same as 0."
        actions={
          <Select value={measure} onValueChange={(v) => setMeasure(v as Measure)}>
            <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
            <SelectContent>{MEASURES.map((m) => <SelectItem key={m} value={m}>{label(m)}</SelectItem>)}</SelectContent>
          </Select>
        } />

      {rows.length === 0 ? (
        <EmptyState icon={BarChart3} title="No performance data yet">
          Metrics are collected daily by the Performance Analysis workflow for posts published in the last 30 days.
          If your Zernio plan lacks the Analytics add-on, the run log says so.
        </EmptyState>
      ) : (
        <>
          {unavailable > 0 && (
            <p className="mb-4 text-sm text-muted-foreground">{label(measure)} is unavailable for {unavailable} of {rows.length} posts. They are left out of the charts below, not counted as zero.</p>
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard title={`${label(measure)} per post over time`} empty={trend.length === 0} emptyText={`${label(measure)} is not reported for any post.`}>
              <ResponsiveContainer>
                <LineChart data={trend}>
                  <CartesianGrid {...GRID} />
                  <XAxis dataKey="label" {...AXIS} />
                  <YAxis {...AXIS} width={40} />
                  <Tooltip content={<ChartTooltip />} />
                  <Line isAnimationActive={false} dataKey="value" name={label(measure)} stroke={SERIES[0]} strokeWidth={2} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>
            <ChartCard title="Single posts vs threads" description={`Average ${label(measure).toLowerCase()}`} empty={byKind.length === 0}
              footer={byKind.map((g) => `${g.key}: ${g.n} post${g.n > 1 ? 's' : ''}`).join(' · ')}>
              <ResponsiveContainer>
                <BarChart data={byKind}>
                  <CartesianGrid {...GRID} />
                  <XAxis dataKey="key" {...AXIS} />
                  <YAxis {...AXIS} width={40} />
                  {tip}
                  <Bar isAnimationActive={false} dataKey="avg" name="Average" fill={SERIES[0]} radius={BAR_RADIUS} maxBarSize={48} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
            <ChartCard title="By topic" description={`Average ${label(measure).toLowerCase()} · small samples are noisy`} empty={byTopic.length === 0}>
              <ResponsiveContainer>
                <BarChart data={byTopic} layout="vertical" margin={{ left: 8 }}>
                  <XAxis type="number" {...AXIS} hide />
                  <YAxis type="category" dataKey="key" {...AXIS} width={160} />
                  {tip}
                  <Bar isAnimationActive={false} dataKey="avg" name="Average" fill={SERIES[0]} radius={HBAR_RADIUS} maxBarSize={16} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
            <ChartCard title="By content style" description={`Average ${label(measure).toLowerCase()}`} empty={byFormat.length === 0}>
              <ResponsiveContainer>
                <BarChart data={byFormat} layout="vertical" margin={{ left: 8 }}>
                  <XAxis type="number" {...AXIS} hide />
                  <YAxis type="category" dataKey="key" {...AXIS} width={140} />
                  {tip}
                  <Bar isAnimationActive={false} dataKey="avg" name="Average" fill={SERIES[0]} radius={HBAR_RADIUS} maxBarSize={16} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
            <ChartCard title="By publishing day" description="Day of week (Malaysia time)" empty={byDay.length === 0}>
              <ResponsiveContainer>
                <BarChart data={WEEKDAYS.map((d) => byDay.find((g) => g.key === d) ?? { key: d, avg: null, n: 0 })}>
                  <CartesianGrid {...GRID} />
                  <XAxis dataKey="key" {...AXIS} />
                  <YAxis {...AXIS} width={40} />
                  {tip}
                  <Bar isAnimationActive={false} dataKey="avg" name="Average" fill={SERIES[0]} radius={BAR_RADIUS} maxBarSize={32} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>

          <h2 className="mt-8 mb-3 text-sm font-medium text-muted-foreground">All posts with metrics (hooks included)</h2>
          <Card className="py-0">
            <CardContent className="overflow-x-auto p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Hook</TableHead>
                    <TableHead className="hidden md:table-cell">Format</TableHead>
                    <TableHead className="hidden sm:table-cell">Published</TableHead>
                    {(['views', 'likes', 'replies', 'shares', 'reposts', 'quotes'] as const).map((m) => (
                      <TableHead key={m} className="text-right">{METRIC_LABEL[m]}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((r) => (
                    <TableRow key={r.snap.id} className="cursor-pointer" onClick={() => setSelected(r.item.id)}>
                      <TableCell className="max-w-72"><div className="truncate">{r.item.draft?.hook ?? r.item.topic}</div></TableCell>
                      <TableCell className="hidden md:table-cell">{formatLabel(r.item.format)}</TableCell>
                      <TableCell className="hidden sm:table-cell text-muted-foreground">{fmtDate(r.snap.published_at)}</TableCell>
                      {(['views', 'likes', 'replies', 'shares', 'reposts', 'quotes'] as const).map((m) => {
                        const v = r.snap.metrics[m]
                        return <TableCell key={m} className="text-right tabular-nums">{v == null ? <span className="text-muted-foreground">n/a</span> : fmtNumber(v)}</TableCell>
                      })}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
      <ContentDetailSheet item={repo.content.find((c) => c.id === selected) ?? null} onClose={() => setSelected(null)} />
    </>
  )
}
