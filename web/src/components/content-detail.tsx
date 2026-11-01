import { useState, type ReactNode } from 'react'
import { CheckCircle2, ChevronRight, ExternalLink, XCircle } from 'lucide-react'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Pill, PostPreview, Score, SeverityBadge, StatusBadge } from '@/components/common'
import { ContentActions } from '@/components/content-actions'
import { fmtDateTime, formatLabel, humanize } from '@/lib/format'
import { useRepo } from '@/lib/data'
import type { ContentItem, Stage } from '@/lib/types'
import { cn } from '@/lib/utils'

export function ContentDetailSheet({ item, onClose }: { item: ContentItem | null; onClose: () => void }) {
  return (
    <Sheet open={!!item} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full gap-0 overflow-y-auto p-0 sm:max-w-2xl">
        {item && <ContentDetail item={item} />}
      </SheetContent>
    </Sheet>
  )
}

function ContentDetail({ item }: { item: ContentItem }) {
  const repo = useRepo()
  const q = repo?.settings.quality
  const ev = item.evaluation
  return (
    <>
      <SheetHeader className="border-b p-5">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={item.status} />
          <Pill>{formatLabel(item.format)}</Pill>
          {item.auto_publish && <Pill tone="info">auto-publish eligible</Pill>}
        </div>
        <SheetTitle className="text-lg">{item.topic}</SheetTitle>
        <SheetDescription>
          {item.angle || 'No angle recorded'} · created {fmtDateTime(item.created_at)} · <span className="font-mono text-xs">{item.id}</span>
        </SheetDescription>
        <div className="pt-2"><ContentActions item={item} /></div>
      </SheetHeader>

      <Tabs defaultValue="content" className="p-5">
        <TabsList className="w-full overflow-x-auto">
          <TabsTrigger value="content">Content</TabsTrigger>
          <TabsTrigger value="evaluation">Evaluation</TabsTrigger>
          <TabsTrigger value="journey">Journey</TabsTrigger>
          <TabsTrigger value="sources">Sources</TabsTrigger>
          <TabsTrigger value="versions">Versions</TabsTrigger>
        </TabsList>

        <TabsContent value="content" className="space-y-5 pt-3">
          {item.draft ? <PostPreview posts={item.draft.posts} /> : <p className="text-sm text-muted-foreground">No draft yet.</p>}
          {item.draft && (
            <dl className="grid gap-3 rounded-lg border p-3 text-sm">
              <Field label="Hook">{item.draft.hook || '—'}</Field>
              <Field label="CTA">{item.draft.cta || '—'}</Field>
            </dl>
          )}
          {item.draft_en && (
            <details className="rounded-lg border p-3">
              <summary className="cursor-pointer text-sm font-medium">English master draft</summary>
              <div className="mt-3"><PostPreview posts={item.draft_en.posts} /></div>
            </details>
          )}
          {item.publishing?.url && (
            <a className="inline-flex items-center gap-1 text-sm text-primary hover:underline" href={item.publishing.url} target="_blank" rel="noreferrer">
              View on Threads <ExternalLink className="size-3.5" />
            </a>
          )}
          {item.publishing?.last_error && (
            <p className="text-sm text-destructive">Last publishing error: {item.publishing.last_error}</p>
          )}
          {item.approval?.reason && <p className="text-sm"><span className="text-muted-foreground">Rejection reason:</span> {item.approval.reason}</p>}
          {item.instructions && <p className="text-sm"><span className="text-muted-foreground">Instructions:</span> {item.instructions}</p>}
        </TabsContent>

        <TabsContent value="evaluation" className="space-y-5 pt-3">
          {!ev ? <p className="text-sm text-muted-foreground">Not evaluated yet.</p> : (
            <>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <Score label="Overall" value={ev.overall_score} min={q?.min_overall} />
                <Score label="Factuality" value={ev.factuality_score} min={q?.min_factuality} />
                <Score label="Brand" value={ev.brand_score} min={q?.min_brand} />
                <div>
                  <div className="text-xs text-muted-foreground">Fact check</div>
                  <div className="mt-1">
                    <Pill tone={ev.fact_check_status === 'passed' ? 'success' : ev.fact_check_status === 'failed' ? 'danger' : 'warning'}>
                      {ev.critical_fact_failure ? 'critical failure' : ev.fact_check_status}
                    </Pill>
                  </div>
                </div>
              </div>
              {ev.scores && (
                <div className="space-y-1.5">
                  {Object.entries(ev.scores).map(([k, v]) => (
                    <div key={k} className="flex items-center gap-3 text-sm">
                      <span className="w-40 shrink-0 text-muted-foreground">{humanize(k)}</span>
                      <div className="h-1.5 flex-1 rounded-full bg-muted">
                        <div className="h-1.5 rounded-full bg-primary" style={{ width: `${v}%` }} />
                      </div>
                      <span className="w-8 text-right tabular-nums">{Math.round(v)}</span>
                    </div>
                  ))}
                </div>
              )}
              <Section title={`Warnings (${ev.warnings.length})`}>
                {ev.warnings.length === 0 ? <p className="text-sm text-muted-foreground">No warnings.</p> : (
                  <ul className="space-y-2">
                    {ev.warnings.map((w, i) => (
                      <li key={i} className="flex gap-2 text-sm">
                        <SeverityBadge severity={w.severity} />
                        <div className="min-w-0">
                          <span className="font-mono text-xs text-muted-foreground">{w.code}</span>
                          {w.agent && <span className="text-xs text-muted-foreground"> · {humanize(w.agent)}</span>}
                          {w.resolved && <span className="text-xs text-success"> · reviewed</span>}
                          <div>{w.message}</div>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </Section>
              {ev.suggestions.length > 0 && (
                <Section title="Suggested improvements">
                  <ul className="list-disc space-y-1 pl-5 text-sm">{ev.suggestions.map((s, i) => <li key={i}>{s}</li>)}</ul>
                </Section>
              )}
              {ev.repetition_similarity != null && (
                <p className="text-xs text-muted-foreground">Similarity to recent content: {Math.round(ev.repetition_similarity * 100)}%</p>
              )}
            </>
          )}
        </TabsContent>

        <TabsContent value="journey" className="pt-3">
          {(item.stages ?? []).length === 0 ? <p className="text-sm text-muted-foreground">No stage records.</p> : (
            <ol className="space-y-2">{item.stages!.map((s, i) => <StageRow key={i} stage={s} />)}</ol>
          )}
        </TabsContent>

        <TabsContent value="sources" className="space-y-5 pt-3">
          <Section title="Sources">
            {(item.sources ?? []).length === 0 ? <p className="text-sm text-muted-foreground">No research sources (opinion or evergreen content).</p> : (
              <ul className="space-y-2">
                {item.sources!.map((s) => (
                  <li key={s.url} className="text-sm">
                    <a href={s.url} target="_blank" rel="noreferrer" className="font-medium text-primary hover:underline">{s.title || s.url}</a>
                    <div className="text-xs text-muted-foreground">{s.publisher} · published {fmtDateTime(s.published_at)} · retrieved {fmtDateTime(s.retrieved_at)}</div>
                  </li>
                ))}
              </ul>
            )}
          </Section>
          <Section title="Verified facts">
            {(item.facts ?? []).length === 0 ? <p className="text-sm text-muted-foreground">No extracted facts.</p> : (
              <ul className="space-y-2">
                {item.facts!.map((f, i) => (
                  <li key={i} className="rounded-md border p-2 text-sm">
                    <div>{f.text}</div>
                    {f.quote && <blockquote className="mt-1 border-l-2 pl-2 text-xs text-muted-foreground">“{f.quote}”</blockquote>}
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </TabsContent>

        <TabsContent value="versions" className="space-y-3 pt-3">
          {(item.versions ?? []).length === 0 ? <p className="text-sm text-muted-foreground">No versions.</p> :
            [...item.versions!].reverse().map((v) => (
              <details key={v.version} className="rounded-lg border p-3" open={v.version === item.versions!.length}>
                <summary className="cursor-pointer text-sm">
                  <span className="font-medium">v{v.version}</span> · {humanize(v.author.replace('user:', 'you: '))} · {fmtDateTime(v.created_at)}
                  {v.note && <span className="text-muted-foreground"> · {v.note}</span>}
                </summary>
                <div className="mt-3"><PostPreview posts={v.draft.posts} compact /></div>
              </details>
            ))}
        </TabsContent>
      </Tabs>
    </>
  )
}

function StageRow({ stage }: { stage: Stage }) {
  const [open, setOpen] = useState(false)
  const ok = stage.status === 'success'
  return (
    <li className="rounded-lg border">
      <button className="flex w-full items-center gap-3 p-3 text-left text-sm" onClick={() => setOpen(!open)}>
        {ok ? <CheckCircle2 className="size-4 shrink-0 text-success" /> : <XCircle className="size-4 shrink-0 text-destructive" />}
        <span className="font-medium">{humanize(stage.stage)}</span>
        <span className="truncate text-muted-foreground">{humanize(stage.agent)}</span>
        <span className="ml-auto hidden shrink-0 text-xs text-muted-foreground sm:inline">
          {stage.model ?? 'code'}{stage.usage?.total_tokens ? ` · ${stage.usage.total_tokens} tok` : ''}
        </span>
        <ChevronRight className={cn('size-4 shrink-0 transition-transform', open && 'rotate-90')} />
      </button>
      {open && (
        <div className="border-t p-3 text-xs">
          <div className="mb-2 text-muted-foreground">{fmtDateTime(stage.started_at)} → {fmtDateTime(stage.completed_at)}</div>
          {stage.error && <p className="mb-2 text-destructive">{stage.error}</p>}
          <pre className="max-h-80 overflow-auto rounded bg-muted p-2 font-mono text-[11px] leading-relaxed">{JSON.stringify(stage.output, null, 2)}</pre>
        </div>
      )}
    </li>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <div><dt className="text-xs text-muted-foreground">{label}</dt><dd className="whitespace-pre-wrap">{children}</dd></div>
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <section><h3 className="mb-2 text-sm font-medium">{title}</h3>{children}</section>
}
