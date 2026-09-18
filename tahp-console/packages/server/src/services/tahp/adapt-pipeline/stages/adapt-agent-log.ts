/** 将 Hermes 流式 delta（思考 / Agent 正文）拼成可读的流水线日志行。 */

export type AdaptAgentStreamKind = 'thinking' | 'output'

const KIND_TAG: Record<AdaptAgentStreamKind, string> = {
  thinking: '思考',
  output: 'Agent',
}

export class AdaptAgentStreamBuffer {
  private pending = ''
  private kind: AdaptAgentStreamKind | null = null
  private prefix = ''
  private timer: ReturnType<typeof setTimeout> | null = null
  private write: (line: string) => void

  constructor(
    write: (line: string) => void,
    private readonly flushMs = 400,
    private readonly maxChunk = 400,
  ) {
    this.write = write
  }

  setWrite(write: (line: string) => void): void {
    this.write = write
  }

  append(prefix: string, kind: AdaptAgentStreamKind, delta: string): void {
    if (!delta) return
    if (this.kind && (this.kind !== kind || this.prefix !== prefix)) this.flush()
    this.prefix = prefix
    this.kind = kind
    this.pending += delta
    this.emitCompleteLines()
    while (this.pending.length >= this.maxChunk) {
      this.emitLine(this.pending.slice(0, this.maxChunk))
      this.pending = this.pending.slice(this.maxChunk)
    }
    this.scheduleFlush()
  }

  flush(): void {
    this.clearTimer()
    this.emitCompleteLines()
    if (this.pending.trim()) this.emitLine(this.pending)
    this.pending = ''
    this.kind = null
  }

  private emitCompleteLines(): void {
    if (!this.kind) return
    const parts = this.pending.split(/\r\n|\n|\r/)
    this.pending = parts.pop() ?? ''
    for (const line of parts) {
      if (line.trim()) this.emitLine(line)
    }
  }

  private emitLine(text: string): void {
    const line = text.replace(/[ \t]+$/g, '')
    if (!line.trim() || !this.kind) return
    this.write(`${this.prefix} ${KIND_TAG[this.kind]}: ${line}`)
  }

  private scheduleFlush(): void {
    this.clearTimer()
    if (!this.pending) return
    this.timer = setTimeout(() => this.flush(), this.flushMs)
  }

  private clearTimer(): void {
    if (!this.timer) return
    clearTimeout(this.timer)
    this.timer = null
  }
}

const buffers = new Map<string, AdaptAgentStreamBuffer>()

export function getAdaptAgentLogBuffer(
  key: string,
  write: (line: string) => void,
): AdaptAgentStreamBuffer {
  let buf = buffers.get(key)
  if (!buf) {
    buf = new AdaptAgentStreamBuffer(write)
    buffers.set(key, buf)
    return buf
  }
  buf.setWrite(write)
  return buf
}

export function disposeAdaptAgentLogBuffer(key: string): void {
  const buf = buffers.get(key)
  if (!buf) return
  buf.flush()
  buffers.delete(key)
}

export function resetAdaptAgentLogBuffersForTest(): void {
  for (const buf of buffers.values()) buf.flush()
  buffers.clear()
}
