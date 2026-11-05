import { useState } from 'react'
import { copyCsv } from './csv'

export function CopyCsvButton({ rows, label = 'Copy CSV' }: { rows: () => (string | number | null | undefined)[][]; label?: string }) {
  const [state, setState] = useState<'idle' | 'done' | 'failed'>('idle')
  return (
    <button
      className="chip"
      title="Copy as CSV (paste into Excel or Google Sheets)"
      onClick={() => copyCsv(rows()).then((ok) => { setState(ok ? 'done' : 'failed'); setTimeout(() => setState('idle'), 1500) })}
    >
      {state === 'done' ? 'Copied' : state === 'failed' ? 'Copy failed' : label}
    </button>
  )
}
