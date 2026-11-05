// Client for the local FinHub backend (backend/src/finhub_backend/server.py).

export const BACKEND_URL = import.meta.env.VITE_FINHUB_BACKEND_URL ?? 'http://127.0.0.1:8765'

export type Health = {
  status: string
  version: string
  python: string
  platform: string
}

export type EngineStatus = {
  id: string
  name: string
  role: string
  license: string
  homepage: string
  available: boolean
  version: string | null
  reason: string | null
}

export type Receipt = {
  label: string
  value: number
  unit: 'fraction' | 'percent' | 'bp' | 'currency' | 'shares' | 'ratio' | 'count'
  currency: string | null
  source: { provider: string; fetched_at: string; detail: string | null }
  formula: string | null
  inputs: Receipt[]
}

export type ReceiptExample = { note: string; receipt: Receipt }

async function get<T>(path: string, timeoutMs = 4000): Promise<T> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const res = await fetch(`${BACKEND_URL}${path}`, { signal: ctrl.signal })
    if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`)
    return (await res.json()) as T
  } finally {
    clearTimeout(timer)
  }
}

export const api = {
  health: () => get<Health>('/health', 2000),
  // Engine probes start each engine's own interpreter, so allow them longer.
  engines: (refresh = false) => get<EngineStatus[]>(refresh ? '/engines?refresh=true' : '/engines', 120_000),
  receiptExample: () => get<ReceiptExample>('/examples/receipt'),
}

export function formatValue(r: Pick<Receipt, 'value' | 'unit' | 'currency'>): string {
  switch (r.unit) {
    case 'fraction':
      return `${(r.value * 100).toFixed(2)}%`
    case 'percent':
      return `${r.value.toFixed(2)}%`
    case 'bp':
      return `${r.value.toFixed(0)} bp`
    case 'currency':
      return `${r.currency ?? ''} ${r.value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`.trim()
    default:
      return r.value.toLocaleString(undefined, { maximumFractionDigits: 4 })
  }
}
