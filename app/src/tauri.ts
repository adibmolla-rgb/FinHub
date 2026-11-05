// Bridge to the desktop shell. In a plain browser (dev, or the future web build) these are no-ops.
import { invoke } from '@tauri-apps/api/core'

export type BackendPhase = {
  phase: 'starting' | 'preparing' | 'launching' | 'running' | 'external' | 'failed'
  detail: string
  logs_dir: string | null
}

export const inDesktopApp = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

export async function backendPhase(): Promise<BackendPhase | null> {
  if (!inDesktopApp) return null
  try {
    return await invoke<BackendPhase>('backend_phase')
  } catch {
    return null
  }
}
