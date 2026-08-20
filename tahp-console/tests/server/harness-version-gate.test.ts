import { describe, expect, it } from 'vitest'
import { semverGte, checkHarnessCliRequirement } from '../../packages/server/src/services/tahp/harness-version-gate'
import { isOfficialHarnessSkillId } from '../../packages/server/src/services/tahp/harness-host-skills'

describe('harness host skills boundary', () => {
  it('treats official harness ids as host-only', () => {
    expect(isOfficialHarnessSkillId('transsion-harness')).toBe(true)
    expect(isOfficialHarnessSkillId('transsion-asf')).toBe(true)
    expect(isOfficialHarnessSkillId('harness-device')).toBe(true)
    expect(isOfficialHarnessSkillId('asf-device')).toBe(true)
    expect(isOfficialHarnessSkillId('harness-install')).toBe(true)
    expect(isOfficialHarnessSkillId('asf-install')).toBe(true)
  })

  it('keeps project wrapper and virtual install id out of official set', () => {
    expect(isOfficialHarnessSkillId('harness-flash-single-img')).toBe(false)
    expect(isOfficialHarnessSkillId('transsion-harness-install')).toBe(false)
    expect(isOfficialHarnessSkillId('gerrit-submit')).toBe(false)
  })
})

describe('harness version gate', () => {
  it('compares semver correctly', () => {
    expect(semverGte('1.3.1', '1.3.1')).toBe(true)
    expect(semverGte('1.3.2', '1.3.1')).toBe(true)
    expect(semverGte('1.2.9', '1.3.1')).toBe(false)
    expect(semverGte('2.0.0', '1.3.1')).toBe(true)
  })

  it('fails when current below required', () => {
    const r = checkHarnessCliRequirement({ currentOverride: '1.1.11', skipProbe: true })
    expect(r.ok).toBe(false)
    expect(r.userMessage).toContain('启动skill配置检查')
    expect(r.agentDirective).toContain('禁止继续业务')
  })

  it('passes when current meets required', () => {
    const r = checkHarnessCliRequirement({ currentOverride: '1.3.1', skipProbe: true })
    expect(r.ok).toBe(true)
  })
})
