import { describe, expect, it } from 'vitest'
import { mkdtempSync, readFileSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import yaml from 'js-yaml'
import {
  buildHarnessEnvOverrides,
  mergeHarnessEnvConfig,
  syncHarnessEnvFromUnifiedConfig,
} from '../../packages/server/src/services/tahp/harness-env-sync'

describe('harness env sync from unified config', () => {
  it('maps unified form fields to harness env keys', () => {
    const overrides = buildHarnessEnvOverrides({
      domain_account: 'qing.li3',
      domain_password: 'secret',
      linux_server_ip: '10.205.0.143',
      linux_server_password: 'linux-pwd',
      windows_map_drive: 'Z:',
    })
    expect(overrides.HARNESS_QIZHI_USER).toBe('qing.li3')
    expect(overrides.HARNESS_QIZHI_BASTION_PASSWORD).toBe('secret')
    expect(overrides.HARNESS_JIRA_USERNAME).toBe('qing.li3')
    expect(overrides.HARNESS_JIRA_API_TOKEN).toBe('secret')
    expect(overrides.HARNESS_GERRIT_PASSWORD).toBe('secret')
    expect(overrides.OPEN_GROK_USERNAME).toBe('qing.li3')
    expect(overrides.HARNESS_SPUG_PASSWORD).toBe('secret')
    expect(overrides.HARNESS_QIZHI_TARGET_HOST).toBe('10.205.0.143')
    expect(overrides.HARNESS_QIZHI_TARGET_PASSWORD).toBe('linux-pwd')
    expect(overrides.HARNESS_QIZHI_SAMBA_PASSWORD).toBe('linux-pwd')
    expect(overrides.HARNESS_MAP_DRIVE_ROOT).toBe('Z:\\')
    expect(overrides.HARNESS_REMOTE_RUNNER_MAPPED_ROOT).toBe('Z:\\')
    expect(overrides.HARNESS_MAP_DRIVE_REMOTE_SHARE).toBe('\\\\10.205.0.143\\qing.li3')
  })

  it('maps qizhi TOTP secret to HARNESS_QIZHI_OTP_SECRET', () => {
    const overrides = buildHarnessEnvOverrides({
      qizhi_totp_secret: 'ABCD EFGH IJKL',
    })
    expect(overrides.HARNESS_QIZHI_OTP_SECRET).toBe('ABCDEFGHIJKL')
  })

  it('merges template defaults with form overrides', () => {
    const merged = mergeHarnessEnvConfig({
      domain_account: 'user1',
      domain_password: 'pwd1',
    })
    expect(merged.HARNESS_UPDATE_CHANNEL).toBe('stable')
    expect(merged.HARNESS_UPDATE_REGISTRY).toContain('artifact.transsion.com')
    expect(merged.HARNESS_QIZHI_USER).toBe('user1')
    expect(merged.HARNESS_JIRA_AUTH_TYPE).toBe('basic')
  })

  it('writes env.yaml under custom home dir', () => {
    const home = mkdtempSync(join(tmpdir(), 'tahp-harness-'))
    const envPath = join(home, '.tran_harness', 'env.yaml')
    const result = syncHarnessEnvFromUnifiedConfig(
      {
        domain_account: 'test.user',
        domain_password: 'pass',
        linux_server_ip: '10.0.0.1',
        windows_map_drive: 'Y:\\',
      },
      { envPath, homeDir: home },
    )
    expect(result.synced).toBe(true)
    const doc = yaml.load(readFileSync(envPath, 'utf-8')) as Record<string, string>
    expect(doc.HARNESS_QIZHI_USER).toBe('test.user')
    expect(doc.HARNESS_QIZHI_TARGET_HOST).toBe('10.0.0.1')
    expect(doc.HARNESS_MAP_DRIVE_ROOT).toBe('Y:\\')
    expect(doc.HARNESS_UPDATE_REGISTRY).toContain('artifact.transsion.com')
  })

  it('skips sync when no harness-related values', () => {
    const home = mkdtempSync(join(tmpdir(), 'tahp-harness-skip-'))
    const envPath = join(home, '.tran_harness', 'env.yaml')
    const result = syncHarnessEnvFromUnifiedConfig(
      { feishu_app_id: 'cli_x' },
      { envPath, homeDir: home },
    )
    expect(result.synced).toBe(false)
  })
})
