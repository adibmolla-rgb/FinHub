// External links. The desktop webview drops target="_blank" clicks without a sound, so news headlines,
// filings and websites did nothing there. One listener sends them all to the default browser instead.
import { openUrl } from '@tauri-apps/plugin-opener'
import { inDesktopApp } from './tauri'

/** The address to open in a browser for a clicked element, or null if the click isn't an external link. */
export function externalHref(target: EventTarget | null): string | null {
  const link = target instanceof Element ? target.closest('a[href]') : null
  if (!link) return null
  const href = link.getAttribute('href') ?? ''
  return /^https?:\/\//i.test(href) ? href : null
}

export function openExternalLinksInBrowser(): () => void {
  if (!inDesktopApp) return () => {}
  const onClick = (e: MouseEvent) => {
    const href = externalHref(e.target)
    if (!href) return
    e.preventDefault()
    openUrl(href).catch((err) => console.error('Could not open link', err))
  }
  document.addEventListener('click', onClick)
  return () => document.removeEventListener('click', onClick)
}
