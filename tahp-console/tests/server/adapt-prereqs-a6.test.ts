/**
 * A6：适配前置中心拉取 — centralClient 方法签名与路由注册冒烟
 */
import { describe, it, expect } from 'vitest'
import { centralClient } from '../../packages/server/src/services/tahp/sync/central-client'
import { tahpAdaptRoutes } from '../../packages/server/src/routes/tahp/adapt'

describe('adapt-prereqs A6 hooks', () => {
  it('centralClient exposes listAdaptPrereqProjects + resolveAdaptPrereqs', () => {
    expect(typeof centralClient.listAdaptPrereqProjects).toBe('function')
    expect(typeof centralClient.resolveAdaptPrereqs).toBe('function')
  })

  it('adapt routes register prereqs endpoints', () => {
    const stack = (tahpAdaptRoutes as any).stack as Array<{ path?: string; methods?: string[] }>
    const paths = stack.map(l => `${(l.methods || []).join(',').toUpperCase()} ${l.path}`)
    expect(paths.some(p => p.includes('/api/tahp/adapt/prereqs/projects'))).toBe(true)
    expect(paths.some(p => p.includes('/api/tahp/adapt/prereqs/resolve'))).toBe(true)
  })
})
