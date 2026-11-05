import { describe, expect, it } from 'vitest'
import { runCommand } from '../commands'
import { ALL_LESSONS, TRACKS } from './index'
import { parse } from './parse'

describe('course markdown parser', () => {
  it('parses headings, paragraphs, lists, code, callouts and tables', () => {
    const blocks = parse([
      '## Title',
      'A paragraph',
      'that continues.',
      '',
      '- one',
      '- two',
      '  continued',
      '1. first',
      '2. second',
      '~~~python',
      'x = 1',
      '',
      'y = 2',
      '~~~',
      '> A callout',
      '| a | b |',
      '|---|---|',
      '| 1 | 2 |',
    ].join('\n'))
    expect(blocks).toEqual([
      { type: 'h', level: 2, text: 'Title' },
      { type: 'p', text: 'A paragraph that continues.' },
      { type: 'ul', items: ['one', 'two continued'] },
      { type: 'ol', items: ['first', 'second'] },
      { type: 'code', lang: 'python', text: 'x = 1\n\ny = 2' },
      { type: 'callout', text: 'A callout' },
      { type: 'table', head: ['a', 'b'], rows: [['1', '2']] },
    ])
  })

  it('terminates on an unclosed code fence', () => {
    expect(parse('~~~\ncode')).toEqual([{ type: 'code', lang: '', text: 'code' }])
  })
})

describe('curriculum integrity', () => {
  it('has unique track and lesson ids', () => {
    const tracks = TRACKS.map((t) => t.id)
    const lessons = ALL_LESSONS.map((x) => x.lesson.id)
    expect(new Set(tracks).size).toBe(tracks.length)
    expect(new Set(lessons).size).toBe(lessons.length)
    for (const t of TRACKS) expect(t.lessons.length).toBeGreaterThan(0)
  })

  it.each(ALL_LESSONS.map((x) => [x.lesson.id, x] as const))('%s is well formed', (_id, { lesson }) => {
    expect(lesson.title.trim()).not.toBe('')
    expect(lesson.minutes).toBeGreaterThan(0)
    const blocks = parse(lesson.body)
    expect(blocks.length).toBeGreaterThan(2)
    // Tables have consistent column counts.
    for (const b of blocks) if (b.type === 'table') for (const r of b.rows) expect(r.length).toBe(b.head.length)
    // No fence left open: an unbalanced ~~~ would swallow the rest of the lesson into a code block.
    expect((lesson.body.match(/^~~~/gm) ?? []).length % 2).toBe(0)
    for (const q of lesson.quiz ?? []) {
      expect(q.options.length).toBeGreaterThanOrEqual(2)
      expect(Number.isInteger(q.answer) && q.answer >= 0 && q.answer < q.options.length).toBe(true)
      expect(q.why.trim()).not.toBe('')
    }
    for (const t of lesson.tryIt ?? []) {
      const r = runCommand(t.command)
      expect(r.kind, `${t.command}: ${r.message}`).not.toBe('error')
    }
    for (const r of lesson.resources ?? []) expect(r.url).toMatch(/^https:\/\//)
    for (const m of lesson.body.matchAll(/\]\(([^)]+)\)/g)) expect(m[1]).toMatch(/^https:\/\//)
  })
})
