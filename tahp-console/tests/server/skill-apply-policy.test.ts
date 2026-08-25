import { describe, expect, it } from 'vitest'
import { decideSkillApply } from '../../packages/server/src/services/tahp/sync/apply-policy'
import { shortHashBuffer, shortHashBufferNormalized } from '../../packages/server/src/services/tahp/sync/hash'

describe('decideSkillApply', () => {
  it('applies when local skill is missing', () => {
    expect(decideSkillApply({
      localHash: null,
      centralHash: 'aaa',
      lastAppliedHash: null,
      force: false,
    })).toBe('apply')
  })

  it('skips write when local already matches central', () => {
    expect(decideSkillApply({
      localHash: 'aaa',
      centralHash: 'aaa',
      lastAppliedHash: null,
      force: false,
    })).toBe('skip_synced')
  })

  it('skips write when only line endings differ (norm hash matches central)', () => {
    expect(decideSkillApply({
      localHash: 'crlf-raw',
      localNormHash: 'lf-central',
      centralHash: 'lf-central',
      lastAppliedHash: null,
      force: false,
    })).toBe('skip_synced')
  })

  it('skips overwrite when local differs and was never recorded as applied', () => {
    expect(decideSkillApply({
      localHash: 'local',
      centralHash: 'central',
      lastAppliedHash: null,
      force: false,
    })).toBe('skip_dirty')
  })

  it('applies when local still equals last applied and central moved', () => {
    expect(decideSkillApply({
      localHash: 'old',
      centralHash: 'new',
      lastAppliedHash: 'old',
      force: false,
    })).toBe('apply')
  })

  it('skips when local changed after last apply even if central also moved', () => {
    expect(decideSkillApply({
      localHash: 'mine',
      centralHash: 'new',
      lastAppliedHash: 'old',
      force: false,
    })).toBe('skip_dirty')
  })

  it('force overwrites dirty local', () => {
    expect(decideSkillApply({
      localHash: 'mine',
      centralHash: 'new',
      lastAppliedHash: 'old',
      force: true,
    })).toBe('apply')
  })
})

describe('line-ending hash', () => {
  it('hashes CRLF text the same as LF', () => {
    const lf = Buffer.from('hello\nworld\n', 'utf8')
    const crlf = Buffer.from('hello\r\nworld\r\n', 'utf8')
    expect(shortHashBuffer(lf)).not.toBe(shortHashBuffer(crlf))
    expect(shortHashBufferNormalized(lf)).toBe(shortHashBufferNormalized(crlf))
  })

  it('does not rewrite buffers that contain NUL', () => {
    const bin = Buffer.from([0x68, 0x00, 0x0d, 0x0a])
    expect(shortHashBufferNormalized(bin)).toBe(shortHashBuffer(bin))
  })
})
