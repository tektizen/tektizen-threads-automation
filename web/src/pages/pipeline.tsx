import { useMemo, useState } from 'react'
import { ChevronRight, Workflow } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { EmptyState, LoadingPage, PageHeader, StatusBadge } from '@/components/common'
import { ContentDetailSheet } from '@/components/content-detail'
import { useRepo } from '@/lib/data'
import { formatLabel, timeAgo } from '@/lib/format'
import type { ContentStatus } from '@/lib/types'
import { cn } from '@/lib/utils'

const STAGES: { id: string; label: string; statuses: ContentStatus[] }[] = [
  { id: 'idea', label: 'Idea', statuses: ['IDEA', 'DRAFT'] },
  { id: 'research', label: 'Research', statuses: ['RESEARCH'] },
  { id: 'generation', label: 'Generation', statuses: ['GENERATION'] },
  { id: 'evaluation', label: 'Evaluation', statuses: ['EVALUATION'] },
  { id: 'refinement', label: 'Refinement', statuses: ['REFINEMENT'] },
  { id: 'approval', label: 'Approval', statuses: ['PENDING_APPROVAL'] },
  { id: 'ready', label: 'Ready to publish', statuses: ['READY_TO_PUBLISH', 'PUBLISHING'] },
  { id: 'published', label: 'Published', statuses: ['PUBLISHED'] },
]
const SIDE: { id: string; label: string; statuses: ContentStatus[] }[] = [
  { id: 'uncertain', label: 'Needs reconciling', statuses: ['PUBLISH_UNCERTAIN'] },
  { id: 'rejected', label: 'Rejected', statuses: ['REJECTED'] },
  { id: 'failed', label: 'Failed', statuses: ['FAILED'] },
  { id: 'archived', label: 'Archived', statuses: ['ARCHIVED'] },
]

export default function Pipeline() {
  const repo = useRepo()
  const [filter, setFilter] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)

  const counts = useMemo(() => {
    const m = new Map<ContentStatus, number>()
    for (const c of repo?.content ?? []) m.set(c.status, (m.get(c.status) ?? 0) + 1)
    return m
  }, [repo])

  if (!repo) return <LoadingPage />
  const newIdeas = repo.ideas.filter((i) => i.status === 'new').length
  const all = [...STAGES, ...SIDE]
  const active = all.find((s) => s.id === filter)
  const items = repo.content
    .filter((c) => (active ? active.statuses.includes(c.status) : c.status !== 'ARCHIVED'))
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
  const count = (statuses: ContentStatus[]) => statuses.reduce((n, s) => n + (counts.get(s) ?? 0), 0)

  return (
    <>
      <PageHeader title="Content Pipeline" description="Every item's position in the pipeline. Select a stage to filter, and an item to see its full journey and each agent's output." />

      <div className="flex gap-1 overflow-x-auto pb-2">
        {STAGES.map((s, i) => (
          <div key={s.id} className="flex items-center">
            <button onClick={() => setFilter(filter === s.id ? null : s.id)}
              className={cn('min-w-28 rounded-lg border px-3 py-2.5 text-left transition-colors',
                filter === s.id ? 'border-primary bg-primary/10' : 'hover:bg-accent')}>
              <div className="text-xs text-muted-foreground">{s.label}</div>
              <div className="text-xl font-semibold tabular-nums">
                {count(s.statuses)}
                {s.id === 'idea' && newIdeas > 0 && <span className="ml-1 text-xs font-normal text-muted-foreground">+{newIdeas} ideas</span>}
              </div>
            </button>
            {i < STAGES.length - 1 && <ChevronRight className="mx-0.5 size-4 shrink-0 text-muted-foreground/50" />}
          </div>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {SIDE.map((s) => (
          <button key={s.id} onClick={() => setFilter(filter === s.id ? null : s.id)}
            className={cn('rounded-md border px-2.5 py-1 text-xs', filter === s.id ? 'border-primary bg-primary/10' : 'hover:bg-accent')}>
            {s.label} <span className="font-semibold tabular-nums">{count(s.statuses)}</span>
          </button>
        ))}
        {filter && <button className="text-xs text-primary hover:underline" onClick={() => setFilter(null)}>Clear filter</button>}
      </div>

      <Card className="mt-4 py-0">
        <CardContent className="p-0">
          {items.length === 0 ? (
            <div className="p-6"><EmptyState icon={Workflow} title={active ? `Nothing in ${active.label}` : 'No content yet'}>
              Content appears here once the daily workflow or the Content Studio creates it.
            </EmptyState></div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Topic</TableHead>
                  <TableHead className="hidden md:table-cell">Format</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="hidden sm:table-cell text-right">Score</TableHead>
                  <TableHead className="hidden lg:table-cell">Origin</TableHead>
                  <TableHead className="text-right">Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((c) => (
                  <TableRow key={c.id} className="cursor-pointer" onClick={() => setSelected(c.id)}>
                    <TableCell className="max-w-72"><div className="truncate font-medium">{c.topic}</div>
                      <div className="truncate text-xs text-muted-foreground">{c.draft?.hook}</div></TableCell>
                    <TableCell className="hidden md:table-cell">{formatLabel(c.format)}</TableCell>
                    <TableCell><StatusBadge status={c.status} /></TableCell>
                    <TableCell className="hidden sm:table-cell text-right tabular-nums">{c.evaluation?.overall_score ?? '—'}</TableCell>
                    <TableCell className="hidden lg:table-cell text-muted-foreground">{c.origin.replace('_', ' ')}</TableCell>
                    <TableCell className="text-right text-muted-foreground">{timeAgo(c.updated_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <ContentDetailSheet item={repo.content.find((c) => c.id === selected) ?? null} onClose={() => setSelected(null)} />
    </>
  )
}
