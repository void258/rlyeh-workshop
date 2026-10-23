import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, isActive, type Job, type ProjectInfo, type StudioState } from './api'
import BoardPage from './Board'
import Home from './Home'
import { LangContext, saveLang, savedLang, toLang, translator, useI18n, type Lang } from './i18n'
import JobsPage from './Jobs'
import Review from './Review'

type Route = 'board' | 'jobs' | 'review'
const ROUTES: Route[] = ['board', 'jobs', 'review']

function readRoute(): { route: Route; id: string | null } {
  const [path, query] = location.hash.replace(/^#\/?/, '').split('?')
  return {
    route: ROUTES.includes(path as Route) ? (path as Route) : 'board',
    id: new URLSearchParams(query ?? '').get('id'),
  }
}

function useRoute() {
  const [route, setRoute] = useState(readRoute)
  useEffect(() => {
    const onHash = () => setRoute(readRoute())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  return route
}

// 后台任务列表：有任务在跑时每 2 秒刷一次，没有时 6 秒一次
function useJobs() {
  const [jobs, setJobs] = useState<Job[]>([])
  const load = useCallback(() => api.jobs().then((r) => setJobs(r.jobs)).catch(() => {}), [])
  const busy = jobs.some(isActive)
  useEffect(() => {
    load()
    const id = window.setInterval(load, busy ? 2000 : 6000)
    return () => window.clearInterval(id)
  }, [load, busy])
  return { jobs, reload: load }
}

function Shell({ project, onClosed }: { project: ProjectInfo; onClosed: () => void }) {
  const { t, lang, setLang } = useI18n()
  const { route, id } = useRoute()
  const { jobs, reload } = useJobs()
  const [focus, setFocus] = useState<string | null>(null)
  const running = jobs.find(isActive)

  const switchProject = () => {
    api.close().finally(() => {
      location.hash = ''
      onClosed()
    })
  }
  const started = (job: Job) => {
    setFocus(job.id)
    reload()
  }

  return (
    <div className="shell">
      <header className="top">
        <div className="brand">
          <span className="sigil">❖</span>
          <b>{t('brand')}</b>
          <span className="tag">{t('studio')}</span>
        </div>
        <div className="proj">
          <b>{project.title}</b>
          <small title={project.root}>{project.root}</small>
        </div>
        <div className="spacer" />
        <button className="ghost" onClick={() => setLang(lang === 'en' ? 'zh' : 'en')}>
          {t('lang.switch')}
        </button>
        <button className="ghost" onClick={switchProject}>
          {t('nav.switch')}
        </button>
      </header>
      <nav className="side">
        {ROUTES.map((r) => (
          <a key={r} href={`#/${r}`} className={route === r ? 'on' : ''}>
            {t(`nav.${r}`)}
            {r === 'jobs' && running && <span className="pulse" title={t('jobs.running')} />}
          </a>
        ))}
      </nav>
      <main className="content">
        {route === 'board' && <BoardPage jobs={jobs} focus={focus} onStarted={started} />}
        {route === 'jobs' && <JobsPage jobs={jobs} selected={id ?? focus ?? jobs[0]?.id ?? null} />}
        {route === 'review' && <Review />}
      </main>
    </div>
  )
}

export default function App() {
  const [state, setState] = useState<StudioState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [lang, setLangState] = useState<Lang>(() => savedLang() ?? toLang(navigator.language))
  const t = useMemo(() => translator(lang), [lang])

  const refresh = useCallback(() => {
    api
      .state()
      .then((s) => {
        setState(s)
        setError(null)
        if (!savedLang() && s.project) setLangState(toLang(s.project.lang))
      })
      .catch((e: Error) => setError(e.message))
  }, [])
  useEffect(refresh, [refresh])

  useEffect(() => {
    document.documentElement.lang = lang === 'en' ? 'en' : 'zh-CN'
    document.title = state?.project ? `${state.project.title} · ${t('brand')}` : `${t('brand')} ${t('studio')}`
  }, [lang, state, t])

  const setLang = (l: Lang) => {
    saveLang(l)
    setLangState(l)
  }

  return (
    <LangContext.Provider value={{ lang, t, setLang }}>
      {!state ? (
        <div className="center muted">{error ? t('error.generic', { err: error }) : t('loading')}</div>
      ) : state.project ? (
        <Shell key={state.project.root} project={state.project} onClosed={refresh} />
      ) : (
        <Home state={state} onOpened={refresh} />
      )}
    </LangContext.Provider>
  )
}
