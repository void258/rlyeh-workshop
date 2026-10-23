import { useCallback, useEffect, useState } from 'react'
import { api, type BackendOption, type Check, type Settings } from './api'
import { hasKey, useI18n } from './i18n'

const MARK = { ok: '✓', warn: '!', fail: '✗' } as const

function optionLabel(o: BackendOption, t: ReturnType<typeof useI18n>['t']) {
  const tags = [o.gpu ? `GPU${o.vram ? ` ${o.vram}GB` : ''}` : '', o.commercial === false ? t('settings.nc') : '', o.license]
  return `${o.id}${tags.filter(Boolean).length ? `  (${tags.filter(Boolean).join(' · ')})` : ''}`
}

function Field({ label, value, onSave, placeholder }: { label: string; value: string; onSave: (v: string) => void; placeholder?: string }) {
  const [v, setV] = useState(value)
  useEffect(() => setV(value), [value])
  return (
    <label className="field inline">
      <span>{label}</span>
      <input value={v} placeholder={placeholder} onChange={(e) => setV(e.target.value)} onBlur={() => v !== value && onSave(v)}
        onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()} />
    </label>
  )
}

export default function SettingsPage() {
  const { t, lang } = useI18n()
  const [s, setS] = useState<Settings | null>(null)
  const [checks, setChecks] = useState<Check[] | null>(null)
  const [checking, setChecking] = useState(false)
  const [msg, setMsg] = useState<{ text: string; bad?: boolean } | null>(null)

  const load = useCallback(() => api.settings().then(setS).catch((e: Error) => setMsg({ text: e.message, bad: true })), [])
  const runCheck = useCallback(() => {
    setChecking(true)
    api
      .doctor(lang)
      .then((r) => setChecks(r.checks))
      .catch((e: Error) => setMsg({ text: e.message, bad: true }))
      .finally(() => setChecking(false))
  }, [lang])
  useEffect(() => {
    load()
    runCheck()
  }, [load, runCheck])

  const save = (table: string, key: string, value: string) =>
    api
      .setSetting(table, key, value)
      .then(() => {
        setMsg({ text: t('settings.saved') })
        load()
        if (table === 'backends') runCheck()
      })
      .catch((e: Error) => setMsg({ text: e.message, bad: true }))

  if (!s) return <p className="muted">{msg?.text ?? t('loading')}</p>
  const groups = ['env', 'backends', 'project'] as const
  return (
    <div className="page-settings">
      {msg && <p className={msg.bad ? 'error' : 'ok-text'}>{msg.text}</p>}
      <section className="panel">
        <h2>{t('settings.backends')}</h2>
        <p className="muted small">{t('settings.backendsHint')}</p>
        <div className="kinds">
          {s.backends.map((b) => {
            const key = `settings.kind.${b.kind}`
            const params = Object.entries(b.params)
            return (
              <div key={b.kind} className="setting">
                <label className="field">
                  <span>{hasKey(key) ? t(key) : b.kind}</span>
                  <select value={b.current} onChange={(e) => save('backends', b.kind, e.target.value)}>
                    {b.options.map((o) => (
                      <option key={o.id} value={o.id}>
                        {optionLabel(o, t)}
                      </option>
                    ))}
                  </select>
                </label>
                {params.length > 0 && (
                  <dl className="params">
                    {params.map(([k, v]) => (
                      <div key={k}>
                        <dt>{k}</dt>
                        <dd className="mono">{typeof v === 'string' ? v : JSON.stringify(v)}</dd>
                      </div>
                    ))}
                  </dl>
                )}
              </div>
            )
          })}
        </div>
        <p className="muted small">{t('settings.paramsHint')}</p>
      </section>

      <section className="panel">
        <h2>{t('settings.harness')}</h2>
        <p className="muted small">{t('settings.harnessHint')}</p>
        <div className="kinds">
          <label className="field">
            <span>{t('settings.default')}</span>
            <select value={s.harness.default} onChange={(e) => save('harness', 'default', e.target.value)}>
              {s.harness.harnesses.map((h) => (
                <option key={h} value={h}>
                  {h}
                </option>
              ))}
            </select>
          </label>
          <div className="setting">
            <b>Codex</b>
            <Field label="model" value={s.harness.codex.model ?? ''} placeholder="gpt-6.1-sol" onSave={(v) => save('harness.codex', 'model', v)} />
            <Field label="effort" value={s.harness.codex.effort ?? ''} placeholder="low" onSave={(v) => save('harness.codex', 'effort', v)} />
          </div>
          <div className="setting">
            <b>Claude Code</b>
            <Field label="model" value={s.harness.claude.model ?? ''} placeholder="sonnet" onSave={(v) => save('harness.claude-code', 'model', v)} />
          </div>
          <div className="setting">
            <b>DeepSeek Harness</b>
            <Field label="provider" value={s.harness.dsh.provider ?? ''} placeholder="deepseek-official" onSave={(v) => save('harness.dsh', 'provider', v)} />
            <Field label="model" value={s.harness.dsh.model ?? ''} placeholder="deepseek-flash" onSave={(v) => save('harness.dsh', 'model', v)} />
          </div>
        </div>
        <p className="muted small">{t('settings.reexport')}</p>
      </section>

      <section className="panel">
        <h2>
          {t('settings.doctor')}
          <button className="ghost" disabled={checking} onClick={runCheck}>
            {checking ? <span className="spin" /> : null} {t('settings.recheck')}
          </button>
        </h2>
        {!checks && <p className="muted">{t('settings.checking')}</p>}
        {checks &&
          groups.map((g) => {
            const rows = checks.filter((c) => c.group === g)
            if (!rows.length) return null
            return (
              <div key={g} className="checks">
                <h3>{t(`settings.group.${g}`)}</h3>
                {rows.map((c, i) => (
                  <div key={i} className={`check ${c.status}`}>
                    <span className="mark">{MARK[c.status]}</span>
                    <b>{c.name}</b>
                    {c.detail && <span className="muted">{c.detail}</span>}
                    {c.hint && <p className="hint-line">→ {c.hint}</p>}
                  </div>
                ))}
              </div>
            )
          })}
      </section>
    </div>
  )
}
