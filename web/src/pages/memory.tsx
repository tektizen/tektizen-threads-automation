import { useState } from 'react'
import { Brain, PencilLine, Plus, RotateCcw, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { EmptyState, LoadingPage, PageHeader, Pill } from '@/components/common'
import { useRepo } from '@/lib/data'
import { useCommands } from '@/lib/commands'
import { MEMORY_CATEGORIES } from '@/lib/config'
import { fmtDateTime, humanize, timeAgo } from '@/lib/format'
import type { Confidence, MemoryItem } from '@/lib/types'

type Editing = { category: string; item?: MemoryItem } | null
const CONF_TONE = { low: 'neutral', medium: 'info', high: 'success' } as const

export default function Memory() {
  const repo = useRepo()
  const { send } = useCommands()
  const [editing, setEditing] = useState<Editing>(null)
  const [text, setText] = useState('')
  const [confidence, setConfidence] = useState<Confidence>('medium')
  const [reset, setReset] = useState<string | null>(null)
  if (!repo) return <LoadingPage />
  const cats = repo.memory.categories
  const total = MEMORY_CATEGORIES.reduce((n, c) => n + (cats[c]?.length ?? 0), 0)

  const openEdit = (category: string, item?: MemoryItem) => {
    setText(item?.text ?? '')
    setConfidence(item?.confidence ?? 'medium')
    setEditing({ category, item })
  }
  const save = async () => {
    if (!editing) return
    const ok = editing.item
      ? await send('Update memory', { type: 'memory_update', category: editing.category, item_id: editing.item.id, text: text.trim(), confidence })
      : await send('Add memory', { type: 'memory_add', category: editing.category, text: text.trim(), confidence })
    if (ok) setEditing(null)
  }

  return (
    <>
      <PageHeader title="Learning Memory"
        description={<>What the system has learned: {total} insights. Only <b>high-confidence</b> insights (5+ supporting data points) strongly steer strategy. AI changes are always incremental and are recorded in the history.</>} />
      <Tabs defaultValue="memory">
        <TabsList>
          <TabsTrigger value="memory">Memory</TabsTrigger>
          <TabsTrigger value="history">Learning history</TabsTrigger>
        </TabsList>
        <TabsContent value="memory" className="pt-3">
          <div className="grid gap-4 md:grid-cols-2">
            {MEMORY_CATEGORIES.map((cat) => {
              const items = cats[cat] ?? []
              return (
                <Card key={cat} className="gap-3">
                  <CardHeader className="flex-row items-center gap-2">
                    <CardTitle className="text-sm font-medium">{humanize(cat)}</CardTitle>
                    <span className="text-xs text-muted-foreground tabular-nums">{items.length}</span>
                    <div className="ml-auto flex gap-1">
                      <Button size="icon" variant="ghost" className="size-7" aria-label={`Add to ${humanize(cat)}`} onClick={() => openEdit(cat)}><Plus /></Button>
                      {items.length > 0 && <Button size="icon" variant="ghost" className="size-7" aria-label={`Reset ${humanize(cat)}`} onClick={() => setReset(cat)}><RotateCcw /></Button>}
                    </div>
                  </CardHeader>
                  <CardContent>
                    {items.length === 0 ? <p className="text-sm text-muted-foreground">Nothing learned yet.</p> : (
                      <ul className="space-y-2.5">
                        {items.map((it) => (
                          <li key={it.id} className="group flex gap-2 text-sm">
                            <div className="min-w-0 flex-1">
                              <div>{it.text}</div>
                              <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                                <Pill tone={CONF_TONE[it.confidence]} icon={false}>{it.confidence}</Pill>
                                <span>n={it.evidence_count}</span>·<span>{it.source === 'user' ? 'you' : humanize(it.source)}</span>·<span>{timeAgo(it.updated_at)}</span>
                              </div>
                            </div>
                            <div className="flex shrink-0 gap-0.5 sm:opacity-0 sm:group-hover:opacity-100">
                              <Button size="icon" variant="ghost" className="size-7" aria-label="Edit" onClick={() => openEdit(cat, it)}><PencilLine /></Button>
                              <Button size="icon" variant="ghost" className="size-7" aria-label="Delete"
                                onClick={() => send('Delete memory', { type: 'memory_delete', category: cat, item_id: it.id, reason: 'deleted from dashboard' })}><Trash2 /></Button>
                            </div>
                          </li>
                        ))}
                      </ul>
                    )}
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </TabsContent>
        <TabsContent value="history" className="pt-3">
          {repo.memory.history.length === 0 ? <EmptyState icon={Brain} title="No learning history yet" /> : (
            <Card className="py-0"><CardContent className="divide-y p-0">
              {[...repo.memory.history].reverse().slice(0, 100).map((h) => {
                const after = h.after as MemoryItem | null
                const before = h.before as MemoryItem | MemoryItem[] | null
                return (
                  <div key={h.id} className="flex gap-3 p-3 text-sm">
                    <Pill tone={h.op === 'add' ? 'success' : h.op === 'update' ? 'info' : 'warning'} icon={false}>{h.op}</Pill>
                    <div className="min-w-0 flex-1">
                      <div className="text-xs text-muted-foreground">{humanize(h.category)} · by {humanize(h.actor)} · {fmtDateTime(h.at)}</div>
                      <div className="truncate">{after?.text ?? (Array.isArray(before) ? `${before.length} items cleared` : before?.text) ?? ''}</div>
                      {h.reason && <div className="text-xs text-muted-foreground">{h.reason}</div>}
                    </div>
                  </div>
                )
              })}
            </CardContent></Card>
          )}
        </TabsContent>
      </Tabs>

      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing?.item ? 'Edit insight' : `Add to ${humanize(editing?.category ?? '')}`}</DialogTitle>
            <DialogDescription>Insights you write are marked as yours and are never removed automatically.</DialogDescription>
          </DialogHeader>
          <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={500} placeholder="One specific, actionable sentence." />
          <div className="space-y-1.5">
            <Label>Confidence</Label>
            <Select value={confidence} onValueChange={(v) => setConfidence(v as Confidence)}>
              <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
              <SelectContent>{(['low', 'medium', 'high'] as const).map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={save} disabled={text.trim().length < 3}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!reset} onOpenChange={(o) => !o && setReset(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Reset {humanize(reset ?? '')}?</AlertDialogTitle>
            <AlertDialogDescription>All insights in this category are removed. The removal is kept in the learning history.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => reset && send(`Reset ${humanize(reset)}`, { type: 'memory_reset', category: reset, confirm: true })}>Reset</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
