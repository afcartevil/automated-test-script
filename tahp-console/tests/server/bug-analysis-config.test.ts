import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync, existsSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import {
  defaultBugAnalysisChannelConfig,
  readBugAnalysisChannelConfig,
  writeBugAnalysisChannelConfig,
  bugAnalysisConfigPath,
  buildRemoteChannelDirective,
  resolveRemoteSkillPath,
  listEnabledRemotePreferredSkillIds,
} from '../../packages/server/src/services/tahp/bug-analysis-config'

function makeValidTahpRoot(): string {
  const root = mkdtempSync(join(tmpdir(), 'tahp-bug-cfg-'))
  mkdirSync(join(root, 'tahp-console', 'packages', 'server'), { recursive: true })
  mkdirSync(join(root, 'skills', '.claude', 'skills'), { recursive: true })
  return root
}

describe('bug-analysis-config', () => {
  let root: string
  let prevRoot: string | undefined

  beforeEach(() => {
    root = makeValidTahpRoot()
    prevRoot = process.env.TAHP_PROJECT_ROOT
    process.env.TAHP_PROJECT_ROOT = root
    delete process.env.TAHP_BUGFIX_CHANNEL
    delete process.env.TAHP_LOGINSIGHT_CHANNEL
  })

  afterEach(() => {
    if (prevRoot === undefined) delete process.env.TAHP_PROJECT_ROOT
    else process.env.TAHP_PROJECT_ROOT = prevRoot
    delete process.env.TAHP_BUGFIX_CHANNEL
    delete process.env.TAHP_LOGINSIGHT_CHANNEL
    rmSync(root, { recursive: true, force: true })
  })

  it('defaults both remote channels to disabled', () => {
    const cfg = defaultBugAnalysisChannelConfig()
    expect(cfg.remote_channels.bugfix_analysis.enabled).toBe(false)
    expect(cfg.remote_channels.loginsight_remote.enabled).toBe(false)
  })

  it('read returns defaults when file missing', () => {
    const cfg = readBugAnalysisChannelConfig()
    expect(cfg.remote_channels.bugfix_analysis.enabled).toBe(false)
    expect(cfg.remote_channels.loginsight_remote.enabled).toBe(false)
  })

  it('write persists and read reflects toggles', () => {
    const written = writeBugAnalysisChannelConfig({
      bugfix_analysis: false,
      loginsight_remote: true,
    })
    expect(written.remote_channels.bugfix_analysis.enabled).toBe(false)
    expect(written.remote_channels.loginsight_remote.enabled).toBe(true)
    expect(existsSync(bugAnalysisConfigPath())).toBe(true)

    const read = readBugAnalysisChannelConfig()
    expect(read.remote_channels.bugfix_analysis.enabled).toBe(false)
    expect(read.remote_channels.loginsight_remote.enabled).toBe(true)
  })

  it('env override can force-disable a channel', () => {
    writeBugAnalysisChannelConfig({ bugfix_analysis: true, loginsight_remote: true })
    process.env.TAHP_BUGFIX_CHANNEL = '0'
    const cfg = readBugAnalysisChannelConfig()
    expect(cfg.remote_channels.bugfix_analysis.enabled).toBe(false)
    expect(cfg.remote_channels.loginsight_remote.enabled).toBe(true)
  })

  it('buildRemoteChannelDirective requires waiting for remote report; queue is not failure', () => {
    const cfg = defaultBugAnalysisChannelConfig()
    cfg.remote_channels.bugfix_analysis.enabled = false
    cfg.remote_channels.loginsight_remote.enabled = true
    const text = buildRemoteChannelDirective(cfg)
    expect(text).toContain('必须持续 `wait` 直到任务结束并下载到报告')
    expect(text).toContain('一律不是失败')
    expect(text).toContain('把排队、预计等待久')
    expect(text).not.toMatch(/失败判定[\s\S]*超时、无分析正文/)
  })

  it('buildRemoteChannelDirective mentions disabled when both off', () => {
    const cfg = defaultBugAnalysisChannelConfig()
    cfg.remote_channels.bugfix_analysis.enabled = false
    cfg.remote_channels.loginsight_remote.enabled = false
    const text = buildRemoteChannelDirective(cfg)
    expect(text).toContain('两渠道均 disabled')
    expect(text).toContain('bugfix_analysis')
    expect(text).toContain('loginsight_remote')
  })

  it('resolveRemoteSkillPath finds skill under configured skill_path', () => {
    const skillRoot = join(root, 'ext-skills', 'bugfix-analysis')
    mkdirSync(skillRoot, { recursive: true })
    writeFileSync(join(skillRoot, 'SKILL.md'), '# test\n', 'utf-8')
    const res = resolveRemoteSkillPath({
      enabled: true,
      skill_id: 'bugfix-analysis',
      skill_path: skillRoot,
    })
    expect(res.found).toBe(true)
    expect(res.skillMdPath).toContain('SKILL.md')
  })

  it('listEnabledRemotePreferredSkillIds follows enabled flags', () => {
    const cfg = defaultBugAnalysisChannelConfig()
    cfg.remote_channels.loginsight_remote.enabled = true
    cfg.remote_channels.bugfix_analysis.enabled = false
    expect(listEnabledRemotePreferredSkillIds(cfg)).toEqual(['loginsight-remote-cli'])
  })
})
