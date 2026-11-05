import { describe, expect, it } from 'vitest'
import { toCsv } from './csv'

describe('csv', () => {
  it('quotes cells with commas, quotes or newlines and blanks missing values', () => {
    expect(toCsv([['a', 'b,c', 'say "hi"'], [1, null, NaN], ['x\ny', 2.5, undefined]])).toBe('a,"b,c","say ""hi"""\n1,,\n"x\ny",2.5,')
  })
})
