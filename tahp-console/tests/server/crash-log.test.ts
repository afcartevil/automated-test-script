import { describe, expect, it } from 'vitest'
import { serializeUnknown } from '../../packages/server/src/services/crash-log'

describe('server crash-log serializeUnknown', () => {
  it('serializes Error and non-Error values', () => {
    const err = new Error('native-ish')
    expect(serializeUnknown(err)).toMatchObject({ name: 'Error', message: 'native-ish' })
    expect(serializeUnknown(null).message).toBe('null')
    expect(serializeUnknown('hang').message).toBe('hang')
  })
})
