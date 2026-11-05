import { useCallback, useEffect, useState } from 'react'
import { ApiError, api, type Range } from './api'

export type Load<T> = { data: T | null; error: ApiError | Error | null; loading: boolean }
const idle = { data: null, error: null, loading: true }

function useLoad<T>(fetcher: () => Promise<T>, deps: unknown[]): Load<T> & { reload: () => void } {
  const [state, setState] = useState<Load<T>>(idle)
  const [nonce, setNonce] = useState(0)
  useEffect(() => {
    let live = true
    setState((s) => ({ ...s, loading: true, error: null }))
    fetcher().then(
      (data) => live && setState({ data, error: null, loading: false }),
      (error) => live && setState({ data: null, error, loading: false }),
    )
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce])
  return { ...state, reload: useCallback(() => setNonce((n) => n + 1), []) }
}

export function useTicker(symbol: string, range: Range) {
  const quote = useLoad(() => api.quote(symbol), [symbol])
  const history = useLoad(() => api.history(symbol, range), [symbol, range])
  const profile = useLoad(() => api.profile(symbol), [symbol])
  const news = useLoad(() => api.news(symbol), [symbol])
  const reload = () => [quote, history, profile, news].forEach((l) => l.reload())
  return { quote, history, profile, news, reload }
}

