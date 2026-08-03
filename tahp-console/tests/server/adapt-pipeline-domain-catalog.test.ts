import { describe, expect, it, vi } from 'vitest'

const getLayoutMock = vi.fn()

vi.mock('../../packages/server/src/services/tahp/adapt-layout/service', () => ({
  getAdaptDomainLayout: (...args: unknown[]) => getLayoutMock(...args),
}))

describe('adapt-pipeline domain-catalog', () => {
  it('returns three workspaces with builtin domains and layout overlay', async () => {
    getLayoutMock.mockImplementation(async (domainId: string, workspaceId?: string) => {
      if (domainId === 'tp' && workspaceId === 'adapt-debug') {
        return {
          domain_id: 'tp',
          fields: [{ name: 'debug_project', label: '调试项目名', type: 'text', required: true }],
          related_skills: ['tp-adapt-bringup'],
          revision: 1,
          updated_at: new Date().toISOString(),
          source: 'user',
          schema_version: 1,
        }
      }
      return null
    })

    const {
      getDomainCatalog,
      mapDomainToModule,
    } = await import('../../packages/server/src/services/tahp/adapt-pipeline/domain-catalog')

    const catalog = await getDomainCatalog()
    expect(catalog.workspaces.map(w => w.id)).toEqual([
      'adapt-debug',
      'feature-adapt',
      'carrier-config',
    ])

    const adaptDebug = catalog.workspaces.find(w => w.id === 'adapt-debug')!
    expect(adaptDebug.domains.some(d => d.domain_id === 'tp')).toBe(true)
    expect(adaptDebug.domains.some(d => d.domain_id === 'fp')).toBe(true)

    const tp = adaptDebug.domains.find(d => d.domain_id === 'tp')!
    expect(tp.schema).toEqual([
      { key: 'debug_project', label: '调试项目名', required: true, type: 'text' },
    ])
    expect(tp.related_skills).toEqual(['tp-adapt-bringup'])

    const feature = catalog.workspaces.find(w => w.id === 'feature-adapt')!
    expect(feature.domains.map(d => d.domain_id)).toContain('scheduling')
    const featureComm = feature.domains.find(d => d.domain_id === 'comm-framework')!
    expect(featureComm.domain_label).toBe('通信框架')
    expect(featureComm.module).toBe('telephony')
    expect(featureComm.related_skills).toContain('comm-framework-agent-test-for-secondWork')

    const carrier = catalog.workspaces.find(w => w.id === 'carrier-config')!
    const ecc = carrier.domains.find(d => d.domain_id === 'ecc-config')!
    expect(ecc.module).toBe('telephony')
    expect(mapDomainToModule('ecc-config')).toBe('telephony')
    expect(mapDomainToModule('tp')).toBe('kernel-driver')
  })
})
