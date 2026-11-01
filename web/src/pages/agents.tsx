import { useState } from 'react'
import { FileText, PencilLine } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { LoadingPage, PageHeader, Pill } from '@/components/common'
import { MarkdownEditor, type MarkdownTarget } from '@/components/markdown-editor'
import { useRepo } from '@/lib/data'
import { AGENTS, CONFIG_DOCS } from '@/lib/config'
import { fmtNumber, timeAgo } from '@/lib/format'

export default function Agents() {
  const repo = useRepo()
  const [target, setTarget] = useState<MarkdownTarget | null>(null)
  if (!repo) return <LoadingPage />
  const ai = repo.settings.ai

  return (
    <>
      <PageHeader title="AI Agents"
        description="Eight specialised agents. Each one's behaviour is defined by a Markdown prompt in the repository, loaded fresh on every run." />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {AGENTS.map((a, i) => {
          const st = repo.agents[a.id]
          const model = ai.agent_models?.[a.id] ?? ai.model
          const status = !st ? { tone: 'neutral' as const, label: 'Not run yet' }
            : st.last_status === 'failed' ? { tone: 'danger' as const, label: 'Last run failed' }
            : { tone: 'success' as const, label: 'Healthy' }
          return (
            <Card key={a.id} className="gap-3">
              <CardHeader>
                <div className="flex items-center gap-2">
                  <span className="grid size-7 place-items-center rounded-md bg-muted text-xs font-semibold tabular-nums">{i + 1}</span>
                  <CardTitle className="text-base">{a.name}</CardTitle>
                  <span className="ml-auto"><Pill tone={status.tone}>{status.label}</Pill></span>
                </div>
                <CardDescription>{a.role}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="grid grid-cols-3 gap-2 text-center">
                  <Metric label="Runs" value={st?.executions ?? 0} />
                  <Metric label="Success" value={st?.successes ?? 0} />
                  <Metric label="Failed" value={st?.failures ?? 0} />
                </div>
                <dl className="space-y-1 text-xs">
                  <Row label="Personality">{a.personality}</Row>
                  <Row label="Model"><span className="font-mono">{model}</span></Row>
                  <Row label="Last run">{st?.last_execution_at ? timeAgo(st.last_execution_at) : '—'}</Row>
                  <Row label="Tokens used">{fmtNumber(st?.total_tokens ?? 0)}</Row>
                  <Row label="Prompt"><span className="font-mono">agents/prompts/{a.id}.md</span></Row>
                </dl>
                {st?.last_error && <p className="line-clamp-2 text-xs text-destructive">{st.last_error}</p>}
                <Button size="sm" variant="outline" className="w-full" onClick={() => setTarget({
                  title: `${a.name} prompt`, path: `agents/prompts/${a.id}.md`,
                  command: { type: 'update_prompt', agent: a.id }, validateSections: true,
                })}><PencilLine /> Edit instructions</Button>
              </CardContent>
            </Card>
          )
        })}
      </div>

      <h2 className="mt-10 mb-3 text-base font-semibold">Shared configuration</h2>
      <p className="mb-4 text-sm text-muted-foreground">Every agent receives the brand profile and content rules. The Malay Localizer also receives the style examples.</p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {CONFIG_DOCS.map((d) => (
          <Card key={d.id} className="gap-2 py-4">
            <CardContent className="flex items-center gap-3 px-4">
              <FileText className="size-5 text-muted-foreground" />
              <div className="min-w-0">
                <div className="text-sm font-medium">{d.name}</div>
                <div className="truncate font-mono text-xs text-muted-foreground">config/{d.id}.md</div>
              </div>
              <Button size="icon" variant="ghost" className="ml-auto" aria-label={`Edit ${d.name}`}
                onClick={() => setTarget({ title: d.name, path: `config/${d.id}.md`, command: { type: 'update_config', name: d.id }, validateSections: false })}>
                <PencilLine />
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
      <MarkdownEditor target={target} onClose={() => setTarget(null)} />
    </>
  )
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="rounded-md bg-muted/60 py-2"><div className="text-lg font-semibold tabular-nums">{value}</div><div className="text-xs text-muted-foreground">{label}</div></div>
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="flex justify-between gap-3"><dt className="text-muted-foreground">{label}</dt><dd className="truncate text-right">{children}</dd></div>
}
