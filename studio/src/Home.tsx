import { useEffect, useState, type ReactNode } from 'react'
import { api, type Browse, type StudioState } from './api'
import { useI18n } from './i18n'

export function Modal({ title, onClose, children, footer }: { title: string; onClose: () => void; children: ReactNode; footer?: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-label={title}>
        <header>
          <h2>{title}</h2>
          <button className="ghost x" onClick={onClose} aria-label="close">
            ×
          </button>
        </header>
        <div className="body">{children}</div>
        {footer && <footer>{footer}</footer>}
      </div>
    </div>
  )
}

// 选文件夹：浏览器拿不到本机路径，所以由本地服务列出文件夹。open 模式只能选项目，pick 模式选任意文件夹。
export function FolderPicker({ mode, start, onPick, onClose }: { mode: 'open' | 'pick'; start?: string; onPick: (path: string) => void; onClose: () => void }) {
  const { t } = useI18n()
  const [dir, setDir] = useState<Browse | null>(null)
  const [typed, setTyped] = useState('')
  const [err, setErr] = useState('')

  const go = (path?: string) =>
    api
      .browse(path)
      .then((b) => {
        setDir(b)
        setTyped(b.path)
        setErr('')
      })
      .catch((e: Error) => setErr(e.message))

  useEffect(() => {
    go(start)
  }, [start])

  const ok = mode === 'pick' ? !!dir : !!dir?.project
  return (
    <Modal
      title={t('pick.title')}
      onClose={onClose}
      footer={
        <>
          {mode === 'open' && dir && !dir.project && <span className="muted small">{t('pick.notProject')}</span>}
          <div className="spacer" />
          <button className="ghost" onClick={onClose}>
            {t('cancel')}
          </button>
          <button className="primary" disabled={!ok} onClick={() => dir && onPick(dir.path)}>
            {mode === 'open' ? t('pick.openHere') : t('pick.useHere')}
          </button>
        </>
      }
    >
      <form
        className="pathbar"
        onSubmit={(e) => {
          e.preventDefault()
          go(typed)
        }}
      >
        <button type="button" className="ghost" disabled={!dir?.parent} onClick={() => dir?.parent && go(dir.parent)}>
          ↑ {t('pick.up')}
        </button>
        <input value={typed} onChange={(e) => setTyped(e.target.value)} spellCheck={false} />
        <button type="submit" className="ghost">
          {t('pick.go')}
        </button>
      </form>
      <div className="roots">
        {dir && (
          <button className="chip" onClick={() => go(dir.home)}>
            ⌂ {t('pick.home')}
          </button>
        )}
        {dir?.roots.map((r) => (
          <button key={r} className="chip" onClick={() => go(r)}>
            {r}
          </button>
        ))}
      </div>
      {err && <p className="error">{err}</p>}
      <ul className="folders">
        {dir?.dirs.map((d) => (
          <li key={d.path}>
            <button className={d.project ? 'folder project' : 'folder'} onClick={() => go(d.path)}>
              <span className="icon">{d.project ? '❖' : '▸'}</span>
              <span className="name">{d.name}</span>
              {d.project && <span className="badge">{t('pick.isProject')}</span>}
            </button>
          </li>
        ))}
        {dir && !dir.dirs.length && <li className="muted small pad">{t('pick.empty')}</li>}
      </ul>
    </Modal>
  )
}

const PARENT = 'rlyeh.studio.parent'

function joinPath(parent: string, name: string) {
  const sep = parent.includes('\\') ? '\\' : '/'
  return parent.replace(/[\\/]+$/, '') + sep + name
}

function NewProject({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const { t, lang } = useI18n()
  const [parent, setParent] = useState(() => {
    try {
      return localStorage.getItem(PARENT) ?? ''
    } catch {
      return ''
    }
  })
  const [folder, setFolder] = useState('')
  const [title, setTitle] = useState('')
  const [scriptLang, setScriptLang] = useState(lang === 'en' ? 'en' : 'zh-CN')
  const [picking, setPicking] = useState(false)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    // 没记过放在哪：默认主目录。异步回来时用户可能已经填了，不覆盖
    if (!parent) api.browse().then((b) => setParent((p) => p || b.home)).catch(() => {})
  }, [parent])

  const name = folder.trim()
  const bad = !name || /[\\/:*?"<>|]/.test(name)
  const create = () => {
    setBusy(true)
    try {
      localStorage.setItem(PARENT, parent)
    } catch {
      /* 不记也行 */
    }
    api
      .create(joinPath(parent, name), title.trim() || name, scriptLang)
      .then(onCreated)
      .catch((e: Error) => setErr(e.message))
      .finally(() => setBusy(false))
  }

  if (picking)
    return (
      <FolderPicker
        mode="pick"
        start={parent}
        onClose={() => setPicking(false)}
        onPick={(p) => {
          setParent(p)
          setPicking(false)
        }}
      />
    )
  return (
    <Modal
      title={t('new.title')}
      onClose={onClose}
      footer={
        <>
          <div className="spacer" />
          <button className="ghost" onClick={onClose}>
            {t('cancel')}
          </button>
          <button className="primary" disabled={bad || !parent || busy} onClick={create}>
            {t('new.create')}
          </button>
        </>
      }
    >
      <label className="field">
        <span>{t('new.parent')}</span>
        <div className="row">
          <input value={parent} onChange={(e) => setParent(e.target.value)} spellCheck={false} />
          <button className="ghost" onClick={() => setPicking(true)}>
            {t('new.choose')}
          </button>
        </div>
      </label>
      <label className="field">
        <span>{t('new.folder')}</span>
        <input value={folder} onChange={(e) => setFolder(e.target.value)} placeholder="fog-harbor" spellCheck={false} autoFocus />
      </label>
      <label className="field">
        <span>{t('new.name')}</span>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t('new.namePh')} />
      </label>
      <label className="field">
        <span>{t('new.lang')}</span>
        <select value={scriptLang} onChange={(e) => setScriptLang(e.target.value)}>
          <option value="zh-CN">中文</option>
          <option value="en">English</option>
        </select>
      </label>
      {name && parent && <p className="muted small mono">{t('new.path', { path: joinPath(parent, name) })}</p>}
      {err && <p className="error">{err}</p>}
    </Modal>
  )
}

export default function Home({ state, onOpened }: { state: StudioState; onOpened: () => void }) {
  const { t, lang, setLang } = useI18n()
  const [dialog, setDialog] = useState<'new' | 'open' | null>(null)
  const [err, setErr] = useState('')

  const open = (path: string) =>
    api
      .open(path)
      .then(onOpened)
      .catch((e: Error) => setErr(e.message))

  return (
    <div className="home">
      <div className="home-top">
        <button className="ghost" onClick={() => setLang(lang === 'en' ? 'zh' : 'en')}>
          {t('lang.switch')}
        </button>
      </div>
      <section className="hero">
        <div className="sigil big">❖</div>
        <h1>{t('brand')}</h1>
        <p className="muted">{t('tagline')}</p>
      </section>
      <section className="actions">
        <button className="action" onClick={() => setDialog('new')}>
          <b>{t('home.new')}</b>
          <span>{t('home.newHint')}</span>
        </button>
        <button className="action" onClick={() => setDialog('open')}>
          <b>{t('home.open')}</b>
          <span>{t('home.openHint')}</span>
        </button>
      </section>
      {err && <p className="error center-text">{err}</p>}
      <section className="recent">
        <h2>{t('home.recent')}</h2>
        {!state.recent.length && <p className="muted">{t('home.noRecent')}</p>}
        <ul>
          {state.recent.map((r) => (
            <li key={r.path}>
              <button className="recent-row" disabled={!r.exists} onClick={() => open(r.path)}>
                <b>{r.title}</b>
                <small className="mono">{r.path}</small>
                {!r.exists && <span className="badge warn">{t('home.missing')}</span>}
              </button>
            </li>
          ))}
        </ul>
      </section>
      <footer className="muted small center-text">v{state.version}</footer>
      {dialog === 'open' && <FolderPicker mode="open" onClose={() => setDialog(null)} onPick={(p) => open(p)} />}
      {dialog === 'new' && <NewProject onClose={() => setDialog(null)} onCreated={onOpened} />}
    </div>
  )
}
