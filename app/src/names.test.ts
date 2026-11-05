import { readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

// Windows and macOS file systems ignore case, so foo.ts and Foo.tsx are the same module there and
// imports silently resolve to the wrong one. This has broken the desktop build twice; keep it out.
function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f)
    return statSync(p).isDirectory() ? files(p) : [p]
  })
}

describe('source file names', () => {
  it('no two modules differ only by letter case or .ts/.tsx', () => {
    const root = join(__dirname)
    const keys = files(root)
      .filter((f) => /\.tsx?$/.test(f))
      .map((f) => relative(root, f).replace(/\.tsx?$/, '').toLowerCase())
    const dupes = keys.filter((k, i) => keys.indexOf(k) !== i)
    expect(dupes).toEqual([])
  })
})
