import { describe, expect, it } from 'vitest'
import { parseDeviceProbeOutput } from '../../packages/server/src/services/tahp/device-self-check'

describe('device self-check adb probe', () => {
  it('parses combined model and sim state output', () => {
    const result = parseDeviceProbeOutput('Infinix X6876\nABSENT,LOADED', '1527625558000195')
    expect(result.deviceName).toBe('Infinix X6876')
    expect(result.simCards[0]?.present).toBe(false)
    expect(result.simCards[1]?.present).toBe(true)
  })

  it('falls back to deviceId when model is missing', () => {
    const result = parseDeviceProbeOutput('', 'device-1')
    expect(result.deviceName).toBe('device-1')
    expect(result.simCards.every(card => !card.present)).toBe(true)
  })
})
