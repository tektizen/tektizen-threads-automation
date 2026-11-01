import { useState } from 'react'
import { ExternalLink, Send } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { EmptyState, LoadingPage, PageHeader, Pill } from '@/components/common'
import { ContentDetailSheet } from '@/components/content-detail'
import { useRepo } from '@/lib/data'
import { fmtDateTime } from '@/lib/format'
import type { PublishRecord } from '@/lib/types'

const RESULT_TONE: Record<PublishRecord['result'], 'success' | 'danger' | 'warning' | 'neutral'> = {
  success: 'success', failed: 'danger', uncertain: 'warning', duplicate: 'warning', blocked: 'neutral',
}

export default function Publishing() {
  const repo = useRepo()
  const [selected, setSelected] = useState<string | null>(null)
  if (!repo) return <LoadingPage />
  const records = [...repo.publishing].sort((a, b) => b.attempted_at.localeCompare(a.attempted_at))
  const byId = new Map(repo.content.map((c) => [c.id, c]))

  return (
    <>
      <PageHeader title="Publishing History"
        description="Every attempt to publish to Threads through Zernio. Uncertain attempts are never retried automatically; reconcile them in the Approval Center." />
      {records.length === 0 ? <EmptyState icon={Send} title="Nothing published yet">Approved content is published by the Publish Approved Content workflow.</EmptyState> : (
        <Card className="py-0">
          <CardContent className="overflow-x-auto p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Content</TableHead>
                  <TableHead>Result</TableHead>
                  <TableHead className="hidden md:table-cell">Mode</TableHead>
                  <TableHead className="hidden lg:table-cell">Posts</TableHead>
                  <TableHead className="hidden lg:table-cell">Zernio ID</TableHead>
                  <TableHead>Link</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {records.map((r) => (
                  <TableRow key={r.id} className="cursor-pointer" onClick={() => setSelected(r.content_id)}>
                    <TableCell className="whitespace-nowrap text-muted-foreground">{fmtDateTime(r.attempted_at)}</TableCell>
                    <TableCell className="max-w-64">
                      <div className="truncate">{byId.get(r.content_id)?.draft?.hook ?? r.content_id}</div>
                      {r.error && <div className="truncate text-xs text-destructive">{r.error}</div>}
                    </TableCell>
                    <TableCell><Pill tone={RESULT_TONE[r.result]}>{r.result}</Pill></TableCell>
                    <TableCell className="hidden md:table-cell">{r.mode === 'auto' ? 'Automatic' : 'Human-approved'}</TableCell>
                    <TableCell className="hidden lg:table-cell tabular-nums">{r.post_count ?? 1}</TableCell>
                    <TableCell className="hidden lg:table-cell font-mono text-xs">{r.zernio_post_id ?? '—'}</TableCell>
                    <TableCell>
                      {r.url ? <a href={r.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center gap-1 text-primary hover:underline">Threads <ExternalLink className="size-3" /></a> : '—'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
      <ContentDetailSheet item={repo.content.find((c) => c.id === selected) ?? null} onClose={() => setSelected(null)} />
    </>
  )
}
