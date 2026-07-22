import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('Dow strategy routing', () => {
  it('excludes the external Dow strategy from the legacy batch engine', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/pages/Screener.tsx'), 'utf8')

    expect(source).toContain('localEnginePool = useMemo')
    expect(source).toContain('id !== DOW_TREND_STRATEGY_ID')
    expect(source).toContain('strategyIds ?? localEnginePool')
  })
})
