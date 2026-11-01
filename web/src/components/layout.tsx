import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  Activity, BarChart3, Bot, Brain, CheckSquare, ExternalLink, GitBranch, History, LayoutDashboard, Menu,
  Moon, PenSquare, RefreshCw, Send, Settings as SettingsIcon, Sun, Workflow,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
import { DropdownMenu, DropdownMenuContent, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Spinner } from '@/components/common'
import { useData } from '@/lib/data'
import { useCommands } from '@/lib/commands'
import { useTheme } from '@/lib/theme'
import { getToken } from '@/lib/github'
import { REPO, REPO_URL } from '@/lib/config'
import { timeAgo } from '@/lib/format'
import { cn } from '@/lib/utils'

const NAV = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/studio', label: 'Content Studio', icon: PenSquare },
  { to: '/pipeline', label: 'Content Pipeline', icon: Workflow },
  { to: '/approvals', label: 'Approval Center', icon: CheckSquare, badge: 'approvals' as const },
  { to: '/agents', label: 'AI Agents', icon: Bot },
  { to: '/memory', label: 'Learning Memory', icon: Brain },
  { to: '/analytics', label: 'Performance Analytics', icon: BarChart3 },
  { to: '/publishing', label: 'Publishing History', icon: Send },
  { to: '/runs', label: 'Automation Runs', icon: History },
  { to: '/settings', label: 'Settings', icon: SettingsIcon },
]

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  const { data } = useData()
  const pending = data?.content.filter((c) => c.status === 'PENDING_APPROVAL').length ?? 0
  return (
    <nav className="space-y-0.5">
      {NAV.map(({ to, label, icon: Icon, badge }) => (
        <NavLink key={to} to={to} end={to === '/'} onClick={onNavigate}
          className={({ isActive }) => cn(
            'flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors',
            isActive ? 'bg-accent font-medium text-foreground' : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground',
          )}>
          <Icon className="size-4 shrink-0" aria-hidden />
          <span className="truncate">{label}</span>
          {badge && pending > 0 && (
            <span className="ml-auto rounded-full bg-warning/15 px-1.5 text-xs font-medium tabular-nums text-warning">{pending}</span>
          )}
        </NavLink>
      ))}
    </nav>
  )
}

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-2.5">
      <div className="grid size-8 place-items-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">TZ</div>
      <div className="leading-tight">
        <div className="text-sm font-semibold">TektiZen</div>
        <div className="text-xs text-muted-foreground">Content Intelligence</div>
      </div>
    </div>
  )
}

function SidebarFooter() {
  const { data } = useData()
  const auto = data?.settings.approval.mode === 'auto_publish'
  const kill = data?.settings.publishing.kill_switch
  return (
    <div className="space-y-2 rounded-lg border p-3 text-xs">
      <div className="flex justify-between"><span className="text-muted-foreground">Approval</span>
        <span className={cn('font-medium', auto && 'text-warning')}>{auto ? 'Auto-publish' : 'Human'}</span></div>
      <div className="flex justify-between"><span className="text-muted-foreground">Publishing</span>
        <span className={cn('font-medium', kill ? 'text-destructive' : 'text-success')}>{kill ? 'Kill switch ON' : 'Enabled'}</span></div>
      <a href={REPO_URL} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-muted-foreground hover:text-foreground">
        <GitBranch className="size-3" /> {REPO.owner}/{REPO.name} <ExternalLink className="size-3" />
      </a>
    </div>
  )
}

function ActivityMenu() {
  const { commands, dismiss } = useCommands()
  const active = commands.filter((c) => ['dispatching', 'queued', 'running'].includes(c.state)).length
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" aria-label="Command activity">
          {active ? <Spinner /> : <Activity className="size-4" />}
          <span className="hidden sm:inline">{active ? `${active} running` : 'Activity'}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <DropdownMenuLabel>Commands sent this session</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {commands.length === 0 && <p className="px-2 py-3 text-sm text-muted-foreground">Nothing sent yet.</p>}
        {commands.slice(0, 8).map((c) => (
          <div key={c.requestId} className="flex items-start gap-2 px-2 py-1.5 text-sm">
            <span className={cn('mt-1.5 size-2 shrink-0 rounded-full',
              c.state === 'success' ? 'bg-success' : c.state === 'failure' ? 'bg-destructive' : 'animate-pulse bg-primary')} />
            <div className="min-w-0 flex-1">
              <div className="truncate">{c.label}</div>
              <div className="text-xs text-muted-foreground">
                {c.state}{c.error ? ` — ${c.error}` : ''}
                {c.url && <> · <a href={c.url} target="_blank" rel="noreferrer" className="underline">log</a></>}
              </div>
            </div>
            {!['dispatching', 'queued', 'running'].includes(c.state) && (
              <button className="text-xs text-muted-foreground hover:text-foreground" onClick={() => dismiss(c.requestId)}>✕</button>
            )}
          </div>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function Layout() {
  const [open, setOpen] = useState(false)
  const { theme, toggle } = useTheme()
  const { demo, lastLoaded, refresh, loading, error, fileErrors } = useData()
  const location = useLocation()
  const connected = !!getToken()

  return (
    <div className="min-h-screen md:grid md:grid-cols-[15.5rem_1fr]">
      <aside className="sticky top-0 hidden h-screen flex-col gap-6 border-r bg-sidebar p-3 md:flex">
        <div className="pt-2"><Brand /></div>
        <div className="flex-1 overflow-y-auto"><Nav /></div>
        <SidebarFooter />
      </aside>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="w-72 gap-6 bg-sidebar p-3">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <div className="pt-2"><Brand /></div>
          <Nav onNavigate={() => setOpen(false)} />
          <SidebarFooter />
        </SheetContent>
      </Sheet>

      <div className="min-w-0">
        {demo && (
          <div className="bg-warning px-4 py-1.5 text-center text-xs font-semibold text-black">
            DEMO DATA: sample content for previewing the interface. Nothing here is real, and no commands are sent.
          </div>
        )}
        <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b bg-background/90 px-4 backdrop-blur md:px-6">
          <Button variant="ghost" size="icon" className="md:hidden" onClick={() => setOpen(true)} aria-label="Open navigation">
            <Menu />
          </Button>
          <div className="truncate text-sm text-muted-foreground">
            {NAV.find((n) => (n.to === '/' ? location.pathname === '/' : location.pathname.startsWith(n.to)))?.label}
          </div>
          <div className="ml-auto flex items-center gap-1">
            <span className="hidden text-xs text-muted-foreground lg:inline">
              {lastLoaded ? `Synced ${timeAgo(lastLoaded.toISOString())}` : ''}
            </span>
            <Button variant="ghost" size="icon" onClick={() => refresh()} aria-label="Refresh data" disabled={loading}>
              <RefreshCw className={cn(loading && 'animate-spin')} />
            </Button>
            <ActivityMenu />
            {!demo && (
              <NavLink to="/settings" className={cn('hidden rounded-md px-2 py-1 text-xs sm:block',
                connected ? 'text-success' : 'bg-warning/15 text-warning')}>
                {connected ? 'GitHub connected' : 'Read-only: connect GitHub'}
              </NavLink>
            )}
            <Button variant="ghost" size="icon" onClick={toggle} aria-label="Toggle theme">
              {theme === 'dark' ? <Sun /> : <Moon />}
            </Button>
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl px-4 py-6 md:px-6 md:py-8">
          {error && <div className="mb-4 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{error}</div>}
          {Object.keys(fileErrors).length > 0 && (
            <div className="mb-4 rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm">
              Some data files could not be read: {Object.entries(fileErrors).map(([f, e]) => `${f} (${e})`).join('; ')}
            </div>
          )}
          <Outlet />
        </main>
      </div>
    </div>
  )
}
