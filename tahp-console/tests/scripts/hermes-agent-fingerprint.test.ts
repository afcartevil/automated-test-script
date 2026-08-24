import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { describe, expect, it } from 'vitest'
import {
  MARKER_VERSION,
  computeAgentFingerprint,
  computeLockFingerprint,
  isAgentFileInsideRoot,
  isCacheFingerprintFresh,
  originCheckPassed,
  readPyprojectVersion,
  formatHermesVersionBanner,
  shouldColorHermesBanner,
  TARGET_HERMES_VERSION,
} from '../../scripts/lib/hermes-agent-fingerprint.mjs'

describe('hermes-agent-fingerprint', () => {
  it('reads pyproject version and hashes lock files', () => {
    const root = mkdtempSync(join(tmpdir(), 'tahp-hermes-fp-'))
    try {
      writeFileSync(join(root, 'pyproject.toml'), '[project]\nversion = "0.20.4"\n')
      writeFileSync(join(root, 'uv.lock'), 'lock-a\n')
      expect(readPyprojectVersion(root)).toBe('0.20.4')
      const first = computeLockFingerprint(root)
      writeFileSync(join(root, 'uv.lock'), 'lock-b\n')
      expect(computeLockFingerprint(root)).not.toBe(first)
      expect(computeAgentFingerprint(root).hermesVersion).toBe('0.20.4')
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  })

  it('skips cache when marker, version, or lock fingerprint changes', () => {
    const fingerprint = { hermesVersion: '0.20.4', lockFingerprint: 'abc' }
    expect(isCacheFingerprintFresh({
      version: MARKER_VERSION,
      hermesVersion: '0.20.4',
      lockFingerprint: 'abc',
    }, fingerprint)).toBe(true)
    expect(isCacheFingerprintFresh({
      version: 1,
      hermesVersion: '0.20.4',
      lockFingerprint: 'abc',
    }, fingerprint)).toBe(false)
    expect(isCacheFingerprintFresh({
      version: MARKER_VERSION,
      hermesVersion: '0.15.1',
      lockFingerprint: 'abc',
    }, fingerprint)).toBe(false)
    expect(isCacheFingerprintFresh({
      version: MARKER_VERSION,
      hermesVersion: '0.20.4',
      lockFingerprint: 'old',
    }, fingerprint)).toBe(false)
  })

  it('rejects global-site packages and accepts bundled run_agent.py', () => {
    const agentDir = 'E:/easyadapter/hermes-agent-main'
    expect(isAgentFileInsideRoot('E:/easyadapter/hermes-agent-main/run_agent.py', agentDir)).toBe(true)
    expect(isAgentFileInsideRoot('C:/Python312/Lib/site-packages/run_agent.py', agentDir)).toBe(false)
    expect(originCheckPassed({
      ok: true,
      version: '0.20.4',
      file: 'E:/easyadapter/hermes-agent-main/run_agent.py',
    }, agentDir, '0.20.4')).toBe(true)
    expect(originCheckPassed({
      ok: true,
      version: '0.15.1',
      file: 'E:/easyadapter/hermes-agent-main/run_agent.py',
    }, agentDir, '0.20.4')).toBe(false)
  })

  it('treats missing lock file as a distinct fingerprint from an empty tree with version only', () => {
    const root = mkdtempSync(join(tmpdir(), 'tahp-hermes-fp-missing-'))
    try {
      mkdirSync(root, { recursive: true })
      writeFileSync(join(root, 'pyproject.toml'), 'version = "0.15.1"\n')
      const withoutLock = computeLockFingerprint(root)
      writeFileSync(join(root, 'uv.lock'), '')
      const withEmptyLock = computeLockFingerprint(root)
      expect(withoutLock).not.toBe(withEmptyLock)
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  })

  it('formats a prominent version banner and paints mismatch as a warning', () => {
    const matched = formatHermesVersionBanner({
      version: '0.20.4',
      targetVersion: TARGET_HERMES_VERSION,
      targetTag: 'v2026.8.18',
      agentDir: 'E:/easyadapter/hermes-agent-main',
    }, { color: false })
    expect(matched).toContain('Hermes Agent')
    expect(matched).toContain('0.20.4')
    expect(matched).toContain('与工程目标版本一致')
    expect(matched).toContain('hermes-agent-main')

    const mismatch = formatHermesVersionBanner({
      version: '0.15.1',
      targetVersion: '0.20.4',
    }, { color: false })
    expect(mismatch).toContain('与目标 0.20.4 不一致')

    const missing = formatHermesVersionBanner({}, { color: false })
    expect(missing).toContain('未检测到版本')

    expect(shouldColorHermesBanner({ NO_COLOR: '1' })).toBe(false)
    expect(shouldColorHermesBanner({})).toBe(true)
  })
})
