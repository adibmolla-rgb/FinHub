// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@tauri-apps/plugin-opener', () => ({ openUrl: vi.fn() }))

class FakeElement {
  href: string | null
  constructor(href: string | null) {
    this.href = href
  }
  closest() {
    return this.href === null ? null : { getAttribute: () => this.href }
  }
}

describe('external links', () => {
  beforeEach(() => vi.stubGlobal('Element', FakeElement))
  afterEach(() => vi.unstubAllGlobals())

  it('only treats real web addresses as external', async () => {
    const { externalHref } = await import('./links')
    const click = (href: string | null) => externalHref(new FakeElement(href) as unknown as EventTarget)
    expect(click('https://www.sec.gov/a.htm')).toBe('https://www.sec.gov/a.htm')
    expect(click('HTTP://example.com')).toBe('HTTP://example.com')
    expect(click(null)).toBeNull()
    expect(click('#section')).toBeNull()
    expect(click('/local')).toBeNull()
    expect(click('javascript:alert(1)')).toBeNull()
    expect(click('file:///C:/secret.txt')).toBeNull()
    expect(externalHref(null)).toBeNull()
  })
})
