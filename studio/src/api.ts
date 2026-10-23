// replay studio 的本地接口。会改东西的请求带 X-Rlyeh 头：服务只认带这个头的，别的网站跨站发不出来。

export type Kind = 'agent' | 'tool' | 'review'
export type Status = 'todo' | 'stale' | 'review' | 'done' | 'skip'

export interface Task {
  id: string
  kind: Kind
  stage: string
  status: Status
  title: string
  detail?: Record<string, unknown>
  command?: string[]
  playbook?: string
  inputs?: string[]
  blocked_by?: string[]
  optional?: boolean
  page?: string
}

export interface Board {
  tasks: Task[]
  next: string | null
  overview: Partial<Record<Status, number>>
}

export interface ProjectInfo {
  root: string
  id: string
  title: string
  lang: string
}

export interface Recent {
  path: string
  title: string
  lang: string
  exists: boolean
}

export interface StudioState {
  version: string
  project: ProjectInfo | null
  recent: Recent[]
}

export interface Folder {
  name: string
  path: string
  project: boolean
}

export interface Browse {
  path: string
  parent: string | null
  project: boolean
  dirs: Folder[]
  roots: string[]
  home: string
}

export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'lost'

export interface Job {
  id: string
  command: string[]
  status: JobStatus
  queued_at?: string
  started_at?: string
  ended_at?: string
  exit_code?: number
  waiting_for?: string
}

export interface JobLog extends Job {
  log: string
  offset: number
  result?: { ok?: boolean; error?: string } | null
}

export class ApiError extends Error {}

async function call<T>(method: 'GET' | 'POST', url: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method }
  if (method === 'POST') {
    init.headers = { 'Content-Type': 'application/json', 'X-Rlyeh': '1' }
    init.body = JSON.stringify(body ?? {})
  }
  const res = await fetch(url, init)
  let data: { ok?: boolean; error?: string } & T
  try {
    data = await res.json()
  } catch {
    throw new ApiError(`HTTP ${res.status}`)
  }
  if (!data.ok) throw new ApiError(data.error || `HTTP ${res.status}`)
  return data
}

const q = encodeURIComponent

export const api = {
  state: () => call<StudioState>('GET', '/api/studio/state'),
  browse: (path?: string) => call<Browse>('GET', '/api/studio/browse' + (path ? `?path=${q(path)}` : '')),
  open: (path: string) => call<{ project: ProjectInfo }>('POST', '/api/studio/open', { path }),
  create: (path: string, title: string, lang: string) =>
    call<{ project: ProjectInfo }>('POST', '/api/studio/new', { path, title, lang }),
  close: () => call<object>('POST', '/api/studio/close'),
  board: (lang: string) => call<Board>('GET', `/api/tasks?lang=${q(lang)}`),
  done: (id: string) => call<object>('POST', '/api/tasks/done', { id }),
  run: (task: string) => call<{ job: Job }>('POST', '/api/run', { task }),
  jobs: () => call<{ jobs: Job[] }>('GET', '/api/jobs'),
  job: (id: string, offset: number) => call<{ job: JobLog }>('GET', `/api/jobs/${q(id)}?offset=${offset}`),
}

export const isActive = (j: Job) => j.status === 'queued' || j.status === 'running'

export const sameCommand = (a?: string[], b?: string[]) => !!a && !!b && a.join('\u0000') === b.join('\u0000')
