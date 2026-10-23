import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, isActive, sameCommand, type Board, type Job, type Task } from './api'
import { hasKey, useI18n, type T } from './i18n'
import { JobPanel } from './Jobs'

const STAGES = ['import', 'script', 'cast', 'voice', 'art', 'sfx', 'music', 'player', 'render'] as const
const FINISHED = new Set(['done', 'skip'])

function itemText(x: unknown): string {
  if (x && typeof x === 'object') {
    const o = x as Record<string, unknown>
    if (typeof o.message === 'string') return (o.line ? `${o.line}: ` : '') + o.message
    for (const k of ['id', 'name', 'text', 'out']) if (typeof o[k] === 'string') return o[k] as string
    return JSON.stringify(x)
  }
  return String(x)
}

function valueText(v: unknown, t: T): string {
  if (Array.isArray(v)) {
    const shown = v.slice(0, 6).map(itemText).join(', ')
    return v.length > 6 ? `${shown} … (${t('detail.items', { n: v.length })})` : shown
  }
  if (v && typeof v === 'object') return Object.entries(v as object).map(([k, x]) => `${k} ${itemText(x)}`).join(', ')
  return String(v)
}

function Detail({ detail }: { detail?: Record<string, unknown> }) {
  const { t } = useI18n()
  const rows = Object.entries(detail ?? {}).filter(
    ([k, v]) => k !== 'key' && v !== null && v !== '' && v !== 0 && !(Array.isArray(v) && !v.length),
  )
  if (!rows.length) return null
  return (
    <dl className="detail">
      {rows.map(([k, v]) => {
        const key = `detail.${k}`
        return (
          <div key={k}>
            <dt>{hasKey(key) ? t(key) : k}</dt>
            <dd>{valueText(v, t)}</dd>
          </div>
        )
      })}
    </dl>
  )
}

interface CardProps {
  task: Task
  byId: Record<string, Task>
  jobs: Job[]
  big?: boolean
  onRun: (task: Task) => void
  onDone: (task: Task) => void
}

function TaskCard({ task, byId, jobs, big, onRun, onDone }: CardProps) {
  const { t } = useI18n()
  const blocked = (task.blocked_by ?? []).filter((id) => byId[id] && !FINISHED.has(byId[id].status))
  const job = jobs.find((j) => isActive(j) && sameCommand(j.command, task.command))
  const open = !FINISHED.has(task.status)
  return (
    <article className={`task ${task.status}${big ? ' big' : ''}`} id={`task-${task.id}`}>
      <div className="task-head">
        <span className={`status ${task.status}`}>{t(`status.${task.status}`)}</span>
        <span className={`kind ${task.kind}`}>{t(`kind.${task.kind}`)}</span>
        {task.optional && <span className="badge">{t('optional')}</span>}
        <h3>{task.title}</h3>
        <code className="tid">{task.id}</code>
      </div>
      {open && <Detail detail={task.detail} />}
      {open && blocked.length > 0 && <p className="muted small">{t('task.blocked', { ids: blocked.join(', ') })}</p>}
      {open && task.kind === 'agent' && (
        <p className="hint">{task.playbook ? t('task.agent', { skill: task.playbook }) : t('task.agentNoSkill')}</p>
      )}
      <div className="task-actions">
        {task.kind === 'tool' && task.command && task.status !== 'skip' && <code className="cmd">replay {task.command.join(' ')}</code>}
        <div className="spacer" />
        {task.kind === 'tool' &&
          (job ? (
            <button className="primary" disabled>
              <span className="spin" /> {t(job.status === 'queued' ? 'task.queued' : 'task.running')}
            </button>
          ) : task.status === 'done' ? (
            <button className="ghost" onClick={() => onRun(task)}>
              {t('task.rerun')}
            </button>
          ) : task.status !== 'skip' ? (
            <button className="primary" disabled={blocked.length > 0} onClick={() => onRun(task)}>
              {t('task.run')}
            </button>
          ) : null)}
        {task.kind === 'review' && task.page && open && (
          <a className="button primary" href={task.page} target="_blank" rel="noreferrer">
            {t('task.openReview')} ↗
          </a>
        )}
        {task.kind === 'agent' && open && task.detail && 'key' in task.detail && (
          <button className="ghost" title={t('task.markDoneHint')} onClick={() => onDone(task)}>
            {t('task.markDone')}
          </button>
        )}
      </div>
    </article>
  )
}

export default function BoardPage({ jobs, focus, onStarted }: { jobs: Job[]; focus: string | null; onStarted: (job: Job) => void }) {
  const { t, lang } = useI18n()
  const [board, setBoard] = useState<Board | null>(null)
  const [err, setErr] = useState('')

  const load = useCallback(
    () =>
      api
        .board(lang)
        .then((b) => {
          setBoard(b)
          setErr('')
        })
        .catch((e: Error) => setErr(e.message)),
    [lang],
  )
  useEffect(() => {
    load()
    const id = window.setInterval(load, 5000)
    return () => window.clearInterval(id)
  }, [load])

  // 后台任务跑完（状态变了）就马上刷新看板
  const signature = jobs.map((j) => `${j.id}:${j.status}`).join('|')
  const last = useRef(signature)
  useEffect(() => {
    if (last.current !== signature) {
      last.current = signature
      load()
    }
  }, [signature, load])

  const byId = useMemo(() => Object.fromEntries((board?.tasks ?? []).map((x) => [x.id, x])), [board])
  const run = (task: Task) =>
    api
      .run(task.id)
      .then((r) => onStarted(r.job))
      .catch((e: Error) => setErr(e.message))
  const done = (task: Task) =>
    api
      .done(task.id)
      .then(load)
      .catch((e: Error) => setErr(e.message))

  if (!board) return <p className="muted">{err ? t('error.generic', { err }) : t('loading')}</p>
  const next = board.next ? byId[board.next] : null
  const panelJob = focus ?? jobs.find(isActive)?.id ?? jobs[0]?.id ?? null
  const cardProps = { byId, jobs, onRun: run, onDone: done }

  return (
    <div className="board">
      <div className="board-main">
        {err && <p className="error">{t('error.generic', { err })}</p>}
        <section className="next">
          <h2>{t('board.next')}</h2>
          {next ? <TaskCard task={next} big {...cardProps} /> : <p className="all-done">{t('board.allDone')}</p>}
        </section>
        {STAGES.map((stage) => {
          const list = board.tasks.filter((x) => x.stage === stage)
          if (!list.length) return null
          const total = list.filter((x) => x.status !== 'skip').length
          const finished = list.filter((x) => x.status === 'done').length
          return (
            <section key={stage} className="stage">
              <header>
                <h2>{t(`stage.${stage}`)}</h2>
                {total > 0 ? (
                  <>
                    <div className="bar" aria-hidden>
                      <i style={{ width: `${(100 * finished) / total}%` }} />
                    </div>
                    <span className="muted small">{t('board.progress', { done: finished, total })}</span>
                  </>
                ) : (
                  <span className="muted small">{t('status.skip')}</span>
                )}
              </header>
              {list.map((x) => (
                <TaskCard key={x.id} task={x} {...cardProps} />
              ))}
            </section>
          )
        })}
      </div>
      <aside className="board-side">
        <h2>{t('jobs.latest')}</h2>
        {panelJob ? <JobPanel id={panelJob} compact /> : <p className="muted">{t('jobs.empty')}</p>}
        <p className="muted small">{t('jobs.one')}</p>
      </aside>
    </div>
  )
}
