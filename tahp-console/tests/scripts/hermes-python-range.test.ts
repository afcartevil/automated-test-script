import { describe, expect, it } from 'vitest'
import {
  HERMES_PYTHON_RANGE_LABEL,
  hermesPythonInstallHints,
  isHermesPythonVersion,
  parseSemverTriple,
} from '../../scripts/lib/tahp-paths.mjs'

describe('hermes python version range', () => {
  it('accepts 3.11–3.13 and rejects 3.10 / 3.14+', () => {
    expect(isHermesPythonVersion(parseSemverTriple('Python 3.11.0'))).toBe(true)
    expect(isHermesPythonVersion(parseSemverTriple('Python 3.12.6'))).toBe(true)
    expect(isHermesPythonVersion(parseSemverTriple('Python 3.13.5'))).toBe(true)
    expect(isHermesPythonVersion(parseSemverTriple('Python 3.10.14'))).toBe(false)
    expect(isHermesPythonVersion(parseSemverTriple('Python 3.14.0'))).toBe(false)
    expect(isHermesPythonVersion(parseSemverTriple('Python 4.0.0'))).toBe(false)
    expect(isHermesPythonVersion(null)).toBe(false)
  })

  it('documents the install range for startup scripts', () => {
    expect(HERMES_PYTHON_RANGE_LABEL).toBe('3.11–3.13')
    const hints = hermesPythonInstallHints().join('\n')
    expect(hints).toContain('>=3.11,<3.14')
    expect(hints).toContain('不要使用 3.14')
    expect(hints).toContain('TAHP_PYTHON')
  })
})
