import type { ReactNode } from 'react'
import { parse } from './parse'

// A small Markdown subset for course text, rendered to React elements (no HTML injection):
//   # / ## / ### headings, paragraphs, - or * bullets, 1. numbered lists, ``` fenced code ```,
//   > callouts, | pipe | tables |, and inline **bold**, *italic*, `code`, [links](https://…).

/** Inline formatting: **bold**, *italic*, `code`, [text](https://url). */
function inline(text: string): ReactNode[] {
  const out: ReactNode[] = []
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^)\s]+\)|\*[^*\s][^*]*\*)/g
  let last = 0
  let m: RegExpExecArray | null
  let k = 0
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const t = m[0]
    if (t.startsWith('**')) out.push(<strong key={k++}>{t.slice(2, -2)}</strong>)
    else if (t.startsWith('`')) out.push(<code key={k++}>{t.slice(1, -1)}</code>)
    else if (t.startsWith('[')) {
      const mm = t.match(/^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/)!
      out.push(<a key={k++} href={mm[2]} target="_blank" rel="noreferrer">{mm[1]}</a>)
    } else out.push(<em key={k++}>{t.slice(1, -1)}</em>)
    last = m.index + t.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

export function Markdown({ src }: { src: string }) {
  return (
    <div className="md">
      {parse(src).map((b, i) => {
        switch (b.type) {
          case 'h':
            return b.level === 1 ? <h2 key={i}>{inline(b.text)}</h2> : b.level === 2 ? <h3 key={i}>{inline(b.text)}</h3> : <h4 key={i}>{inline(b.text)}</h4>
          case 'p':
            return <p key={i}>{inline(b.text)}</p>
          case 'ul':
            return <ul key={i}>{b.items.map((it, j) => <li key={j}>{inline(it)}</li>)}</ul>
          case 'ol':
            return <ol key={i}>{b.items.map((it, j) => <li key={j}>{inline(it)}</li>)}</ol>
          case 'code':
            return <pre key={i} className="md__code" data-lang={b.lang}><code>{b.text}</code></pre>
          case 'callout':
            return <div key={i} className="md__callout">{inline(b.text)}</div>
          case 'table':
            return (
              <div key={i} className="md__table">
                <table className="table">
                  <thead><tr>{b.head.map((c, j) => <th key={j}>{inline(c)}</th>)}</tr></thead>
                  <tbody>{b.rows.map((r, j) => <tr key={j}>{r.map((c, k) => <td key={k}>{inline(c)}</td>)}</tr>)}</tbody>
                </table>
              </div>
            )
        }
      })}
    </div>
  )
}
