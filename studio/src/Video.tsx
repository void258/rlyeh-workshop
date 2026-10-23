import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, isActive, type Job, type VideoInfo } from './api'
import { useI18n } from './i18n'
import { JobPanel, useJobLog } from './Jobs'

const STEPS = /^(ch\d+ )?.*· steps (\d+)\/(\d+)\s*$/

/** 渲染日志里每 10 秒画面报一次「steps 已渲染/总数」，几章并行时各报各的 */
export function renderProgress(log: string) {
  const parts = new Map<string, [number, number]>()
  for (const line of log.split('\n')) {
    const m = STEPS.exec(line.trim())
    if (m) parts.set(m[1] ?? '', [Number(m[2]), Number(m[3])])
  }
  let done = 0
  let total = 0
  for (const [a, b] of parts.values()) {
    done += Math.min(a, b)
    total += b
  }
  return total ? done / total : null
}

const minutes = (s: number) => Math.max(1, Math.round(s / 60))

function RenderProgress({ job }: { job: Job }) {
  const { t } = useI18n()
  const { job: live } = useJobLog(job.id)
  const frac = live ? renderProgress(live.log) : null
  const started = job.started_at ? Date.parse(job.started_at) : null
  const elapsed = started ? (Date.now() - started) / 1000 : 0
  return (
    <div className="render-progress">
      <div className="bar big" aria-hidden>
        <i style={{ width: `${Math.round((frac ?? 0) * 100)}%` }} />
      </div>
      <p className="small">
        {frac == null
          ? t('video.starting')
          : t('video.progress', {
              pct: Math.round(frac * 100),
              used: minutes(elapsed),
              left: frac > 0.02 ? minutes((elapsed * (1 - frac)) / frac) : '?',
            })}
      </p>
    </div>
  )
}

export default function VideoPage({ jobs, onStarted }: { jobs: Job[]; onStarted: (job: Job) => void }) {
  const { t } = useI18n()
  const [v, setV] = useState<VideoInfo | null>(null)
  const [err, setErr] = useState('')
  const [chapter, setChapter] = useState('')
  const [from, setFrom] = useState('')
  const [seconds, setSeconds] = useState('30')
  const [playing, setPlaying] = useState<string | null>(null)

  const load = useCallback(() => api.video().then(setV).catch((e: Error) => setErr(e.message)), [])
  const signature = jobs.map((j) => `${j.id}:${j.status}`).join('|')
  useEffect(() => {
    load()
  }, [load, signature])

  const busy = jobs.find((j) => isActive(j) && ['render', 'encode', 'build'].includes(j.command[0]))
  const run = (stage: string, args: string[] = []) =>
    api
      .runStage(stage, args)
      .then((r) => onStarted(r.job))
      .catch((e: Error) => setErr(e.message))
  const reveal = (path: string) => api.reveal(path).catch((e: Error) => setErr(e.message))
  const firstLine = useMemo(() => v?.chapters.find((c) => c.first)?.first ?? '', [v])

  if (!v) return <p className="muted">{err ? t('error.generic', { err }) : t('loading')}</p>
  const master = v.files.find((f) => f.kind === 'master')
  const renderJob = jobs.find((j) => isActive(j) && j.command[0] === 'render')
  const lastJob = v.jobs[0]
  const length = v.last_seconds
    ? t('video.lastLength', { m: minutes(v.last_seconds) })
    : v.voice_seconds
      ? t('video.voiceLength', { m: minutes(v.voice_seconds) })
      : ''

  return (
    <div className="page-video">
      {err && <p className="error">{t('error.generic', { err })}</p>}
      {(!v.tools.ffmpeg || !v.tools.playwright) && (
        <p className="warn-text">
          {!v.tools.playwright && t('video.noPlaywright')} {!v.tools.ffmpeg && t('video.noFfmpeg')}
        </p>
      )}

      <section className="panel">
        <h2>{t('video.player')}</h2>
        <p className="muted small">{v.player ? t('video.playerBuilt') : t('video.playerNot')}</p>
        <div className="row-actions">
          <button className={v.player ? 'ghost' : 'primary'} disabled={!!busy} onClick={() => run('build')}>
            {v.player ? t('video.rebuild') : t('video.build')}
          </button>
          {v.player && (
            <a className="button ghost" href="#/review?page=player">
              {t('video.watch')}
            </a>
          )}
        </div>
      </section>

      <section className="panel">
        <h2>{t('video.render')}</h2>
        <p className="muted small">
          {t('video.renderHint')} {length}
        </p>
        {renderJob && <RenderProgress key={renderJob.id} job={renderJob} />}
        <div className="row-actions">
          <button className="primary" disabled={!!busy || !v.tools.playwright} onClick={() => run('render')}>
            {t('video.renderAll')}
          </button>
          <button className="ghost" disabled={!!busy || !master} onClick={() => run('render', ['--remix'])} title={t('video.remixHint')}>
            {t('video.remix')}
          </button>
        </div>
        <div className="row-actions">
          <select value={chapter} onChange={(e) => setChapter(e.target.value)}>
            <option value="">{t('video.pickChapter')}</option>
            {v.chapters.map((c) => (
              <option key={c.number} value={c.number}>
                {c.number} · {c.title}
              </option>
            ))}
          </select>
          <button className="ghost" disabled={!!busy || !chapter} onClick={() => run('render', ['--chapter', chapter])}>
            {t('video.renderChapter')}
          </button>
        </div>
        <div className="row-actions">
          <input className="short" value={from} placeholder={firstLine || 'c1-0001'} onChange={(e) => setFrom(e.target.value)} />
          <input className="tiny" value={seconds} onChange={(e) => setSeconds(e.target.value.replace(/[^\d.]/g, ''))} />
          <span className="muted small">{t('video.seconds')}</span>
          <button className="ghost" disabled={!!busy || !Number(seconds)} onClick={() => run('render', ['--from', from || firstLine, '--seconds', seconds])}>
            {t('video.renderClip')}
          </button>
        </div>
      </section>

      <section className="panel">
        <h2>{t('video.encode')}</h2>
        <p className="muted small">{master ? t('video.encodeHint') : t('video.needMaster')}</p>
        <div className="row-actions">
          <button className="primary" disabled={!!busy || !master} onClick={() => run('encode', ['share'])}>
            {t('video.share')}
          </button>
          <button className="ghost" disabled={!!busy || !master} onClick={() => run('encode', ['compat'])}>
            {t('video.compat')}
          </button>
        </div>
      </section>

      <section className="panel">
        <h2>{t('video.files')}</h2>
        {!v.files.length && <p className="muted">{t('video.noFiles')}</p>}
        <ul className="outputs">
          {v.files.map((f) => (
            <li key={f.path}>
              <div className="out-row">
                <span className="badge">{t(`video.kind.${f.kind}` as 'video.kind.master')}</span>
                <code>{f.name}</code>
                <span className="muted small">
                  {(f.bytes / 2 ** 20).toFixed(1)} MB · {new Date(f.mtime * 1000).toLocaleString()}
                </span>
                <div className="spacer" />
                <button className="ghost" onClick={() => setPlaying(playing === f.path ? null : f.path)}>
                  {playing === f.path ? t('close') : t('video.play')}
                </button>
                <button className="ghost" onClick={() => reveal(f.path)}>
                  {t('video.reveal')}
                </button>
              </div>
              {playing === f.path && <video className="preview" src={`/files/${f.path}?v=${f.mtime}`} controls autoPlay />}
            </li>
          ))}
        </ul>
        {v.files.length > 0 && (
          <button className="ghost" onClick={() => reveal('build/video')}>
            {t('video.openFolder')}
          </button>
        )}
      </section>

      {lastJob && (
        <section className="panel">
          <h2>{t('jobs.latest')}</h2>
          <JobPanel key={lastJob.id} id={lastJob.id} compact />
        </section>
      )}
    </div>
  )
}
