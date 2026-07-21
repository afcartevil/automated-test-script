/**
 * Windows DPAPI (LocalMachine) secret store for TAHP Console.
 * Secrets live at %USERPROFILE%\.tahp-console\secrets.json as DPAPI blobs.
 * Non-Windows: stores base64-obfuscated values (dev/CI only; not DPAPI).
 */

import { execFileSync } from 'child_process'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import { join } from 'path'
import { homedir } from 'os'
import { logger } from '../logger'

export type SecretName = 'dify_api_key'

interface SecretsFile {
  version: 1
  entries: Record<string, { scheme: 'dpapi' | 'b64'; blob: string; updated_at: string }>
}

function secretsHome(): string {
  return process.env.TAHP_CONSOLE_HOME?.trim() || join(homedir(), '.tahp-console')
}

export function getSecretsFilePath(): string {
  return join(secretsHome(), 'secrets.json')
}

function isWindows(): boolean {
  return process.platform === 'win32'
}

function readStore(): SecretsFile {
  const path = getSecretsFilePath()
  if (!existsSync(path)) return { version: 1, entries: {} }
  try {
    const parsed = JSON.parse(readFileSync(path, 'utf-8')) as SecretsFile
    if (!parsed || typeof parsed !== 'object') return { version: 1, entries: {} }
    return {
      version: 1,
      entries: parsed.entries && typeof parsed.entries === 'object' ? parsed.entries : {},
    }
  } catch {
    return { version: 1, entries: {} }
  }
}

function writeStore(store: SecretsFile): void {
  const dir = secretsHome()
  mkdirSync(dir, { recursive: true })
  writeFileSync(getSecretsFilePath(), JSON.stringify(store, null, 2), {
    encoding: 'utf-8',
    mode: 0o600,
  })
}

/** Protect UTF-8 plaintext with Windows DPAPI LocalMachine scope. */
export function dpapiProtect(plain: string): string {
  if (!isWindows()) {
    throw new Error('DPAPI is only available on Windows')
  }
  const plainB64 = Buffer.from(plain, 'utf8').toString('base64')
  // Pass base64 via env to avoid PowerShell quoting issues with special chars
  const script = [
    'Add-Type -AssemblyName System.Security',
    '$plain = [Convert]::FromBase64String($env:TAHP_DPAPI_PLAIN_B64)',
    '$prot = [System.Security.Cryptography.ProtectedData]::Protect($plain, $null, [System.Security.Cryptography.DataProtectionScope]::LocalMachine)',
    '[Convert]::ToBase64String($prot)',
  ].join('; ')

  const out = execFileSync(
    'powershell.exe',
    ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
    {
      encoding: 'utf8',
      windowsHide: true,
      timeout: 15000,
      env: { ...process.env, TAHP_DPAPI_PLAIN_B64: plainB64 },
    },
  )
  const blob = out.trim().replace(/\r/g, '')
  if (!blob) throw new Error('DPAPI Protect returned empty blob')
  return blob
}

/** Unprotect a DPAPI LocalMachine blob to UTF-8 plaintext. */
export function dpapiUnprotect(blob: string): string {
  if (!isWindows()) {
    throw new Error('DPAPI is only available on Windows')
  }
  const script = [
    'Add-Type -AssemblyName System.Security',
    '$prot = [Convert]::FromBase64String($env:TAHP_DPAPI_BLOB_B64)',
    '$plain = [System.Security.Cryptography.ProtectedData]::Unprotect($prot, $null, [System.Security.Cryptography.DataProtectionScope]::LocalMachine)',
    '[Convert]::ToBase64String($plain)',
  ].join('; ')

  const out = execFileSync(
    'powershell.exe',
    ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
    {
      encoding: 'utf8',
      windowsHide: true,
      timeout: 15000,
      env: { ...process.env, TAHP_DPAPI_BLOB_B64: blob },
    },
  )
  const plainB64 = out.trim().replace(/\r/g, '')
  if (!plainB64) throw new Error('DPAPI Unprotect returned empty payload')
  return Buffer.from(plainB64, 'base64').toString('utf8')
}

function encodeSecret(plain: string): { scheme: 'dpapi' | 'b64'; blob: string } {
  if (isWindows()) {
    return { scheme: 'dpapi', blob: dpapiProtect(plain) }
  }
  // Dev/CI fallback — not a security boundary; Windows production uses DPAPI.
  return { scheme: 'b64', blob: Buffer.from(plain, 'utf8').toString('base64') }
}

function decodeSecret(entry: { scheme: 'dpapi' | 'b64'; blob: string }): string {
  if (entry.scheme === 'dpapi') {
    return dpapiUnprotect(entry.blob)
  }
  return Buffer.from(entry.blob, 'base64').toString('utf8')
}

/** Read a secret; returns null if missing or decrypt fails. */
export function getSecret(name: SecretName): string | null {
  const store = readStore()
  const entry = store.entries[name]
  if (!entry?.blob) return null
  try {
    const value = decodeSecret(entry).trim()
    return value || null
  } catch (err) {
    logger.warn('[secret-store] failed to decrypt %s: %s', name, err)
    return null
  }
}

/** Encrypt and persist a secret. */
export function setSecret(name: SecretName, plain: string): void {
  const value = plain.trim()
  if (!value) throw new Error(`Cannot store empty secret: ${name}`)
  const encoded = encodeSecret(value)
  const store = readStore()
  store.entries[name] = {
    scheme: encoded.scheme,
    blob: encoded.blob,
    updated_at: new Date().toISOString(),
  }
  writeStore(store)
}

export function hasSecret(name: SecretName): boolean {
  return Boolean(readStore().entries[name]?.blob)
}
