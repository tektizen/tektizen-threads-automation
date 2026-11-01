import { REPO } from './config'

// The viewer's fine-grained token lives in sessionStorage only (cleared when the tab closes).
// It is never bundled, never sent anywhere except api.github.com.
const TOKEN_KEY = 'tz-github-token'
const API = 'https://api.github.com'

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string | null) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token)
    else sessionStorage.removeItem(TOKEN_KEY)
  } catch {
    /* storage unavailable: token simply isn't remembered */
  }
}

export class GitHubError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function api<T>(path: string, init: RequestInit = {}, token = getToken()): Promise<T> {
  const headers: Record<string, string> = {
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    ...(init.headers as Record<string, string>),
  }
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(`${API}${path}`, { ...init, headers })
  if (!res.ok) {
    let message = `GitHub API ${res.status}`
    try {
      const body = await res.json()
      if (body?.message) message = `${message}: ${body.message}`
    } catch {
      /* ignore */
    }
    if (res.status === 403 && res.headers.get('x-ratelimit-remaining') === '0') {
      message = 'GitHub API rate limit reached. Connect a token in Settings to raise the limit.'
    }
    throw new GitHubError(message, res.status)
  }
  return (res.status === 204 ? undefined : await res.json()) as T
}

const repoPath = `/repos/${REPO.owner}/${REPO.name}`

/** Latest commit SHA of the branch; data is then read at that exact SHA (no CDN staleness). */
export async function latestSha(): Promise<string> {
  const body = await api<{ sha: string }>(`${repoPath}/commits/${REPO.branch}`)
  return body.sha
}

export async function readFile(path: string, ref: string): Promise<string> {
  // raw.githubusercontent.com serves public repos without auth or API rate limits.
  const res = await fetch(`https://raw.githubusercontent.com/${REPO.owner}/${REPO.name}/${ref}/${path}`)
  if (res.status === 404) throw new GitHubError(`${path} not found`, 404)
  if (!res.ok) throw new GitHubError(`Could not load ${path} (${res.status})`, res.status)
  return res.text()
}

export interface TokenCheck { ok: boolean; login?: string; canDispatch: boolean; message: string }

export async function checkToken(token: string): Promise<TokenCheck> {
  try {
    const user = await api<{ login: string }>('/user', {}, token).catch(() => null)
    const repo = await api<{ permissions?: { push?: boolean; admin?: boolean; maintain?: boolean } }>(repoPath, {}, token)
    const canDispatch = !!(repo.permissions?.push || repo.permissions?.admin || repo.permissions?.maintain)
    return {
      ok: true, login: user?.login, canDispatch,
      message: canDispatch ? 'Token can trigger workflows on this repository.'
        : 'Token can read the repository but cannot trigger workflows. Give it Actions: Read and write.',
    }
  } catch (e) {
    return { ok: false, canDispatch: false, message: e instanceof Error ? e.message : 'Token check failed' }
  }
}

export async function dispatchWorkflow(file: string, inputs: Record<string, string>) {
  if (!getToken()) throw new GitHubError('Connect a GitHub token first (Settings → Connection).', 401)
  await api(`${repoPath}/actions/workflows/${file}/dispatches`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ref: REPO.branch, inputs }),
  })
}

export interface WorkflowRun {
  id: number; display_title: string; status: string; conclusion: string | null; html_url: string
  created_at: string
}

export async function findRun(file: string, requestId: string): Promise<WorkflowRun | null> {
  const body = await api<{ workflow_runs: WorkflowRun[] }>(
    `${repoPath}/actions/workflows/${file}/runs?event=workflow_dispatch&per_page=20`,
  )
  return body.workflow_runs.find((r) => r.display_title.includes(requestId)) ?? null
}
