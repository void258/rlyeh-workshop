import { useEffect, useRef, useState } from 'react'
import { api, isActive, type Job, type JobLog } from './api'
import { useI18n } from './i18n'

const time = (s?: string) => (s ? s.replace('T', ' ').slice(5, 19) : '')

function resultText(result: unknown) {
  const s = JSON.stringify(result, null, 1)
  return s.length > 6000 ? `${s.slice(0, 6000)}\n…` : s
}

// 跟着一个后台任务：每秒取一次新增的日志，任务结束后停。
function useJobLog(id: string) {
  const [job, setJob] = useState<JobLog | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    let offset = 0
    let log = ''
    let timer = 0
    let alive = true
    setJob(null)
    setErr('')
    const tick = () =>
      api
        .job(id, offset)
        .then(({ job: j }) => {
          if (!alive) return
          log += j.log
          offset = j.offset
          setJob({ ...j, log })
          if (isActive(j)) timer = window.setTimeout(tick, 1000)
        })
        .catch((e: Error) => alive && setErr(e.message))
    tick()
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
  }, [id])
  return { job, err }
}

export function JobPanel({ id, compact }: { id: string; compact?: boolean }) {
  const { t } = useI18n()
  const { job, err } = useJobLog(id)
  const pre = useRef<HTMLPreElement>(null)
  const stick = useRef(true)

  useEffect(() => {
    const el = pre.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [job?.log])

  if (err) return <p className="error">{t('error.generic', { err })}</p>
  if (!job) return <p className="muted">{t('loading')}</p>
  const failed = job.status === 'failed' && job.result?.error
  return (
    <div className={`jobpanel${compact ? ' compact' : ''}`}>
      <div className="job-head">
        <span className={`jstatus ${job.status}`}>
          {isActive(job) && <span className="spin" />}
          {t(`jobs.${job.status}`)}
        </span>
        <code className="cmd">replay {job.command.join(' ')}</code>
      </div>
      <p className="muted small">
        {time(job.started_at || job.queued_at)}
        {job.ended_at && ` → ${time(job.ended_at)}`}
        {job.waiting_for && ` · ${t('jobs.waiting', { id: job.waiting_for })}`}
        {job.exit_code != null && job.exit_code !== 0 && ` · ${t('jobs.exit', { code: job.exit_code })}`}
      </p>
      {failed && <p className="error">{t('jobs.error', { err: String(job.result?.error) })}</p>}
      <pre
        ref={pre}
        className="log"
        onScroll={(e) => {
          const el = e.currentTarget
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24
        }}
      >
        {job.log || t(isActive(job) ? 'jobs.noLog' : 'jobs.quiet')}
      </pre>
      {job.result && !isActive(job) && (
        <details className="result">
          <summary>{t('jobs.result')}</summary>
          <pre>{resultText(job.result)}</pre>
        </details>
      )}
    </div>
  )
}

export default function JobsPage({ jobs, selected }: { jobs: Job[]; selected: string | null }) {
  const { t } = useI18n()
  return (
    <div className="jobs">
      <section className="jobs-list">
        <h2>{t('jobs.title')}</h2>
        <p className="muted small">{t('jobs.one')}</p>
        {!jobs.length && <p className="muted">{t('jobs.empty')}</p>}
        <ul>
          {jobs.map((j) => (
            <li key={j.id}>
              <a href={`#/jobs?id=${j.id}`} className={j.id === selected ? 'on' : ''}>
                <span className={`jstatus ${j.status}`}>
                  {isActive(j) && <span className="spin" />}
                  {t(`jobs.${j.status}`)}
                </span>
                <code>replay {j.command.join(' ')}</code>
                <small className="muted">{time(j.started_at || j.queued_at)}</small>
              </a>
            </li>
          ))}
        </ul>
      </section>
      <section className="jobs-log">{selected ? <JobPanel key={selected} id={selected} /> : null}</section>
    </div>
  )
}
