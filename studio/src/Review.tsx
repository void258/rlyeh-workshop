import { useI18n } from './i18n'

const PAGES = [
  ['voices', '/voices'],
  ['voice', '/review/voice'],
  ['art', '/review/art'],
  ['music', '/review/music'],
  ['player', '/player'],
] as const

export default function Review() {
  const { t } = useI18n()
  return (
    <div className="review">
      <h2>{t('review.title')}</h2>
      <p className="muted">{t('review.hint')}</p>
      <div className="cards">
        {PAGES.map(([key, href]) => (
          <a key={key} className="card" href={href} target="_blank" rel="noreferrer">
            <b>{t(`review.${key}`)} ↗</b>
            <span>{t(`review.${key}D`)}</span>
          </a>
        ))}
      </div>
    </div>
  )
}
