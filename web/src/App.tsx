import { lazy, Suspense } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Layout } from '@/components/layout'
import { LoadingPage } from '@/components/common'
import { DataProvider } from '@/lib/data'
import { CommandsProvider } from '@/lib/commands'
import { ThemeProvider } from '@/lib/theme'

const Overview = lazy(() => import('@/pages/overview'))
const Studio = lazy(() => import('@/pages/studio'))
const Pipeline = lazy(() => import('@/pages/pipeline'))
const Approvals = lazy(() => import('@/pages/approvals'))
const Agents = lazy(() => import('@/pages/agents'))
const Memory = lazy(() => import('@/pages/memory'))
const Analytics = lazy(() => import('@/pages/analytics'))
const Publishing = lazy(() => import('@/pages/publishing'))
const Runs = lazy(() => import('@/pages/runs'))
const Settings = lazy(() => import('@/pages/settings'))

export default function App() {
  return (
    <ThemeProvider>
      <TooltipProvider>
        <DataProvider>
          <CommandsProvider>
            <BrowserRouter>
              <Suspense fallback={<div className="p-6"><LoadingPage /></div>}>
                <Routes>
                  <Route element={<Layout />}>
                    <Route index element={<Overview />} />
                    <Route path="studio" element={<Studio />} />
                    <Route path="pipeline" element={<Pipeline />} />
                    <Route path="approvals" element={<Approvals />} />
                    <Route path="agents" element={<Agents />} />
                    <Route path="memory" element={<Memory />} />
                    <Route path="analytics" element={<Analytics />} />
                    <Route path="publishing" element={<Publishing />} />
                    <Route path="runs" element={<Runs />} />
                    <Route path="settings" element={<Settings />} />
                    <Route path="*" element={<Overview />} />
                  </Route>
                </Routes>
              </Suspense>
            </BrowserRouter>
            <Toaster position="bottom-right" />
          </CommandsProvider>
        </DataProvider>
      </TooltipProvider>
    </ThemeProvider>
  )
}
