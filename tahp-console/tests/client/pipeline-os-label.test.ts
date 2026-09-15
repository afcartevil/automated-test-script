import { describe, expect, it } from 'vitest'
import {
  formatOsRange,
  formatPipelineProjectTitle,
  formatTosLabel,
  parseTosMajor,
} from '@/utils/pipeline-os-label'

describe('parseTosMajor', () => {
  it('reads Android N, bare N, and tOSN as the same major', () => {
    expect(parseTosMajor('Android 16')).toBe(16)
    expect(parseTosMajor('Android16')).toBe(16)
    expect(parseTosMajor('16')).toBe(16)
    expect(parseTosMajor('16.0')).toBe(16)
    expect(parseTosMajor('tOS16')).toBe(16)
    expect(parseTosMajor('tOS 17.0')).toBe(17)
  })

  it('does not pick digits from empty or non-version text', () => {
    expect(parseTosMajor('')).toBeNull()
    expect(parseTosMajor('Android')).toBeNull()
  })
})

describe('formatTosLabel / formatOsRange', () => {
  it('always presents as tOSN', () => {
    expect(formatTosLabel('Android 16')).toBe('tOS16')
    expect(formatTosLabel('16')).toBe('tOS16')
    expect(formatTosLabel('tOS16')).toBe('tOS16')
    expect(formatOsRange('Android 16', 'Android 17')).toBe('tOS16 → tOS17')
    expect(formatOsRange('16', '17')).toBe('tOS16 → tOS17')
  })
})

describe('formatPipelineProjectTitle', () => {
  it('renders X6879Android17 as X6879-tOS17', () => {
    expect(formatPipelineProjectTitle('X6879Android17')).toBe('X6879-tOS17')
    expect(formatPipelineProjectTitle('X6879Android17', 'Android 17')).toBe('X6879-tOS17')
    expect(formatPipelineProjectTitle('X6879', 'Android 17')).toBe('X6879-tOS17')
    expect(formatPipelineProjectTitle('X6879-tOS17')).toBe('X6879-tOS17')
  })

  it('keeps a bare project code when no OS is known', () => {
    expect(formatPipelineProjectTitle('KM9')).toBe('KM9')
  })
})
