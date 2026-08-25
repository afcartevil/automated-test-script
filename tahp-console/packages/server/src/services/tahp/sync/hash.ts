/**
 * 与中心 easyadapter_bff/src/services/hash.ts 保持一致。
 * shortHash = sha256(utf8).hex.slice(0, 16)
 */
import { createHash } from 'crypto'

export function sha256(content: string): string {
  return createHash('sha256').update(content, 'utf-8').digest('hex')
}

export function shortHash(content: string): string {
  return sha256(content).slice(0, 16)
}

/** 二进制 / 整包文件 hash（与中心 shortHashBuffer 一致） */
export function shortHashBuffer(buf: Buffer): string {
  return createHash('sha256').update(buf).digest('hex').slice(0, 16)
}

/**
 * 文本按 LF 对齐后再 hash，使本机 CRLF 与中心 LF 包能对上。
 * 含 NUL 的按二进制原样 hash，避免破坏非文本附件。
 */
export function normalizeEolBuffer(buf: Buffer): Buffer {
  if (!buf.length || buf.includes(0) || !buf.includes(0x0d)) return buf
  return Buffer.from(buf.toString('utf8').replace(/\r\n/g, '\n').replace(/\r/g, '\n'), 'utf8')
}

export function shortHashBufferNormalized(buf: Buffer): string {
  return shortHashBuffer(normalizeEolBuffer(buf))
}
