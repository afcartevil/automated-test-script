import { existsSync } from 'fs'
import { execFile } from 'child_process'
import { resolve } from 'path'
import { promisify } from 'util'
import { describe, expect, it } from 'vitest'

const execFileAsync = promisify(execFile)

describe('hermes compat probe', () => {
  const python = resolve('../hermes-agent-main/.venv/Scripts/python.exe')
  const probe = resolve('scripts/hermes-compat-probe.py')
  const agentRoot = resolve('../hermes-agent-main')

  it.skipIf(!existsSync(python))('source-mode probe passes against bundled hermes-agent-main', async () => {
    const { stdout } = await execFileAsync(python, [probe, '--agent-root', agentRoot, '--mode', 'source'], {
      maxBuffer: 2 * 1024 * 1024,
    })
    const result = JSON.parse(stdout)
    expect(result.ok).toBe(true)
    expect(result.missing).toEqual([])
  }, 20000)
})
