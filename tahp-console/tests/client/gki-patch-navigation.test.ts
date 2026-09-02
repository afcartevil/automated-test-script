import { describe, expect, it } from 'vitest'
import {
  buildGkiFrameSrc,
  isGkiPatchReadyMessage,
  resolveGkiFrameSync,
} from '@/utils/gki-patch-navigation'

const status = { appUrl: 'http://127.0.0.1:8651/app/' }

describe('buildGkiFrameSrc', () => {
  it('puts embedded=1 on the GKI app path', () => {
    expect(buildGkiFrameSrc(status, '/settings')).toBe(
      'http://127.0.0.1:8651/app/settings?embedded=1',
    )
  })

  it('keeps extra query on the iframe url', () => {
    expect(buildGkiFrameSrc(status, '/upgrade', { job: '12' })).toBe(
      'http://127.0.0.1:8651/app/upgrade?embedded=1&job=12',
    )
  })
})

describe('resolveGkiFrameSync', () => {
  it('does not mount an iframe on the native workbench', () => {
    expect(resolveGkiFrameSync({
      nativeWorkbench: true,
      desiredSrc: 'http://127.0.0.1:8651/app/settings?embedded=1',
      mountedSrc: '',
      frameAppReady: false,
    })).toBe('none')
  })

  it('mounts by src when leaving the workbench', () => {
    expect(resolveGkiFrameSync({
      nativeWorkbench: false,
      desiredSrc: 'http://127.0.0.1:8651/app/settings?embedded=1',
      mountedSrc: '',
      frameAppReady: false,
    })).toBe('mount')
  })

  it('posts in-app when the GKI spa is already ready', () => {
    expect(resolveGkiFrameSync({
      nativeWorkbench: false,
      desiredSrc: 'http://127.0.0.1:8651/app/patches?embedded=1',
      mountedSrc: 'http://127.0.0.1:8651/app/settings?embedded=1',
      frameAppReady: true,
    })).toBe('post')
  })

  it('reloads src when the spa never signals ready', () => {
    expect(resolveGkiFrameSync({
      nativeWorkbench: false,
      desiredSrc: 'http://127.0.0.1:8651/app/patches?embedded=1',
      mountedSrc: 'http://127.0.0.1:8651/app/settings?embedded=1',
      frameAppReady: false,
    })).toBe('reload')
  })
})

describe('isGkiPatchReadyMessage', () => {
  it('accepts the iframe handshake', () => {
    expect(isGkiPatchReadyMessage({ type: 'ea-gki-patch-ready' })).toBe(true)
    expect(isGkiPatchReadyMessage({ type: 'ea-gki-patch-nav', path: '/settings' })).toBe(false)
  })
})
