import { useCallback, useEffect, useState } from 'react'
import { api, isActive, type AgentInfo, type ExportResult, type Job } from './api'
import { useI18n } from './i18n'

const NAMES: Record<string, string> = { 'claude-code': 'Claude Code', codex: 'Codex', dsh: 'DeepSeek Harness' }
const REVIEW_PAGE: Record<string, string> = { voices: 'voices', voice: 'voice', art: 'art', music: 'music', player: 'player' }

function Copy({ text }: { text: string }) {
  const { t } = useI18n()
  const [done, setDone] = useState(false)
  const copy = () =>
    navigator.clipboard
      ?.writeText(text)
      .then(() => {
        setDone(true)
        window.setTimeout(() => setDone(false), 1500)
      })
      .catch(() => {})
  return (
    <div className="copyline">
      <code>{text}</code>
      <button className="ghost" onClick={copy}>
        {done ? t('agent.copied') : t('agent.copy')}
      </button>
    </div>
  )
}

export default function AgentPage({ jobs }: { jobs: Job[] }) {
  const { t, lang } = useI18n()
  const [info, setInfo] = useState<AgentInfo | null>(null)
  const [pick, setPick] = useState<string | null>(null)
  const [result, setResult] = useState<ExportResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const load = useCallback(
    () =>
      api
        .agent(lang)
        .then((a) => {
          setInfo(a)
          setPick((p) => p ?? a.default)
        })
        .catch((e: Error) => setErr(e.message)),
    [lang],
  )
  useEffect(() => {
    load()
    const id = window.setInterval(load, 8000)
    return () => window.clearInterval(id)
  }, [load])

  if (!info || !pick) return <p className="muted">{err ? t('error.generic', { err }) : t('loading')}</p>

  const choose = (h: string) => {
    setPick(h)
    setResult(null)
    api.setSetting('harness', 'default', h).then(load).catch((e: Error) => setErr(e.message))
  }
  const doExport = (names: string[], force = false) => {
    setBusy(true)
    api
      .exportAgent(names, lang, force)
      .then((r) => {
        setResult(r)
        load()
      })
      .catch((e: Error) => setErr(e.message))
      .finally(() => setBusy(false))
  }
  const close = (index: number) => api.closeRequest(index).then(load).catch((e: Error) => setErr(e.message))

  const exported = info.exported[pick]
  const open = info.requests.filter((r) => r.status === 'open')
  const running = jobs.filter(isActive)
  const kept = result?.files.filter((f) => f.action === 'kept') ?? []
  const cd = `cd ${/\s/.test(info.root) ? `"${info.root}"` : info.root}`

  return (
    <div className="page-agent">
      {err && <p className="error">{t('error.generic', { err })}</p>}
      <p className="muted">{t('agent.intro')}</p>

      <section className="panel">
        <h2>{t('agent.which')}</h2>
        <div className="harnesses">
          {info.harnesses.map((h) => (
            <button key={h} className={h === pick ? 'harness on' : 'harness'} onClick={() => choose(h)}>
              <b>{NAMES[h] ?? h}</b>
              <small className={info.installed[h] ? 'ok' : 'muted'}>{info.installed[h] ? t('agent.installed') : t('agent.notFound')}</small>
              <small className="muted">
                {info.exported[h] ? t('agent.exportedAt', { at: info.exported[h].at.replace('T', ' ').slice(0, 16) }) : t('agent.notExported')}
              </small>
            </button>
          ))}
        </div>
        <div className="row-actions">
          <button className="primary" disabled={busy} onClick={() => doExport([pick])}>
            {exported ? t('agent.reexport', { name: NAMES[pick] }) : t('agent.export', { name: NAMES[pick] })}
          </button>
          <button className="ghost" disabled={busy} onClick={() => doExport(['all'])}>
            {t('agent.exportAll')}
          </button>
          {kept.length > 0 && (
            <button className="ghost" disabled={busy} onClick={() => doExport(result!.harnesses, true)}>
              {t('agent.force', { n: kept.length })}
            </button>
          )}
        </div>
        {result && (
          <div className="export-result">
            <ul>
              {result.files
                .filter((f) => f.action !== 'unchanged')
                .map((f) => (
                  <li key={f.path} className={f.action}>
                    <span className="act">{t(`agent.action.${f.action}` as 'agent.action.written')}</span>
                    <code>{f.path}</code>
                    {f.reason && <span className="muted small"> — {f.reason}</span>}
                  </li>
                ))}
              {result.files.every((f) => f.action === 'unchanged') && <li className="muted">{t('agent.allSame')}</li>}
            </ul>
            {result.notes.map((n) => (
              <p key={n} className="muted small">
                {n}
              </p>
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <h2>{t('agent.start')}</h2>
        {!exported && <p className="warn-text">{t('agent.exportFirst')}</p>}
        <ol className="steps">
          <li>
            {t('agent.step1')}
            <Copy text={cd} />
          </li>
          <li>
            {t(`agent.step2.${pick}` as 'agent.step2.codex')}
            {info.commands[pick].map((c) => (
              <Copy key={c} text={c} />
            ))}
          </li>
          {pick !== 'dsh' && (
            <li>
              {t('agent.step3')}
              <Copy text={info.prompt} />
            </li>
          )}
        </ol>
        <p className="muted small">{t('agent.cost')}</p>
      </section>

      <section className="panel">
        <h2>{t('agent.progress')}</h2>
        {running.map((j) => (
          <p key={j.id} className="small">
            <span className="spin" /> <code>replay {j.command.join(' ')}</code>
          </p>
        ))}
        {!info.activity.length && !running.length && <p className="muted">{t('agent.noActivity')}</p>}
        <ul className="activity">
          {info.activity.map((a) => (
            <li key={a.id + a.at}>
              <span className="muted small">{a.at.replace('T', ' ').slice(5, 16)}</span>
              <code>{a.id}</code>
              <span>{t('agent.doneTask')}</span>
              {a.note && <span className="muted small">— {a.note}</span>}
            </li>
          ))}
        </ul>
        <a href="#/board">{t('agent.toBoard')} →</a>
      </section>

      <section className="panel">
        <h2>
          {t('agent.requests')}
          {open.length > 0 && <span className="count">{open.length}</span>}
        </h2>
        {!info.requests.length && <p className="muted">{t('agent.noRequests')}</p>}
        <ul className="requests">
          {info.requests.map((r) => (
            <li key={r.index} className={r.status}>
              <div>
                <b>{t(`review.${REVIEW_PAGE[r.kind] ?? 'player'}` as 'review.art')}</b>
                <span className="muted small"> · {r.at.replace('T', ' ').slice(5, 16)}</span>
                {r.status !== 'open' && <span className="badge">{t('agent.handled')}</span>}
                {r.note && <p>{r.note}</p>}
                {r.items.length > 0 && <p className="muted small">{r.items.slice(0, 12).join(', ')}</p>}
              </div>
              {r.status === 'open' && (
                <div className="row-actions">
                  <a className="button primary" href={`#/review?page=${REVIEW_PAGE[r.kind] ?? 'player'}`}>
                    {t('task.openReview')}
                  </a>
                  <button className="ghost" onClick={() => close(r.index)}>
                    {t('agent.markHandled')}
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
