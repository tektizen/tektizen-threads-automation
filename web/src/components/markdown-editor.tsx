import { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Spinner } from '@/components/common'
import { useData } from '@/lib/data'
import { useCommands } from '@/lib/commands'

const REQUIRED = ['Role', 'Objective', 'Personality', 'Responsibilities', 'Rules', 'Input Format', 'Output Format', 'Failure Conditions', 'Examples']

export interface MarkdownTarget {
  title: string
  path: string
  command: Record<string, unknown> // update_prompt {agent} or update_config {name}
  validateSections: boolean
}

export function MarkdownEditor({ target, onClose }: { target: MarkdownTarget | null; onClose: () => void }) {
  const { readText } = useData()
  const { send } = useCommands()
  const [text, setText] = useState('')
  const [original, setOriginal] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!target) return
    setLoading(true)
    setError(null)
    readText(target.path)
      .then((t) => { setText(t); setOriginal(t) })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [target, readText])

  const headings = new Set([...text.matchAll(/^##\s+(.+?)\s*$/gm)].map((m) => m[1].toLowerCase()))
  const missing = target?.validateSections ? REQUIRED.filter((s) => !headings.has(s.toLowerCase())) : []
  const bytes = new TextEncoder().encode(text).length

  const save = async () => {
    if (!target) return
    const ok = await send(`Update ${target.title}`, { ...target.command, markdown: text })
    if (ok) onClose()
  }

  return (
    <Dialog open={!!target} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="flex max-h-[92vh] flex-col sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>{target?.title}</DialogTitle>
          <DialogDescription className="font-mono text-xs">{target?.path}</DialogDescription>
        </DialogHeader>
        {loading ? <div className="flex items-center gap-2 py-10 text-sm text-muted-foreground"><Spinner /> Loading…</div>
          : error ? <p className="text-sm text-destructive">{error}</p>
          : <Textarea value={text} onChange={(e) => setText(e.target.value)} className="min-h-[55vh] flex-1 font-mono text-xs leading-relaxed" spellCheck={false} />}
        <div className="text-xs text-muted-foreground">
          {missing.length > 0 && <span className="text-destructive">Missing required sections: {missing.join(', ')}. </span>}
          {bytes > 60000 && <span className="text-destructive">Too large ({bytes} bytes; max 60,000). </span>}
          Saved through GitHub Actions. The engine validates it again before committing.
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={loading || !!error || text === original || missing.length > 0 || bytes > 60000 || !text.trim()}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
