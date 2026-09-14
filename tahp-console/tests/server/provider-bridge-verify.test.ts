import { mkdtemp, readFile, rm, writeFile } from 'fs/promises'
import { existsSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, describe, expect, it, vi } from 'vitest'

const tempDirs: string[] = []

afterEach(async () => {
  vi.resetModules()
  vi.clearAllMocks()
  vi.doUnmock('../../packages/server/src/services/hermes/hermes-profile')
  vi.doUnmock('../../packages/server/src/services/config-helpers')
  vi.doUnmock('../../packages/server/src/services/hermes/agent-bridge')
  vi.doUnmock('../../packages/server/src/services/logger')
  while (tempDirs.length) {
    const dir = tempDirs.pop()
    if (!dir) continue
    await rm(dir, { recursive: true, force: true })
  }
})

describe('verifyProviderViaBridge missing config.yaml', () => {
  it('does not throw ENOENT when config.yaml is absent on a fresh machine', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'provider-verify-'))
    tempDirs.push(dir)
    const configPath = join(dir, 'config.yaml')
    expect(existsSync(configPath)).toBe(false)

    vi.doMock('../../packages/server/src/services/hermes/hermes-profile', () => ({
      getActiveConfigPath: () => configPath,
      getActiveProfileName: () => 'default',
    }))
    vi.doMock('../../packages/server/src/services/config-helpers', () => ({
      updateConfigYaml: async (updater: (cfg: any) => any) => {
        const next = await updater({})
        await writeFile(configPath, 'model:\n  default: x\n', 'utf-8')
        return next
      },
    }))
    vi.doMock('../../packages/server/src/services/logger', () => ({
      logger: { info: () => undefined, warn: () => undefined, error: () => undefined },
    }))
    vi.doMock('../../packages/server/src/services/hermes/agent-bridge', () => ({
      getAgentBridgeManager: () => ({ running: true }),
      AgentBridgeClient: class {
        async destroyProfile() { return undefined }
        async chat() { return { run_id: 'run-1' } }
        async *streamOutput() {
          yield { delta: 'OK', done: true, status: 'completed' }
        }
        async destroy() { return undefined }
      },
    }))

    const { verifyProviderViaBridge } = await import(
      '../../packages/server/src/services/hermes/provider-bridge-verify'
    )
    const result = await verifyProviderViaBridge({
      base_url: 'https://example.com/v1',
      api_key: 'sk-test',
      model: 'demo-model',
    })
    expect(result.ok).toBe(true)
    expect(result.reply).toContain('OK')
    // Fresh machine: temp config removed after verify
    expect(existsSync(configPath)).toBe(false)
  })

  it('restores prior config.yaml content after verify', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'provider-verify-'))
    tempDirs.push(dir)
    const configPath = join(dir, 'config.yaml')
    await writeFile(configPath, 'model:\n  default: keep-me\n', 'utf-8')

    vi.doMock('../../packages/server/src/services/hermes/hermes-profile', () => ({
      getActiveConfigPath: () => configPath,
      getActiveProfileName: () => 'default',
    }))
    vi.doMock('../../packages/server/src/services/config-helpers', () => ({
      updateConfigYaml: async (updater: (cfg: any) => any) => {
        await updater({ model: { default: 'keep-me' } })
        await writeFile(configPath, 'model:\n  default: temp\n', 'utf-8')
      },
    }))
    vi.doMock('../../packages/server/src/services/logger', () => ({
      logger: { info: () => undefined, warn: () => undefined, error: () => undefined },
    }))
    vi.doMock('../../packages/server/src/services/hermes/agent-bridge', () => ({
      getAgentBridgeManager: () => ({ running: true }),
      AgentBridgeClient: class {
        async destroyProfile() { return undefined }
        async chat() { return { run_id: 'run-2' } }
        async *streamOutput() {
          yield { delta: 'OK', done: true, status: 'completed' }
        }
        async destroy() { return undefined }
      },
    }))

    const { verifyProviderViaBridge } = await import(
      '../../packages/server/src/services/hermes/provider-bridge-verify'
    )
    await verifyProviderViaBridge({
      base_url: 'https://example.com/v1',
      api_key: 'sk-test',
      model: 'demo-model',
    })
    await expect(readFile(configPath, 'utf-8')).resolves.toContain('keep-me')
  })
})
