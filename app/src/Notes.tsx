import { useEffect, useState } from 'react'
import { notesApi, timeAgo, type Note, type NoteSummary } from './api'
import { Panel } from './components'

/** Past ASK / BT / DEBATE runs, read from disk: question, answer and the full tool trace. */
export function NotesWorkspace({ onRerun }: { onRerun: (command: string) => void }) {
  const [list, setList] = useState<NoteSummary[] | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [note, setNote] = useState<Note | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    notesApi.list().then((l) => {
      setList(l)
      if (l.length) setSelected(l[0].id)
    }, (e) => setError(String(e.message ?? e)))
  }, [])

  useEffect(() => {
    if (!selected) return
    notesApi.get(selected).then(setNote, (e) => setError(String(e.message ?? e)))
  }, [selected])

  const rerun = note ? `${note.kind.toUpperCase()} ${note.title.replace(/^[A-Z]+:\s*/, '')}` : ''

  return (
    <main className="grid grid--notes">
      <Panel code="NOTES" title={`Research history${list ? ` · ${list.length}` : ''}`} className="grid__noteslist">
        {error && <p className="bad small">{error}</p>}
        {list && !list.length && <p className="muted">No agent runs yet. Try ASK, BT or DEBATE.</p>}
        <ol className="notes">
          {list?.map((n) => (
            <li key={n.id}>
              <button className={`note ${selected === n.id ? 'note--on' : ''}`} onClick={() => setSelected(n.id)}>
                <span className="note__title">{n.title}</span>
                <span className="muted small">{timeAgo(n.created_at)} · <span className={n.status === 'completed' ? 'ok' : n.status === 'failed' ? 'bad' : 'warn'}>{n.status}</span></span>
                {n.preview && !n.preview.startsWith('Execution failed') && <span className="muted small note__preview">{n.preview}</span>}
              </button>
            </li>
          ))}
        </ol>
      </Panel>
      <Panel code="ANS" title={note?.title ?? 'Answer'} className="grid__notesans">
        {note ? (
          <div className="stack">
            <div className="ticket">
              <span className="muted small">{new Date(note.created_at).toLocaleString()}</span>
              <button className="chip" onClick={() => onRerun(rerun)}>Run again</button>
            </div>
            {note.error && <p className="bad small">{note.error}</p>}
            {/* On failure the agent also stores "Execution failed: <error>" as its answer; don't show it twice. */}
            {note.answer && !(note.error && note.answer.startsWith('Execution failed')) ? (
              <div className="answer">{note.answer}</div>
            ) : (
              !note.error && <p className="muted">No answer was recorded.</p>
            )}
            <details>
              <summary className="muted small">Prompt sent to the agent</summary>
              <pre className="agent-prompt">{note.prompt}</pre>
            </details>
          </div>
        ) : <p className="muted">Select a run.</p>}
      </Panel>
      <Panel code="TRACE" title={`Reasoning trace${note ? ` · ${note.steps.length} steps` : ''}`} className="grid__notestrace">
        {note && !note.steps.length && <p className="muted">No tool calls were recorded for this run.</p>}
        <ol className="trace">
          {note?.steps.map((s, i) => (
            <li key={s.id + i} className={`trace__step trace__step--${s.status}`}>
              <div className="trace__head"><span className="trace__n">{i + 1}</span><code>{s.tool}</code><span className="muted">{s.status}</span></div>
              {Object.keys(s.args).length > 0 && <pre className="trace__args">{JSON.stringify(s.args, null, 1)}</pre>}
              {s.preview && <pre className="trace__result">{s.preview}</pre>}
            </li>
          ))}
        </ol>
      </Panel>
    </main>
  )
}
