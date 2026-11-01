import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import { DEMO_MODE } from './config'
import { useData } from './data'
import { dispatchWorkflow, findRun } from './github'

export type CommandState = 'dispatching' | 'queued' | 'running' | 'success' | 'failure'

export interface TrackedCommand {
  requestId: string
  label: string
  workflow: string
  target?: string // content id, when the command acts on one item
  state: CommandState
  url?: string
  error?: string
  createdAt: number
}

interface CommandsState {
  commands: TrackedCommand[]
  /** Send a dashboard command (validated and applied by the dashboard-command workflow). */
  send: (label: string, command: Record<string, unknown>, target?: string) => Promise<boolean>
  /** Start the manual generation workflow. */
  generate: (label: string, inputs: Record<string, string>) => Promise<boolean>
  pendingFor: (target: string) => TrackedCommand | undefined
  dismiss: (requestId: string) => void
}

const CommandsContext = createContext<CommandsState | null>(null)
const POLL_MS = 6000
const GIVE_UP_MS = 30 * 60 * 1000

function newRequestId() {
  return `r${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`
}

export function CommandsProvider({ children }: { children: ReactNode }) {
  const { refresh } = useData()
  const [commands, setCommands] = useState<TrackedCommand[]>([])
  const commandsRef = useRef(commands)
  commandsRef.current = commands

  const update = (requestId: string, patch: Partial<TrackedCommand>) =>
    setCommands((list) => list.map((c) => (c.requestId === requestId ? { ...c, ...patch } : c)))

  const start = useCallback(async (label: string, workflow: string, inputs: Record<string, string>, target?: string) => {
    if (DEMO_MODE) {
      toast.info('Demo mode: nothing is sent to GitHub.', { description: label })
      return false
    }
    const requestId = newRequestId()
    const entry: TrackedCommand = { requestId, label, workflow, target, state: 'dispatching', createdAt: Date.now() }
    setCommands((list) => [entry, ...list].slice(0, 30))
    try {
      await dispatchWorkflow(workflow, { ...inputs, request_id: requestId })
      update(requestId, { state: 'queued' })
      toast.success('Sent to GitHub Actions', { description: label })
      return true
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e)
      update(requestId, { state: 'failure', error })
      toast.error('Could not send command', { description: error })
      return false
    }
  }, [])

  const send = useCallback(
    (label: string, command: Record<string, unknown>, target?: string) =>
      start(label, 'dashboard-command.yml', { command: JSON.stringify(command) }, target),
    [start],
  )
  const generate = useCallback(
    (label: string, inputs: Record<string, string>) => start(label, 'manual-generation.yml', inputs),
    [start],
  )

  // Poll GitHub for the runs we started; refresh data when one finishes.
  useEffect(() => {
    const timer = window.setInterval(async () => {
      const active = commandsRef.current.filter((c) => c.state === 'queued' || c.state === 'running')
      for (const c of active) {
        if (Date.now() - c.createdAt > GIVE_UP_MS) {
          update(c.requestId, { state: 'failure', error: 'Timed out waiting for the workflow run' })
          continue
        }
        try {
          const run = await findRun(c.workflow, c.requestId)
          if (!run) continue
          if (run.status !== 'completed') {
            update(c.requestId, { state: 'running', url: run.html_url })
            continue
          }
          const ok = run.conclusion === 'success'
          update(c.requestId, { state: ok ? 'success' : 'failure', url: run.html_url,
            error: ok ? undefined : `Workflow ${run.conclusion}. Open the run log for details.` })
          if (ok) toast.success('Done', { description: c.label })
          else toast.error('Command failed', { description: `${c.label} — see the GitHub run log` })
          window.setTimeout(() => refresh(), 1500)
        } catch {
          /* transient polling error: try again next tick */
        }
      }
    }, POLL_MS)
    return () => window.clearInterval(timer)
  }, [refresh])

  const value = useMemo<CommandsState>(() => ({
    commands, send, generate,
    pendingFor: (target) => commands.find((c) => c.target === target && ['dispatching', 'queued', 'running'].includes(c.state)),
    dismiss: (requestId) => setCommands((list) => list.filter((c) => c.requestId !== requestId)),
  }), [commands, send, generate])

  return <CommandsContext.Provider value={value}>{children}</CommandsContext.Provider>
}

export function useCommands() {
  const ctx = useContext(CommandsContext)
  if (!ctx) throw new Error('useCommands must be used inside CommandsProvider')
  return ctx
}
