// A small Markdown subset for course text: see markdown.tsx for the rendering side.

export type Block =
  | { type: 'h'; level: 1 | 2 | 3; text: string }
  | { type: 'p'; text: string }
  | { type: 'ul' | 'ol'; items: string[] }
  | { type: 'code'; lang: string; text: string }
  | { type: 'callout'; text: string }
  | { type: 'table'; head: string[]; rows: string[][] }

export function parse(src: string): Block[] {
  const lines = src.replace(/\r\n/g, '\n').split('\n')
  const blocks: Block[] = []
  let i = 0
  // Code fences may be ``` or ~~~ (course text lives in JS template strings, where ~~~ needs no escaping).
  const isSpecial = (l: string) => /^(#{1,3}\s|```|~~~|>\s?|\s*[-*]\s|\s*\d+\.\s|\|)/.test(l)
  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) {
      i++
      continue
    }
    const h = line.match(/^(#{1,3})\s+(.*)$/)
    if (h) {
      blocks.push({ type: 'h', level: h[1].length as 1 | 2 | 3, text: h[2].trim() })
      i++
      continue
    }
    if (line.startsWith('```') || line.startsWith('~~~')) {
      const fence = line.slice(0, 3)
      const lang = line.slice(3).trim()
      const body: string[] = []
      i++
      while (i < lines.length && !lines[i].startsWith(fence)) body.push(lines[i++])
      i++ // closing fence
      blocks.push({ type: 'code', lang, text: body.join('\n') })
      continue
    }
    if (/^>\s?/.test(line)) {
      const body: string[] = []
      while (i < lines.length && /^>\s?/.test(lines[i])) body.push(lines[i++].replace(/^>\s?/, ''))
      blocks.push({ type: 'callout', text: body.join(' ') })
      continue
    }
    if (line.startsWith('|')) {
      const rows: string[][] = []
      while (i < lines.length && lines[i].startsWith('|')) {
        const cells = lines[i].trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
        if (!cells.every((c) => /^:?-{2,}:?$/.test(c))) rows.push(cells) // skip the --- separator row
        i++
      }
      blocks.push({ type: 'table', head: rows[0] ?? [], rows: rows.slice(1) })
      continue
    }
    const bullet = /^\s*[-*]\s+/
    const numbered = /^\s*\d+\.\s+/
    if (bullet.test(line) || numbered.test(line)) {
      const re = bullet.test(line) ? bullet : numbered
      const items: string[] = []
      while (i < lines.length && re.test(lines[i])) {
        let item = lines[i++].replace(re, '')
        // continuation lines (indented, not a new item)
        while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !re.test(lines[i])) item += ' ' + lines[i++].trim()
        items.push(item)
      }
      blocks.push({ type: re === bullet ? 'ul' : 'ol', items })
      continue
    }
    const para: string[] = []
    while (i < lines.length && lines[i].trim() && !isSpecial(lines[i])) para.push(lines[i++].trim())
    blocks.push({ type: 'p', text: para.join(' ') })
  }
  return blocks
}
