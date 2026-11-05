import { useEffect, useMemo, useState } from 'react'
import { Panel } from '../components'
import { Markdown } from './markdown'
import { ALL_LESSONS, TRACKS, findLesson } from './index'
import type { Lesson, QuizQuestion, Track } from './types'

const PROGRESS_KEY = 'finhub.learn.progress'
const LAST_KEY = 'finhub.learn.last'

// Progress lives only in this browser/app (localStorage). Storage can be unavailable (private windows,
// blocked site data), so every access is wrapped and the page works without it.
function loadProgress(): Set<string> {
  try {
    const raw = localStorage.getItem(PROGRESS_KEY)
    const ids = raw ? (JSON.parse(raw) as unknown) : []
    return new Set(Array.isArray(ids) ? ids.filter((x): x is string => typeof x === 'string') : [])
  } catch {
    return new Set()
  }
}
function saveProgress(done: Set<string>) {
  try { localStorage.setItem(PROGRESS_KEY, JSON.stringify([...done])) } catch { /* not persisted */ }
}
function loadLast(): string | null {
  try { return localStorage.getItem(LAST_KEY) } catch { return null }
}
function saveLast(id: string | null) {
  try { if (id) localStorage.setItem(LAST_KEY, id); else localStorage.removeItem(LAST_KEY) } catch { /* not persisted */ }
}

function Quiz({ questions }: { questions: QuizQuestion[] }) {
  const [picked, setPicked] = useState<Record<number, number>>({})
  const correct = questions.filter((q, i) => picked[i] === q.answer).length
  const answered = Object.keys(picked).length
  return (
    <div className="quiz">
      <h3 className="subhead">Check yourself</h3>
      {questions.map((q, i) => {
        const p = picked[i]
        return (
          <div key={i} className="quiz__q">
            <p><strong>{i + 1}.</strong> {q.q}</p>
            <div className="quiz__options">
              {q.options.map((o, j) => {
                const state = p === undefined ? '' : j === q.answer ? 'quiz__opt--right' : j === p ? 'quiz__opt--wrong' : ''
                return (
                  <button key={j} className={`quiz__opt ${state}`} disabled={p !== undefined} onClick={() => setPicked({ ...picked, [i]: j })}>
                    {o}
                  </button>
                )
              })}
            </div>
            {p !== undefined && (
              <p className={p === q.answer ? 'ok small' : 'bad small'}>
                {p === q.answer ? 'Correct. ' : 'Not quite. '}<span className="muted">{q.why}</span>
              </p>
            )}
          </div>
        )
      })}
      {answered === questions.length && (
        <p className="small">
          {correct}/{questions.length} correct.{' '}
          <button className="link" onClick={() => setPicked({})}>Try again</button>
        </p>
      )}
    </div>
  )
}

function Roadmap({ done, onOpen }: { done: Set<string>; onOpen: (id: string) => void }) {
  const total = ALL_LESSONS.length
  const complete = ALL_LESSONS.filter((x) => done.has(x.lesson.id)).length
  const next = ALL_LESSONS.find((x) => !done.has(x.lesson.id))
  const hours = Math.round(ALL_LESSONS.reduce((s, x) => s + x.lesson.minutes, 0) / 60)
  return (
    <div className="stack learn__roadmap">
      <h2 className="learn__h">Learn quant finance from zero</h2>
      <p>
        No background needed. This course explains what quantitative finance is, how markets and trading work, the maths
        and programming you need, the methods quants actually use, and how to get a job in the industry. Each lesson links
        to a FinHub tool so you can try the idea straight away.
      </p>
      <div className="learn__progress" aria-label={`${complete} of ${total} lessons complete`}>
        <div className="learn__bar"><div style={{ width: `${(100 * complete) / total}%` }} /></div>
        <span className="small muted">{complete}/{total} lessons · about {hours} hours of reading, plus practice</span>
      </div>
      {next && (
        <p>
          <button className="btn btn--buy learn__cta" onClick={() => onOpen(next.lesson.id)}>
            {complete === 0 ? 'Start the first lesson' : 'Continue'}: {next.lesson.title}
          </button>
        </p>
      )}
      <ol className="learn__tracks">
        {TRACKS.map((t, i) => {
          const n = t.lessons.filter((l) => done.has(l.id)).length
          return (
            <li key={t.id}>
              <button className="learn__track" onClick={() => onOpen(t.lessons[0].id)}>
                <span className="learn__num">{i + 1}</span>
                <span>
                  <strong>{t.title}</strong>
                  {t.access === 'premium' && <span className="learn__premium">premium</span>}
                  <br /><span className="muted small">{t.description}</span>
                </span>
                <span className="small muted learn__count">{n}/{t.lessons.length}</span>
              </button>
            </li>
          )
        })}
      </ol>
      <p className="muted small">
        Your progress is saved on this device only. Nothing here is financial advice; it is education about how markets and
        quantitative methods work.
      </p>
    </div>
  )
}

function LessonView({ track, lesson, done, onToggle, onOpen, onRun, canRun }: {
  track: Track; lesson: Lesson; done: Set<string>; onToggle: () => void; onOpen: (id: string | null) => void
  onRun?: (command: string) => void; canRun?: (command: string) => boolean
}) {
  const index = ALL_LESSONS.findIndex((x) => x.lesson.id === lesson.id)
  const prev = ALL_LESSONS[index - 1]
  const next = ALL_LESSONS[index + 1]
  const isDone = done.has(lesson.id)
  // Premium content: this is where an access check would go once paid courses exist.
  return (
    <article className="stack learn__lesson">
      <p className="small muted">
        <button className="link" onClick={() => onOpen(null)}>Roadmap</button> / {track.title} · lesson {track.lessons.indexOf(lesson) + 1} of {track.lessons.length} · {lesson.minutes} min
      </p>
      <h2 className="learn__h">{lesson.title}</h2>
      <p className="muted">{lesson.summary}</p>
      <Markdown src={lesson.body} />
      {lesson.tryIt && lesson.tryIt.length > 0 && (
        <div className="learn__try">
          <h3 className="subhead">Try it in FinHub</h3>
          {lesson.tryIt.map((t) => (
            <button key={t.command} className="chip" onClick={() => onRun?.(t.command)} disabled={!onRun}>
              <span className="ok">›</span> {t.command} <span className="muted">· {t.label}</span>
              {canRun && !canRun(t.command) && <span className="learn__desk"> · desktop app</span>}
            </button>
          ))}
        </div>
      )}
      {lesson.quiz && lesson.quiz.length > 0 && <Quiz key={lesson.id} questions={lesson.quiz} />}
      {lesson.resources && lesson.resources.length > 0 && (
        <div>
          <h3 className="subhead">Go further</h3>
          <ul className="learn__res">
            {lesson.resources.map((r) => (
              <li key={r.url}>
                <a href={r.url} target="_blank" rel="noreferrer">{r.title}</a>
                {r.free && <span className="ok small"> free</span>}
                {r.note && <span className="muted small"> · {r.note}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="learn__nav">
        {prev ? <button className="chip" onClick={() => onOpen(prev.lesson.id)}>← {prev.lesson.title}</button> : <span />}
        <button className={`chip ${isDone ? 'chip--on' : ''}`} onClick={onToggle}>{isDone ? '✓ Completed' : 'Mark complete'}</button>
        {next ? (
          <button className="chip" onClick={() => { if (!isDone) onToggle(); onOpen(next.lesson.id) }}>{next.lesson.title} →</button>
        ) : (
          <button className="chip" onClick={() => { if (!isDone) onToggle(); onOpen(null) }}>Finish → roadmap</button>
        )}
      </div>
    </article>
  )
}

export function LearnWorkspace({ onRun, canRun }: { onRun?: (command: string) => void; canRun?: (command: string) => boolean }) {
  const [done, setDone] = useState<Set<string>>(loadProgress)
  const [current, setCurrent] = useState<string | null>(() => {
    const last = loadLast()
    return last && findLesson(last) ? last : null
  })
  const found = useMemo(() => (current ? findLesson(current) : undefined), [current])

  useEffect(() => saveProgress(done), [done])
  useEffect(() => {
    saveLast(current)
    document.querySelector('.learn__main .panel__body')?.scrollTo({ top: 0 })
  }, [current])

  const toggle = (id: string) => setDone((d) => {
    const n = new Set(d)
    if (n.has(id)) n.delete(id); else n.add(id)
    return n
  })

  return (
    <main className="grid grid--learn">
      <Panel code="LEARN" title="Course" className="learn__side">
        <nav className="learn__toc">
          <button className={`learn__item ${current === null ? 'learn__item--on' : ''}`} onClick={() => setCurrent(null)}>Roadmap</button>
          {TRACKS.map((t, i) => (
            <div key={t.id}>
              <h3 className="subhead">{i + 1}. {t.title}</h3>
              {t.lessons.map((l) => (
                <button key={l.id} className={`learn__item ${current === l.id ? 'learn__item--on' : ''}`} onClick={() => setCurrent(l.id)}>
                  <span className={done.has(l.id) ? 'ok' : 'muted'}>{done.has(l.id) ? '✓' : '○'}</span> {l.title}
                </button>
              ))}
            </div>
          ))}
        </nav>
      </Panel>
      <Panel code={found ? found.track.id.toUpperCase() : 'START'} title={found ? found.lesson.title : 'Roadmap'} className="learn__main">
        {found ? (
          <LessonView
            track={found.track} lesson={found.lesson} done={done}
            onToggle={() => toggle(found.lesson.id)} onOpen={setCurrent} onRun={onRun} canRun={canRun}
          />
        ) : (
          <Roadmap done={done} onOpen={setCurrent} />
        )}
      </Panel>
    </main>
  )
}
