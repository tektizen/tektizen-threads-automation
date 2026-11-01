import { useMemo, useState } from 'react'
import { CheckSquare, ExternalLink } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { EmptyState, LoadingPage, PageHeader, Pill, PostPreview, Score, SeverityBadge, StatusBadge } from '@/components/common'
import { ContentActions } from '@/components/content-actions'
import { ContentDetailSheet } from '@/components/content-detail'
import { useRepo } from '@/lib/data'
import { fmtDateTime, formatLabel, timeAgo } from '@/lib/format'
import type { ContentItem } from '@/lib/types'

export default function Approvals() {
  const repo = useRepo()
  const [selected, setSelected] = useState<string | null>(null)
  const groups = useMemo(() => {
    const c = repo?.content ?? []
    const by = (s: string[]) => c.filter((i) => s.includes(i.status)).sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    return {
      pending: by(['PENDING_APPROVAL']),
      ready: by(['READY_TO_PUBLISH', 'PUBLISHING']),
      attention: by(['PUBLISH_UNCERTAIN', 'FAILED']),
      decided: [...(repo?.approvals ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 30),
    }
  }, [repo])
  if (!repo) return <LoadingPage />
  const byId = new Map(repo.content.map((c) => [c.id, c]))
  const auto = repo.settings.approval.mode === 'auto_publish'

  return (
    <>
      <PageHeader title="Approval Center"
        description={auto
          ? 'Automatic publishing is ON: content that passes every gate publishes without you. Everything else waits here.'
          : 'Human approval is required. Nothing is published until you approve it.'} />
      <Tabs defaultValue="pending">
        <TabsList className="w-full justify-start overflow-x-auto sm:w-auto">
          <TabsTrigger value="pending">Pending <Count n={groups.pending.length} /></TabsTrigger>
          <TabsTrigger value="ready">Ready to publish <Count n={groups.ready.length} /></TabsTrigger>
          <TabsTrigger value="attention">Needs attention <Count n={groups.attention.length} /></TabsTrigger>
          <TabsTrigger value="decided">Decision log</TabsTrigger>
        </TabsList>
        <TabsContent value="pending" className="space-y-4 pt-3">
          {groups.pending.length === 0
            ? <EmptyState icon={CheckSquare} title="Inbox zero">New drafts appear here after each generation run.</EmptyState>
            : groups.pending.map((c) => <ApprovalCard key={c.id} item={c} onOpen={() => setSelected(c.id)} />)}
        </TabsContent>
        <TabsContent value="ready" className="space-y-4 pt-3">
          {repo.settings.publishing.kill_switch && <Pill tone="danger">Kill switch is ON: nothing will publish until it is turned off in Settings.</Pill>}
          {groups.ready.length === 0 ? <EmptyState title="Nothing queued">Approved content waits here until the publish workflow runs.</EmptyState>
            : groups.ready.map((c) => <ApprovalCard key={c.id} item={c} onOpen={() => setSelected(c.id)} />)}
        </TabsContent>
        <TabsContent value="attention" className="space-y-4 pt-3">
          {groups.attention.length === 0 ? <EmptyState title="All clear">Failed or uncertain publishing attempts show up here.</EmptyState>
            : groups.attention.map((c) => <ApprovalCard key={c.id} item={c} onOpen={() => setSelected(c.id)} />)}
        </TabsContent>
        <TabsContent value="decided" className="pt-3">
          {groups.decided.length === 0 ? <EmptyState title="No decisions yet" /> : (
            <Card className="py-0"><CardContent className="divide-y p-0">
              {groups.decided.map((a) => (
                <button key={a.id} className="flex w-full items-start gap-3 p-3 text-left text-sm hover:bg-accent/50" onClick={() => setSelected(a.content_id)}>
                  <Pill tone={a.status === 'rejected_invalid' ? 'danger' : a.action === 'reject' ? 'warning' : 'success'}>{a.action.replace('_', ' ')}</Pill>
                  <div className="min-w-0 flex-1">
                    <div className="truncate">{byId.get(a.content_id)?.topic ?? a.content_id}</div>
                    {a.reason && <div className="text-xs text-muted-foreground">“{a.reason}”</div>}
                    {a.error && <div className="text-xs text-destructive">Not applied: {a.error}</div>}
                  </div>
                  <span className="shrink-0 text-xs text-muted-foreground">{a.actor} · {timeAgo(a.created_at)}</span>
                </button>
              ))}
            </CardContent></Card>
          )}
        </TabsContent>
      </Tabs>
      <ContentDetailSheet item={repo.content.find((c) => c.id === selected) ?? null} onClose={() => setSelected(null)} />
    </>
  )
}

function Count({ n }: { n: number }) {
  return n ? <span className="ml-1 rounded-full bg-muted px-1.5 text-xs tabular-nums">{n}</span> : null
}

function ApprovalCard({ item, onOpen }: { item: ContentItem; onOpen: () => void }) {
  const repo = useRepo()!
  const q = repo.settings.quality
  const ev = item.evaluation
  const severe = ev?.warnings.filter((w) => !w.resolved && (w.severity === 'high' || w.severity === 'critical')) ?? []
  const other = ev?.warnings.filter((w) => !severe.includes(w)) ?? []
  return (
    <Card className="py-0">
      <CardContent className="grid gap-5 p-4 lg:grid-cols-5 lg:p-5">
        <div className="lg:col-span-3">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <StatusBadge status={item.status} />
            <Pill>{formatLabel(item.format)}</Pill>
            <span className="text-xs text-muted-foreground">{fmtDateTime(item.created_at)}</span>
            <button onClick={onOpen} className="ml-auto text-xs text-primary hover:underline">Full journey <ExternalLink className="inline size-3" /></button>
          </div>
          <h3 className="mb-3 font-medium">{item.topic}</h3>
          {item.draft ? <PostPreview posts={item.draft.posts} /> : <p className="text-sm text-muted-foreground">No draft.</p>}
          {item.publishing?.last_error && <p className="mt-3 text-sm text-destructive">Publishing: {item.publishing.last_error}</p>}
          <div className="mt-4"><ContentActions item={item} /></div>
        </div>
        <div className="space-y-4 lg:col-span-2 lg:border-l lg:pl-5">
          <div className="grid grid-cols-3 gap-3">
            <Score label="Quality" value={ev?.overall_score} min={q.min_overall} />
            <Score label="Factuality" value={ev?.factuality_score} min={q.min_factuality} />
            <Score label="Brand" value={ev?.brand_score} min={q.min_brand} />
          </div>
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Fact check</span>
            {ev ? <Pill tone={ev.critical_fact_failure ? 'danger' : ev.fact_check_status === 'passed' ? 'success' : 'warning'}>
              {ev.critical_fact_failure ? 'critical failure' : ev.fact_check_status}</Pill> : <Pill>not run</Pill>}
            <span className="ml-auto text-xs text-muted-foreground">{item.sources?.length ?? 0} sources</span>
          </div>
          {severe.length > 0 && (
            <div>
              <div className="mb-1.5 text-xs font-medium text-destructive">Must review ({severe.length})</div>
              <ul className="space-y-1.5">{severe.map((w, i) => <WarningRow key={i} w={w} />)}</ul>
            </div>
          )}
          {other.length > 0 && (
            <details>
              <summary className="cursor-pointer text-xs text-muted-foreground">Other notes ({other.length})</summary>
              <ul className="mt-1.5 space-y-1.5">{other.map((w, i) => <WarningRow key={i} w={w} />)}</ul>
            </details>
          )}
          {ev && ev.suggestions.length > 0 && (
            <div>
              <div className="mb-1 text-xs font-medium text-muted-foreground">Suggested improvements</div>
              <ul className="list-disc space-y-0.5 pl-4 text-sm">{ev.suggestions.slice(0, 4).map((s, i) => <li key={i}>{s}</li>)}</ul>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function WarningRow({ w }: { w: NonNullable<ContentItem['evaluation']>['warnings'][number] }) {
  return (
    <li className="flex gap-2 text-sm">
      <SeverityBadge severity={w.severity} />
      <span className="min-w-0">{w.message}</span>
    </li>
  )
}
