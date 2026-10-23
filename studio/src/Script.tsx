import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { completionKeymap } from '@codemirror/autocomplete'
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands'
import { bracketMatching } from '@codemirror/language'
import { forceLinting, linter, lintGutter, type Diagnostic } from '@codemirror/lint'
import { highlightSelectionMatches, searchKeymap } from '@codemirror/search'
import { EditorState } from '@codemirror/state'
import {
  drawSelection,
  EditorView,
  highlightActiveLine,
  highlightActiveLineGutter,
  highlightSpecialChars,
  keymap,
  lineNumbers,
} from '@codemirror/view'
import { api, ApiError, type Issue, type ScriptFile, type ScriptMeta } from './api'
import { useI18n } from './i18n'
import { anchorDecorations, completions, external, language, protectIds, theme } from './scriptLang'

// 没保存的修改：切到别的章节、别的页面再回来还在；关页面前提醒
const drafts = new Map<string, { text: string; base: string }>()
window.addEventListener('beforeunload', (e) => {
  if (drafts.size) e.preventDefault()
})

interface Conflict {
  text: string
  version: string
}

function readParams() {
  const q = new URLSearchParams(location.hash.split('?')[1] ?? '')
  return { file: q.get('file'), line: Number(q.get('line')) || 0 }
}

export default function Script() {
  const { t, lang } = useI18n()
  const [files, setFiles] = useState<ScriptFile[]>([])
  const [path, setPath] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)
  const [issues, setIssues] = useState<Issue[]>([])
  const [notice, setNotice] = useState<{ text: string; kind: 'ok' | 'warn' | 'bad' } | null>(null)
  const [conflict, setConflict] = useState<Conflict | null>(null)
  const [saving, setSaving] = useState(false)
  const [newTitle, setNewTitle] = useState('')

  const host = useRef<HTMLDivElement>(null)
  const view = useRef<EditorView | null>(null)
  const meta = useRef<ScriptMeta | null>(null)
  const cur = useRef({ path: null as string | null, base: '', saved: '' })
  const langRef = useRef(lang)
  langRef.current = lang
  const tRef = useRef(t)
  tRef.current = t
  const saveRef = useRef(() => {})
  const jump = useRef(readParams().line)

  const say = useCallback((text: string, kind: 'ok' | 'warn' | 'bad' = 'ok') => {
    setNotice({ text, kind })
    window.setTimeout(() => setNotice((n) => (n?.text === text ? null : n)), kind === 'ok' ? 2500 : 8000)
  }, [])

  const loadFiles = useCallback(() => api.scripts().then((r) => setFiles(r.files)).catch((e: Error) => say(e.message, 'bad')), [say])

  // 编辑器只建一次；换章节时换 state。这里用到的都走 ref，切换界面语言不会重建编辑器
  const makeState = useCallback(
    (doc: string) =>
      EditorState.create({
        doc,
        extensions: [
          lineNumbers(),
          highlightActiveLineGutter(),
          highlightSpecialChars(),
          history(),
          drawSelection(),
          highlightActiveLine(),
          bracketMatching(),
          highlightSelectionMatches(),
          EditorView.lineWrapping,
          language,
          theme,
          anchorDecorations,
          protectIds(() => say(tRef.current('script.blocked'), 'warn')),
          completions(() => meta.current),
          lintGutter(),
          linter(
            async (v): Promise<Diagnostic[]> => {
              const p = cur.current.path
              if (!p) return []
              const text = v.state.doc.toString()
              const res = await api.lintScript(p, text, langRef.current).catch(() => null)
              if (!res || v.state.doc.toString() !== text) return []
              setIssues(res.issues)
              return res.issues.map((i) => {
                const line = v.state.doc.line(Math.min(Math.max(i.line, 1), v.state.doc.lines))
                return { from: line.from, to: line.to, severity: i.level, message: i.message }
              })
            },
            { delay: 500 },
          ),
          keymap.of([
            { key: 'Mod-s', preventDefault: true, run: () => (saveRef.current(), true) },
            indentWithTab,
            ...completionKeymap,
            ...searchKeymap,
            ...historyKeymap,
            ...defaultKeymap,
          ]),
          EditorView.updateListener.of((u) => {
            if (!u.docChanged || !cur.current.path) return
            const text = u.state.doc.toString()
            const d = text !== cur.current.saved
            setDirty(d)
            if (d) drafts.set(cur.current.path, { text, base: cur.current.base })
            else drafts.delete(cur.current.path)
          }),
        ],
      }),
    [say],
  )

  useEffect(() => {
    if (!host.current) return
    view.current = new EditorView({ state: makeState(''), parent: host.current })
    return () => view.current?.destroy()
  }, [makeState])

  const goLine = (n: number) => {
    const v = view.current
    if (!v || n < 1) return
    const line = v.state.doc.line(Math.min(n, v.state.doc.lines))
    v.dispatch({ selection: { anchor: line.from }, effects: EditorView.scrollIntoView(line.from, { y: 'center' }) })
    v.focus()
  }

  const show = useCallback(
    (p: string, text: string, base: string, saved: string) => {
      const v = view.current
      if (!v) return
      cur.current = { path: p, base, saved }
      v.setState(makeState(text))
      setDirty(text !== saved)
      setConflict(null)
      setIssues([])
      forceLinting(v)
      if (jump.current) {
        const n = jump.current
        jump.current = 0
        window.setTimeout(() => goLine(n))
      }
    },
    [makeState],
  )

  const open = useCallback(
    (p: string) => {
      setPath(p)
      api
        .script(p)
        .then(({ file }) => {
          const draft = drafts.get(p)
          if (draft) {
            show(p, draft.text, draft.base, file.text)
            if (draft.base !== file.version) setConflict({ text: file.text, version: file.version })
          } else show(p, file.text, file.version, file.text)
        })
        .catch((e: Error) => say(e.message, 'bad'))
    },
    [show, say],
  )

  // 首次进来：拿名字表、章节列表，打开地址里指定的或第一章
  useEffect(() => {
    api.scriptMeta().then((m) => (meta.current = m)).catch(() => {})
    api
      .scripts()
      .then((r) => {
        setFiles(r.files)
        const want = readParams().file
        const first = (want && r.files.find((f) => f.path === want)?.path) || r.files[0]?.path
        if (first) open(first)
      })
      .catch((e: Error) => say(e.message, 'bad'))
  }, [open, say])

  // 外面（AI、别的编辑器）改了文件：没改动时直接载入，有改动时提示冲突
  useEffect(() => {
    const id = window.setInterval(() => {
      const c = cur.current
      if (!c.path || saving) return
      api
        .script(c.path)
        .then(({ file }) => {
          if (file.path !== cur.current.path || file.version === cur.current.base) return
          const v = view.current
          if (!v) return
          if (v.state.doc.toString() === cur.current.saved) {
            cur.current = { path: file.path, base: file.version, saved: file.text }
            v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: file.text }, annotations: external.of(true) })
            say(t('script.remote'), 'warn')
            loadFiles()
          } else setConflict({ text: file.text, version: file.version })
        })
        .catch(() => {})
    }, 3000)
    return () => window.clearInterval(id)
  }, [saving, say, t, loadFiles])

  const save = async (force = false) => {
    const v = view.current
    const c = cur.current
    if (!v || !c.path) return false
    const text = v.state.doc.toString()
    setSaving(true)
    try {
      const r = await api.saveScript(c.path, text, c.base, force)
      cur.current = { path: c.path, base: r.version, saved: text }
      drafts.delete(c.path)
      setDirty(false)
      setConflict(null)
      if (r.removed.length) say(t('script.removed', { n: r.removed.length, ids: r.removed.slice(0, 6).join(', ') }), 'warn')
      else say(t('script.saved'))
      loadFiles()
      return true
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && e.data.conflict) setConflict(e.data.conflict as Conflict)
      else say((e as Error).message, 'bad')
      return false
    } finally {
      setSaving(false)
    }
  }

  saveRef.current = () => {
    save()
  }

  const useTheirs = () => {
    const c = cur.current
    if (!conflict || !c.path) return
    drafts.delete(c.path)
    show(c.path, conflict.text, conflict.version, conflict.text)
  }

  const assignIds = async () => {
    if (dirty && !(await save())) return
    try {
      const r = await api.assignIds(lang)
      say(r.message)
      const p = cur.current.path
      if (p) {
        const { file } = await api.script(p)
        show(p, file.text, file.version, file.text)
      }
      loadFiles()
    } catch (e) {
      say((e as Error).message, 'bad')
    }
  }

  const addChapter = (e: FormEvent) => {
    e.preventDefault()
    const title = newTitle.trim()
    if (!title) return
    api
      .newChapter(title)
      .then((r) => {
        setNewTitle('')
        loadFiles()
        open(r.path)
      })
      .catch((err: Error) => say(err.message, 'bad'))
  }

  const errors = issues.filter((i) => i.level === 'error').length
  return (
    <div className="script">
      <aside className="script-files">
        <h2>{t('script.files')}</h2>
        {!files.length && <p className="muted small">{t('script.empty')}</p>}
        <ul>
          {files.map((f) => (
            <li key={f.path}>
              <button className={f.path === path ? 'chapter on' : 'chapter'} onClick={() => f.path !== path && open(f.path)}>
                <span className="num">{f.number}</span>
                <span className="name">
                  {f.title || f.path}
                  <small className="muted">
                    {t('script.lines', { n: f.lines })}
                    {f.errors > 0 && <b className="e"> · {f.errors} ✗</b>}
                    {f.warnings > 0 && <b className="w"> · {f.warnings} !</b>}
                  </small>
                </span>
                {(drafts.has(f.path) || (f.path === path && dirty)) && <span className="dot" title={t('script.draft')} />}
              </button>
            </li>
          ))}
        </ul>
        <form className="newch" onSubmit={addChapter}>
          <input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder={t('script.newPh')} />
          <button className="ghost" disabled={!newTitle.trim()}>
            {t('script.new')}
          </button>
        </form>
        <button className="ghost wide" onClick={assignIds} title={t('script.idsHint')}>
          {t('script.ids')}
        </button>
        <p className="muted small help">{t('script.help')}</p>
      </aside>
      <section className="script-main">
        <div className="editor-bar">
          <code className="mono">{path ?? ''}</code>
          <span className={dirty ? 'state unsaved' : 'state'}>{saving ? t('script.saving') : dirty ? t('script.unsaved') : t('script.saved')}</span>
          {notice && <span className={`notice ${notice.kind}`}>{notice.text}</span>}
          <div className="spacer" />
          <button className="primary" disabled={!dirty || saving || !path} onClick={() => save()}>
            {t('script.save')}
          </button>
        </div>
        {conflict && (
          <div className="conflict">
            <span>{t('script.conflict')}</span>
            <div className="spacer" />
            <button className="ghost" onClick={useTheirs}>
              {t('script.useTheirs')}
            </button>
            <button className="ghost" onClick={() => save(true)}>
              {t('script.useMine')}
            </button>
          </div>
        )}
        <div className="editor" ref={host} />
        <div className="issues">
          <header>
            <b>{t('script.issues')}</b>
            <span className="muted small">
              {issues.length ? t('script.counts', { e: errors, w: issues.length - errors }) : t('script.noIssues')}
            </span>
          </header>
          <ul>
            {issues.map((i, n) => (
              <li key={n}>
                <button className={`issue ${i.level}`} onClick={() => goLine(i.line)}>
                  <span className="where">{i.line ? t('script.line', { n: i.line }) : '—'}</span>
                  <span>{i.message}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  )
}
