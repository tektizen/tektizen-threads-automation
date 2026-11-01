import { useState } from 'react'
import { ExternalLink, History } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { EmptyState, LoadingPage, PageHeader, Pill } from '@/components/common'
import { useRepo } from '@/lib/data'
import { fmtDateTime, fmtDuration, fmtNumber } from '@/lib/format'
import type { RunRecord } from '@/lib/types'
import { cn } from '@/lib/utils'

const TONE = { success: 'success', failed: 'danger', partial: 'warning', running: 'info' } as const

export default function Runs() {
  const repo = useRepo()
  const [open, setOpen] = useState<RunRecord | null>(null)
  if (!repo) return <LoadingPage />
  const runs = [...repo.runs].sort((a, b) => b.started_at.localeCompare(a.started_at))

  return (
    <>
      <PageHeader title="Automation Runs" description="Every engine execution in GitHub Actions, with AI usage and logs. Select a run to inspect it." />
      {runs.length === 0 ? <EmptyState icon={History} title="No runs recorded yet">Trigger “Daily Content Generation” from the Actions tab or wait for the schedule.</EmptyState> : (
        <Card className="py-0">
          <CardContent className="overflow-x-auto p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Workflow</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="hidden sm:table-cell">Started</TableHead>
                  <TableHead className="hidden md:table-cell">Duration</TableHead>
                  <TableHead className="hidden md:table-cell">Trigger</TableHead>
                  <TableHead className="text-right">AI requests</TableHead>
                  <TableHead className="hidden lg:table-cell text-right">Tokens</TableHead>
                  <TableHead className="hidden lg:table-cell text-right">Issues</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((r) => (
                  <TableRow key={r.id} className="cursor-pointer" onClick={() => setOpen(r)}>
                    <TableCell><div className="font-medium">{r.workflow}</div><div className="font-mono text-xs text-muted-foreground">{r.id}</div></TableCell>
                    <TableCell><Pill tone={TONE[r.status]}>{r.status}</Pill></TableCell>
                    <TableCell className="hidden sm:table-cell whitespace-nowrap text-muted-foreground">{fmtDateTime(r.started_at)}</TableCell>
                    <TableCell className="hidden md:table-cell tabular-nums">{fmtDuration(r.duration_ms)}</TableCell>
                    <TableCell className="hidden md:table-cell">{r.trigger}</TableCell>
                    <TableCell className="text-right tabular-nums">{r.ai_requests ?? 0}</TableCell>
                    <TableCell className="hidden lg:table-cell text-right tabular-nums">{r.tokens?.total ? fmtNumber(r.tokens.total) : 'n/a'}</TableCell>
                    <TableCell className="hidden lg:table-cell text-right tabular-nums">
                      <span className={cn((r.errors?.length ?? 0) > 0 && 'text-destructive')}>{r.errors?.length ?? 0}E</span>{' '}
                      <span className={cn((r.warnings?.length ?? 0) > 0 && 'text-warning')}>{r.warnings?.length ?? 0}W</span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <Dialog open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
          {open && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">{open.workflow} <Pill tone={TONE[open.status]}>{open.status}</Pill></DialogTitle>
                <DialogDescription className="font-mono text-xs">{open.id}</DialogDescription>
              </DialogHeader>
              <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                <Item label="Started">{fmtDateTime(open.started_at)}</Item>
                <Item label="Completed">{fmtDateTime(open.completed_at)}</Item>
                <Item label="Duration">{fmtDuration(open.duration_ms)}</Item>
                <Item label="Trigger">{open.trigger}</Item>
                <Item label="AI requests">{open.ai_requests ?? 0}</Item>
                <Item label="Prompt tokens">{fmtNumber(open.tokens?.prompt)}</Item>
                <Item label="Completion tokens">{fmtNumber(open.tokens?.completion)}</Item>
                <Item label="Models">{open.models?.length ? open.models.join(', ') : '—'}</Item>
              </dl>
              {open.github_run_url && (
                <a href={open.github_run_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
                  Full GitHub Actions log <ExternalLink className="size-3.5" />
                </a>
              )}
              {(open.errors?.length ?? 0) > 0 && (
                <div><div className="mb-1 text-sm font-medium text-destructive">Errors</div>
                  <ul className="list-disc space-y-1 pl-5 text-sm">{open.errors!.map((e, i) => <li key={i}>{e}</li>)}</ul></div>
              )}
              <div>
                <div className="mb-1 text-sm font-medium">Log</div>
                <pre className="max-h-96 overflow-auto rounded-md bg-muted p-3 font-mono text-[11px] leading-relaxed">
                  {(open.log ?? []).map((l, i) => (
                    <div key={i} className={cn(l.level === 'error' && 'text-destructive', l.level === 'warning' && 'text-warning')}>
                      {l.at.slice(11, 19)} {l.level.toUpperCase().padEnd(7)} {l.message}
                    </div>
                  ))}
                </pre>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}

function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><dt className="text-xs text-muted-foreground">{label}</dt><dd className="truncate">{children}</dd></div>
}
