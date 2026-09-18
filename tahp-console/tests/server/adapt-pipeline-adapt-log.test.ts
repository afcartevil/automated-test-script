import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  AdaptAgentStreamBuffer,
  disposeAdaptAgentLogBuffer,
  getAdaptAgentLogBuffer,
  resetAdaptAgentLogBuffersForTest,
} from '../../packages/server/src/services/tahp/adapt-pipeline/stages/adapt-agent-log'

describe('AdaptAgentStreamBuffer', () => {
  afterEach(() => {
    resetAdaptAgentLogBuffersForTest()
    vi.useRealTimers()
  })

  it('coalesces deltas until newline', () => {
    const lines: string[] = []
    const buf = new AdaptAgentStreamBuffer(line => lines.push(line), 10_000, 400)
    buf.append('[TP]', 'thinking', 'hello ')
    buf.append('[TP]', 'thinking', 'world\n')
    expect(lines).toEqual(['[TP] 思考: hello world'])
  })

  it('flushes pending thinking before agent output', () => {
    const lines: string[] = []
    const buf = new AdaptAgentStreamBuffer(line => lines.push(line), 10_000, 400)
    buf.append('[TP]', 'thinking', 'plan A')
    buf.append('[TP]', 'output', 'doing it\n')
    expect(lines).toEqual([
      '[TP] 思考: plan A',
      '[TP] Agent: doing it',
    ])
  })

  it('splits oversized chunks without waiting for newline', () => {
    const lines: string[] = []
    const buf = new AdaptAgentStreamBuffer(line => lines.push(line), 10_000, 8)
    buf.append('[TP]', 'output', 'abcdefghijkl')
    expect(lines[0]).toBe('[TP] Agent: abcdefgh')
    buf.flush()
    expect(lines[1]).toBe('[TP] Agent: ijkl')
  })

  it('treats CRLF as a single line break', () => {
    const lines: string[] = []
    const buf = new AdaptAgentStreamBuffer(line => lines.push(line), 10_000, 400)
    buf.append('[TP]', 'output', 'hello\r\nworld\n')
    expect(lines).toEqual([
      '[TP] Agent: hello',
      '[TP] Agent: world',
    ])
  })

  it('flushes leftover text after idle timeout', async () => {
    vi.useFakeTimers()
    const lines: string[] = []
    const buf = new AdaptAgentStreamBuffer(line => lines.push(line), 400, 400)
    buf.append('[TP]', 'output', 'partial')
    expect(lines).toEqual([])
    await vi.advanceTimersByTimeAsync(400)
    expect(lines).toEqual(['[TP] Agent: partial'])
  })

  it('dispose flushes pending text and drops the buffer', async () => {
    vi.useFakeTimers()
    const lines: string[] = []
    const buf = getAdaptAgentLogBuffer('run:task', line => lines.push(line))
    buf.append('[TP]', 'output', 'pending')
    disposeAdaptAgentLogBuffer('run:task')
    expect(lines).toEqual(['[TP] Agent: pending'])
    await vi.advanceTimersByTimeAsync(1000)
    expect(lines).toEqual(['[TP] Agent: pending'])
  })
})
