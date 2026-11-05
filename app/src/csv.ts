// Tables to CSV, for pasting into Excel or Google Sheets.

export function toCsv(rows: (string | number | null | undefined)[][]): string {
  const cell = (v: string | number | null | undefined) => {
    if (v == null) return ''
    const s = typeof v === 'number' ? (Number.isFinite(v) ? String(v) : '') : v
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  return rows.map((r) => r.map(cell).join(',')).join('\n')
}

export async function copyCsv(rows: (string | number | null | undefined)[][]): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(toCsv(rows))
    return true
  } catch {
    return false
  }
}
