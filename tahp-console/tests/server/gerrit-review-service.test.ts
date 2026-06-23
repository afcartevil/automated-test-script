import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { existsSync, mkdtempSync, rmSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import {
  buildGerritReviewInstructions,
  GERRIT_NOT_CONFIGURED_ERROR,
  sendGerritReviewChat,
} from '../../packages/server/src/services/tahp/gerrit-review'
import { saveGerritConfig } from '../../packages/server/src/services/tahp/gerrit-credentials'

describe('sendGerritReviewChat', () => {
  let tempDir = ''

  beforeEach(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'tahp-gerrit-review-'))
    process.env.TAHP_GERRIT_CONFIG_DIR = tempDir
  })

  afterEach(() => {
    delete process.env.TAHP_GERRIT_CONFIG_DIR
    if (tempDir && existsSync(tempDir)) {
      rmSync(tempDir, { recursive: true, force: true })
    }
  })

  it('rejects empty message', () => {
    const result = sendGerritReviewChat({ message: '' })
    expect(result).toEqual({ ok: false, error: '消息不能为空' })
  })

  it('rejects whitespace-only message', () => {
    const result = sendGerritReviewChat({ message: '   \n  ' })
    expect(result).toEqual({ ok: false, error: '消息不能为空' })
  })

  it('rejects when gerrit credentials are not configured', () => {
    const result = sendGerritReviewChat({ message: 'https://gerrit.transsion.com/c/foo/+/1' })
    expect(result).toEqual({ ok: false, error: GERRIT_NOT_CONFIGURED_ERROR })
  })

  it('starts chat when gerrit credentials are configured', async () => {
    await saveGerritConfig({
      user: 'test.user',
      password: 'http-pass',
    })

    const result = sendGerritReviewChat({
      message: 'https://gerrit.transsion.com/c/MTK_CODE/quark/kernel-5.15/+/1543793',
    })

    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.sessionId).toMatch(/^sess-gerrit-/)
      expect(result.taskId).toMatch(/^task-gerrit-/)
    }
  })
})

describe('buildGerritReviewInstructions', () => {
  it('includes --cred-file path when credentials are provided', () => {
    const credPath = 'C:\\tahp\\.tahp-config\\gerrit-cred.runtime.json'
    const instructions = buildGerritReviewInstructions('review this change', {
      credFilePath: credPath,
      host: 'https://gerrit.transsion.com',
    })

    expect(instructions).toContain(`--cred-file ${credPath}`)
    expect(instructions).toContain('Gerrit Host: https://gerrit.transsion.com')
  })
})
