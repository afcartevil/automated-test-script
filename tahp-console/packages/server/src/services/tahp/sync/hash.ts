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
