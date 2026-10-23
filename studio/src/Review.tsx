import { useEffect, useState } from 'react'
import { api } from './api'
import { useI18n } from './i18n'

// 审核页还是 replay preview 那几页，嵌在 Studio 里（?embed 时不显示回首页的链接）
const PAGES = [
  ['voices', '/voices'],
  ['voice', '/review/voice'],
  ['art', '/review/art'],
  ['music', '/review/music'],
  ['player', '/player'],
] as const

type Page = (typeof PAGES)[number][0]

/** 任务里的审核页地址（/review/art）→ Studio 里的地址（#/review?page=art） */
export function reviewHash(page?: string) {
  const hit = PAGES.find(([, href]) => href === page)
  return hit ? `#/review?page=${hit[0]}` : null
}

export default function Review({ page }: { page: string | null }) {
  const { t } = useI18n()
  const key: Page = PAGES.find(([k]) => k === page)?.[0] ?? 'voices'
  const href = PAGES.find(([k]) => k === key)![1]
  const [playerBuilt, setPlayerBuilt] = useState<boolean | null>(null)

  useEffect(() => {
    if (key !== 'player') return
    setPlayerBuilt(null)
    api
      .playerBuilt()
      .then((r) => setPlayerBuilt(r.built))
      .catch(() => setPlayerBuilt(false))
  }, [key])

  return (
    <div className="review">
      <nav className="tabs">
        {PAGES.map(([k]) => (
          <a key={k} href={`#/review?page=${k}`} className={k === key ? 'on' : ''}>
            {t(`review.${k}`)}
          </a>
        ))}
        <div className="spacer" />
        <a className="newtab" href={href} target="_blank" rel="noreferrer">
          {t('review.newTab')} ↗
        </a>
      </nav>
      <p className="muted small">{t(`review.${key}D`)}</p>
      {key === 'player' && playerBuilt === false ? (
        <p className="empty-frame muted">{t('review.noPlayer')}</p>
      ) : key === 'player' && playerBuilt === null ? null : (
        <iframe key={key} className="frame" src={key === 'player' ? href : `${href}?embed=1`} title={t(`review.${key}`)} />
      )}
    </div>
  )
}
